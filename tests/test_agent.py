import pytest

from src import agent
from src.agent import EXIT_OK, EXIT_REJECTED, load_resources, main, run_agent
from src.logging_setup import configure, get_run_logger


class FakeLLM:
    """Stands in for GeminiClient; returns canned plan/explanation values."""

    def __init__(self, plan=None, text=None):
        self.available = True
        self.plan = plan
        self.text = text
        self.calls = []

    def generate_json(self, prompt, step="llm"):
        self.calls.append(("json", prompt))
        return self.plan

    def generate_text(self, prompt, step="llm"):
        self.calls.append(("text", prompt))
        return self.text


@pytest.fixture(scope="module")
def res():
    configure(verbose=False)
    return load_resources(get_run_logger("test"))


def titles(result):
    return [song["title"] for song, _, _ in result.final.results]


def test_offline_study_request(res):
    result = run_agent("something chill for studying on a rainy night", res)
    assert result.status == "ok" and result.plan_source == "offline"
    assert {"rainy_day.md", "studying.md"} <= {d.doc_id for d, _ in result.docs}
    assert result.final.prefs["favorite_genre"] == "lofi"
    assert all(song["energy"] < 0.5 for song, _, _ in result.final.results[:3])
    assert result.explanation_source == "template"
    assert "[rainy_day.md" in result.explanation


def test_offline_k_pop_is_repaired(res):
    result = run_agent("k-pop for a party", res)
    assert result.final.prefs["favorite_genre"] == "pop"
    assert any("k-pop" in r for r in result.repairs)


def test_rejections(res):
    assert run_agent("", res).status == "rejected"
    assert run_agent("what's the weather tomorrow", res).status == "rejected"
    assert run_agent("x" * 301, res).status == "rejected"


def test_k_controls_result_count(res):
    assert len(run_agent("hype songs for the gym", res, k=3).final.results) == 3


def test_llm_plan_is_used_and_repaired(res):
    llm = FakeLLM(plan={"favorite_genre": "EDM", "favorite_mood": "hype", "target_energy": 1.4,
                        "target_valence": 0.7, "likes_acoustic": False, "rationale": "gym"})
    result = run_agent("hype songs for the gym", res, llm=llm)
    assert result.plan_source == "llm"
    assert result.final.prefs["favorite_genre"] == "electronic"
    assert result.final.prefs["favorite_mood"] == "energetic"
    assert result.final.prefs["target_energy"] == 1.0
    assert "target_energy 1.4 clamped to 1" in result.repairs
    assert result.rationale == "gym"
    assert "[workout.md]" in llm.calls[0][1]          # retrieved docs are in the prompt


def test_llm_failure_falls_back_to_offline(res):
    # GeminiClient returns None for API errors, timeouts and bad JSON alike
    llm = FakeLLM(plan=None, text=None)
    result = run_agent("hype songs for the gym", res, llm=llm)
    assert result.status == "ok"
    assert result.plan_source == "offline"
    assert result.explanation_source == "template"


def test_grounded_llm_explanation_is_accepted(res):
    offline = run_agent("hype songs for the gym", res)
    top = titles(offline)[0]
    llm = FakeLLM(plan=None, text=f"{top} keeps the energy high for lifting [workout.md].")
    result = run_agent("hype songs for the gym", res, llm=llm)
    assert result.explanation_source == "llm"


def test_hallucinated_explanation_is_replaced(res):
    llm = FakeLLM(plan=None, text="Try Library Rain and Spacewalk Thoughts [workout.md].")
    result = run_agent("hype songs for the gym", res, llm=llm)
    assert result.explanation_source == "template"
    assert "not in the results" in result.explanation_note
    for title in ("Library Rain", "Spacewalk Thoughts"):
        assert title not in result.explanation


def test_self_check_retries_on_contradiction(res):
    # A "calm" request planned as loud metal should be flagged and revised
    llm = FakeLLM(plan={"favorite_genre": "metal", "favorite_mood": "angry", "target_energy": 0.95,
                        "target_valence": 0.2, "likes_acoustic": False, "mode": "genre-first"})
    result = run_agent("calm music for sleep", res, llm=llm)
    assert len(result.attempts) == 3
    assert result.attempts[0].issues[0].kind == "energy"
    assert "energy-focused" in result.attempts[1].change
    assert "swapped" in result.attempts[2].change
    assert result.caveats                              # leftover issue is surfaced to the user


def test_vague_request_gets_catalog_defaults_and_a_caveat(res):
    result = run_agent("play me some songs", res)
    assert result.docs == []
    assert result.caveats and "general picks" in result.caveats[0]
    # Before the fix this fell back to the alphabetically first labels ("ambient" / "angry")
    assert result.final.prefs["favorite_mood"] != "angry"
    assert "general picks" in result.explanation


def test_explicit_energy_limit_is_flagged_when_catalog_cannot_honor_it(res):
    result = run_agent("sad songs but not too slow", res)
    assert result.attempts[0].issues[0].kind == "energy_constraint"
    assert len(result.attempts) > 1
    assert any("energy you asked for" in c for c in result.caveats)


def test_mix_request_turns_on_diversity(res):
    result = run_agent("give me a mix of party songs", res)
    assert result.final.prefs["diverse"] is True
    artists = [song["artist"] for song, _, _ in result.final.results]
    assert len(set(artists)) == len(artists)


def test_agent_works_without_knowledge_base(res, monkeypatch, tmp_path):
    monkeypatch.setattr(agent.config, "KNOWLEDGE_DIR", tmp_path / "missing")
    bare = load_resources(get_run_logger("test-nokb"))
    assert bare.kb_docs == []
    result = run_agent("hype songs for the gym", bare)
    assert result.status == "ok" and result.final.results
    assert result.caveats


def test_cli_clamps_k(capsys):
    assert main(["hype songs for the gym", "--offline", "--k", "99"]) == EXIT_OK
    assert "Top 20 recommendations" in capsys.readouterr().out
    assert main(["hype songs for the gym", "--offline", "--k", "0"]) == EXIT_OK
    assert "Top 1 recommendations" in capsys.readouterr().out


def test_cli_exit_codes_and_ascii_output(capsys):
    assert main(["", "--offline"]) == EXIT_REJECTED
    assert main(["hype songs for the gym", "--offline", "--table"]) == EXIT_OK
    printed = capsys.readouterr().out
    printed.encode("ascii")                           # raises if any non-ASCII slipped through
    assert "Gym Hero" in printed


def test_cli_never_crashes(monkeypatch, capsys):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent, "load_resources", explode)
    assert main(["hype songs", "--offline"]) == 1
    assert "Something went wrong" in capsys.readouterr().out
