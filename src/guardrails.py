"""Guardrails: (a) input check, (d) plan validation/repair, and the output check on explanations."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.config import MAX_EXPLANATION_CHARS, MAX_REQUEST_CHARS, MIN_RELEVANCE
from src.labels import LabelSpace
from src.recommender import DEFAULT_MODE, SCORING_MODES
from src.retriever import BM25Index, tokenize

# --- a. Input guardrail ---

MUSIC_WORDS = frozenset("""
song songs music playlist track tracks tune tunes vibe vibes listen listening album artist
band beat beats sound sounds mix jam jams banger bangers melody instrumental vocals singer
""".split())

MSG_EMPTY = "Tell me what you'd like to hear, e.g. 'upbeat songs for a road trip'."
MSG_TOO_LONG = f"Please keep requests under {MAX_REQUEST_CHARS} characters."
MSG_OFF_TOPIC = "I can only help with music recommendations - try describing a mood, activity, or genre."

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class InputCheck:
    ok: bool
    request: str            # cleaned request (control characters stripped, whitespace collapsed)
    rule: str               # which rule decided: "ok", "empty", "too_long", "off_topic"
    message: str = ""       # shown to the user when ok is False
    stripped_control: bool = False


def build_music_vocabulary(kb_docs: List, songs: List[Dict]) -> set:
    """Collect words that mark a request as music-related: KB keywords/labels/aliases plus catalog labels and tags."""
    words = set(MUSIC_WORDS)
    for doc in kb_docs:
        for key in ("keywords", "genres", "moods"):
            for item in doc.meta.get(key, []):
                words.update(tokenize(item, drop_stopwords=False))
        for alias in doc.meta.get("aliases", {}):
            words.update(tokenize(alias, drop_stopwords=False))
    for song in songs:
        for item in [song["genre"], song["mood"], *song.get("mood_tags", [])]:
            words.update(tokenize(item, drop_stopwords=False))
    return words


def check_input(raw: Optional[str], vocabulary: set, kb_index: BM25Index) -> InputCheck:
    """Reject empty, over-long or clearly non-music requests; never raises."""
    text = raw if isinstance(raw, str) else ""
    cleaned = _CONTROL_CHARS.sub(" ", text)
    stripped_control = cleaned != text
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return InputCheck(False, cleaned, "empty", MSG_EMPTY, stripped_control)
    if len(cleaned) > MAX_REQUEST_CHARS:
        return InputCheck(False, cleaned, "too_long", MSG_TOO_LONG, stripped_control)

    has_music_word = any(token in vocabulary for token in tokenize(cleaned, drop_stopwords=False))
    best = kb_index.search(cleaned, 1)
    best_score = best[0][1] if best else 0.0
    if not has_music_word and best_score < MIN_RELEVANCE:
        return InputCheck(False, cleaned, "off_topic", MSG_OFF_TOPIC, stripped_control)
    return InputCheck(True, cleaned, "ok", "", stripped_control)


# --- d. Validate / repair ---

REQUIRED_KEYS = ("favorite_genre", "favorite_mood", "target_energy", "target_valence", "likes_acoustic")
OPTIONAL_KEYS = ("mode", "diverse", "rationale")
UNIT_KEYS = ("target_energy", "target_valence")
TRUE_WORDS = {"true", "yes", "y", "1"}
FALSE_WORDS = {"false", "no", "n", "0"}
MAX_RATIONALE_CHARS = 300


def _normalize_label(value: str) -> str:
    """Lowercase, trim and tidy spacing/separators: "Hip Hop" -> "hip hop", "R & B" -> "r&b"."""
    value = re.sub(r"\s+", " ", value.strip().lower())
    return re.sub(r"\s*&\s*", "&", value)


def map_label(
    value: str,
    kind: str,
    labels: LabelSpace,
    song_index: Optional[BM25Index],
    kb_docs: List[Tuple],
    request: str,
) -> Tuple[Optional[str], str]:
    """Map a genre/mood that isn't in the catalog to the closest valid one; return (label, how)."""
    catalog = labels.genres if kind == "genre" else labels.moods
    aliases = labels.genre_aliases if kind == "genre" else labels.mood_aliases
    normalized = _normalize_label(value)

    if normalized in catalog:
        return normalized, "normalized spelling"
    hyphenated = normalized.replace(" ", "-")
    if hyphenated in catalog:
        return hyphenated, "normalized spelling"
    for candidate in (normalized, hyphenated, normalized.replace("-", " ")):
        if candidate in aliases:
            return aliases[candidate], "alias from knowledge base"
    if kind == "mood" and normalized in labels.family_reps:
        return labels.family_reps[normalized], "mood family name"

    if song_index is not None:
        field = "genre" if kind == "genre" else "mood"
        hits = song_index.search(f"{normalized} {request}", 1)
        if hits:
            return hits[0][0].meta[field], f"closest song by retrieval ({hits[0][0].meta['title']})"

    key = "genres" if kind == "genre" else "moods"
    for doc, _ in kb_docs:
        listed = [label for label in doc.meta.get(key, []) if label in catalog]
        if listed:
            return listed[0], f"first {kind} in top doc {doc.doc_id}"
    return None, "no mapping found"


def validate_prefs(
    raw,
    fallback: Dict,
    labels: LabelSpace,
    song_index: Optional[BM25Index],
    kb_docs: List[Tuple],
    request: str,
) -> Tuple[Dict, List[str], Optional[str]]:
    """Check a plan against the schema and repair it; return (clean prefs, repairs, rationale).

    fallback is the offline plan, used for anything missing or unusable. Every change is recorded.
    """
    repairs: List[str] = []
    if not isinstance(raw, dict):
        repairs.append(f"plan was {type(raw).__name__}, not an object; used offline plan")
        raw = dict(fallback)
    prefs = dict(raw)

    rationale = prefs.pop("rationale", None)
    if rationale is not None:
        rationale = str(rationale)[:MAX_RATIONALE_CHARS]

    for key in list(prefs):
        if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS:
            repairs.append(f"dropped unknown key '{key}'")
            del prefs[key]

    for key in REQUIRED_KEYS:
        if key not in prefs or prefs[key] is None:
            prefs[key] = fallback[key]
            repairs.append(f"{key} missing; filled from offline plan ({fallback[key]!r})")

    for key in UNIT_KEYS:
        value = prefs[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                number = float(str(value).strip())
                repairs.append(f"{key} {value!r} cast to number {number:g}")
            except ValueError:
                number = fallback[key]
                repairs.append(f"{key} {value!r} is not a number; used offline value {number}")
            value = number
        if value != value:  # NaN
            value = fallback[key]
            repairs.append(f"{key} was NaN; used offline value {value}")
        clamped = max(0.0, min(1.0, float(value)))
        if clamped != value:
            repairs.append(f"{key} {value:g} clamped to {clamped:g}")
        prefs[key] = round(clamped, 2)

    prefs["likes_acoustic"] = _coerce_bool("likes_acoustic", prefs["likes_acoustic"], fallback["likes_acoustic"], repairs)

    mode = prefs.get("mode", DEFAULT_MODE)
    if not isinstance(mode, str) or mode.strip().lower() not in SCORING_MODES:
        repairs.append(f"mode {mode!r} unknown; set to {DEFAULT_MODE}")
        mode = DEFAULT_MODE
    prefs["mode"] = mode.strip().lower()

    diverse = prefs.get("diverse", False)
    if not isinstance(diverse, bool):
        repairs.append(f"diverse {diverse!r} is not a boolean; set to false")
        diverse = False
    prefs["diverse"] = diverse

    for key, kind in (("favorite_genre", "genre"), ("favorite_mood", "mood")):
        value = prefs[key]
        catalog = labels.genres if kind == "genre" else labels.moods
        if not isinstance(value, str) or not value.strip():
            prefs[key] = fallback[key] if fallback[key] in catalog else catalog[0]
            repairs.append(f"{key} {value!r} invalid; used {prefs[key]!r}")
            continue
        if value in catalog:
            continue
        mapped, how = map_label(value, kind, labels, song_index, kb_docs, request)
        if mapped is None:
            mapped = fallback[key] if fallback[key] in catalog else catalog[0]
            how = "fallback"
        prefs[key] = mapped
        repairs.append(f"{key} '{value}' -> '{mapped}' ({how})")

    return prefs, repairs, rationale


def _coerce_bool(key: str, value, fallback: bool, repairs: List[str]) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE_WORDS or text in FALSE_WORDS:
        result = text in TRUE_WORDS
        repairs.append(f"{key} {value!r} coerced to {result}")
        return result
    repairs.append(f"{key} {value!r} unreadable; used offline value {fallback}")
    return bool(fallback)


# --- g. Output guardrail ---

_CITATION = re.compile(r"\[([^\[\]]+)\]")


def check_explanation(
    text: Optional[str],
    result_titles: List[str],
    catalog_titles: List[str],
    retrieved_doc_ids: List[str],
) -> Tuple[bool, str]:
    """Return (ok, reason). The text may only name songs in the results and must cite a retrieved doc."""
    if not text or not text.strip():
        return False, "empty explanation"
    if len(text) > MAX_EXPLANATION_CHARS:
        return False, f"too long ({len(text)} chars)"
    lowered = text.lower()
    in_results = {title.lower() for title in result_titles}
    for title in catalog_titles:
        if title.lower() in lowered and title.lower() not in in_results:
            return False, f"mentions '{title}', which is not in the results"
    if not any(title in lowered for title in in_results):
        return False, "mentions none of the recommended songs"
    cited = [part.strip() for group in _CITATION.findall(text) for part in group.split(",")]
    cited_docs = [c for c in cited if c.endswith(".md")]
    if not cited_docs:
        return False, "cites no knowledge doc"
    unknown = [c for c in cited_docs if c not in retrieved_doc_ids]
    if unknown:
        return False, f"cites docs that were not retrieved: {', '.join(unknown)}"
    return True, "ok"
