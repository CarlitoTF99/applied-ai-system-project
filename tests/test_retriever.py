from src.config import KNOWLEDGE_DIR, SONGS_CSV
from src.recommender import load_songs
from src.retriever import BM25Index, Doc, load_knowledge, parse_front_matter, song_to_doc, tokenize


def kb_index():
    return BM25Index(load_knowledge(KNOWLEDGE_DIR))


def test_tokenize_keeps_joined_words_and_their_parts():
    tokens = tokenize("Some K-Pop and R&B, hip-hop!")
    assert "k-pop" in tokens and "pop" in tokens
    assert "r&b" in tokens
    assert "hip-hop" in tokens and "hop" in tokens
    assert "some" not in tokens and "and" not in tokens


def test_front_matter_parses_lists_ranges_and_aliases():
    meta, body = parse_front_matter(
        "---\ntype: mood\nenergy: 0.20-0.45\ngenres: lofi, jazz\naliases: calm=chill\n---\nBody text"
    )
    assert meta["type"] == "mood"
    assert meta["energy"] == (0.20, 0.45)
    assert meta["genres"] == ["lofi", "jazz"]
    assert meta["aliases"] == {"calm": "chill"}
    assert body == "Body text"


def test_knowledge_base_has_8_to_12_docs():
    assert 8 <= len(load_knowledge(KNOWLEDGE_DIR)) <= 12


def test_knowledge_labels_exist_in_catalog():
    songs = load_songs(str(SONGS_CSV))
    genres = {s["genre"] for s in songs}
    moods = {s["mood"] for s in songs}
    for doc in load_knowledge(KNOWLEDGE_DIR):
        assert set(doc.meta.get("genres", [])) <= genres, doc.doc_id
        assert set(doc.meta.get("moods", [])) <= moods, doc.doc_id
        for alias_target in doc.meta.get("aliases", {}).values():
            assert alias_target in genres | moods, (doc.doc_id, alias_target)


def test_context_requests_rank_the_matching_doc_first():
    index = kb_index()
    assert index.search("hype songs for the gym", 3)[0][0].doc_id == "workout.md"
    assert index.search("music to help me study for an exam", 3)[0][0].doc_id == "studying.md"
    assert index.search("songs for a road trip", 3)[0][0].doc_id == "road_trip.md"


def test_results_sorted_and_positive():
    results = kb_index().search("chill rainy night studying", 5)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    assert all(score > 0 for score in scores)


def test_empty_or_stopword_query_returns_nothing():
    index = kb_index()
    assert index.search("", 3) == []
    assert index.search("the and of", 3) == []


def test_song_index_finds_rainy_songs():
    songs = load_songs(str(SONGS_CSV))
    index = BM25Index([song_to_doc(s) for s in songs])
    titles = [doc.meta["title"] for doc, _ in index.search("rainy", 5)]
    assert "Library Rain" in titles and "Rust in the Rain" in titles


def test_missing_directory_and_empty_index():
    assert load_knowledge("does/not/exist") == []
    assert BM25Index([]).search("anything", 3) == []
    assert BM25Index([Doc("x", "context", "lofi")]).search("lofi", 0) == []
