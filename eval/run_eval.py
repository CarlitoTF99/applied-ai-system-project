"""
Reliability / evaluation harness for the VibeMatch agent.

    python -m eval.run_eval                 # offline (deterministic, no API calls)
    python -m eval.run_eval --llm           # use Gemini (see the quota note below)
    python -m eval.run_eval --llm --runs 1  # one pass, to save quota

Every case in eval/test_cases.json goes through the full agent pipeline (run_agent). Each case is run
--runs times (default 3): run 1 is checked against the case's expected properties, and all runs are compared
for consistency (identical top 5, or the identical rejection). Prints a plain-ASCII summary and writes
eval/results.md.

Quota note: with --llm each accepted case makes 2 Gemini calls per run (plan + explain), plus retries.
The default 11 accepted cases x 3 runs is ~66 calls, which can exceed free-tier per-minute or per-day
limits. 429 quota errors are not retried, so those calls fall back offline and show up as LLM fallbacks.
"""

import argparse
import json
import logging
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.agent import AgentResult, build_llm, load_resources, run_agent, to_ascii
from src.confidence import HIGH as HIGH_CONFIDENCE
from src.logging_setup import LOGGER_NAME, configure, get_run_logger

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = EVAL_DIR / "test_cases.json"
DEFAULT_REPORT = EVAL_DIR / "results.md"
DEFAULT_RUNS = 3
DEFAULT_K = 5
TOP3 = 3


# --- Property checks: each takes (expected value, AgentResult) and returns (passed, actual value as text) ---

def _songs(result: AgentResult) -> List[Dict]:
    return [song for song, _, _ in result.final.results]


def _avg(result: AgentResult, feature: str) -> float:
    songs = _songs(result)
    return sum(song[feature] for song in songs) / len(songs) if songs else 0.0


def _bound(feature: str, kind: str, source: str) -> Callable:
    """Build a min_/max_ check for an average over the results (source="avg") or a profile target ("target")."""
    def check(expected: float, result: AgentResult) -> Tuple[bool, str]:
        actual = _avg(result, feature) if source == "avg" else result.final.prefs[f"target_{feature}"]
        passed = actual >= expected if kind == "min" else actual <= expected
        return passed, f"{actual:.2f}"
    return check


def _top1_in(feature: str) -> Callable:
    def check(expected: List[str], result: AgentResult) -> Tuple[bool, str]:
        songs = _songs(result)
        actual = songs[0][feature] if songs else "(none)"
        return actual in expected, actual
    return check


def _any_top3_mood_in(expected: List[str], result: AgentResult) -> Tuple[bool, str]:
    moods = [song["mood"] for song in _songs(result)[:TOP3]]
    return any(mood in expected for mood in moods), ",".join(moods)


def _profile(key: str) -> Callable:
    def check(expected, result: AgentResult) -> Tuple[bool, str]:
        actual = result.final.prefs[key]
        return actual == expected, str(actual)
    return check


def _repair_contains(expected: str, result: AgentResult) -> Tuple[bool, str]:
    hits = [r for r in result.repairs if expected.lower() in r.lower()]
    return bool(hits), hits[0] if hits else f"{len(result.repairs)} repair(s), none mention '{expected}'"


def _has_caveat(expected: bool, result: AgentResult) -> Tuple[bool, str]:
    return bool(result.caveats) == expected, f"{len(result.caveats)} caveat(s)"


def _top1_energy_or_caveat(kind: str) -> Callable:
    """The #1 song honors an energy limit, OR the agent told the user it couldn't (a caveat)."""
    def check(expected: float, result: AgentResult) -> Tuple[bool, str]:
        energy = _songs(result)[0]["energy"]
        honored = energy >= expected if kind == "min" else energy <= expected
        flagged = bool(result.caveats)
        return honored or flagged, f"top1 energy {energy:.2f}" + (", caveat shown" if flagged else ", no caveat")
    return check


def _genre_in_top3_or_caveat(expected: str, result: AgentResult) -> Tuple[bool, str]:
    """A genre the user named is in the top 3 (exact or related pair), OR the agent flagged that it isn't."""
    from src.recommender import RELATED_GENRES
    genres = [song["genre"] for song in _songs(result)[:TOP3]]
    present = any(g == expected or frozenset((g, expected)) in RELATED_GENRES for g in genres)
    flagged = bool(result.caveats)
    return present or flagged, ",".join(genres) + (", caveat shown" if flagged else "")


def _rejected(expected: str, result: AgentResult) -> Tuple[bool, str]:
    actual = result.reject_rule if result.status == "rejected" else "accepted"
    return actual == expected, actual


PROPERTY_CHECKS: Dict[str, Callable] = {
    "min_avg_energy": _bound("energy", "min", "avg"),
    "max_avg_energy": _bound("energy", "max", "avg"),
    "min_avg_valence": _bound("valence", "min", "avg"),
    "max_avg_valence": _bound("valence", "max", "avg"),
    "min_target_energy": _bound("energy", "min", "target"),
    "max_target_energy": _bound("energy", "max", "target"),
    "min_target_valence": _bound("valence", "min", "target"),
    "max_target_valence": _bound("valence", "max", "target"),
    "top1_genre_in": _top1_in("genre"),
    "top1_mood_in": _top1_in("mood"),
    "any_top3_mood_in": _any_top3_mood_in,
    "profile_genre": _profile("favorite_genre"),
    "profile_mood": _profile("favorite_mood"),
    "likes_acoustic": _profile("likes_acoustic"),
    "repair_contains": _repair_contains,
    "has_caveat": _has_caveat,
    "min_top1_energy_or_caveat": _top1_energy_or_caveat("min"),
    "max_top1_energy_or_caveat": _top1_energy_or_caveat("max"),
    "genre_in_top3_or_caveat": _genre_in_top3_or_caveat,
    "rejected": _rejected,
}


def explanation_grounded(result: AgentResult, catalog_titles: List[str]) -> Tuple[bool, str]:
    """Universal check: the explanation names no catalog song outside the results."""
    in_results = {song["title"].lower() for song in _songs(result)}
    text = result.explanation.lower()
    strays = [t for t in catalog_titles if t.lower() in text and t.lower() not in in_results]
    return not strays, ("ok" if not strays else "mentions " + ", ".join(strays))


# --- Running ---

@dataclass
class PropertyResult:
    name: str
    expected: object
    passed: bool
    actual: str


@dataclass
class CaseResult:
    case: Dict
    runs: List[AgentResult]
    properties: List[PropertyResult] = field(default_factory=list)
    consistent: bool = True

    @property
    def passed(self) -> bool:
        return all(p.passed for p in self.properties)


class LogCounter(logging.Handler):
    """Counts Gemini retry / fallback-model log lines emitted while the eval runs."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.counts = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "retrying in" in message:
            self.counts["api_retries"] += 1
        if "trying fallback model" in message:
            self.counts["fallback_model_used"] += 1


def load_cases(path: Path) -> List[Dict]:
    """Load and validate the test cases; unknown property names are an error, not a silent pass."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]
    for case in cases:
        unknown = set(case["expect"]) - set(PROPERTY_CHECKS)
        if unknown:
            raise ValueError(f"case {case['id']}: unknown properties {sorted(unknown)}")
    return cases


def signature(result: AgentResult) -> Tuple:
    """What must match across repeated runs: the top 5 titles, or the rejection rule."""
    if result.status != "ok":
        return ("rejected", result.reject_rule)
    return tuple(song["title"] for song in _songs(result)[:5])


def evaluate_case(case: Dict, result: AgentResult, catalog_titles: List[str]) -> List[PropertyResult]:
    """Check one run against the case's expected properties (plus the universal checks)."""
    expect = case["expect"]
    if "rejected" not in expect and result.status != "ok":
        return [PropertyResult("not_rejected", True, False, f"rejected ({result.reject_rule})")]
    if "rejected" in expect and result.status == "ok":
        return [PropertyResult("rejected", expect["rejected"], False, "accepted")]
    props = []
    for name, expected in expect.items():
        passed, actual = PROPERTY_CHECKS[name](expected, result)
        props.append(PropertyResult(name, expected, passed, actual))
    if result.status == "ok":
        passed, actual = explanation_grounded(result, catalog_titles)
        props.append(PropertyResult("explanation_grounded", True, passed, actual))
    return props


def run_suite(cases: List[Dict], res, llm, runs: int, k: int) -> List[CaseResult]:
    catalog_titles = [song["title"] for song in res.songs]
    results = []
    for case in cases:
        outcomes = [run_agent(case["request"], res, llm=llm, k=k, run_id=f"eval-{case['id']}-{i + 1}")
                    for i in range(runs)]
        case_result = CaseResult(case, outcomes)
        case_result.properties = evaluate_case(case, outcomes[0], catalog_titles)
        case_result.consistent = len({signature(o) for o in outcomes}) == 1
        results.append(case_result)
    return results


def tally(results: List[CaseResult], llm_used: bool, log_counts: Counter) -> Dict:
    """Aggregate metrics. Counters are summed over ALL runs; 'per pass' divides by the number of runs."""
    all_runs = [run for r in results for run in r.runs]
    accepted = [run for run in all_runs if run.status == "ok"]
    props = [p for r in results for p in r.properties]
    return {
        "cases": len(results),
        "cases_passed": sum(r.passed for r in results),
        "properties": len(props),
        "properties_passed": sum(p.passed for p in props),
        "consistent": sum(r.consistent for r in results),
        "runs": len(all_runs),
        "rejections": sum(run.status == "rejected" for run in all_runs),
        "repairs": sum(len(run.repairs) for run in accepted),
        "runs_with_repairs": sum(bool(run.repairs) for run in accepted),
        "selfcheck_retries": sum(len(run.attempts) - 1 for run in accepted),
        "runs_with_caveats": sum(bool(run.caveats) for run in accepted),
        "llm_plan_fallbacks": sum(run.plan_source == "offline" for run in accepted) if llm_used else 0,
        "llm_explain_fallbacks": sum(run.explanation_source == "template" for run in accepted) if llm_used else 0,
        "api_retries": log_counts["api_retries"],
        "fallback_model_used": log_counts["fallback_model_used"],
    }


# --- Reporting ---

def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def _short(text: str, width: int) -> str:
    text = text if text else '""'
    return text if len(text) <= width else text[: width - 3] + "..."


def counter_rows(m: Dict, runs: int, llm_used: bool) -> List[Tuple[str, int]]:
    rows = [
        ("guardrail rejections", m["rejections"]),
        ("repairs (total)", m["repairs"]),
        ("runs with >=1 repair", m["runs_with_repairs"]),
        ("self-check retries", m["selfcheck_retries"]),
        ("runs with caveats", m["runs_with_caveats"]),
    ]
    if llm_used:
        rows += [
            ("LLM plan -> offline fallback", m["llm_plan_fallbacks"]),
            ("LLM explain -> template fallback", m["llm_explain_fallbacks"]),
            ("Gemini API retries (5xx/timeout)", m["api_retries"]),
            ("fallback model used", m["fallback_model_used"]),
        ]
    return rows


def _fmt(value) -> str:
    if isinstance(value, list):
        return "/".join(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


CRITERIA_TEXT = {
    "min_avg_energy": "avg energy >= {}",
    "max_avg_energy": "avg energy <= {}",
    "min_avg_valence": "avg valence >= {}",
    "max_avg_valence": "avg valence <= {}",
    "min_target_energy": "target energy >= {}",
    "max_target_energy": "target energy <= {}",
    "min_target_valence": "target valence >= {}",
    "max_target_valence": "target valence <= {}",
    "top1_genre_in": "#1 genre in {}",
    "top1_mood_in": "#1 mood in {}",
    "any_top3_mood_in": "a top-3 mood in {}",
    "profile_genre": "profile genre = {}",
    "profile_mood": "profile mood = {}",
    "likes_acoustic": "acoustic = {}",
    "repair_contains": "repair logged for '{}'",
    "min_top1_energy_or_caveat": "#1 energy >= {} or caveat",
    "max_top1_energy_or_caveat": "#1 energy <= {} or caveat",
    "genre_in_top3_or_caveat": "{} in top 3 or caveat",
    "rejected": "rejected as {}",
}


def describe_criteria(case: Dict) -> str:
    """Plain-English list of what a case checks."""
    parts = []
    for name, value in case["expect"].items():
        if name == "has_caveat":
            parts.append("caveat shown" if value else "no caveat")
        else:
            parts.append(CRITERIA_TEXT[name].format(_fmt(value)))
    if "rejected" not in case["expect"]:
        parts.append("explanation grounded")
    return "; ".join(parts)


def result_text(r: "CaseResult") -> str:
    if r.passed:
        return "Pass"
    reasons = [f"{p.name}: expected {_fmt(p.expected)}, got {p.actual}" for p in r.properties if not p.passed]
    return "Fail - " + "; ".join(reasons)


def notes_text(r: "CaseResult") -> str:
    first = r.runs[0]
    if first.status != "ok":
        notes = [f"rejected by `{first.reject_rule}` guardrail before retrieval"]
    else:
        notes = [repair.split(" (")[0] for repair in first.repairs]
        retries = len(first.attempts) - 1
        if retries:
            notes.append(f"{retries} self-check retr{'ies' if retries != 1 else 'y'}, used attempt #{first.final.number}")
        if first.caveats:
            notes.append("caveat shown")
        if first.llm_used and (first.plan_source == "offline" or first.explanation_source == "template"):
            notes.append("LLM fell back to offline")
        if not notes:
            notes = ["clean run"]
    if not r.consistent:
        notes.append("results differed between runs")
    return "; ".join(notes)


def confidence_text(run: AgentResult) -> str:
    if run.confidence is None:
        return "n/a (rejected)"
    return f"{run.confidence.score:.2f} ({run.confidence.label})"


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def confidence_stats(results: List["CaseResult"]) -> Dict:
    """Average confidence over accepted cases (run 1), overall and split by pass/fail; rejected cases have none."""
    scored = [(r, r.runs[0].confidence.score) for r in results if r.runs[0].confidence is not None]
    struggling = sorted(
        (item for item in scored if item[0].runs[0].confidence.label != "high" or not item[0].passed),
        key=lambda item: item[1],
    )
    return {
        "avg": _mean([s for _, s in scored]),
        "avg_pass": _mean([s for r, s in scored if r.passed]),
        "avg_fail": _mean([s for r, s in scored if not r.passed]),
        "scored_cases": len(scored),
        "struggling": struggling,
    }


def _avg_text(value: Optional[float], empty: str) -> str:
    return f"{value:.2f}" if value is not None else empty


def summary_line(m: Dict, stats: Dict, llm_used: bool) -> str:
    """One sentence: pass rate, consistency, average confidence and where the agent struggled."""
    mode_word = "LLM-mode" if llm_used else "offline"
    if stats["struggling"]:
        cases = ", ".join(
            f"\"{r.case['request']}\" ({s:.2f}: {r.runs[0].confidence.lowered_by[0].split(' ', 1)[1]})"
            for r, s in stats["struggling"]
        )
        struggle = f"the agent struggled when confidence fell below {HIGH_CONFIDENCE:.2f}: {cases}"
    else:
        struggle = "the agent did not struggle: every accepted case had high confidence"
    return (f"{m['cases_passed']} out of {m['cases']} cases passed ({_pct(m['cases_passed'], m['cases'])}); "
            f"{mode_word} consistency {_pct(m['consistent'], m['cases'])}; "
            f"average confidence {_avg_text(stats['avg'], 'n/a')}; {struggle}.")


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def print_summary(results: List[CaseResult], m: Dict, mode: str, runs: int, llm_used: bool) -> None:
    out = lambda s="": print(to_ascii(s))
    width = 78
    stats = confidence_stats(results)
    out("=" * width)
    out(f"VibeMatch evaluation  |  mode: {mode}  |  {m['cases']} cases x {runs} runs")
    out("=" * width)
    out(f"{'case':<20}{'category':<9}{'request':<26}{'result':<7}{'conf':<7}{'consistent'}")
    out("-" * width)
    for r in results:
        conf = r.runs[0].confidence
        out(f"{_short(r.case['id'], 19):<20}{r.case['category']:<9}{_short(r.case['request'], 24):<26}"
            f"{'PASS' if r.passed else 'FAIL':<7}{(f'{conf.score:.2f}' if conf else 'n/a'):<7}"
            f"{'yes' if r.consistent else 'NO'}")
    failures = [(r, p) for r in results for p in r.properties if not p.passed]
    if failures:
        out("-" * width)
        out("Failed properties:")
        for r, p in failures:
            out(f"  {r.case['id']}: {p.name} expected {p.expected!r}, got {p.actual}")
    out("-" * width)
    out(f"Cases passed:       {m['cases_passed']}/{m['cases']} ({_pct(m['cases_passed'], m['cases'])})")
    out(f"Properties passed:  {m['properties_passed']}/{m['properties']} ({_pct(m['properties_passed'], m['properties'])})")
    out(f"Consistency:        {m['consistent']}/{m['cases']} cases identical across {runs} runs "
        f"({_pct(m['consistent'], m['cases'])})")
    out(f"Avg confidence:     {_avg_text(stats['avg'], 'n/a')} overall, "
        f"{_avg_text(stats['avg_pass'], 'n/a')} passed, {_avg_text(stats['avg_fail'], 'n/a (no failures)')} failed "
        f"({stats['scored_cases']} accepted cases; rejected cases have no confidence)")
    out(f"Counters over all {m['runs']} runs (per pass = total / {runs}):")
    for label, value in counter_rows(m, runs, llm_used):
        out(f"  {label:<34}{value:>5}   per pass {value / runs:.1f}")
    out("-" * width)
    out(textwrap.fill("Summary: " + summary_line(m, stats, llm_used), width))
    out("=" * width)


def write_report(path: Path, results: List[CaseResult], m: Dict, mode: str, runs: int, llm_used: bool) -> None:
    stats = confidence_stats(results)
    fallbacks = (f"{m['llm_plan_fallbacks']} plan, {m['llm_explain_fallbacks']} explanation"
                 if llm_used else "0 (offline run: no LLM calls were made)")
    lines = [
        "# VibeMatch Evaluation Results",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Mode: **{mode}**",
        f"- {m['cases']} cases x {runs} runs each = {m['runs']} agent runs",
        "",
        "## Summary",
        "",
        summary_line(m, stats, llm_used),
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cases passed | {m['cases_passed']}/{m['cases']} ({_pct(m['cases_passed'], m['cases'])}) |",
        f"| Properties passed | {m['properties_passed']}/{m['properties']} ({_pct(m['properties_passed'], m['properties'])}) |",
        f"| Consistency (identical top 5 / rejection across {runs} runs) | {m['consistent']}/{m['cases']} ({_pct(m['consistent'], m['cases'])}) |",
        f"| Average confidence (accepted cases, run 1) | {_avg_text(stats['avg'], 'n/a')} |",
        f"| Average confidence, passed cases | {_avg_text(stats['avg_pass'], 'n/a')} |",
        f"| Average confidence, failed cases | {_avg_text(stats['avg_fail'], 'n/a (no failed cases)')} |",
        "",
        "Confidence is computed, never self-rated by the LLM: it starts at 1.0 and loses points for a top score "
        "below the maximum, a weak knowledge-base match, plan repairs, self-check retries and LLM fallbacks "
        "(see `src/confidence.py`). Rejected requests have no confidence.",
        "",
        "## Results by case",
        "",
        "| # | Test Input | Evaluation Criteria | Result | Confidence | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for number, r in enumerate(results, start=1):
        lines.append(f"| {number} | {_cell(_short(r.case['request'], 70))} | {_cell(describe_criteria(r.case))} "
                     f"| {_cell(result_text(r))} | {confidence_text(r.runs[0])} | {_cell(notes_text(r))} |")
    lines += [
        "",
        "## Counts",
        "",
        f"Totals over all {m['runs']} runs ({runs} per case):",
        "",
        "| Count | Total | Per pass |",
        "|---|---|---|",
        f"| Guardrail rejections | {m['rejections']} | {m['rejections'] / runs:.1f} |",
        f"| Repairs | {m['repairs']} | {m['repairs'] / runs:.1f} |",
        f"| Self-check retries | {m['selfcheck_retries']} | {m['selfcheck_retries'] / runs:.1f} |",
        f"| Runs with caveats | {m['runs_with_caveats']} | {m['runs_with_caveats'] / runs:.1f} |",
        f"| LLM fallbacks to offline | {fallbacks} | |",
    ]
    if llm_used:
        lines += [
            f"| Gemini API retries (5xx/timeout) | {m['api_retries']} | {m['api_retries'] / runs:.1f} |",
            f"| Fallback model used | {m['fallback_model_used']} | {m['fallback_model_used'] / runs:.1f} |",
        ]
    lines += ["", "## Details (run 1 of each case)", ""]
    for r in results:
        first = r.runs[0]
        lines.append(f"### {r.case['id']} - {'PASS' if r.passed else 'FAIL'}")
        lines.append("")
        lines.append(f"Request: `{_short(r.case['request'], 120)}`")
        lines.append("")
        if first.status != "ok":
            lines.append(f"Rejected by rule `{first.reject_rule}`: {first.message}")
        else:
            p = first.final.prefs
            c = first.confidence
            lines.append(f"- Docs: {', '.join(d.doc_id for d, _ in first.docs) or '(none)'}")
            lines.append(f"- Profile: genre={p['favorite_genre']}, mood={p['favorite_mood']}, "
                         f"energy={p['target_energy']:.2f}, valence={p['target_valence']:.2f}, "
                         f"acoustic={p['likes_acoustic']}, mode={p['mode']}, diverse={p['diverse']}")
            lines.append(f"- Plan source: {first.plan_source}; explanation: {first.explanation_source}")
            lines.append(f"- Repairs: {'; '.join(first.repairs) or 'none'}")
            lines.append(f"- Attempts: {len(first.attempts)} (using #{first.final.number}); "
                         f"caveats: {'; '.join(first.caveats) or 'none'}")
            lines.append(f"- Confidence: {c.score:.2f} ({c.label}); lowered by: {'; '.join(c.lowered_by) or 'nothing'}")
            top = ", ".join(f"{s['title']} ({sc:.2f}, e={s['energy']:.2f}, v={s['valence']:.2f})"
                            for s, sc, _ in first.final.results)
            lines.append(f"- Top {len(first.final.results)}: {top}")
        lines.append("")
        lines.append("| Property | Expected | Actual | Pass |")
        lines.append("|---|---|---|---|")
        for prop in r.properties:
            lines.append(f"| {prop.name} | {json.dumps(prop.expected)} | {_cell(prop.actual)} | {'yes' if prop.passed else '**no**'} |")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the VibeMatch agent against eval/test_cases.json.",
        epilog="--llm uses Gemini: ~2 calls per accepted case per run. Free-tier quota is limited; "
               "use --runs 1 to save calls. Quota (429) errors fall back offline and are counted.",
    )
    parser.add_argument("--llm", action="store_true", help="use Gemini instead of the offline planner (default: offline)")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help=f"runs per case for consistency (default {DEFAULT_RUNS})")
    parser.add_argument("--k", type=int, default=DEFAULT_K, help=f"songs per recommendation (default {DEFAULT_K})")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="test case file")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT, help="markdown report path")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    runs = max(1, args.runs)
    configure(verbose=False)
    log = get_run_logger("eval")
    counter = LogCounter()
    logging.getLogger(LOGGER_NAME).addHandler(counter)
    try:
        cases = load_cases(args.cases)
        llm = build_llm(log, offline=not args.llm)
        llm_used = llm is not None and llm.available
        if args.llm and not llm_used:
            print(to_ascii(f"warning: --llm requested but Gemini is unavailable ({llm.disabled_reason}); running offline"))
        if args.llm:
            print("note: --llm makes real Gemini calls; free-tier quota is limited (see --help).")
        mode = f"llm ({llm.model}, fallback {llm.fallback_model or 'none'})" if llm_used else "offline"
        res = load_resources(log)
        results = run_suite(cases, res, llm if llm_used else None, runs, args.k)
    finally:
        logging.getLogger(LOGGER_NAME).removeHandler(counter)
    metrics = tally(results, llm_used, counter.counts)
    print_summary(results, metrics, mode, runs, llm_used)
    write_report(args.out, results, metrics, mode, runs, llm_used)
    print(f"Report written to {args.out.relative_to(Path.cwd()) if args.out.is_relative_to(Path.cwd()) else args.out}")
    return 0 if metrics["cases_passed"] == metrics["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
