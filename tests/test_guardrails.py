import pytest

from src.config import KNOWLEDGE_DIR, SONGS_CSV
from src.guardrails import (
    MSG_EMPTY, MSG_OFF_TOPIC, MSG_TOO_LONG,
    build_music_vocabulary, check_explanation, check_input, validate_prefs,
)
from src.labels import LabelSpace
from src.recommender import load_songs
from src.retriever import BM25Index, load_knowledge, song_to_doc

FALLBACK = {
    "favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.4,
    "target_valence": 0.6, "likes_acoustic": True, "mode": "balanced", "diverse": False,
}


@pytest.fixture(scope="module")
def ctx():
    songs = load_songs(str(SONGS_CSV))
    kb = load_knowledge(KNOWLEDGE_DIR)
    kb_index = BM25Index(kb)
    return {
        "songs": songs,
        "labels": LabelSpace.build(songs, kb),
        "kb_index": kb_index,
        "song_index": BM25Index([song_to_doc(s) for s in songs]),
        "vocab": build_music_vocabulary(kb, songs),
        "kb_docs": kb_index.search("party", 3),
    }


def validate(ctx, raw, request="request"):
    return validate_prefs(raw, FALLBACK, ctx["labels"], ctx["song_index"], ctx["kb_docs"], request)


# --- input guardrail ---

@pytest.mark.parametrize("raw", ["", "   ", None, "\n\t"])
def test_rejects_empty(ctx, raw):
    result = check_input(raw, ctx["vocab"], ctx["kb_index"])
    assert not result.ok and result.rule == "empty" and result.message == MSG_EMPTY


def test_rejects_too_long(ctx):
    result = check_input("chill " * 60, ctx["vocab"], ctx["kb_index"])
    assert not result.ok and result.rule == "too_long" and result.message == MSG_TOO_LONG


@pytest.mark.parametrize("raw", ["what's the weather tomorrow", "solve 2x + 3 = 7", "who won the election"])
def test_rejects_off_topic(ctx, raw):
    result = check_input(raw, ctx["vocab"], ctx["kb_index"])
    assert not result.ok and result.rule == "off_topic" and result.message == MSG_OFF_TOPIC


@pytest.mark.parametrize("raw", [
    "something chill for studying on a rainy night",
    "hype songs for the gym",
    "k-pop for a party",
    "rainy sunday",
])
def test_accepts_music_requests(ctx, raw):
    assert check_input(raw, ctx["vocab"], ctx["kb_index"]).ok


def test_strips_control_characters(ctx):
    result = check_input("chill\x00 songs\x07", ctx["vocab"], ctx["kb_index"])
    assert result.ok and result.request == "chill songs" and result.stripped_control


# --- validate / repair ---

def test_valid_plan_needs_no_repairs(ctx):
    prefs, repairs, _ = validate(ctx, dict(FALLBACK))
    assert repairs == []
    assert prefs == FALLBACK


def test_k_pop_maps_to_pop_and_calm_maps_to_chill(ctx):
    prefs, repairs, _ = validate(ctx, {**FALLBACK, "favorite_genre": "k-pop", "favorite_mood": "calm"})
    assert prefs["favorite_genre"] == "pop"
    assert prefs["favorite_mood"] == "chill"
    assert any("k-pop" in r and "alias" in r for r in repairs)
    assert any("calm" in r for r in repairs)


def test_spelling_and_alias_variants(ctx):
    prefs, _, _ = validate(ctx, {**FALLBACK, "favorite_genre": "Hip Hop", "favorite_mood": "Hype"})
    assert prefs["favorite_genre"] == "hip-hop"
    assert prefs["favorite_mood"] == "energetic"
    prefs, _, _ = validate(ctx, {**FALLBACK, "favorite_genre": "R & B"})
    assert prefs["favorite_genre"] == "r&b"


def test_unknown_label_mapped_by_retrieval(ctx):
    prefs, repairs, _ = validate(ctx, {**FALLBACK, "favorite_genre": "zydeco"}, request="rainy blues night")
    assert prefs["favorite_genre"] in ctx["labels"].genres
    assert any("zydeco" in r for r in repairs)


def test_clamps_casts_and_coerces(ctx):
    raw = {**FALLBACK, "target_energy": 1.7, "target_valence": "0.3", "likes_acoustic": "yes",
           "mode": "turbo", "diverse": "sure", "tempo": 120, "rationale": "because"}
    prefs, repairs, rationale = validate(ctx, raw)
    assert prefs["target_energy"] == 1.0
    assert prefs["target_valence"] == 0.3
    assert prefs["likes_acoustic"] is True
    assert prefs["mode"] == "balanced"
    assert prefs["diverse"] is False
    assert "tempo" not in prefs and "rationale" not in prefs
    assert rationale == "because"
    assert len(repairs) == 6


def test_missing_keys_and_garbage_filled_from_fallback(ctx):
    prefs, repairs, _ = validate(ctx, {"favorite_genre": "rock", "target_energy": "loud"})
    assert prefs["target_energy"] == FALLBACK["target_energy"]
    assert prefs["favorite_mood"] == "chill"
    assert len(repairs) >= 4
    prefs, repairs, _ = validate(ctx, ["not", "a", "dict"])
    assert prefs["favorite_genre"] == "lofi" and repairs


# --- output guardrail ---

TITLES = ["Library Rain", "Focus Flow", "Gym Hero", "Storm Runner"]


def test_explanation_ok():
    ok, _ = check_explanation("Library Rain fits a rainy study session [studying.md].",
                              ["Library Rain", "Focus Flow"], TITLES, ["studying.md"])
    assert ok


@pytest.mark.parametrize("text, reason", [
    ("Try Gym Hero [studying.md].", "not in the results"),
    ("These songs are great [studying.md].", "none of the recommended"),
    ("Library Rain is great.", "cites no knowledge doc"),
    ("Library Rain is great [workout.md].", "not retrieved"),
    ("", "empty"),
    ("Library Rain [studying.md] " + "x" * 1000, "too long"),
])
def test_explanation_rejections(text, reason):
    ok, why = check_explanation(text, ["Library Rain", "Focus Flow"], TITLES, ["studying.md"])
    assert not ok and reason in why
