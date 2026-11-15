"""Step g (Explain): a grounded LLM explanation, or a template built from the scoring reasons."""

import re
from typing import Dict, List, Optional, Tuple

REASONS_PER_SONG = 3
_POINTS = re.compile(r"\(\+([0-9.]+)\)$")


def _top_reasons(explanation: str, n: int = REASONS_PER_SONG) -> List[str]:
    """Return the n highest-scoring positive reasons, without their "(+x.xx)" suffix."""
    scored = []
    for reason in explanation.split("; "):
        match = _POINTS.search(reason)
        if match and float(match.group(1)) > 0:
            scored.append((float(match.group(1)), _POINTS.sub("", reason).strip()))
    scored.sort(key=lambda pair: -pair[0])
    return [label for _, label in scored[:n]]


def explain_template(prefs: Dict, results: List[Tuple], doc_ids: List[str], caveats: List[str]) -> str:
    """Build a factual explanation from the profile, the retrieved doc names and each song's top reasons."""
    sources = f"Based on [{', '.join(doc_ids)}], " if doc_ids else "Based on the catalog, "
    lines = [
        sources
        + f"I looked for {prefs['favorite_genre']} / {prefs['favorite_mood']} songs around energy "
        f"{prefs['target_energy']:.2f} and valence {prefs['target_valence']:.2f}"
        + (" with an acoustic sound." if prefs["likes_acoustic"] else " with an electric sound.")
    ]
    for rank, (song, score, explanation) in enumerate(results, start=1):
        reasons = ", ".join(_top_reasons(explanation)) or "closest overall score"
        lines.append(f"#{rank} {song['title']} by {song['artist']}: {reasons}.")
    lines.extend(f"Note: {caveat}" for caveat in caveats)
    return "\n".join(lines)


def build_explain_prompt(request: str, results: List[Tuple], doc_ids: List[str], caveats: List[str], best: float) -> str:
    """Build the explanation prompt: request, results with reasons, doc names and the citation rules."""
    song_lines = [
        f"{rank}. {song['title']} by {song['artist']} - score {score:.2f}/{best:g} - reasons: {explanation}"
        for rank, (song, score, explanation) in enumerate(results, start=1)
    ]
    return "\n".join([
        "You explain music recommendations to a listener. Write at most 120 words of plain text.",
        "Rules:",
        "- Mention ONLY songs from the RESULTS list, by their exact titles. Do not suggest any other song.",
        "- Ground the explanation in the scoring reasons given.",
        "- Cite at least one knowledge doc in square brackets exactly as named, e.g. [" + (doc_ids[0] if doc_ids else "doc.md") + "].",
        "- Use plain ASCII characters only.",
        "",
        f"REQUEST: {request}",
        "KNOWLEDGE DOCS USED: " + (", ".join(doc_ids) or "(none)"),
        "RESULTS:",
        *song_lines,
        "CAVEATS: " + ("; ".join(caveats) or "none"),
    ])


def explain_llm(llm, request: str, results: List[Tuple], doc_ids: List[str], caveats: List[str], best: float) -> Optional[str]:
    """Ask Gemini for an explanation; None if the LLM is unavailable or the call fails."""
    if llm is None or not llm.available:
        return None
    return llm.generate_text(build_explain_prompt(request, results, doc_ids, caveats, best), step="explain")
