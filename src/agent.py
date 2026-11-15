"""
VibeMatch Agent: natural-language music requests -> recommendations from the existing engine.

    python -m src.agent "something chill for studying on a rainy night" [--offline] [--verbose] [--k 5] [--table]

Steps: (a) input guardrail, (b) retrieve, (c) plan, (d) validate, (e) act, (f) self-check, (g) explain.
Every step is logged to logs/agent.log.
"""

import argparse
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src import config
from src.explainer import explain_llm, explain_template
from src.guardrails import build_music_vocabulary, check_explanation, check_input, validate_prefs
from src.labels import LabelSpace
from src.llm import GeminiClient
from src.logging_setup import configure, get_run_logger
from src.planner import expected_ranges, parse_modifiers, plan_llm, plan_offline
from src.recommender import load_songs, max_score, recommend_songs
from src.retriever import BM25Index, load_knowledge, song_to_doc
from src.selfcheck import Attempt, caveat_for, evaluate_results, pick_best, revise_prefs

LINE_WIDTH = 64
NAME_WIDTH = 44
ENGINE_KEYS = ("favorite_genre", "favorite_mood", "target_energy", "target_valence", "likes_acoustic")

VAGUE_CAVEAT = ("Your request didn't match any mood, activity or genre notes, so these are general picks - "
                "try adding a mood, activity or genre.")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REJECTED = 2


@dataclass
class Resources:
    """Everything loaded once and shared across requests."""
    songs: List[Dict]
    kb_docs: List
    kb_index: BM25Index
    song_index: BM25Index
    labels: LabelSpace
    vocabulary: set


def load_resources(log) -> Resources:
    """Load the catalog and knowledge base and build both BM25 indexes."""
    songs = load_songs(str(config.SONGS_CSV))
    try:
        kb_docs = load_knowledge(config.KNOWLEDGE_DIR)
    except OSError as exc:
        log.warning(f"could not read {config.KNOWLEDGE_DIR}: {exc}", step="setup")
        kb_docs = []
    if not kb_docs:
        log.warning("knowledge base is empty; retrieval will use the song catalog only", step="setup")
    log.info(f"loaded {len(songs)} songs and {len(kb_docs)} knowledge docs", step="setup")
    return Resources(
        songs=songs,
        kb_docs=kb_docs,
        kb_index=BM25Index(kb_docs),
        song_index=BM25Index([song_to_doc(song) for song in songs]),
        labels=LabelSpace.build(songs, kb_docs),
        vocabulary=build_music_vocabulary(kb_docs, songs),
    )


@dataclass
class AgentResult:
    status: str                                   # "ok" | "rejected"
    request: str
    run_id: str
    message: str = ""
    reject_rule: str = ""                         # guardrail rule that rejected the request, if any
    plan_source: str = "offline"                  # "llm" | "offline"
    docs: List[Tuple] = field(default_factory=list)
    song_hits: List[Tuple] = field(default_factory=list)
    repairs: List[str] = field(default_factory=list)
    rationale: Optional[str] = None
    attempts: List[Attempt] = field(default_factory=list)
    final: Optional[Attempt] = None
    caveats: List[str] = field(default_factory=list)
    explanation: str = ""
    explanation_source: str = "template"          # "llm" | "template"
    explanation_note: str = ""


def _engine_prefs(prefs: Dict) -> Dict:
    """The dict passed to recommend_songs: only the keys score_song reads (mode/diverse are separate args)."""
    return {key: prefs[key] for key in ENGINE_KEYS}


def _act(prefs: Dict, res: Resources, k: int, number: int, change: str, expected: Dict, log) -> Attempt:
    """Step e + f: run the existing engine on prefs and self-check the results."""
    engine_prefs = _engine_prefs(prefs)
    results = recommend_songs(engine_prefs, res.songs, k=k, mode=prefs["mode"], diverse=prefs["diverse"])
    best = max_score(engine_prefs, prefs["mode"])
    attempt = Attempt(number, dict(prefs), results, best, change=change)
    attempt.issues = evaluate_results(prefs, results, best, expected)
    top3 = ", ".join(f"{song['title']} {score:.2f}" for song, score, _ in results[:3])
    log.info(f"attempt {number} ({change}): prefs={prefs}", step="act")
    log.info(f"attempt {number} top-3: {top3} (max {best:g})", step="act")
    if attempt.issues:
        for issue in attempt.issues:
            log.info(f"attempt {number} issue [{issue.kind}]: {issue.detail}", step="selfcheck")
    else:
        log.info(f"attempt {number} passed self-check", step="selfcheck")
    return attempt


def run_agent(request, res: Resources, llm: Optional[GeminiClient] = None, k: int = config.DEFAULT_K,
              docs_k: int = config.DEFAULT_DOCS_K, run_id: Optional[str] = None) -> AgentResult:
    """Run steps a-g for one request and return everything the CLI (or a test) needs. Never raises on bad input."""
    run_id = run_id or uuid.uuid4().hex[:6]
    log = get_run_logger(run_id)
    use_llm = llm is not None and llm.available
    log.info(f"request={str(request)[:config.MAX_REQUEST_CHARS]!r} k={k} docs_k={docs_k} llm={'yes' if use_llm else 'no'}",
             step="start")

    # a. Input guardrail
    check = check_input(request, res.vocabulary, res.kb_index)
    if check.stripped_control:
        log.info("stripped control characters from request", step="input")
    if not check.ok:
        log.info(f"rejected by rule '{check.rule}'", step="input")
        return AgentResult("rejected", check.request, run_id, message=check.message, reject_rule=check.rule)
    log.info("passed input guardrail", step="input")
    request = check.request

    # b. Retrieve
    mods = parse_modifiers(request)
    query = mods.retrieval_query or request
    docs = res.kb_index.search(query, docs_k)
    song_hits = res.song_index.search(query, config.SONG_HITS_K)
    if query != request.lower():
        log.info(f"retrieval query (negations removed): {query!r}", step="retrieve")
    for doc, score in docs:
        log.info(f"doc {doc.doc_id} score={score:.3f}", step="retrieve")
    for doc, score in song_hits:
        log.info(f"song {doc.meta['title']} score={score:.3f}", step="retrieve")
    if not docs:
        log.warning("no knowledge docs matched; planning from song hits and defaults", step="retrieve")

    # c. Plan (the offline plan is always built: it is the fallback and fills missing keys)
    offline_prefs, trace = plan_offline(request, docs, song_hits, res.labels, mods)
    for note in trace.notes:
        log.info(note, step="plan")
    log.debug(f"genre votes {trace.genre_votes}", step="plan")
    log.debug(f"mood votes {trace.mood_votes}", step="plan")
    raw_plan, plan_source = offline_prefs, "offline"
    if use_llm:
        llm_plan = plan_llm(llm, request, docs, song_hits, res.labels)
        if llm_plan is None:
            log.warning("LLM plan unavailable; falling back to offline plan", step="plan")
        else:
            raw_plan, plan_source = llm_plan, "llm"
    log.info(f"{plan_source} plan: {raw_plan}", step="plan")

    # d. Validate
    prefs, repairs, rationale = validate_prefs(raw_plan, offline_prefs, res.labels, res.song_index, docs, request)
    if rationale:
        log.info(f"LLM rationale: {rationale}", step="validate")
    for repair in repairs:
        log.info(f"repair: {repair}", step="validate")
    log.info(f"validated prefs: {prefs}", step="validate")

    # e + f. Act and self-check, revising up to MAX_ATTEMPTS - 1 times
    expected = expected_ranges(docs, mods)
    if "source" in expected:
        log.info(f"expected ranges from {expected['source']}: energy {expected['energy'][0]:.2f}-{expected['energy'][1]:.2f}, "
                 f"valence {expected['valence'][0]:.2f}-{expected['valence'][1]:.2f}", step="selfcheck")
    for key, word, kind in (("explicit_genre", trace.explicit_genre, "genre"), ("explicit_mood", trace.explicit_mood, "mood")):
        resolved = res.labels.resolve(word, kind) if word else ""
        if resolved:
            expected[key] = resolved
    for key in ("energy_floor", "energy_ceiling"):
        if key in expected:
            log.info(f"explicit {key.replace('_', ' ')} {expected[key]:.2f} from request wording", step="selfcheck")
    for key in ("explicit_genre", "explicit_mood"):
        if key in expected:
            log.info(f"{key.replace('_', ' ')} '{expected[key]}' must appear in top 3", step="selfcheck")
    attempts = [_act(prefs, res, k, 1, "initial plan", expected, log)]
    while attempts[-1].issues and len(attempts) < config.MAX_ATTEMPTS:
        current = attempts[-1]
        revised, change = revise_prefs(current.prefs, current.issues, current.number + 1, expected, trace, res.labels)
        if revised is None:
            log.info(f"stopping retries: {change}", step="selfcheck")
            break
        revised, more_repairs, _ = validate_prefs(revised, offline_prefs, res.labels, res.song_index, docs, request)
        for repair in more_repairs:
            log.info(f"repair: {repair}", step="validate")
        repairs.extend(more_repairs)
        attempts.append(_act(revised, res, k, current.number + 1, change, expected, log))
    final = pick_best(attempts)
    log.info(f"using attempt {final.number} of {len(attempts)} ({len(final.issues)} issue(s))", step="selfcheck")
    caveats = list(dict.fromkeys(caveat_for(issue) for issue in final.issues))
    if not docs:
        caveats.insert(0, VAGUE_CAVEAT)
        log.info("no knowledge doc matched; adding vague-request caveat", step="selfcheck")

    # g. Explain + output guardrail
    doc_ids = [doc.doc_id for doc, _ in docs]
    result_titles = [song["title"] for song, _, _ in final.results]
    catalog_titles = [song["title"] for song in res.songs]
    explanation, source, note = None, "template", ""
    if llm is not None and llm.available:
        text = explain_llm(llm, request, final.results, doc_ids, caveats, final.best)
        if text is None:
            note = "LLM explanation unavailable"
            log.warning(f"{note}; using template", step="explain")
        else:
            ok, reason = check_explanation(text, result_titles, catalog_titles, doc_ids)
            if ok:
                explanation, source = text, "llm"
                log.info("LLM explanation passed output guardrail", step="explain")
            else:
                note = f"LLM explanation rejected: {reason}"
                log.warning(f"{note}; using template", step="explain")
    if explanation is None:
        explanation = explain_template(final.prefs, final.results, doc_ids, caveats)
        ok, reason = check_explanation(explanation, result_titles, catalog_titles, doc_ids)
        log.info(f"template explanation used; output guardrail check: {reason}", step="explain")

    return AgentResult(
        status="ok", request=request, run_id=run_id, plan_source=plan_source, docs=docs,
        song_hits=song_hits, repairs=repairs, rationale=rationale, attempts=attempts, final=final,
        caveats=caveats, explanation=explanation, explanation_source=source, explanation_note=note,
    )


# --- Console output (plain ASCII for Windows terminals) ---

_ASCII_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "→": "->", " ": " ",
})


def to_ascii(text: str) -> str:
    """Replace curly quotes/dashes and strip anything else outside ASCII."""
    text = unicodedata.normalize("NFKD", str(text).translate(_ASCII_MAP))
    return text.encode("ascii", "ignore").decode("ascii")


def out(text: str = "") -> None:
    print(to_ascii(text))


def print_result(result: AgentResult, offline: bool, table: bool) -> None:
    out("=" * LINE_WIDTH)
    out(f"VibeMatch Agent  |  plan: {result.plan_source}" + ("  (--offline)" if offline else ""))
    out(f'Request: "{result.request}"')
    out("=" * LINE_WIDTH)

    out("\n[1] Retrieved knowledge docs")
    for doc, score in result.docs:
        out(f"    {doc.doc_id:<18} score {score:.2f}   ({doc.kind})")
    if not result.docs:
        out("    (none matched)")
    hits = ", ".join(f"{doc.meta['title']} ({score:.2f})" for doc, score in result.song_hits)
    out(f"    song evidence: {hits or '(none)'}")

    prefs = result.final.prefs
    out("\n[2] Profile (attempt %d)" % result.final.number)
    out(f"    genre={prefs['favorite_genre']} | mood={prefs['favorite_mood']} | energy={prefs['target_energy']:.2f}"
        f" | valence={prefs['target_valence']:.2f} | acoustic={'yes' if prefs['likes_acoustic'] else 'no'}")
    out(f"    mode={prefs['mode']} | diverse={'yes' if prefs['diverse'] else 'no'}")
    if result.rationale:
        out(f"    LLM rationale: {result.rationale}")

    out("\n[3] Repairs")
    for repair in result.repairs or ["none"]:
        out(f"    - {repair}")

    out(f"\n[4] Self-check ({len(result.attempts)} attempt(s), using #{result.final.number})")
    for attempt in result.attempts:
        status = "pass" if not attempt.issues else "; ".join(f"{i.kind}: {i.detail}" for i in attempt.issues)
        out(f"    #{attempt.number} {attempt.change}")
        out(f"       top: {attempt.results[0][0]['title']} {attempt.top_score:.2f}/{attempt.best:g} -> {status}")

    out(f"\n[5] Top {len(result.final.results)} recommendations")
    if table:
        from src.main import print_table
        print_table(result.final.results, result.final.best)
    else:
        out("-" * LINE_WIDTH)
        for rank, (song, score, explanation) in enumerate(result.final.results, start=1):
            title = f"{song['title']} - {song['artist']}"
            out(f"{rank}. {title:<{NAME_WIDTH}}Score: {score:.2f} / {result.final.best:g}")
            for reason in explanation.split("; "):
                out(f"     + {reason}")

    label = "LLM" if result.explanation_source == "llm" else "template"
    out(f"\n[6] Explanation ({label})" + (f"  [{result.explanation_note}]" if result.explanation_note else ""))
    for line in result.explanation.splitlines():
        out(f"    {line}")
    out(f"\n(run {result.run_id} logged to logs/agent.log)")


def build_llm(log, offline: bool = False) -> Optional[GeminiClient]:
    """Create the Gemini client from .env settings (None when offline) and log its configuration."""
    if offline:
        log.info("offline mode requested (--offline)", step="start")
        return None
    config.load_env()
    llm = GeminiClient(
        config.gemini_api_key(), config.gemini_model(), log,
        timeout=config.gemini_timeout(), fallback_model=config.gemini_fallback_model(),
    )
    log.info(f"Gemini model={llm.model} fallback={llm.fallback_model or 'none'} "
             f"timeout={llm.timeout:g}s retries={len(llm.retry_delays)} "
             f"backoff={'/'.join(f'{d:g}s' for d in llm.retry_delays)}", step="start")
    if not llm.available:
        log.warning(f"LLM unavailable ({llm.disabled_reason}); running offline", step="start")
    return llm


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VibeMatch Agent: describe what you want to hear.")
    parser.add_argument("request", nargs="?", default="", help='e.g. "hype songs for the gym"')
    parser.add_argument("--offline", action="store_true", help="never call the LLM, even if a key is set")
    parser.add_argument("--verbose", action="store_true", help="also print each step's log lines to the console")
    parser.add_argument("--k", type=int, default=config.DEFAULT_K,
                        help=f"number of songs to recommend ({config.MIN_K}-{config.MAX_K}, default {config.DEFAULT_K})")
    parser.add_argument("--table", action="store_true", help="show recommendations as a grid table")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    configure(verbose=args.verbose)
    run_id = uuid.uuid4().hex[:6]
    log = get_run_logger(run_id)
    try:
        config.load_env()
        k = max(config.MIN_K, min(config.MAX_K, args.k))
        if k != args.k:
            log.warning(f"--k {args.k} clamped to {k}", step="start")

        llm = build_llm(log, offline=args.offline)
        res = load_resources(log)
        result = run_agent(args.request, res, llm=llm, k=k, run_id=run_id)
        if result.status == "rejected":
            out(result.message)
            return EXIT_REJECTED
        print_result(result, args.offline, args.table)
        return EXIT_OK
    except Exception:
        log.exception("unexpected error", step="error")
        out("Something went wrong - see logs/agent.log")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
