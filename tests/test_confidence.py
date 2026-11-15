"""Deterministic confidence score: unit rules and end-to-end ordering."""

import pytest

from src.agent import load_resources, main, run_agent
from src.confidence import compute_confidence
from src.logging_setup import configure, get_run_logger


class NoLLM:
    """An LLM that is 'available' but always fails, so the agent falls back offline."""
    available = True

    def generate_json(self, prompt, step="llm"):
        return None

    def generate_text(self, prompt, step="llm"):
        return None


@pytest.fixture(scope="module")
def res():
    configure(verbose=False)
    return load_resources(get_run_logger("test-confidence"))


def test_perfect_run_is_high_and_has_no_reasons():
    c = compute_confidence(top_ratio=1.0, top_doc_score=6.0, repairs=0, retries=0, llm_fallback=False)
    assert (c.score, c.label, c.lowered_by) == (1.0, "high", [])
    assert c.summary == "top score 100% of max, no repairs, no retries"


def test_each_signal_lowers_confidence_and_is_explained():
    base = compute_confidence(1.0, 6.0, 0, 0, False).score
    assert compute_confidence(0.7, 6.0, 0, 0, False).score < base
    assert compute_confidence(1.0, 1.0, 0, 0, False).score < base
    assert compute_confidence(1.0, 0.0, 0, 0, False).lowered_by == ["-0.25 no knowledge doc matched the request"]
    assert compute_confidence(1.0, 6.0, 2, 0, False).score == 0.90
    assert compute_confidence(1.0, 6.0, 0, 1, False).score == 0.90
    fallback = compute_confidence(1.0, 6.0, 0, 0, True)
    assert fallback.score == 0.90 and "LLM fallback" in fallback.summary
    # caps keep one runaway signal from dominating
    assert compute_confidence(1.0, 6.0, 10, 0, False).score == 0.85
    assert compute_confidence(1.0, 6.0, 0, 9, False).score == 0.80
    worst = compute_confidence(0.0, 0.0, 10, 9, True)
    assert worst.score == 0.0 and worst.label == "low"


def test_repaired_kpop_request_scores_below_clean_lofi_request(res):
    clean = run_agent("chill lofi music for studying", res)
    repaired = run_agent("k-pop for a party", res)
    assert repaired.repairs and not clean.repairs
    assert repaired.confidence.score < clean.confidence.score
    assert clean.confidence.label == "high"


def test_conflicting_request_with_retries_is_not_high(res):
    result = run_agent("rock but not too loud", res)
    assert len(result.attempts) > 1
    assert result.confidence.label in ("medium", "low")
    assert any("self-check retries" in r for r in result.confidence.lowered_by)


def test_llm_fallback_lowers_confidence_but_offline_choice_does_not(res):
    offline = run_agent("chill lofi music for studying", res)              # --offline: no penalty
    fell_back = run_agent("chill lofi music for studying", res, llm=NoLLM())
    assert not offline.llm_used and fell_back.llm_used
    assert fell_back.confidence.score == pytest.approx(offline.confidence.score - 0.10)
    assert "-0.10 LLM fell back to offline mode" in fell_back.confidence.lowered_by


def test_rejected_request_has_no_confidence_and_cli_prints_it(res, capsys):
    assert run_agent("", res).confidence is None
    assert main(["k-pop for a party", "--offline"]) == 0
    printed = capsys.readouterr().out
    assert "[7] Confidence: 0.94 (high) - top score 99% of max, 1 repair, no retries" in printed
    assert "-0.05 1 repair to the plan" in printed
