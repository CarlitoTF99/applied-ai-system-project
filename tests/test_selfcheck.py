"""Self-check step: issue detection, targeted revisions and best-attempt choice."""

import pytest

from src.config import KNOWLEDGE_DIR, SONGS_CSV
from src.labels import LabelSpace
from src.planner import PlanTrace
from src.recommender import load_songs
from src.retriever import load_knowledge
from src.selfcheck import Attempt, Issue, caveat_for, evaluate_results, pick_best, revise_prefs

PREFS = {"favorite_genre": "blues", "favorite_mood": "sad", "target_energy": 0.5,
         "target_valence": 0.25, "likes_acoustic": True, "mode": "mood-first", "diverse": False}


def song(title, genre, mood, energy, valence=0.3):
    return {"title": title, "genre": genre, "mood": mood, "energy": energy, "valence": valence}


def results(*songs, score=7.0):
    return [(s, score, "") for s in songs]


SLOW_SAD = results(song("A", "blues", "sad", 0.33), song("B", "electronic", "melancholy", 0.30),
                   song("C", "synthwave", "moody", 0.75))


def labels():
    return LabelSpace.build(load_songs(str(SONGS_CSV)), load_knowledge(KNOWLEDGE_DIR))


def kinds(issues):
    return [i.kind for i in issues]


def test_explicit_energy_floor_is_checked_on_the_first_song():
    # Top-3 mean (0.46) is inside the soft range tolerance, but the #1 song breaks "not too slow"
    expected = {"source": "mood_low.md", "energy": (0.5, 0.55), "valence": (0.0, 0.4), "energy_floor": 0.5}
    issues = evaluate_results(PREFS, SLOW_SAD, 8.5, expected)
    assert kinds(issues) == ["energy_constraint"]
    assert issues[0].severity == pytest.approx(0.17)


def test_energy_ceiling_and_slack():
    loud = results(song("L", "blues", "sad", 0.91))
    assert kinds(evaluate_results(PREFS, loud, 8.5, {"energy_ceiling": 0.6})) == ["energy_constraint"]
    near = results(song("N", "blues", "sad", 0.64))          # within the 0.05 slack
    assert "energy_constraint" not in kinds(evaluate_results(PREFS, near, 8.5, {"energy_ceiling": 0.6}))


def test_explicitly_named_label_must_be_in_top3_even_if_other_label_matches():
    # Mood matches (so the generic label check passes) but the genre the user named is absent
    prefs = {**PREFS, "favorite_genre": "rock", "favorite_mood": "happy"}
    happy = results(song("H", "reggae", "happy", 0.55))
    issues = evaluate_results(prefs, happy, 8.5, {"explicit_genre": "rock"})
    assert kinds(issues) == ["explicit_miss"]
    related = results(song("M", "metal", "angry", 0.9))      # related genre counts
    assert evaluate_results(prefs, related, 8.5, {"explicit_genre": "rock"}) == []


def test_low_confidence_and_label_miss():
    weak = results(song("W", "pop", "happy", 0.4), score=3.0)   # pop is unrelated to blues, happy not in sad's family
    assert set(kinds(evaluate_results(PREFS, weak, 8.5, {}))) == {"low_confidence", "label_miss"}


def test_revision_moves_target_inside_violated_floor():
    issues = [Issue("energy_constraint", "x", 0.17)]
    revised, change = revise_prefs(PREFS, issues, 2, {"energy_floor": 0.5}, PlanTrace(), labels())
    assert revised["target_energy"] == 0.6
    assert revised["mode"] == "energy-focused"
    assert "requested limit" in change


def test_revision_for_missing_named_genre_switches_to_genre_first():
    issues = [Issue("explicit_miss", "requested genre 'rock' not in top-3", 0.5)]
    revised, _ = revise_prefs(PREFS, issues, 2, {}, PlanTrace(explicit_genre="rock"), labels())
    assert revised["mode"] == "genre-first"


def test_swap_never_replaces_labels_the_user_named():
    trace = PlanTrace(explicit_genre="blues", explicit_mood="sad",
                      genre_votes=[("blues", 5), ("folk", 3)], mood_votes=[("sad", 5), ("hopeful", 2)])
    revised, why = revise_prefs(PREFS, [Issue("valence", "x", 0.2)], 3, {}, trace, labels())
    assert revised is None and "named by the user" in why


def test_pick_best_prefers_fewer_issues_then_smaller_violation_then_earliest():
    def attempt(number, issues, top_score):
        return Attempt(number, PREFS, results(song("S", "blues", "sad", 0.3), score=top_score), 8.5, issues)

    a1 = attempt(1, [Issue("valence", "x", 0.10)], 7.0)
    a3 = attempt(3, [Issue("valence", "x", 0.10)], 8.4)      # higher ratio, same issues and severity
    assert pick_best([a1, a3]) is a1                          # ratio is NOT a tie-breaker
    a2 = attempt(2, [Issue("valence", "x", 0.05)], 6.0)
    assert pick_best([a1, a2, a3]) is a2                      # smaller violation wins
    a4 = attempt(4, [], 5.0)
    assert pick_best([a1, a2, a3, a4]) is a4                  # no issues beats everything


def test_every_issue_kind_has_a_caveat():
    for kind in ("low_confidence", "energy", "valence", "energy_constraint", "explicit_miss", "label_miss"):
        assert caveat_for(Issue(kind, "x"))
