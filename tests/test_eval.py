"""Evaluation harness: case-file validity and property checks (no network, offline agent)."""

import pytest

from eval.run_eval import (
    DEFAULT_CASES, PROPERTY_CHECKS, evaluate_case, load_cases, main, signature,
)
from src.agent import load_resources, run_agent
from src.config import SONGS_CSV
from src.logging_setup import configure, get_run_logger
from src.recommender import load_songs

GENRE_KEYS = ("top1_genre_in",)
GENRE_VALUE_KEYS = ("profile_genre", "genre_in_top3_or_caveat")


@pytest.fixture(scope="module")
def res():
    configure(verbose=False)
    return load_resources(get_run_logger("test-eval"))


def test_case_file_is_valid_and_uses_only_catalog_genres():
    cases = load_cases(DEFAULT_CASES)
    assert 12 <= len(cases) <= 15
    assert len({c["id"] for c in cases}) == len(cases)
    assert {"normal", "edge", "reject"} <= {c["category"] for c in cases}
    catalog = {s["genre"] for s in load_songs(str(SONGS_CSV))}
    moods = {s["mood"] for s in load_songs(str(SONGS_CSV))}
    for case in cases:
        expect = case["expect"]
        for key in GENRE_KEYS:
            assert set(expect.get(key, [])) <= catalog, case["id"]
        for key in GENRE_VALUE_KEYS:
            if key in expect:
                assert expect[key] in catalog, case["id"]
        for key in ("top1_mood_in", "any_top3_mood_in"):
            assert set(expect.get(key, [])) <= moods, case["id"]


def test_unknown_property_is_an_error(tmp_path):
    bad = tmp_path / "cases.json"
    bad.write_text('{"cases": [{"id": "x", "category": "normal", "request": "jazz", "expect": {"min_vibes": 1}}]}')
    with pytest.raises(ValueError, match="min_vibes"):
        load_cases(bad)


def test_property_checks_pass_and_fail(res):
    result = run_agent("hype songs for the gym", res)
    titles = [s["title"] for s in res.songs]
    good = evaluate_case({"expect": {"min_avg_energy": 0.7, "likes_acoustic": False}}, result, titles)
    assert all(p.passed for p in good)
    bad = evaluate_case({"expect": {"max_avg_energy": 0.3, "profile_genre": "jazz"}}, result, titles)
    assert [p.passed for p in bad if p.name != "explanation_grounded"] == [False, False]
    assert any(p.name == "explanation_grounded" and p.passed for p in bad)


def test_or_caveat_properties_accept_a_flagged_miss(res):
    result = run_agent("sad songs but not too slow", res)       # #1 is slow, but a caveat is shown
    passed, actual = PROPERTY_CHECKS["min_top1_energy_or_caveat"](0.45, result)
    assert passed and "caveat shown" in actual
    result.caveats = []
    assert not PROPERTY_CHECKS["min_top1_energy_or_caveat"](0.45, result)[0]


def test_rejection_expectations(res):
    titles = [s["title"] for s in res.songs]
    rejected = run_agent("", res)
    assert evaluate_case({"expect": {"rejected": "empty"}}, rejected, titles)[0].passed
    assert not evaluate_case({"expect": {"rejected": "off_topic"}}, rejected, titles)[0].passed
    wrongly = evaluate_case({"expect": {"min_avg_energy": 0.5}}, rejected, titles)
    assert wrongly[0].name == "not_rejected" and not wrongly[0].passed
    assert signature(rejected) == ("rejected", "empty")


def test_failed_case_reports_reason_and_confidence_split(res):
    from eval.run_eval import CaseResult, confidence_stats, result_text, run_suite, summary_line, tally
    from collections import Counter
    cases = [
        {"id": "ok", "category": "normal", "request": "hype songs for the gym", "expect": {"min_avg_energy": 0.7}},
        {"id": "bad", "category": "normal", "request": "k-pop for a party", "expect": {"profile_genre": "jazz"}},
    ]
    results = run_suite(cases, res, None, 1, 5)
    assert result_text(results[0]) == "Pass"
    assert result_text(results[1]) == "Fail - profile_genre: expected jazz, got pop"
    stats = confidence_stats(results)
    assert stats["avg_pass"] == pytest.approx(0.87) and stats["avg_fail"] == pytest.approx(0.94)
    line = summary_line(tally(results, False, Counter()), stats, False)
    assert line.startswith("1 out of 2 cases passed (50%); offline consistency 100%; average confidence")
    assert "k-pop for a party" in line          # failed cases count as struggling even with high confidence


def test_main_writes_report_offline(tmp_path, capsys):
    cases = tmp_path / "cases.json"
    cases.write_text('{"cases": ['
                     '{"id": "gym", "category": "normal", "request": "hype songs for the gym", "expect": {"min_avg_energy": 0.7}},'
                     '{"id": "empty", "category": "reject", "request": "", "expect": {"rejected": "empty"}}]}')
    report = tmp_path / "results.md"
    assert main(["--cases", str(cases), "--out", str(report), "--runs", "2"]) == 0
    printed = capsys.readouterr().out
    printed.encode("ascii")
    assert "Cases passed:       2/2" in printed and "Consistency:        2/2" in printed
    text = report.read_text(encoding="utf-8")
    assert "Mode: **offline**" in text
    assert "2 out of 2 cases passed (100%); offline consistency 100%; average confidence 0.87;" in text
    assert "| # | Test Input | Evaluation Criteria | Result | Confidence | Notes |" in text
    assert ("| 1 | hype songs for the gym | avg energy >= 0.7; explanation grounded | Pass | 0.87 (high) "
            "| favorite_mood 'hype' -> 'energetic' |") in text
    assert "| 2 | \"\" | rejected as empty | Pass | n/a (rejected) | rejected by `empty` guardrail" in text
    assert "| Average confidence, failed cases | n/a (no failed cases) |" in text
