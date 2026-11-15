"""A thin Gemini wrapper (google-genai) that never raises: every failure returns None and logs a warning.

Resilience, per call:
  1. The main model gets 1 attempt + up to len(retry_delays) retries, but ONLY for timeouts and 5xx errors.
     4xx errors (bad key, unknown model, bad request, quota) are never retried.
  2. If the main model still fails, the optional fallback model gets exactly one attempt.
     A bad API key skips this step, since every model would reject it.
  3. If everything fails the caller gets None and uses the offline path.
"""

import json
import re
import time
from typing import Callable, List, Optional, Sequence, Tuple

from src.config import DEFAULT_GEMINI_TIMEOUT, LLM_RETRY_DELAYS, LLM_TEMPERATURE

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
MAX_ERROR_CHARS = 200

# Outcomes of a single failed attempt
RETRYABLE = "retryable"      # timeout or 5xx: worth another try
AUTH = "auth"                # bad / unauthorized key: no model will work
BAD_MODEL = "bad_model"      # 404: this model name is unusable for the rest of the run
CLIENT = "client"            # any other 4xx or unexpected error: don't retry this model


class GeminiClient:
    """Calls Gemini for JSON or text. Check .available first; .disabled_reason says why it isn't."""

    def __init__(
        self,
        api_key: str,
        model: str,
        log,
        timeout: float = DEFAULT_GEMINI_TIMEOUT,
        temperature: float = LLM_TEMPERATURE,
        fallback_model: str = "",
        retry_delays: Sequence[float] = LLM_RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.fallback_model = fallback_model if fallback_model and fallback_model != model else ""
        self.log = log
        self.timeout = timeout
        self.temperature = temperature
        self.retry_delays = tuple(retry_delays)
        self._sleep = sleep
        self._dead_models = set()
        self.available = False
        self.disabled_reason = ""
        self._client = None
        self._types = None

        if not api_key:
            self.disabled_reason = "GEMINI_API_KEY is not set"
            return
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            self.disabled_reason = "google-genai is not installed"
            return
        try:
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(timeout * 1000),
                    # attempts=1: this class owns retries, so the SDK must not add its own
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as exc:  # bad key format, proxy config, etc.
            self.disabled_reason = f"could not create Gemini client ({type(exc).__name__})"
            return
        self._types = types
        self.available = True

    def _config(self, model: str, json_mode: bool):
        kwargs = {"temperature": self.temperature}
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        # 2.5 Flash models "think" by default, which is slow for a short structured task
        if model.startswith("gemini-2.5-flash"):
            kwargs["thinking_config"] = self._types.ThinkingConfig(thinking_budget=0)
        return self._types.GenerateContentConfig(**kwargs)

    def _plan(self) -> List[Tuple[str, int]]:
        """Return [(model, max_attempts)]: main model with retries, then the fallback model once."""
        plan = []
        if self.model not in self._dead_models:
            plan.append((self.model, 1 + len(self.retry_delays)))
        if self.fallback_model and self.fallback_model not in self._dead_models:
            plan.append((self.fallback_model, 1))
        return plan

    def _try_model(self, model: str, max_attempts: int, prompt: str, json_mode: bool, step: str) -> Tuple[Optional[str], str]:
        """Call one model, retrying timeouts/5xx; return (text, "ok") or (None, failure kind)."""
        for attempt in range(1, max_attempts + 1):
            label = f"Gemini {model} attempt {attempt}/{max_attempts}"
            start = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=model, contents=prompt, config=self._config(model, json_mode)
                )
                text = response.text
            except Exception as exc:
                elapsed = time.monotonic() - start
                kind = classify_error(exc)
                error = describe_error(exc)
                if kind == RETRYABLE and attempt < max_attempts:
                    delay = self.retry_delays[attempt - 1]
                    self.log.warning(f"{label} failed after {elapsed:.2f}s: {error}; retrying in {delay:g}s", step=step)
                    self._sleep(delay)
                    continue
                why = {
                    RETRYABLE: "no retries left",
                    AUTH: "not retryable (auth error)",
                    BAD_MODEL: "not retryable (model not found)",
                    CLIENT: "not retryable (client error)",
                }[kind]
                self.log.warning(f"{label} failed after {elapsed:.2f}s: {error}; {why}", step=step)
                if kind == BAD_MODEL:
                    self._dead_models.add(model)
                return None, kind
            elapsed = time.monotonic() - start
            if not text or not text.strip():
                self.log.warning(f"{label} returned an empty response after {elapsed:.2f}s", step=step)
                return None, CLIENT
            self.log.info(f"{label} succeeded in {elapsed:.2f}s", step=step)
            self.log.debug(f"raw Gemini output: {text}", step=step)
            return text, "ok"
        return None, RETRYABLE  # only reached if max_attempts < 1

    def _generate(self, prompt: str, json_mode: bool, step: str) -> Optional[str]:
        if not self.available:
            return None
        plan = self._plan()
        for index, (model, max_attempts) in enumerate(plan):
            if index > 0:
                self.log.warning(f"trying fallback model {model}", step=step)
            text, outcome = self._try_model(model, max_attempts, prompt, json_mode, step)
            if outcome == "ok":
                return text
            if outcome == AUTH:
                self.available = False
                self.disabled_reason = "Gemini disabled for this run: API key rejected"
                self.log.warning(self.disabled_reason, step=step)
                return None
        if not self._plan():
            self.available = False
            self.disabled_reason = "Gemini disabled for this run: no usable model"
        self.log.warning("all Gemini attempts failed; using offline fallback", step=step)
        return None

    def generate_json(self, prompt: str, step: str = "llm") -> Optional[dict]:
        """Return the response parsed as a JSON object, or None if the call or the parse fails."""
        text = self._generate(prompt, json_mode=True, step=step)
        if text is None:
            return None
        try:
            data = json.loads(_FENCE.sub("", text.strip()))
        except json.JSONDecodeError as exc:
            self.log.warning(f"Gemini returned invalid JSON ({exc.msg}); using offline fallback", step=step)
            return None
        if not isinstance(data, dict):
            self.log.warning(f"Gemini JSON was a {type(data).__name__}, not an object; using offline fallback", step=step)
            return None
        return data

    def generate_text(self, prompt: str, step: str = "llm") -> Optional[str]:
        """Return the response text, or None on failure."""
        text = self._generate(prompt, json_mode=False, step=step)
        return text.strip() if text else None


def _is_timeout(exc: BaseException) -> bool:
    """True for timeouts from Python, httpx (ReadTimeout, ConnectTimeout, ...) or anything named *Timeout*."""
    while exc is not None:
        if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def classify_error(exc: Exception) -> str:
    """Sort an exception into RETRYABLE (timeout/5xx), AUTH, BAD_MODEL (404) or CLIENT (other 4xx / unknown)."""
    code = getattr(exc, "code", None)
    text = str(exc)
    if code in (401, 403) or "API_KEY_INVALID" in text or "API key not valid" in text:
        return AUTH
    if isinstance(code, int) and 500 <= code <= 599:
        return RETRYABLE
    if code == 404:
        return BAD_MODEL
    if isinstance(code, int) and 400 <= code <= 499:
        return CLIENT
    if _is_timeout(exc):
        return RETRYABLE
    return CLIENT


def describe_error(exc: Exception) -> str:
    """Short one-line description: type, HTTP code/status if any, and a truncated message."""
    message = str(exc).replace("\n", " ")[:MAX_ERROR_CHARS]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
