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
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.agent import AgentResult, build_llm, load_resources, run_agent, to_ascii
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


def print_summary(results: List[CaseResult], m: Dict, mode: str, runs: int, llm_used: bool) -> None:
    out = lambda s="": print(to_ascii(s))
    width = 78
    out("=" * width)
    out(f"VibeMatch evaluation  |  mode: {mode}  |  {m['cases']} cases x {runs} runs")
    out("=" * width)
    out(f"{'case':<20}{'category':<9}{'request':<28}{'result':<7}{'props':<7}{'consistent'}")
    out("-" * width)
    for r in results:
        passed = sum(p.passed for p in r.properties)
        out(f"{_short(r.case['id'], 19):<20}{r.case['category']:<9}{_short(r.case['request'], 26):<28}"
            f"{'PASS' if r.passed else 'FAIL':<7}{f'{passed}/{len(r.properties)}':<7}{'yes' if r.consistent else 'NO'}")
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
    out(f"Counters over all {m['runs']} runs (per pass = total / {runs}):")
    for label, value in counter_rows(m, runs, llm_used):
        out(f"  {label:<34}{value:>5}   per pass {value / runs:.1f}")
    out("=" * width)


def write_report(path: Path, results: List[CaseResult], m: Dict, mode: str, runs: int, llm_used: bool) -> None:
    lines = [
        "# VibeMatch Evaluation Results",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Mode: **{mode}**",
        f"- {m['cases']} cases x {runs} runs each = {m['runs']} agent runs",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cases passed | {m['cases_passed']}/{m['cases']} ({_pct(m['cases_passed'], m['cases'])}) |",
        f"| Properties passed | {m['properties_passed']}/{m['properties']} ({_pct(m['properties_passed'], m['properties'])}) |",
        f"| Consistency (identical top 5 / rejection across {runs} runs) | {m['consistent']}/{m['cases']} ({_pct(m['consistent'], m['cases'])}) |",
    ]
    for label, value in counter_rows(m, runs, llm_used):
        lines.append(f"| {label} (all runs) | {value} ({value / runs:.1f} per pass) |")
    lines += ["", "## Cases", "", "| Case | Category | Request | Result | Properties | Consistent |", "|---|---|---|---|---|---|"]
    for r in results:
        passed = sum(p.passed for p in r.properties)
        request = _short(r.case["request"], 60).replace("|", "\\|")
        lines.append(f"| {r.case['id']} | {r.case['category']} | {request} | {'PASS' if r.passed else '**FAIL**'} "
                     f"| {passed}/{len(r.properties)} | {'yes' if r.consistent else '**no**'} |")
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
            lines.append(f"- Docs: {', '.join(d.doc_id for d, _ in first.docs) or '(none)'}")
            lines.append(f"- Profile: genre={p['favorite_genre']}, mood={p['favorite_mood']}, "
                         f"energy={p['target_energy']:.2f}, valence={p['target_valence']:.2f}, "
                         f"acoustic={p['likes_acoustic']}, mode={p['mode']}, diverse={p['diverse']}")
            lines.append(f"- Plan source: {first.plan_source}; explanation: {first.explanation_source}")
            lines.append(f"- Repairs: {'; '.join(first.repairs) or 'none'}")
            lines.append(f"- Attempts: {len(first.attempts)} (using #{first.final.number}); "
                         f"caveats: {'; '.join(first.caveats) or 'none'}")
            top = ", ".join(f"{s['title']} ({sc:.2f}, e={s['energy']:.2f}, v={s['valence']:.2f})"
                            for s, sc, _ in first.final.results)
            lines.append(f"- Top {len(first.final.results)}: {top}")
        lines.append("")
        lines.append("| Property | Expected | Actual | Pass |")
        lines.append("|---|---|---|---|")
        for prop in r.properties:
            lines.append(f"| {prop.name} | {json.dumps(prop.expected)} | {prop.actual} | {'yes' if prop.passed else '**no**'} |")
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
