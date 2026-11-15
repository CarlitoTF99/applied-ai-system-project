"""Step c (Plan): turn a request plus retrieved docs into a raw user_prefs dict, offline or with Gemini."""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.labels import LabelSpace
from src.recommender import DEFAULT_LIKES_ACOUSTIC, DEFAULT_TARGET_VALENCE, SCORING_MODES

DEFAULT_TARGET_ENERGY = 0.5
POSITION_DECAY = 0.1          # each later label in a doc's list gets 10% less of the doc's vote
MIN_POSITION_WEIGHT = 0.5
SONG_VOTE_SHARE = 0.5         # a song hit votes for its own genre/mood with half its score
ENERGY_FOCUSED_DOCS = {"workout.md", "party.md"}

# --- Modifier lexicon (applied after the doc-derived values) ---
_NEG = r"\bnot\s+(?:too\s+|so\s+|that\s+|very\s+|overly\s+)?"
NEGATED_SLOW = re.compile(_NEG + r"(?:slow|sleepy|mellow|quiet|soft|boring)\b")
NEGATED_FAST = re.compile(_NEG + r"(?:fast|loud|intense|hype|energetic|upbeat|heavy|aggressive)\b")
UP_WORDS = re.compile(r"\b(?:upbeat|fast|faster|energetic|lively)\b")
SLOW_WORDS = re.compile(r"\b(?:slow|slower|mellow|soft|quiet|gentle)\b")
HAPPY_WORDS = re.compile(r"\b(?:happy|cheerful|uplifting|joyful)\b")
SAD_WORDS = re.compile(r"\b(?:sad|depressing|heartbroken|gloomy)\b")
DIVERSE_WORDS = re.compile(r"\b(?:mix|variety|varied|different|assorted|eclectic)\b")

ENERGY_FLOOR = 0.5
ENERGY_CEILING = 0.6
ENERGY_SHIFT = 0.15
VALENCE_SHIFT = 0.15


@dataclass
class Modifiers:
    """Adjustments read from the request wording (e.g. "not too slow")."""
    energy_floor: Optional[float] = None
    energy_ceiling: Optional[float] = None
    energy_shift: float = 0.0
    valence_shift: float = 0.0
    diverse: bool = False
    matched: List[str] = field(default_factory=list)
    retrieval_query: str = ""     # request with negated phrases removed, so "not too slow" doesn't retrieve "slow"


def parse_modifiers(request: str) -> Modifiers:
    """Read energy/valence/diversity modifiers from the request; negated phrases are handled first."""
    text = request.lower()
    mods = Modifiers()
    for pattern, kind in ((NEGATED_SLOW, "floor"), (NEGATED_FAST, "ceiling")):
        for match in pattern.finditer(text):
            mods.matched.append(match.group(0))
            if kind == "floor":
                mods.energy_floor = ENERGY_FLOOR
            else:
                mods.energy_ceiling = ENERGY_CEILING
        text = pattern.sub(" ", text)

    if (m := UP_WORDS.search(text)):
        mods.energy_floor = max(mods.energy_floor or 0.0, ENERGY_FLOOR)
        mods.matched.append(m.group(0))
    if (m := SLOW_WORDS.search(text)):
        mods.energy_shift -= ENERGY_SHIFT
        mods.matched.append(m.group(0))
    if (m := HAPPY_WORDS.search(text)):
        mods.valence_shift += VALENCE_SHIFT
        mods.matched.append(m.group(0))
    if (m := SAD_WORDS.search(text)):
        mods.valence_shift -= VALENCE_SHIFT
        mods.matched.append(m.group(0))
    if (m := DIVERSE_WORDS.search(text)):
        mods.diverse = True
        mods.matched.append(m.group(0))
    mods.retrieval_query = re.sub(r"\s+", " ", text).strip()
    return mods


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def apply_energy_modifiers(energy: float, mods: Modifiers) -> float:
    """Shift then floor/ceiling an energy target, staying inside [0, 1]."""
    energy = _clamp(energy + mods.energy_shift)
    if mods.energy_floor is not None:
        energy = max(energy, mods.energy_floor)
    if mods.energy_ceiling is not None:
        energy = min(energy, mods.energy_ceiling)
    return energy


def expected_ranges(docs: List[Tuple], mods: Modifiers) -> Dict:
    """Return what the results should satisfy: the top ranged doc's energy/valence ranges adjusted by modifiers
    (soft), plus any explicit energy floor/ceiling from the wording (hard).

    The range keys are absent when no retrieved doc defines ranges (the self-check then skips range checks).
    """
    expected = _doc_ranges(docs, mods)
    if mods.energy_floor is not None:
        expected["energy_floor"] = mods.energy_floor
    if mods.energy_ceiling is not None:
        expected["energy_ceiling"] = mods.energy_ceiling
    return expected


def _doc_ranges(docs: List[Tuple], mods: Modifiers) -> Dict:
    for doc, _ in docs:
        energy, valence = doc.range("energy"), doc.range("valence")
        if not energy or not valence:
            continue
        e_lo, e_hi = _clamp(energy[0] + mods.energy_shift), _clamp(energy[1] + mods.energy_shift)
        if mods.energy_floor is not None:
            e_lo = max(e_lo, mods.energy_floor)
            e_hi = max(e_hi, e_lo)
        if mods.energy_ceiling is not None:
            e_hi = min(e_hi, mods.energy_ceiling)
            e_lo = min(e_lo, e_hi)
        v_lo, v_hi = _clamp(valence[0] + mods.valence_shift), _clamp(valence[1] + mods.valence_shift)
        return {"source": doc.doc_id, "energy": (e_lo, e_hi), "valence": (v_lo, v_hi)}
    return {}


@dataclass
class PlanTrace:
    """How the offline plan was derived; logged, and reused by the self-check to pick alternatives."""
    genre_votes: List[Tuple[str, float]] = field(default_factory=list)
    mood_votes: List[Tuple[str, float]] = field(default_factory=list)
    explicit_genre: Optional[str] = None
    explicit_mood: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    modifiers: Modifiers = field(default_factory=Modifiers)


def _weighted_mean(pairs: List[Tuple[float, float]], default: float) -> float:
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return default
    return sum(value * weight for value, weight in pairs) / total


def _midpoint(rng: Tuple[float, float]) -> float:
    return (rng[0] + rng[1]) / 2


def plan_offline(
    request: str,
    docs: List[Tuple],
    song_hits: List[Tuple],
    labels: LabelSpace,
    mods: Optional[Modifiers] = None,
) -> Tuple[Dict, PlanTrace]:
    """Derive user_prefs deterministically from the retrieved docs' ranges, label lists and the request wording."""
    mods = mods or parse_modifiers(request)
    trace = PlanTrace(modifiers=mods)
    ranged = [(doc, score) for doc, score in docs if doc.range("energy") and doc.range("valence")]
    sources = ", ".join(f"{doc.doc_id}({score:.2f})" for doc, score in ranged) or "none"

    # 1. Numeric targets: score-weighted mean of the docs' range midpoints
    energy = _weighted_mean([(_midpoint(d.range("energy")), s) for d, s in ranged], DEFAULT_TARGET_ENERGY)
    valence = _weighted_mean([(_midpoint(d.range("valence")), s) for d, s in ranged], DEFAULT_TARGET_VALENCE)
    trace.notes.append(f"doc-weighted energy={energy:.2f} valence={valence:.2f} from {sources}")

    # 2. Genre / mood votes from docs (position-weighted) and song hits
    genre_votes: Dict[str, float] = {}
    mood_votes: Dict[str, float] = {}
    for doc, score in docs:
        for key, votes in (("genres", genre_votes), ("moods", mood_votes)):
            for position, label in enumerate(doc.meta.get(key, [])):
                weight = max(MIN_POSITION_WEIGHT, 1 - POSITION_DECAY * position)
                votes[label] = votes.get(label, 0.0) + score * weight
    for doc, score in song_hits:
        song = doc.meta
        genre_votes[song["genre"]] = genre_votes.get(song["genre"], 0.0) + SONG_VOTE_SHARE * score
        mood_votes[song["mood"]] = mood_votes.get(song["mood"], 0.0) + SONG_VOTE_SHARE * score
    trace.genre_votes = sorted(((g, round(v, 2)) for g, v in genre_votes.items()), key=lambda p: (-p[1], p[0]))
    trace.mood_votes = sorted(((m, round(v, 2)) for m, v in mood_votes.items()), key=lambda p: (-p[1], p[0]))

    genre = trace.genre_votes[0][0] if trace.genre_votes else ""
    mood = trace.mood_votes[0][0] if trace.mood_votes else ""

    # A label the user names explicitly beats the votes. Non-catalog words (k-pop, calm, hype) are kept
    # as written so the validator maps them and records the repair.
    genre_mentions = labels.mentions(request, "genre")
    mood_mentions = labels.mentions(request, "mood")
    if genre_mentions:
        genre = trace.explicit_genre = genre_mentions[0][0]
        trace.notes.append(f"genre '{genre}' named in request")
    if mood_mentions:
        mood = trace.explicit_mood = mood_mentions[0][0]
        trace.notes.append(f"mood '{mood}' named in request")

    # Nothing retrieved for a label: use what the catalog pairs with the other label (or the catalog's
    # most common), never an arbitrary alphabetical pick like "ambient"/"angry".
    if not genre:
        genre = labels.default_label("genre", other=mood)
        trace.notes.append(f"no genre evidence; catalog default '{genre}'")
    if not mood:
        mood = labels.default_label("mood", other=genre)
        trace.notes.append(f"no mood evidence; catalog default '{mood}'")

    # 3. Acoustic preference: score-weighted vote of docs that take a side
    acoustic_yes = sum(s for d, s in docs if d.meta.get("acoustic") == "yes")
    acoustic_no = sum(s for d, s in docs if d.meta.get("acoustic") == "no")
    likes_acoustic = acoustic_yes > acoustic_no if (acoustic_yes or acoustic_no) else DEFAULT_LIKES_ACOUSTIC

    # 4. Modifier lexicon
    adjusted_energy = apply_energy_modifiers(energy, mods)
    adjusted_valence = _clamp(valence + mods.valence_shift)
    if mods.matched:
        trace.notes.append(
            f"modifiers {mods.matched}: energy {energy:.2f}->{adjusted_energy:.2f}, "
            f"valence {valence:.2f}->{adjusted_valence:.2f}" + (", diverse" if mods.diverse else "")
        )

    # 5. Ranking mode from the top doc
    mode = "balanced"
    if docs:
        top = docs[0][0]
        if top.doc_id in ENERGY_FOCUSED_DOCS:
            mode = "energy-focused"
        elif top.kind == "mood":
            mode = "mood-first"
    trace.notes.append(f"mode={mode} (top doc {docs[0][0].doc_id if docs else 'none'})")

    prefs = {
        "favorite_genre": genre,
        "favorite_mood": mood,
        "target_energy": round(adjusted_energy, 2),
        "target_valence": round(adjusted_valence, 2),
        "likes_acoustic": bool(likes_acoustic),
        "mode": mode,
        "diverse": mods.diverse,
    }
    return prefs, trace


# --- LLM planning ---

PLAN_SCHEMA_TEXT = """{
  "favorite_genre": string, one of ALLOWED GENRES,
  "favorite_mood":  string, one of ALLOWED MOODS,
  "target_energy":  number 0-1,
  "target_valence": number 0-1,
  "likes_acoustic": boolean,
  "mode":    one of %s (optional),
  "diverse": boolean (optional),
  "rationale": string, at most 300 characters (optional)
}""" % ", ".join(f'"{m}"' for m in SCORING_MODES)


def build_plan_prompt(request: str, docs: List[Tuple], song_hits: List[Tuple], labels: LabelSpace) -> str:
    """Build the structured planning prompt: task, allowed labels, retrieved docs, song hits and the schema."""
    doc_blocks = []
    for doc, score in docs:
        meta = {k: v for k, v in doc.meta.items() if k in ("type", "energy", "valence", "acoustic", "genres", "moods")}
        doc_blocks.append(f"[{doc.doc_id}] (relevance {score:.2f}) {json.dumps(meta)}\n{doc.body[:400]}")
    song_lines = [
        f"- {d.meta['title']} ({d.meta['genre']}, {d.meta['mood']}, energy {d.meta['energy']:.2f}, "
        f"valence {d.meta['valence']:.2f}, acousticness {d.meta['acousticness']:.2f})"
        for d, _ in song_hits
    ]
    return "\n".join([
        "You are the planning step of a music recommender. Convert the listener's request into a",
        "preference profile for a scoring engine. Base the numbers on the ranges in the retrieved",
        "knowledge docs, and adjust them for the exact wording of the request.",
        "",
        f"REQUEST: {request}",
        "",
        "ALLOWED GENRES: " + ", ".join(labels.genres),
        "ALLOWED MOODS: " + ", ".join(labels.moods),
        "",
        "RETRIEVED KNOWLEDGE DOCS:",
        "\n\n".join(doc_blocks) or "(none)",
        "",
        "CLOSEST CATALOG SONGS:",
        "\n".join(song_lines) or "(none)",
        "",
        "Return ONLY a JSON object with this shape:",
        PLAN_SCHEMA_TEXT,
    ])


def plan_llm(llm, request: str, docs: List[Tuple], song_hits: List[Tuple], labels: LabelSpace) -> Optional[Dict]:
    """Ask Gemini for a JSON plan; return the parsed dict, or None on any failure (caller falls back offline)."""
    if llm is None or not llm.available:
        return None
    result = llm.generate_json(build_plan_prompt(request, docs, song_hits, labels), step="plan")
    if not isinstance(result, dict):
        return None
    return result
