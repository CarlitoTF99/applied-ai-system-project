"""GeminiClient retry / fallback behavior with a fake transport (no network)."""

import logging

import pytest
from google.genai import errors

from src.llm import AUTH, BAD_MODEL, CLIENT, RETRYABLE, GeminiClient, classify_error
from src.logging_setup import configure, get_run_logger


def api_error(code: int, status: str, message: str):
    body = {"error": {"code": code, "status": status, "message": message}}
    return (errors.ServerError if code >= 500 else errors.ClientError)(code, body)


class Response:
    def __init__(self, text):
        self.text = text


class FakeModels:
    """Plays back a script of outcomes (exceptions or response text), one per call, recording each model asked."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return Response(outcome)


class FakeTypes:
    GenerateContentConfig = staticmethod(lambda **kw: kw)
    ThinkingConfig = staticmethod(lambda **kw: kw)


def make_client(script, fallback_model=""):
    """A GeminiClient wired to FakeModels; sleeps are recorded instead of taken."""
    configure(verbose=False)
    sleeps = []
    client = GeminiClient("", "gemini-2.5-flash", get_run_logger("test"),
                          fallback_model=fallback_model, sleep=sleeps.append)
    fake = FakeModels(script)
    client._client = type("FakeGenai", (), {"models": fake})()
    client._types = FakeTypes
    client.available = True
    return client, fake, sleeps


def test_503_is_retried_with_backoff_then_succeeds():
    client, fake, sleeps = make_client([
        api_error(503, "UNAVAILABLE", "The model is overloaded due to high demand."),
        api_error(504, "DEADLINE_EXCEEDED", "Deadline expired before operation could complete."),
        '{"favorite_genre": "lofi"}',
    ])
    assert client.generate_json("prompt") == {"favorite_genre": "lofi"}
    assert fake.calls == ["gemini-2.5-flash"] * 3
    assert sleeps == [2.0, 5.0]


def test_404_is_not_retried():
    client, fake, sleeps = make_client([api_error(404, "NOT_FOUND", "models/gemini-nope is not found.")])
    assert client.generate_json("prompt") is None
    assert fake.calls == ["gemini-2.5-flash"]           # exactly one attempt
    assert sleeps == []
    assert not client.available                          # no usable model left for this run


def test_retries_stop_after_two_then_fallback_model_gets_one_try():
    overloaded = lambda: api_error(503, "UNAVAILABLE", "high demand")
    client, fake, sleeps = make_client(
        [overloaded(), overloaded(), overloaded(), "fallback answer"],
        fallback_model="gemini-2.5-flash-lite",
    )
    assert client.generate_text("prompt") == "fallback answer"
    assert fake.calls == ["gemini-2.5-flash"] * 3 + ["gemini-2.5-flash-lite"]
    assert sleeps == [2.0, 5.0]


def test_fallback_failure_returns_none_for_offline_path():
    overloaded = lambda: api_error(503, "UNAVAILABLE", "high demand")
    client, fake, _ = make_client([overloaded()] * 4, fallback_model="gemini-2.5-flash-lite")
    assert client.generate_json("prompt") is None
    assert fake.calls == ["gemini-2.5-flash"] * 3 + ["gemini-2.5-flash-lite"]   # fallback tried once, not retried


def test_404_on_main_model_goes_straight_to_fallback_and_is_remembered():
    client, fake, sleeps = make_client(
        [api_error(404, "NOT_FOUND", "no such model"), "first", "second"],
        fallback_model="gemini-2.5-flash-lite",
    )
    assert client.generate_text("p") == "first"
    assert client.generate_text("p") == "second"       # dead main model is skipped on the next call
    assert fake.calls == ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite"]
    assert sleeps == []


def test_bad_key_is_not_retried_and_skips_fallback():
    client, fake, sleeps = make_client(
        [api_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")],
        fallback_model="gemini-2.5-flash-lite",
    )
    assert client.generate_json("prompt") is None
    assert fake.calls == ["gemini-2.5-flash"]
    assert sleeps == []
    assert not client.available and "API key" in client.disabled_reason


def test_timeout_is_retried():
    client, fake, sleeps = make_client([TimeoutError("read timed out"), "ok"])
    assert client.generate_text("prompt") == "ok"
    assert sleeps == [2.0]


@pytest.mark.parametrize("exc, kind", [
    (api_error(503, "UNAVAILABLE", "x"), RETRYABLE),
    (api_error(500, "INTERNAL", "x"), RETRYABLE),
    (api_error(504, "DEADLINE_EXCEEDED", "x"), RETRYABLE),
    (TimeoutError(), RETRYABLE),
    (type("ReadTimeout", (Exception,), {})("slow"), RETRYABLE),
    (api_error(404, "NOT_FOUND", "x"), BAD_MODEL),
    (api_error(403, "PERMISSION_DENIED", "x"), AUTH),
    (api_error(429, "RESOURCE_EXHAUSTED", "quota"), CLIENT),
    (api_error(400, "INVALID_ARGUMENT", "x"), CLIENT),
    (ValueError("weird"), CLIENT),
])
def test_classify_error(exc, kind):
    assert classify_error(exc) == kind


def test_every_attempt_is_logged(tmp_path, caplog):
    client, _, _ = make_client([api_error(503, "UNAVAILABLE", "high demand"), "ok"])
    logger = logging.getLogger("vibematch")
    logger.addHandler(caplog.handler)
    try:
        client.generate_text("prompt")
    finally:
        logger.removeHandler(caplog.handler)
    messages = [r.getMessage() for r in caplog.records]
    assert any("gemini-2.5-flash attempt 1/3 failed after" in m and "503" in m and "retrying in 2s" in m
               for m in messages)
    assert any("gemini-2.5-flash attempt 2/3 succeeded in" in m for m in messages)


@pytest.mark.parametrize("raw, expected", [("", 30.0), ("15", 15.0), ("abc", 30.0), ("-5", 30.0), ("2.5", 2.5)])
def test_gemini_timeout_from_env(monkeypatch, raw, expected):
    from src import config
    monkeypatch.setenv("GEMINI_TIMEOUT", raw)
    assert config.gemini_timeout() == expected


@pytest.mark.parametrize("raw, expected", [
    ("", "gemini-3.8-flash"), ("none", ""), ("NONE", ""), ("gemini-x", "gemini-x"),
])
def test_fallback_model_from_env(monkeypatch, raw, expected):
    from src import config
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", raw)
    assert config.gemini_fallback_model() == expected


def test_default_models(monkeypatch):
    from src import config
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    assert config.gemini_model() == "gemini-3.5-flash-lite"
    assert config.gemini_fallback_model() == "gemini-3.8-flash"


def test_fallback_equal_to_main_model_is_ignored():
    client = GeminiClient("", "gemini-3.8-flash", get_run_logger("t"), fallback_model="gemini-3.8-flash")
    assert client.fallback_model == ""


def test_client_without_key_is_unavailable():
    client = GeminiClient("", "gemini-2.5-flash", get_run_logger("t"))
    assert not client.available and "GEMINI_API_KEY" in client.disabled_reason
    assert client.generate_json("x") is None and client.generate_text("x") is None
