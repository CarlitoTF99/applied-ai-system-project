import pytest

from src.config import KNOWLEDGE_DIR, SONGS_CSV
from src.labels import LabelSpace
from src.planner import build_plan_prompt, expected_ranges, parse_modifiers, plan_offline
from src.recommender import load_songs
from src.retriever import BM25Index, load_knowledge, song_to_doc


@pytest.fixture(scope="module")
def setup():
    songs = load_songs(str(SONGS_CSV))
    kb = load_knowledge(KNOWLEDGE_DIR)
    return {
        "labels": LabelSpace.build(songs, kb),
        "kb_index": BM25Index(kb),
        "song_index": BM25Index([song_to_doc(s) for s in songs]),
    }


def plan(setup, request):
    mods = parse_modifiers(request)
    docs = setup["kb_index"].search(mods.retrieval_query, 3)
    hits = setup["song_index"].search(mods.retrieval_query, 5)
    prefs, trace = plan_offline(request, docs, hits, setup["labels"], mods)
    return prefs, trace, docs, mods


def test_study_request_is_quiet_acoustic_lofi(setup):
    prefs, _, _, _ = plan(setup, "something chill for studying on a rainy night")
    assert prefs["favorite_genre"] == "lofi"
    assert prefs["favorite_mood"] == "chill"
    assert prefs["target_energy"] < 0.5
    assert prefs["likes_acoustic"] is True


def test_gym_request_is_high_energy_and_keeps_raw_mood_word(setup):
    prefs, trace, _, _ = plan(setup, "hype songs for the gym")
    assert prefs["target_energy"] >= 0.8
    assert prefs["likes_acoustic"] is False
    assert prefs["mode"] == "energy-focused"
    assert prefs["favorite_mood"] == "hype"   # left for the validator to map
    assert trace.explicit_mood == "hype"


def test_not_too_slow_sets_an_energy_floor_and_is_not_retrieved_as_slow(setup):
    prefs, _, docs, mods = plan(setup, "sad songs but not too slow")
    assert mods.energy_floor == 0.5
    assert "slow" not in mods.retrieval_query
    assert prefs["target_energy"] >= 0.5
    assert prefs["favorite_mood"] == "sad"
    assert docs[0][0].doc_id == "mood_low.md"


def test_k_pop_is_passed_through_raw(setup):
    prefs, _, _, _ = plan(setup, "k-pop for a party")
    assert prefs["favorite_genre"] == "k-pop"
    assert prefs["target_energy"] > 0.7


def test_plan_without_docs_uses_defaults(setup):
    prefs, _ = plan_offline("music", [], [], setup["labels"])
    assert 0 <= prefs["target_energy"] <= 1
    assert prefs["favorite_genre"] in setup["labels"].genres
    assert prefs["mode"] == "balanced"


def test_modifiers():
    assert parse_modifiers("mellow songs").energy_shift == pytest.approx(-0.15)
    assert parse_modifiers("not too loud please").energy_ceiling == 0.6
    assert parse_modifiers("give me a mix").diverse is True
    assert parse_modifiers("happy tunes").valence_shift == pytest.approx(0.15)


def test_expected_ranges_apply_floor(setup):
    _, _, docs, mods = plan(setup, "sad songs but not too slow")
    ranges = expected_ranges(docs, mods)
    assert ranges["source"] == "mood_low.md"
    assert ranges["energy"][0] >= 0.5


def test_prompt_contains_docs_labels_and_schema(setup):
    mods = parse_modifiers("hype songs for the gym")
    docs = setup["kb_index"].search(mods.retrieval_query, 3)
    prompt = build_plan_prompt("hype songs for the gym", docs, [], setup["labels"])
    assert "[workout.md]" in prompt
    assert "ALLOWED GENRES:" in prompt and "hip-hop" in prompt
    assert "Return ONLY a JSON object" in prompt
