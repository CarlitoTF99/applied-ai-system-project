"""Step f (Self-check): judge a result list against the request and propose one targeted revision."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.config import MIN_SCORE_RATIO, RANGE_TOLERANCE
from src.recommender import MOOD_FAMILIES, RELATED_GENRES

TOP_N = 3                    # how many top results the checks look at
NUDGE = 0.5                  # move a target this fraction of the way to the expected range midpoint
CONSTRAINT_SLACK = 0.05      # the #1 song may miss an explicit energy floor/ceiling by this much
CONSTRAINT_MARGIN = 0.1      # a revision moves the target this far inside the violated floor/ceiling
LABEL_MISS_SEVERITY = 0.5


@dataclass
class Issue:
    kind: str                # low_confidence | energy | valence | energy_constraint | explicit_miss | label_miss
    detail: str
    severity: float = 0.0    # how far off; only used to rank attempts with the same number of issues


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

    @property
    def severity(self) -> float:
        return round(sum(issue.severity for issue in self.issues), 3)


def _genre_hit(song_genre: str, wanted: str) -> bool:
    return song_genre == wanted or frozenset((song_genre, wanted)) in RELATED_GENRES


def _mood_hit(song_mood: str, wanted: str) -> bool:
    if song_mood == wanted:
        return True
    return any(song_mood in moods and wanted in moods for moods in MOOD_FAMILIES.values())


def evaluate_results(prefs: Dict, results: List, best: float, expected: Dict) -> List[Issue]:
    """Return the problems with this result list; an empty list means it passes.

    expected holds soft doc-derived ranges ("energy", "valence", checked on the top-3 mean with a tolerance)
    and hard user constraints ("energy_floor", "energy_ceiling" from wording like "not too slow", checked on
    the #1 song, because the first recommendation should honor what the user explicitly said).
    """
    if not results:
        return [Issue("low_confidence", "no results", 1.0)]
    issues = []
    top_score = results[0][1]
    ratio = top_score / best if best else 0.0
    if ratio < MIN_SCORE_RATIO:
        issues.append(Issue("low_confidence", f"top score {top_score:.2f}/{best:g} = {ratio:.2f} < {MIN_SCORE_RATIO}",
                            MIN_SCORE_RATIO - ratio))

    top = [song for song, _, _ in results[:TOP_N]]
    for feature in ("energy", "valence"):
        if feature not in expected:
            continue
        low, high = expected[feature]
        mean = sum(song[feature] for song in top) / len(top)
        if mean < low - RANGE_TOLERANCE or mean > high + RANGE_TOLERANCE:
            distance = low - mean if mean < low else mean - high
            issues.append(Issue(
                feature,
                f"top-{len(top)} mean {feature} {mean:.2f} outside {expected['source']} range "
                f"{low:.2f}-{high:.2f} (+/-{RANGE_TOLERANCE})",
                distance,
            ))

    first = top[0]
    floor, ceiling = expected.get("energy_floor"), expected.get("energy_ceiling")
    if floor is not None and first["energy"] < floor - CONSTRAINT_SLACK:
        issues.append(Issue("energy_constraint",
                            f"#1 {first['title']} energy {first['energy']:.2f} below requested floor {floor:.2f}",
                            floor - first["energy"]))
    if ceiling is not None and first["energy"] > ceiling + CONSTRAINT_SLACK:
        issues.append(Issue("energy_constraint",
                            f"#1 {first['title']} energy {first['energy']:.2f} above requested ceiling {ceiling:.2f}",
                            first["energy"] - ceiling))

    # A genre/mood the user named must show up (exactly or related/same family) in the top 3
    for key, kind, hit in (("explicit_genre", "genre", _genre_hit), ("explicit_mood", "mood", _mood_hit)):
        wanted = expected.get(key)
        if wanted and not any(hit(song[kind], wanted) for song in top):
            issues.append(Issue("explicit_miss", f"requested {kind} '{wanted}' not in top-{len(top)}",
                                LABEL_MISS_SEVERITY))

    genre_ok = any(_genre_hit(song["genre"], prefs["favorite_genre"]) for song in top)
    mood_ok = any(_mood_hit(song["mood"], prefs["favorite_mood"]) for song in top)
    if not genre_ok and not mood_ok:
        issues.append(Issue(
            "label_miss",
            f"no top-{len(top)} song matches genre '{prefs['favorite_genre']}' or mood '{prefs['favorite_mood']}'",
            LABEL_MISS_SEVERITY,
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

    if next_number == 2 and kinds & {"energy", "valence", "energy_constraint"}:
        changes = []
        if "energy_constraint" in kinds:
            target = prefs["target_energy"]
            if expected.get("energy_floor") is not None:
                target = max(target, expected["energy_floor"] + CONSTRAINT_MARGIN)
            if expected.get("energy_ceiling") is not None:
                target = min(target, expected["energy_ceiling"] - CONSTRAINT_MARGIN)
            revised["target_energy"] = round(max(0.0, min(1.0, target)), 2)
            if revised["target_energy"] != prefs["target_energy"]:
                changes.append(f"target_energy {prefs['target_energy']:.2f}->{revised['target_energy']:.2f} (requested limit)")
        for feature in ("energy", "valence"):
            key = f"target_{feature}"
            if feature in kinds and feature in expected and revised[key] == prefs[key]:
                low, high = expected[feature]
                midpoint = (low + high) / 2
                revised[key] = round(prefs[key] + NUDGE * (midpoint - prefs[key]), 2)
                changes.append(f"{key} {prefs[key]:.2f}->{revised[key]:.2f}")
        revised["mode"] = "energy-focused"
        changes.append(f"mode {prefs['mode']}->energy-focused")
        description = "nudged toward expected energy/valence: " + ", ".join(changes)
    elif next_number == 2 and kinds & {"label_miss", "explicit_miss"}:
        missed = " ".join(i.detail for i in issues if i.kind == "explicit_miss")
        if "requested genre" in missed:
            new_mode = "genre-first"
        elif "requested mood" in missed:
            new_mode = "mood-first"
        else:
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
    """Fewest issues wins; then the smallest total violation; then the EARLIEST attempt.

    The score ratio is deliberately not a tie-breaker: a revision that swapped labels can score higher
    against its own (less faithful) profile while fixing nothing, so it only wins if it reduces the issues.
    """
    return min(attempts, key=lambda a: (len(a.issues), a.severity, a.number))


def caveat_for(issue: Issue) -> str:
    """Turn a leftover issue into a short note for the user."""
    if issue.kind == "low_confidence":
        return "No song matches this request closely; these are the nearest options."
    if issue.kind == "energy":
        return "The catalog has few songs at the energy level this request suggests."
    if issue.kind == "valence":
        return "The catalog has few songs with the brightness/darkness this request suggests."
    if issue.kind == "energy_constraint":
        return "No song in the catalog fits both the style and the energy you asked for; the closest matches are shown."
    if issue.kind == "explicit_miss":
        return "The catalog has no close match for the genre or mood you named together with the rest of the request."
    return "None of the top songs match the requested genre or mood exactly."
