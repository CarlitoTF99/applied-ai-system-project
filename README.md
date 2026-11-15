# VibeMatch Agent: An Applied AI Music Recommender

## Summary

VibeMatch turns a plain-English request such as "something chill for studying
on a rainy night" into ranked, explained song recommendations. It retrieves
relevant music knowledge, uses an AI agent to plan and check a listener
profile, and ranks songs with a transparent scoring engine. Guardrails check
the request, the plan and the final explanation. The result is a recommender
whose every pick can be traced to a score breakdown and a cited source. It is
covered by 111 automated tests and an evaluation suite, and it keeps working,
with clear warnings, when the AI model is overloaded, out of quota or
unavailable.

## Original Project

This project extends **"Music Recommender Simulation"** (CodePath AI110,
Module 3). The original was a content-based recommender: it scored each of 20
songs on genre, mood, energy, valence and acousticness, returned a ranked top
5, and showed how many points each feature contributed. Stretch features added
four switchable scoring modes, a diversity penalty for repeated artists and
genres, and a grid-table view. What motivated the extension: users had to
hand-write a Python profile dict, and genres or moods missing from the catalog
(like "k-pop" or "calm") matched nothing, with no warning.

## What's New

- **RAG retrieval:** a pure-Python BM25 retriever searches 11 knowledge docs
  (activities, mood families, genre notes) and the song catalog. The listener
  profile is built from what it finds.
- **Agentic loop:** each request goes through plan, validate, act, self-check
  and explain. The self-check can revise the profile up to twice.
- **Gemini with an offline fallback:** Gemini writes the plan and the
  explanation when available. Otherwise, deterministic rules build the plan
  from the same retrieved docs.
- **Guardrails:**
  - input checks for empty, too-long and off-topic requests;
  - plan validation that clamps out-of-range values and maps unknown genres
    and moods;
  - an output check that blocks explanations naming songs that weren't
    recommended.
- **Logging:** every step, retrieved doc, repair, retry and error goes to
  `logs/agent.log`. `--verbose` also prints them to the console.
- **Evaluation harness:** `python -m eval.run_eval` runs 15 property-based test
  cases and reports pass rate, consistency, repairs, retries and fallbacks.

## Architecture Overview

The diagram source is [diagrams/architecture.mmd](diagrams/architecture.mmd),
and a rendered copy is at [assets/architecture.png](assets/architecture.png).

```mermaid
flowchart TD
    %% ===== INPUT =====
    IN["User request<br/>python -m src.agent ..."]
    GIN{"check_input<br/>empty, over 300 chars, off-topic"}
    REJ["Helpful rejection message<br/>exit code 2"]

    %% ===== PROCESSING: RETRIEVAL =====
    subgraph RAG["Retrieval - RAG - retriever.py"]
        KB[("knowledge/*.md<br/>11 docs")]
        CSV[("data/songs.csv<br/>20 songs")]
        BM["BM25Index.search<br/>top-3 docs + top-5 song hits"]
    end

    %% ===== PROCESSING: AGENT LOOP =====
    subgraph AGENT["Agent loop - run_agent in agent.py"]
        PLAN{"Planner<br/>planner.py"}
        LLMP["plan_llm - Gemini JSON plan<br/>retry 5xx or timeout 2s then 5s,<br/>then fallback model once"]
        OFFP["plan_offline<br/>doc ranges + label votes"]
        VAL["validate_prefs<br/>schema, clamp 0-1,<br/>map unknown genre or mood"]
        REC["recommend_songs + score_song<br/>original Module 3 engine"]
        SC{"Self-check<br/>evaluate_results"}
        REV["revise_prefs<br/>max 3 attempts, pick_best"]
        EXL["explain_llm - Gemini"]
        OG{"check_explanation<br/>only result titles,<br/>cites retrieved docs"}
        TPL["explain_template<br/>from scoring reasons"]
    end

    %% ===== OUTPUT =====
    OUT["OUTPUT: ranked top-k songs<br/>per-feature reasons + caveats<br/>explanation citing docs"]
    LOG[("logs/agent.log")]

    %% ===== HUMAN AND TESTING CHECKS =====
    subgraph CHECKS["Human and Testing Checks"]
        PYT[["pytest - tests/<br/>offline, Gemini errors mocked"]]
        EVAL[["eval/run_eval.py<br/>test_cases.json to results.md"]]
        DEV[/"Developer review<br/>reads results.md + agent.log"/]
        USR[/"End user review<br/>reads reasons + explanation"/]
    end

    %% ===== main data flow =====
    IN --> GIN
    GIN -- reject --> REJ
    GIN -- ok --> BM
    KB --> BM
    CSV --> BM
    BM -- "docs + song hits" --> PLAN
    PLAN -- "API key, LLM up" --> LLMP
    PLAN -- "offline or no key" --> OFFP
    LLMP -- "all models fail or bad JSON" --> OFFP
    LLMP -- "raw plan" --> VAL
    OFFP -- "plan + fallback values" --> VAL
    VAL --> REC
    REC --> SC
    SC -- "issues, attempts left" --> REV
    REV -- "revised profile" --> VAL
    SC -- "best attempt, LLM up" --> EXL
    SC -- "best attempt, offline" --> TPL
    EXL --> OG
    OG -- pass --> OUT
    OG -- "rejected or LLM error" --> TPL
    TPL --> OUT

    %% ===== logging: every step writes here =====
    GIN -.-> LOG
    RAG -.-> LOG
    AGENT -.-> LOG

    %% ===== what each checkpoint inspects =====
    RAG -. "unit tests" .-> PYT
    AGENT -. "unit tests, mocked 503 404 429" .-> PYT
    OUT -. "properties checked" .-> EVAL
    OUT -. "read by" .-> USR
    LOG -. "read by" .-> DEV
    EVAL -. "results.md" .-> DEV

    %% ===== feedback into the system =====
    EVAL == "runs same pipeline on 15 cases" ==> IN
    DEV == "tunes config.py thresholds + knowledge docs" ==> SC
    USR == "re-run: --verbose, --k, reworded request" ==> IN

    %% ===== styles =====
    classDef io fill:#e6f4ea,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef guard fill:#fde8e8,stroke:#c0392b,color:#000
    classDef llm fill:#e8f0fe,stroke:#3b5bdb,color:#000
    classDef check fill:#fff4d6,stroke:#b8860b,stroke-width:2px,stroke-dasharray:5 3,color:#000
    class IN,OUT io
    class GIN,VAL,OG guard
    class LLMP,EXL llm
    class PYT,EVAL,DEV,USR check
```

A request enters through `python -m src.agent`, and `check_input` either
rejects it with a helpful message or passes it to the BM25 retriever, which
returns the top 3 knowledge docs and the top 5 matching songs. The planner
turns those docs into a listener profile. It uses Gemini when available, with
retries and a fallback model, and deterministic rules when not. `validate_prefs`
repairs the profile before the original Module 3 engine (`recommend_songs` /
`score_song`) ranks the catalog. The self-check compares the results with the
request, loops back with a revised profile up to 3 attempts in total, and keeps
the best attempt. The explanation, from Gemini or a template, must pass
`check_explanation` before it reaches the user. Humans and tests check the AI
in the bottom row of the diagram: `pytest` unit-tests each component with
mocked Gemini errors, `eval/run_eval.py` runs the full pipeline on 15 cases, a
developer reads `eval/results.md` and `logs/agent.log` to tune thresholds and
knowledge docs, and the end user reads the reasons and can re-run or reword
the request.

## Project Structure

```text
applied-ai-system-project/
├── src/
│   ├── agent.py           # CLI + run_agent(): the agent loop (guardrail -> retrieve -> plan -> validate -> act -> self-check -> explain)
│   ├── retriever.py       # knowledge-base loader and pure-Python BM25 index
│   ├── planner.py         # Gemini planner (plan_llm) and offline rule-based planner (plan_offline)
│   ├── guardrails.py      # input check, plan validation/repair, explanation check
│   ├── selfcheck.py       # result checks, profile revisions, best-attempt choice
│   ├── explainer.py       # Gemini explanation and template explanation
│   ├── llm.py             # Gemini client: timeout, retries, fallback model, never raises
│   ├── labels.py          # catalog genres/moods and aliases from the knowledge base
│   ├── config.py          # thresholds and .env settings
│   ├── logging_setup.py   # logs/agent.log + optional console output
│   ├── recommender.py     # original Module 3 scoring engine (unchanged)
│   └── main.py            # original Module 3 CLI (unchanged)
├── knowledge/             # 11 markdown docs: activities, mood families, genre notes
├── data/songs.csv         # 20-song catalog
├── eval/                  # test_cases.json, run_eval.py, results.md
├── tests/                 # 111 pytest tests (no network)
├── diagrams/              # architecture.mmd (Mermaid source)
├── assets/                # architecture.png
├── docs/                  # DESIGN.md (full design), ORIGINAL_PROJECT.md (Module 3 README)
├── model_card.md          # model card and reflection
├── requirements.txt
└── .env.example           # template for optional Gemini settings
```

## Setup

**Windows PowerShell**

1. Clone the repository:
   ```powershell
   git clone https://github.com/CarlitoTF99/applied-ai-system-project.git
   cd applied-ai-system-project
   ```
2. Create and activate a virtual environment. If activation is blocked, run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Copy the settings template:
   ```powershell
   Copy-Item .env.example .env
   ```
5. *(Optional)* Open `.env` and replace the placeholder value of
   `GEMINI_API_KEY` with your own key. Without a key the agent runs in offline
   mode and still gives full recommendations.
6. Check that everything works:
   ```powershell
   pytest
   ```

**macOS / Linux**

1. Clone the repository:
   ```bash
   git clone https://github.com/CarlitoTF99/applied-ai-system-project.git
   cd applied-ai-system-project
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the settings template:
   ```bash
   cp .env.example .env
   ```
5. *(Optional)* Open `.env` and replace the placeholder value of
   `GEMINI_API_KEY` with your own key. Without a key the agent runs in offline
   mode and still gives full recommendations.
6. Check that everything works:
   ```bash
   pytest
   ```

`.env` is git-ignored, so your key is never committed. The optional settings:

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | main model |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.8-flash` | tried once if the main model fails (`none` turns it off) |
| `GEMINI_TIMEOUT` | `30` | seconds per attempt |

## Usage

**The agent:**

```bash
python -m src.agent "something chill for studying on a rainy night"
python -m src.agent "hype songs for the gym" --offline --verbose --k 3 --table
```

| Flag | Effect |
|---|---|
| `--offline` | never call Gemini, even if a key is set |
| `--verbose` | also print each step's log lines to the console |
| `--k N` | number of songs to return (default 5, range 1-20) |
| `--table` | show the results as a grid table |

The exit code is 0 on success, 2 when the input guardrail rejects the request,
and 1 on an unexpected error.

**The original Module 3 CLI** (unchanged; runs the built-in profiles):

```bash
python -m src.main
python -m src.main --mode mood-first --diverse --table
```

`--mode` accepts `balanced`, `genre-first`, `mood-first` or `energy-focused`.

**Tests:**

```bash
pytest
```

**Evaluation:**

```bash
python -m eval.run_eval
python -m eval.run_eval --llm --runs 1
```

The eval runs offline by default and writes `eval/results.md`. `--llm` uses
Gemini, at about 2 calls per case per run, so `--runs 1` helps stay within
free-tier quota.

## Sample Interactions

All output below is real: copied from the console or from `logs/agent.log`.
Long outputs are trimmed where marked.

### 1. "something chill for studying on a rainy night": LLM vs. offline

**LLM run.** The console output wasn't saved, so this is the run's trace from
`logs/agent.log` (run `4e4bf7`, trimmed). The main model was overloaded, so the
fallback model wrote both the plan and the explanation.

```text
step=retrieve | doc rainy_day.md score=5.742
step=retrieve | doc studying.md score=5.361
step=retrieve | doc road_trip.md score=2.185
step=plan     | Gemini gemini-3.8-flash attempt 1/3 failed after 13.12s: ServerError: 504 DEADLINE_EXCEEDED. [...]
step=plan     | Gemini gemini-3.8-flash attempt 2/3 failed after 13.14s: ServerError: 504 DEADLINE_EXCEEDED. [...]
step=plan     | Gemini gemini-3.8-flash attempt 3/3 failed after 0.34s: ServerError: 503 UNAVAILABLE. [...]
step=plan     | trying fallback model gemini-3.5-flash-lite
step=plan     | Gemini gemini-3.5-flash-lite attempt 1/1 succeeded in 0.77s
step=plan     | llm plan: {'favorite_genre': 'lofi', 'favorite_mood': 'chill', 'target_energy': 0.32,
                'target_valence': 0.55, 'likes_acoustic': True, 'mode': 'genre-first', 'diverse': False, [...]}
step=act      | attempt 1 top-3: Library Rain 8.38, Midnight Coding 8.17, Focus Flow 7.50 (max 8.5)
step=selfcheck| attempt 1 passed self-check
step=explain  | Gemini gemini-3.5-flash-lite attempt 1/1 succeeded in 0.91s
step=explain  | LLM explanation passed output guardrail
```

The explanation the model wrote, which passed the output guardrail:

```text
Here are some chill lofi tracks tailored for your study session tonight, matching your need for a calm
atmosphere [rainy_day.md].

Library Rain by Paper Lanterns hits the mark with an exact genre match for lofi, a perfect chill mood, and
high acousticness that fits your preferences. Midnight Coding by LoRoom also features a great lofi genre
match and a relaxed chill mood with low, steady energy levels ideal for deep focus [studying.md]. Finally,
Focus Flow by LoRoom brings a supportive focused mood family match alongside strong lofi elements to keep
you locked into your work without distractions.
```

**Offline run:**

```bash
python -m src.agent "something chill for studying on a rainy night" --offline
```

```text
================================================================
VibeMatch Agent  |  plan: offline  (--offline)
Request: "something chill for studying on a rainy night"
================================================================

[1] Retrieved knowledge docs
    rainy_day.md       score 5.74   (context)
    studying.md        score 5.36   (context)
    road_trip.md       score 2.19   (context)
    song evidence: Library Rain (3.87), Midnight Coding (3.70), Night Drive Loop (2.49), Rust in the Rain (2.10), Velvet Hours (1.85)

[2] Profile (attempt 1)
    genre=lofi | mood=chill | energy=0.41 | valence=0.53 | acoustic=yes
    mode=balanced | diverse=no

[3] Repairs
    - none

[4] Self-check (1 attempt(s), using #1)
    #1 initial plan
       top: Midnight Coding 8.33/8.5 -> pass

[5] Top 5 recommendations
----------------------------------------------------------------
1. Midnight Coding - LoRoom                    Score: 8.33 / 8.5
     + genre match: lofi (+2.50)
     + mood match: chill (+2.00)
     + energy 0.42 vs target 0.41 (+2.00)
     + valence 0.56 vs target 0.53 (+1.48)
     + acousticness 0.71, likes acoustic (+0.35)
2. Library Rain - Paper Lanterns               Score: 8.25 / 8.5
     + genre match: lofi (+2.50)
     + mood match: chill (+2.00)
     + energy 0.35 vs target 0.41 (+1.91)
     + valence 0.60 vs target 0.53 (+1.41)
     + acousticness 0.86, likes acoustic (+0.43)
[... #3 Focus Flow 7.32, #4 Spacewalk Thoughts 6.58, #5 Coffee Shop Stories 5.66 trimmed ...]

[6] Explanation (template)
    Based on [rainy_day.md, studying.md, road_trip.md], I looked for lofi / chill songs around energy 0.41 and valence 0.53 with an acoustic sound.
    #1 Midnight Coding by LoRoom: genre match: lofi, mood match: chill, energy 0.42 vs target 0.41.
    #2 Library Rain by Paper Lanterns: genre match: lofi, mood match: chill, energy 0.35 vs target 0.41.
    [... #3-#5 trimmed ...]
```

| | Offline | LLM (gemini-3.5-flash-lite) |
|---|---|---|
| Docs used | rainy_day, studying, road_trip | same 3 docs, given in the prompt |
| `target_energy` | 0.41 | **0.32** |
| `mode` | balanced | **genre-first** |
| #1 song | Midnight Coding (8.33) | **Library Rain (8.38)** |
| Explanation | template, built from scoring reasons | natural prose citing 2 docs, passed the guardrail |

Both plans come from the same retrieved docs. The offline average gets pulled
up by `road_trip.md`, which matched only on the word "night". The LLM gave that
doc less weight and picked a quieter target, so Library Rain moved to #1.

### 2. "hype songs for the gym"

```bash
python -m src.agent "hype songs for the gym" --offline
```

```text
[1] Retrieved knowledge docs
    workout.md         score 5.14   (context)
    mood_driven.md     score 2.58   (mood)
    song evidence: Gym Hero (2.66)

[2] Profile (attempt 1)
    genre=pop | mood=energetic | energy=0.89 | valence=0.62 | acoustic=no
    mode=energy-focused | diverse=no

[3] Repairs
    - favorite_mood 'hype' -> 'energetic' (alias from knowledge base)

[4] Self-check (1 attempt(s), using #1)
    #1 initial plan
       top: Gym Hero 7.39/8.5 -> pass

[5] Top 5 recommendations
----------------------------------------------------------------
1. Gym Hero - Max Pulse                        Score: 7.39 / 8.5
     + genre match: pop (+1.50)
     + mood family match: intense ~ energetic (+0.75)
     + energy 0.93 vs target 0.89 (+3.92)
     + valence 0.77 vs target 0.62 (+0.75)
     + acousticness 0.05, prefers non-acoustic (+0.47)
2. Sunrise City - Neon Echo                    Score: 6.22 / 8.5
3. Fuego en la Plaza - Los Faroles             Score: 6.17 / 8.5
4. Storm Runner - Voltline                     Score: 5.96 / 8.5
5. Concrete Psalms - Verse Theory              Score: 5.80 / 8.5
[trimmed: header, reasons for #2-#5, explanation]
```

The top doc is `workout.md`, so the planner chose `energy-focused` mode, and
all five songs have energy between 0.80 and 0.93. "Hype" isn't a catalog mood,
so the validator mapped it to `energetic` using the alias list in
`mood_driven.md`, and the repair is shown to the user.

### 3. "k-pop for a party" (genre repair)

```bash
python -m src.agent "k-pop for a party" --offline
```

```text
[1] Retrieved knowledge docs
    party.md           score 5.17   (context)
    genre_notes.md     score 4.21   (genre)
    mood_bright.md     score 1.12   (mood)

[2] Profile (attempt 1)
    genre=pop | mood=happy | energy=0.81 | valence=0.83 | acoustic=no
    mode=energy-focused | diverse=no

[3] Repairs
    - favorite_genre 'k-pop' -> 'pop' (alias from knowledge base)

[5] Top 5 recommendations
----------------------------------------------------------------
1. Sunrise City - Neon Echo                    Score: 8.41 / 8.5
     + genre match: pop (+1.50)
     + mood match: happy (+1.50)
     + energy 0.82 vs target 0.81 (+4.00)
     + valence 0.84 vs target 0.83 (+1.00)
     + acousticness 0.18, prefers non-acoustic (+0.41)
2. Rooftop Lights - Indigo Parade              Score: 7.46 / 8.5
3. Gym Hero - Max Pulse                        Score: 6.27 / 8.5
[trimmed: header, self-check, #4-#5, reasons, explanation]
```

In Module 3, a "k-pop" profile silently earned zero genre points from every
song, and its best score was 5.87 / 8.5. Now `genre_notes.md` is retrieved, its
alias list maps k-pop to pop, the repair is logged and shown, and the top song
scores 8.41 / 8.5.

### 4. Guardrail rejections

```text
PS> python -m src.agent "" --offline
Tell me what you'd like to hear, e.g. 'upbeat songs for a road trip'.
(exit code 2)
PS> python -m src.agent "what's the weather tomorrow" --offline
I can only help with music recommendations - try describing a mood, activity, or genre.
(exit code 2)
```

Both requests are stopped by deterministic checks before any retrieval or LLM
call: one is empty, and the other contains no music words and matches no
knowledge doc. The user gets a helpful message instead of made-up
recommendations or a stack trace.

## Design Decisions

- **The LLM plans and explains; a deterministic engine ranks.** Gemini never
  picks songs. It produces a profile that `score_song` scores against the
  catalog, so every ranking can be reproduced and unit-tested, and every score
  has a breakdown. *Trade-off:* results are less "creative" than letting a
  model pick freely.
- **Pure-Python BM25 instead of embeddings.** There are no heavy dependencies
  or vector stores, and every retrieval score can be read and explained.
  *Trade-off:* matching is purely lexical. For example, `road_trip.md` is
  retrieved for a study request just because of the word "night".
- **The offline planner uses the same retrieved docs.** It builds the profile
  from score-weighted doc ranges and label votes, so the system always works,
  even with no key, no network or no quota, and tests are fully reproducible.
  *Trade-off:* its profiles are less nuanced than the LLM's (energy 0.41 vs.
  0.32 in Sample 1).
- **The validator repairs and clamps instead of rejecting.** An LLM's
  `target_energy: 1.4` is clamped to 1.0 and "k-pop" is mapped to "pop", so
  the user still gets an answer. *Trade-off:* a repair can guess wrong, so
  every repair is logged and shown under `[3] Repairs`.
- **The self-check keeps the best attempt, not the last.** Attempts are ranked
  by number of issues, then by size of violation, then by order. The score
  ratio is deliberately not used, because the eval showed that a label swap
  can score higher while fitting the request worse. *Trade-off:* when no
  attempt is clean, the user gets the least-bad list plus a caveat rather than
  a perfect answer.
- **A lite Gemini model is the primary, with retries only for timeouts and 5xx
  errors.** In development, the lite model answered in under 1 second while
  the larger model was returning 503/504 errors. 4xx errors (bad key, retired
  model, quota) are never retried, because retrying can't fix them.
  *Trade-off:* a smaller model may reason less well. The larger model is kept
  as a one-shot fallback.
- **The Module 3 engine is reused unchanged.** `recommender.py` and `main.py`
  weren't modified, and `python -m src.main` was checked byte-for-byte against
  its original output after every change. *Trade-off:* the agent has to work
  within the engine's limits, such as one genre and one mood per profile and
  no way to exclude a genre.

## Testing Summary

**Results**

| Check | Result |
|---|---|
| `pytest` | **111 passed**, all offline (Gemini is replaced by fakes) |
| Eval cases (`python -m eval.run_eval`) | **15/15** passed (52/52 properties) |
| Consistency across 3 runs | **15/15** identical (expected offline, since the planner is deterministic) |
| Repairs | 18 over 45 runs (6 per pass) |
| Self-check retries | 18 over 45 runs (6 per pass), all in the conflicting-request cases |
| Guardrail rejections | 12 over 45 runs (the 4 reject cases x 3) |
| Runs with caveats | 12 over 45 runs (4 per pass) |

**What worked**

- The guardrails and validator turned every silent failure from Module 3 into
  a visible repair or a helpful message.
- The offline fallback meant no request ever crashed, even when every Gemini
  call failed.
- The output guardrail accepted the real LLM explanation and, in tests,
  rejected explanations that named songs outside the results.
- All 5 normal eval cases passed on their first attempt, with no false
  self-check alarms.

**What didn't work at first, and how it was handled**

- **Gemini failures in live runs** (all from `logs/agent.log`):
  - a fallback model name had been retired (**404** "no longer available to
    new users"); it was not retried, and the agent switched to the offline
    plan;
  - the main model was overloaded (**503/504**); calls were retried after 2s
    and 5s, then the fallback model answered in 0.77s;
  - a **429 quota** error was not retried, and the fallback model answered in
    0.91s;
  - in one run every attempt failed, and the offline plan still returned the
    same correct top 3.
- **Bugs the evaluation exposed.** My first eval passed 100% while these bugs
  existed, because its expectations were too loose. Stricter properties caught
  all four:
  - vague requests like "play me some songs" got a contradictory "ambient /
    angry" profile (alphabetical defaults); they now use catalog-majority
    labels plus a "general picks" caveat;
  - explicit limits like "not too slow" weren't enforced, because a top-3
    average hid a slow #1 song; the #1 song must now respect them, or the user
    gets a caveat;
  - the best-attempt tie-break let a label swap win ("hopeful" for a
    heartbreak request); it now prefers the smallest violation, then the
    earliest attempt;
  - a genre the user named could drop out of the top 3 with no warning; that
    is now checked.
- **Smaller fixes:**
  - "sad but **not too slow**" originally retrieved `sleep.md` because of the
    word "slow", so negated phrases are now removed from the retrieval query;
  - mood-family names mapped to different moods between runs, because Python
    sets have no fixed order; the knowledge docs now define each family's
    representative mood.
- **Threshold analysis:** the 55% low-confidence threshold never fired across
  31 probe requests, while bad profiles still scored 0.60-0.69. A score ratio
  measures fit to the *profile*, not to the *request*, so I kept the threshold
  and added checks against the request instead.

**What I learned**

- An evaluation is only as good as its expectations. A suite that passes 100%
  can still miss real bugs.
- With a small model plus retries, fallbacks and an offline path, the system
  stays reliable even when the API isn't.
- A good error message should say what the system couldn't do, not just pick
  something and hide the problem.

## Reflection

This project taught me that most of the work in an applied AI system is around
the model, not in it: deciding what the model is allowed to do, checking what
it returns, and planning for when it isn't there. Keeping the LLM out of the
ranking made every recommendation explainable and testable, and building the
evaluation showed me that passing tests and correct behavior aren't the same
thing until the tests ask the right questions. The real API failures I hit,
from overloaded servers to quota limits and retired model names, made
resilience feel like a core feature rather than an extra. Above all, I learned
to treat both my own code and the AI's output as something to verify, not
trust.

For a detailed reflection on AI collaboration, limitations, and responsible use, see the [Model Card](model_card.md).

## Original Project Details

The complete Module 3 README (scoring recipe, profile experiments, weight-shift
experiment, bias analysis and stretch features) is preserved in
[docs/ORIGINAL_PROJECT.md](docs/ORIGINAL_PROJECT.md).
