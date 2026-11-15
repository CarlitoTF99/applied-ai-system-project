"""Step f (Self-check): judge a result list against the request and propose one targeted revision."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.config import MIN_SCORE_RATIO, RANGE_TOLERANCE
from src.recommender import MOOD_FAMILIES, RELATED_GENRES

TOP_N = 3                    # how many top results the checks look at
NUDGE = 0.5                  # move a target this fraction of the way to the expected range midpoint


@dataclass
class Issue:
    kind: str                # "low_confidence" | "energy" | "valence" | "label_miss"
    detail: str


@dataclass
class Attempt:
    number: int
    prefs: Dict
    results: List[Tuple[Dict, float, str]]
    best: float
    issues: List[Issue] = field(default_factory=list)
    change: str = "initial plan"

    @property
    def top_score(self) -> float:
        return self.results[0][1] if self.results else 0.0

    @property
    def ratio(self) -> float:
        return self.top_score / self.best if self.best else 0.0


def _genre_hit(song_genre: str, wanted: str) -> bool:
    return song_genre == wanted or frozenset((song_genre, wanted)) in RELATED_GENRES


def _mood_hit(song_mood: str, wanted: str) -> bool:
    if song_mood == wanted:
        return True
    return any(song_mood in moods and wanted in moods for moods in MOOD_FAMILIES.values())


def evaluate_results(prefs: Dict, results: List, best: float, expected: Dict) -> List[Issue]:
    """Return the problems with this result list; an empty list means it passes."""
    if not results:
        return [Issue("low_confidence", "no results")]
    issues = []
    top_score = results[0][1]
    ratio = top_score / best if best else 0.0
    if ratio < MIN_SCORE_RATIO:
        issues.append(Issue("low_confidence", f"top score {top_score:.2f}/{best:g} = {ratio:.2f} < {MIN_SCORE_RATIO}"))

    top = [song for song, _, _ in results[:TOP_N]]
    for feature in ("energy", "valence"):
        if feature not in expected:
            continue
        low, high = expected[feature]
        mean = sum(song[feature] for song in top) / len(top)
        if mean < low - RANGE_TOLERANCE or mean > high + RANGE_TOLERANCE:
            issues.append(Issue(
                feature,
                f"top-{len(top)} mean {feature} {mean:.2f} outside {expected['source']} range "
                f"{low:.2f}-{high:.2f} (+/-{RANGE_TOLERANCE})",
            ))

    genre_ok = any(_genre_hit(song["genre"], prefs["favorite_genre"]) for song in top)
    mood_ok = any(_mood_hit(song["mood"], prefs["favorite_mood"]) for song in top)
    if not genre_ok and not mood_ok:
        issues.append(Issue(
            "label_miss",
            f"no top-{len(top)} song matches genre '{prefs['favorite_genre']}' or mood '{prefs['favorite_mood']}'",
        ))
    return issues


def _next_label(votes: List[Tuple[str, float]], current: str, valid: List[str]) -> Optional[str]:
    for label, _ in votes:
        if label != current and label in valid:
            return label
    return None


def revise_prefs(
    prefs: Dict,
    issues: List[Issue],
    next_number: int,
    expected: Dict,
    trace,
    labels,
) -> Tuple[Optional[Dict], str]:
    """Make one targeted change for attempt next_number; return (new prefs, description) or (None, why not)."""
    kinds = {issue.kind for issue in issues}
    revised = dict(prefs)

    if next_number == 2 and kinds & {"energy", "valence"}:
        changes = []
        for feature in ("energy", "valence"):
            if feature in kinds and feature in expected:
                key = f"target_{feature}"
                low, high = expected[feature]
                midpoint = (low + high) / 2
                revised[key] = round(prefs[key] + NUDGE * (midpoint - prefs[key]), 2)
                changes.append(f"{key} {prefs[key]:.2f}->{revised[key]:.2f}")
        revised["mode"] = "energy-focused"
        changes.append(f"mode {prefs['mode']}->energy-focused")
        description = "nudged toward expected range: " + ", ".join(changes)
    elif next_number == 2 and "label_miss" in kinds:
        new_mode = "genre-first" if trace.explicit_genre and not trace.explicit_mood else "mood-first"
        revised["mode"] = new_mode
        description = f"label miss: mode {prefs['mode']}->{new_mode}"
    else:
        # Swap a label the user did not name for the next-best vote from the offline tally
        swapped = None
        if not trace.explicit_genre:
            alt = _next_label(trace.genre_votes, prefs["favorite_genre"], labels.genres)
            if alt:
                revised["favorite_genre"] = alt
                swapped = f"favorite_genre {prefs['favorite_genre']}->{alt}"
        if swapped is None and not trace.explicit_mood:
            alt = _next_label(trace.mood_votes, prefs["favorite_mood"], labels.moods)
            if alt:
                revised["favorite_mood"] = alt
                swapped = f"favorite_mood {prefs['favorite_mood']}->{alt}"
        if swapped is None:
            return None, "no alternative label to try (labels were named by the user or no other votes)"
        description = "swapped to next-best vote: " + swapped

    if revised == prefs:
        return None, "revision would not change the profile"
    return revised, description


def pick_best(attempts: List[Attempt]) -> Attempt:
    """Fewest issues wins; ties go to the higher normalized top score, then the earlier attempt."""
    return min(attempts, key=lambda a: (len(a.issues), -a.ratio, a.number))


def caveat_for(issue: Issue) -> str:
    """Turn a leftover issue into a short note for the user."""
    if issue.kind == "low_confidence":
        return "No song matches this request closely; these are the nearest options."
    if issue.kind == "energy":
        return "The catalog has few songs at the energy level this request suggests."
    if issue.kind == "valence":
        return "The catalog has few songs with the brightness/darkness this request suggests."
    return "None of the top songs match the requested genre or mood exactly."
