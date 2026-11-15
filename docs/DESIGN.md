# VibeMatch Agent — Design

VibeMatch turns a natural-language request ("something chill for studying on a
rainy night") into song recommendations. Retrieval and an agentic loop sit in
front of the **existing, unchanged** `score_song` / `recommend_songs` engine in
`src/recommender.py`.

---

## 1. File / module layout

```
src/
  recommender.py      UNCHANGED  scoring engine (score_song, recommend_songs, max_score, MOOD_FAMILIES…)
  main.py             UNCHANGED  `python -m src.main` keeps working
  agent.py            NEW  CLI entry point + run_agent() orchestrator (steps a–g)
  retriever.py        NEW  doc loading, tokenizer, pure-Python BM25 index
  planner.py          NEW  plan_offline() + plan_llm() → raw user_prefs dict
  guardrails.py       NEW  check_input(), validate_prefs(), check_explanation()
  selfcheck.py        NEW  evaluate_results() + revise_prefs()
  explainer.py        NEW  explain_llm() + explain_template()
  llm.py              NEW  thin Gemini wrapper: timeout, JSON mode, never raises
  config.py           NEW  load .env (python-dotenv), constants/thresholds
  logging_setup.py    NEW  file + optional console handlers
knowledge/            NEW  10 markdown docs (see §2)
logs/agent.log        NEW  created at runtime (logs/ is git-ignored)
tests/
  test_recommender.py UNCHANGED
  test_retriever.py   NEW  ranking sanity, empty query, scores sorted
  test_guardrails.py  NEW  input rejects, clamping, k-pop→pop, calm→chill
  test_planner.py     NEW  offline plans for canned requests
  test_agent.py       NEW  offline end-to-end, LLM failure → fallback (mocked)
.env.example          NEW  GEMINI_API_KEY=  /  GEMINI_MODEL=gemini-2.5-flash
.gitignore            EDIT add .env, logs/
requirements.txt      EDIT add python-dotenv, google-genai
```

`google-genai` is imported lazily inside `llm.py`. If the import fails or no key
is set, the agent runs in offline mode, so the offline path has no new
dependencies beyond `python-dotenv`.

---

## 2. Knowledge base (RAG corpus)

**10 markdown docs** in `knowledge/`. Each one starts with a small front-matter
block (parsed with plain string splitting, no YAML dependency) followed by 3–6
sentences of prose that the retriever indexes:

```markdown
---
type: context
energy: 0.20-0.45
valence: 0.45-0.70
acoustic: yes            # yes | no | any
genres: lofi, ambient, jazz, classical
moods: focused, chill, relaxed
keywords: study, homework, focus, concentrate, reading, exam
---
Studying music stays in the background: steady, low energy, few vocals…
```

| Doc | type |
|---|---|
| `studying.md`, `workout.md`, `rainy_day.md`, `party.md`, `sleep.md`, `road_trip.md` | context |
| `mood_calm.md`, `mood_bright.md`, `mood_driven.md`, `mood_low.md` (aligned with `MOOD_FAMILIES`, `turbulent` folded into driven/low) | mood |
| `genre_notes.md` (a short paragraph per catalog genre plus aliases such as "k-pop → pop", "hip hop → hip-hop", "edm → electronic") | genre |

Every `genres:` / `moods:` value in front matter **must** be a label that exists
in `songs.csv`. A test enforces this.

**Song catalog as documents.** Each CSV row also becomes a doc,
`song:<id>`, with text like
`"Library Rain Paper Lanterns lofi chill rainy cozy dreamy low-energy acoustic instrumental"`.
Numeric features become words using fixed bins (energy <0.4 low, 0.4–0.7 mid,
>0.7 high, plus the same bins for valence and acousticness).

**Retriever (`retriever.py`).** BM25 (k1=1.5, b=0.75) in roughly 60 lines of
pure Python. The tokenizer lowercases, splits on non-alphanumerics, keeps `-`
and `&` inside tokens (`hip-hop`, `r&b`) and drops a small stopword list. There
are two indexes:

- `kb_index` holds the knowledge docs. `retrieve(query, k)` returns `[(doc, score)]`.
- `song_index` holds the song docs. It supplies evidence for the planner and the label mapper.

Both return results sorted by descending score and drop zero-score hits.

---

## 3. Agent steps (input → output)

All steps share a `RunState` dataclass:
`request, run_id, docs, song_hits, prefs, repairs, attempts, results, explanation, mode_used ("llm"|"offline")`.

| Step | Input | Output | Notes |
|---|---|---|---|
| **a. Input guardrail** `check_input` | raw string | `ok` or `Rejection(message)` | rules in §5 |
| **b. Retrieve** | request, `k` | `docs` (top-k KB docs + scores), `song_hits` (top-5 songs + scores) | |
| **c. Plan** | request, `docs`, `song_hits` | raw prefs dict (untrusted) | LLM or offline, see below |
| **d. Validate** | raw prefs, `docs` | clean prefs + `repairs: list[str]` | rules in §5 |
| **e. Act** | clean prefs, `--k` | `recommend_songs(prefs, songs, k, mode, diverse)` | engine called as-is |
| **f. Self-check** | prefs, results, `docs` | `pass` or a revised prefs dict (back to **d**) | max 2 revisions, see §6 |
| **g. Explain** | request, results, doc names | explanation text | LLM, then output guardrail, then template fallback |

### c. Plan, LLM mode (`plan_llm`)
The prompt contains:
1. The role and the task.
2. The **allowed genres and moods**, listed from the catalog.
3. The retrieved docs (name, front matter, and the first ~400 characters of each).
4. The top song hits.
5. The JSON schema from §4 and the instruction "Return ONLY JSON."

The call uses `response_mime_type="application/json"`, temperature 0.2 and a
10-second timeout. The output still goes through `json.loads`, and any failure
returns `None`, which triggers offline mode.

### c. Plan, offline mode (`plan_offline`): deterministic, grounded in the retrieved docs
1. **Numeric targets.** `target_energy` and `target_valence` are the
   BM25-score-weighted mean of the midpoints of each retrieved doc's range.
2. **Genre and mood.** Each retrieved doc gives its listed genres and moods a
   vote equal to its score. Each top song hit adds half its score to its own
   genre and mood. The highest vote wins in each category. If the request names
   a catalog label explicitly ("jazz", "sad"), that label wins.
3. **`likes_acoustic`.** Score-weighted majority of the docs' `acoustic:` field,
   ignoring docs marked `any`.
4. **Modifier lexicon.** A small table applied last. For example: "not too
   slow" / "upbeat" raises the energy floor to ≥0.5; "slow" / "mellow" lowers
   energy by 0.15; "happy" raises valence by 0.15; "sad" lowers it by 0.15;
   "mix" / "variety" sets `diverse=true`.
5. **`mode`.** Set to `energy-focused` if an activity doc (workout, party)
   ranks first, `mood-first` if a mood doc ranks first, and `balanced`
   otherwise.

Each derived value is logged together with the docs it came from.

---

## 4. Plan JSON schema

```json
{
  "type": "object",
  "required": ["favorite_genre", "favorite_mood", "target_energy",
               "target_valence", "likes_acoustic"],
  "properties": {
    "favorite_genre": {"type": "string", "enum": ["<17 catalog genres>"]},
    "favorite_mood":  {"type": "string", "enum": ["<16 catalog moods>"]},
    "target_energy":  {"type": "number", "minimum": 0, "maximum": 1},
    "target_valence": {"type": "number", "minimum": 0, "maximum": 1},
    "likes_acoustic": {"type": "boolean"},
    "mode":    {"type": "string",
                "enum": ["balanced", "genre-first", "mood-first", "energy-focused"]},
    "diverse": {"type": "boolean"},
    "rationale": {"type": "string", "maxLength": 300}
  },
  "additionalProperties": false
}
```

The schema is written into the prompt for the LLM and enforced by hand in
`validate_prefs`, so there is no `jsonschema` dependency. `rationale` is logged
only and is removed before the prefs reach `recommend_songs`.

---

## 5. Guardrail rules

### a. Input guardrail (deterministic, no LLM)
| Rule | Result |
|---|---|
| Empty or whitespace-only | reject: "Tell me what you'd like to hear, e.g. 'upbeat songs for a road trip'." |
| Longer than 300 characters after stripping | reject: "Please keep requests under 300 characters." |
| **Not about music.** The request has no token from the music vocabulary (KB keywords, catalog genres/moods/tags, and a small list such as song, music, playlist, vibe, listen), **and** the best KB BM25 score is below `MIN_RELEVANCE` (1.0) | reject: "I can only help with music recommendations — try describing a mood, activity, or genre." |
| Control characters | stripped and logged; the request is not rejected |

A rejection exits with code 2 and is logged at INFO. It never raises.

### d. Validate / repair (`validate_prefs`)
Repairs are applied in this order. Each one appends a human-readable entry to
`repairs`, for example `"favorite_genre 'k-pop' → 'pop' (alias)"`.

1. Missing required key: fill it from the offline plan.
2. Unknown key: drop it.
3. Number given as a string: cast it. A value that can't be cast is replaced from the offline plan.
4. `target_energy` / `target_valence` outside [0, 1]: clamp. This is required,
   because `score_song` raises `ValueError` on out-of-range values.
5. `likes_acoustic` given as "yes"/"no"/0/1: coerce to bool.
6. `mode` not in `SCORING_MODES`: set to `balanced`. `diverse` that isn't a bool: set to `false`.
7. **Genre or mood not in the catalog.** This fixes the silent failures recorded in `model_card.md`.
   1. Normalize spelling (lowercase, `hip hop` → `hip-hop`).
   2. Look up the alias table from `genre_notes.md` (`k-pop` → `pop`, `edm` → `electronic`).
   3. For moods: if the value is a `MOOD_FAMILIES` key, use the family's first member (`calm` → `chill`, `low` → `sad`).
   4. Otherwise, query `song_index` with the bad label plus the request and take the genre or mood of the top hit.
   5. If retrieval returns nothing, use the first label listed in the top KB doc.

---

## 6. Self-check & retry logic

After each **Act**, `evaluate_results` produces a list of issues:

| Check | Condition |
|---|---|
| Low confidence | `top_score / max_score(prefs, mode) < 0.55` |
| Energy contradiction | the mean energy of the top 3 songs falls outside the top context doc's `energy` range by more than 0.15 (e.g. a "calm" request whose top songs have energy above 0.7) |
| Valence contradiction | the same comparison against the doc's `valence` range |
| Label miss | none of the top 3 songs match the requested genre **or** mood, not even a related genre or a mood in the same family |

If no issues are found, the result passes. Otherwise `revise_prefs` makes **one
targeted change** per attempt and the revised prefs go back through **d → e → f**:

- **Attempt 2.** Energy or valence contradiction: nudge the target 50% toward
  the doc range midpoint and switch to `energy-focused` mode. Label miss: switch
  to `mood-first` or `genre-first` mode, whichever label missed.
- **Attempt 3.** Swap `favorite_genre` (or mood) for the next-highest vote from
  the offline planner's tally.

The loop stops after **3 attempts in total** (the original plus 2 revisions).
The agent returns the attempt with the fewest issues, breaking ties on the
higher normalized top score. That is not necessarily the last attempt. Every
attempt logs its prefs, top-3 songs with scores, the issues found and the
change made. Remaining issues are shown to the user as a short caveat (e.g.
"no song in the catalog is quieter than 0.28").

---

## 7. Explain + output guardrail

`explain_llm` prompt: the request, the final top-k (title, artist, score, the
reason strings from `recommend_songs`), the retrieved doc names, and any
caveats. The instructions say to write at most 120 words, mention only the
listed songs, and cite at least one doc name in brackets, e.g. `[studying.md]`.

`check_explanation` rejects the LLM text if any of these holds:
- It mentions a catalog title that is **not** in the results (the text is
  scanned for all 20 titles, case-insensitive).
- It mentions none of the result titles.
- It cites no retrieved doc name, or cites a doc that was not retrieved.
- It is empty or longer than 1,000 characters.

On rejection or LLM failure, `explain_template` builds the explanation from
data. Example:
`"Based on [studying.md, rainy_day.md] I looked for lofi / chill around energy 0.38. #1 Library Rain — genre match: lofi, mood match: chill, energy 0.35 vs target 0.38 …"`.

---

## 8. Logging

`logging_setup.configure(verbose)` creates the logger `vibematch` with:
- a **file handler** writing to `logs/agent.log` at DEBUG, always on (`RotatingFileHandler`, 1 MB × 3);
- a **console handler** that is off by default and runs at INFO with `--verbose`.

The line format is
`2026-11-15 12:00:00 | INFO | run=a1b2c3 | step=retrieve | <message>`.

| Step | Logged |
|---|---|
| start | run_id, request (truncated to 300 chars), flags, LLM available yes/no |
| a | pass or reject, plus the rule that fired |
| b | each doc and song hit with its BM25 score |
| c | mode (llm/offline), LLM latency, raw LLM text (DEBUG), parsed prefs, offline vote tallies (DEBUG) |
| d | every repair, final prefs |
| e/f | per attempt: prefs, top-3 and scores, issues, revision made |
| g | LLM or template, guardrail verdict and reason |
| errors | WARNING for every fallback (API error, timeout, bad JSON, guardrail fail); ERROR with traceback for anything unexpected |

---

## 9. Error handling

- `llm.py` wraps every call in `try/except Exception` with a timeout and returns
  `None` on any failure, logged at WARNING with the exception type. Callers
  treat `None` as "use offline". The fallback is per step: a failed plan call
  doesn't stop the agent from trying the LLM for the explanation, unless the
  failure was an authentication or missing-key error, which disables the LLM
  for the rest of the run.
- Validation means `score_song` never sees bad input.
- `agent.main()` wraps `run_agent` in a final catch. On an unexpected error it
  logs the traceback, prints "Something went wrong — see logs/agent.log" and
  exits with code 1. A bad request never produces a stack trace.
- A missing or unreadable `knowledge/` directory logs a WARNING. Retrieval then
  falls back to the song index only, and the planner falls back to catalog-wide
  defaults.

---

## 10. CLI & config

```
python -m src.agent "sad songs but not too slow" [--offline] [--verbose] [--k 5] [--table]
```
- `--offline` skips the LLM even if a key is set.
- `--k` sets the number of songs (default 5, clamped to 1–20) and the number of KB docs retrieved (3).
- `--table` reuses `print_table` from `src/main.py`.

The output is the request summary, the retrieved docs, the final profile, a
repairs/attempts summary, the recommendations and the explanation.

`config.py` calls `load_dotenv()` and reads `GEMINI_API_KEY` and
`GEMINI_MODEL` (default `gemini-2.5-flash`). The key is never logged.
`.env.example` is committed and `.env` is git-ignored.

---

## 11. Data flow

```mermaid
flowchart TD
    U[User request] --> A{a. Input guardrail}
    A -- reject --> R[Helpful message, exit 2]
    A -- ok --> B[b. Retrieve<br/>BM25 over knowledge/ + songs.csv]
    KB[(knowledge/*.md)] --> B
    CSV[(data/songs.csv)] --> B
    B --> C{c. Plan}
    C -- API key & LLM ok --> CL[Gemini JSON plan<br/>prompt includes retrieved docs]
    C -- offline / LLM error --> CO[Offline rules<br/>score-weighted doc ranges + votes]
    CL -- bad JSON / timeout --> CO
    CL --> D[d. Validate & repair<br/>schema, clamp, label mapping via retrieval]
    CO --> D
    D --> E[e. Act<br/>recommend_songs — existing engine]
    E --> F{f. Self-check<br/>score ≥ 0.55·max? matches doc ranges?}
    F -- issues & attempts < 3 --> V[Revise prefs] --> D
    F -- pass / out of attempts --> G[g. Explain<br/>Gemini, cites docs]
    G --> H{Output guardrail<br/>only result titles? cites docs?}
    H -- fail / LLM error --> T[Template explanation from reasons]
    H -- pass --> O[Recommendations + explanation]
    T --> O
    A & B & C & D & E & F & G & H -.-> L[(logs/agent.log)]
```
