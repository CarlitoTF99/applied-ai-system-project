# VibeMatch Evaluation Results

- Generated: 2026-11-15 15:02
- Mode: **offline**
- 15 cases x 3 runs each = 45 agent runs

## Summary

15 out of 15 cases passed (100%); offline consistency 100%; average confidence 0.78; the agent struggled when confidence fell below 0.75: "rock but not too loud" (0.44: top score only 66% of max), "sad but energetic" (0.62: 2 self-check retries), "sad songs but not too slow" (0.66: 2 self-check retries), "country songs about heartbreak" (0.66: top score only 57% of max), "play me some songs" (0.71: no knowledge doc matched the request).

| Metric | Value |
|---|---|
| Cases passed | 15/15 (100%) |
| Properties passed | 52/52 (100%) |
| Consistency (identical top 5 / rejection across 3 runs) | 15/15 (100%) |
| Average confidence (accepted cases, run 1) | 0.78 |
| Average confidence, passed cases | 0.78 |
| Average confidence, failed cases | n/a (no failed cases) |

Confidence is computed, never self-rated by the LLM: it starts at 1.0 and loses points for a top score below the maximum, a weak knowledge-base match, plan repairs, self-check retries and LLM fallbacks (see `src/confidence.py`). Rejected requests have no confidence.

## Results by case

| # | Test Input | Evaluation Criteria | Result | Confidence | Notes |
|---|---|---|---|---|---|
| 1 | something chill for studying on a rainy night | avg energy <= 0.5; #1 genre in lofi/ambient/jazz; acoustic = yes; no caveat; explanation grounded | Pass | 0.99 (high) | clean run |
| 2 | hype songs for the gym | avg energy >= 0.7; #1 genre in pop/rock/metal/hip-hop; acoustic = no; explanation grounded | Pass | 0.87 (high) | favorite_mood 'hype' -> 'energetic' |
| 3 | calm music to help me fall asleep | avg energy <= 0.45; #1 mood in chill/relaxed/focused; profile mood = chill; repair logged for 'calm'; explanation grounded | Pass | 0.94 (high) | favorite_mood 'calm' -> 'chill' |
| 4 | upbeat songs for a road trip with friends | avg energy >= 0.55; avg valence >= 0.55; target energy >= 0.5; explanation grounded | Pass | 0.93 (high) | favorite_mood 'upbeat' -> 'happy' |
| 5 | angry heavy metal for lifting weights | #1 genre in metal/rock; #1 mood in angry/intense; avg energy >= 0.7; repair logged for 'heavy metal'; explanation grounded | Pass | 0.86 (high) | favorite_genre 'heavy metal' -> 'metal' |
| 6 | sad songs but not too slow | avg valence <= 0.45; a top-3 mood in sad/melancholy/moody; target energy >= 0.5; #1 energy >= 0.45 or caveat; explanation grounded | Pass | 0.66 (medium) | 2 self-check retries, used attempt #1; caveat shown |
| 7 | k-pop for a party | profile genre = pop; repair logged for 'k-pop'; avg energy >= 0.7; avg valence >= 0.65; explanation grounded | Pass | 0.94 (high) | favorite_genre 'k-pop' -> 'pop' |
| 8 | sad but energetic | target valence <= 0.4; target energy >= 0.5; a top-3 mood in sad/melancholy/moody/angry/dramatic; #1 energy >= 0.45 or caveat; explanation grounded | Pass | 0.62 (medium) | 2 self-check retries, used attempt #1; caveat shown |
| 9 | country songs about heartbreak | profile genre = country; profile mood = sad; country in top 3 or caveat; a top-3 mood in sad/melancholy/moody; explanation grounded | Pass | 0.66 (medium) | favorite_mood 'heartbreak' -> 'sad' |
| 10 | rock but not too loud | #1 energy <= 0.65 or caveat; rock in top 3 or caveat; explanation grounded | Pass | 0.44 (low) | 2 self-check retries, used attempt #3; caveat shown |
| 11 | play me some songs | caveat shown; explanation grounded | Pass | 0.71 (medium) | caveat shown |
| 12 | "" | rejected as empty | Pass | n/a (rejected) | rejected by `empty` guardrail before retrieval |
| 13 | I want some songs for a long drive through the mountains with my fa... | rejected as too_long | Pass | n/a (rejected) | rejected by `too_long` guardrail before retrieval |
| 14 | what's the weather tomorrow | rejected as off_topic | Pass | n/a (rejected) | rejected by `off_topic` guardrail before retrieval |
| 15 | write me a python function that sorts a list | rejected as off_topic | Pass | n/a (rejected) | rejected by `off_topic` guardrail before retrieval |

## Counts

Totals over all 45 runs (3 per case):

| Count | Total | Per pass |
|---|---|---|
| Guardrail rejections | 12 | 4.0 |
| Repairs | 18 | 6.0 |
| Self-check retries | 18 | 6.0 |
| Runs with caveats | 12 | 4.0 |
| LLM fallbacks to offline | 0 (offline run: no LLM calls were made) | |

## Details (run 1 of each case)

### study-rain - PASS

Request: `something chill for studying on a rainy night`

- Docs: rainy_day.md, studying.md, road_trip.md
- Profile: genre=lofi, mood=chill, energy=0.41, valence=0.53, acoustic=True, mode=balanced, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.99 (high); lowered by: -0.01 top score only 98% of max
- Top 5: Midnight Coding (8.33, e=0.42, v=0.56), Library Rain (8.25, e=0.35, v=0.60), Focus Flow (7.32, e=0.40, v=0.59), Spacewalk Thoughts (6.58, e=0.28, v=0.65), Coffee Shop Stories (5.66, e=0.37, v=0.71)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| max_avg_energy | 0.5 | 0.36 | yes |
| top1_genre_in | ["lofi", "ambient", "jazz"] | lofi | yes |
| likes_acoustic | true | True | yes |
| has_caveat | false | 0 caveat(s) | yes |
| explanation_grounded | true | ok | yes |

### gym-hype - PASS

Request: `hype songs for the gym`

- Docs: workout.md, mood_driven.md
- Profile: genre=pop, mood=energetic, energy=0.89, valence=0.62, acoustic=False, mode=energy-focused, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_mood 'hype' -> 'energetic' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.87 (high); lowered by: -0.08 top score only 87% of max; -0.05 1 repair to the plan
- Top 5: Gym Hero (7.39, e=0.93, v=0.77), Sunrise City (6.22, e=0.82, v=0.84), Fuego en la Plaza (6.17, e=0.86, v=0.88), Storm Runner (5.96, e=0.91, v=0.48), Concrete Psalms (5.80, e=0.80, v=0.62)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| min_avg_energy | 0.7 | 0.86 | yes |
| top1_genre_in | ["pop", "rock", "metal", "hip-hop"] | pop | yes |
| likes_acoustic | false | False | yes |
| explanation_grounded | true | ok | yes |

### sleep-calm - PASS

Request: `calm music to help me fall asleep`

- Docs: sleep.md, mood_calm.md, workout.md
- Profile: genre=ambient, mood=chill, energy=0.34, valence=0.59, acoustic=True, mode=balanced, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_mood 'calm' -> 'chill' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.94 (high); lowered by: -0.05 1 repair to the plan; -0.01 top score only 98% of max
- Top 5: Spacewalk Thoughts (8.30, e=0.28, v=0.65), Library Rain (7.18, e=0.35, v=0.60), Midnight Coding (6.93, e=0.42, v=0.56), Focus Flow (6.05, e=0.40, v=0.59), Coffee Shop Stories (4.68, e=0.37, v=0.71)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| max_avg_energy | 0.45 | 0.36 | yes |
| top1_mood_in | ["chill", "relaxed", "focused"] | chill | yes |
| profile_mood | "chill" | chill | yes |
| repair_contains | "calm" | favorite_mood 'calm' -> 'chill' (alias from knowledge base) | yes |
| explanation_grounded | true | ok | yes |

### road-trip - PASS

Request: `upbeat songs for a road trip with friends`

- Docs: road_trip.md, party.md, mood_bright.md
- Profile: genre=indie pop, mood=happy, energy=0.74, valence=0.76, acoustic=False, mode=balanced, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_mood 'upbeat' -> 'happy' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.93 (high); lowered by: -0.05 1 repair to the plan; -0.02 top score only 97% of max
- Top 5: Rooftop Lights (8.27, e=0.76, v=0.81), Sunrise City (6.89, e=0.82, v=0.84), Gym Hero (4.49, e=0.93, v=0.77), Dust Road Letters (4.01, e=0.58, v=0.70), Island Slowdown (3.93, e=0.55, v=0.85)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| min_avg_energy | 0.55 | 0.73 | yes |
| min_avg_valence | 0.55 | 0.79 | yes |
| min_target_energy | 0.5 | 0.74 | yes |
| explanation_grounded | true | ok | yes |

### metal-lifting - PASS

Request: `angry heavy metal for lifting weights`

- Docs: workout.md, mood_driven.md, genre_notes.md
- Profile: genre=metal, mood=angry, energy=0.89, valence=0.61, acoustic=False, mode=energy-focused, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_genre 'heavy metal' -> 'metal' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.86 (high); lowered by: -0.09 top score only 86% of max; -0.05 1 repair to the plan
- Top 5: Ironclad Fury (7.27, e=0.97, v=0.18), Storm Runner (5.99, e=0.91, v=0.48), Gym Hero (5.12, e=0.93, v=0.77), Concrete Psalms (5.05, e=0.80, v=0.62), Sunrise City (4.69, e=0.82, v=0.84)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| top1_genre_in | ["metal", "rock"] | metal | yes |
| top1_mood_in | ["angry", "intense"] | angry | yes |
| min_avg_energy | 0.7 | 0.89 | yes |
| repair_contains | "heavy metal" | favorite_genre 'heavy metal' -> 'metal' (alias from knowledge base) | yes |
| explanation_grounded | true | ok | yes |

### sad-not-slow - PASS

Request: `sad songs but not too slow`

- Docs: mood_low.md, rainy_day.md, sleep.md
- Profile: genre=blues, mood=sad, energy=0.50, valence=0.23, acoustic=True, mode=mood-first, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 3 (using #1); caveats: No song in the catalog fits both the style and the energy you asked for; the closest matches are shown.
- Confidence: 0.66 (medium); lowered by: -0.20 2 self-check retries; -0.10 weak retrieval match (top doc score 2.36); -0.04 top score only 93% of max
- Top 5: Rust in the Rain (7.94, e=0.33, v=0.22), Afterglow Static (4.15, e=0.30, v=0.28), Night Drive Loop (3.19, e=0.75, v=0.49), Tempest Overture (2.70, e=0.72, v=0.30), Coffee Shop Stories (2.49, e=0.37, v=0.71)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| max_avg_valence | 0.45 | 0.40 | yes |
| any_top3_mood_in | ["sad", "melancholy", "moody"] | sad,melancholy,moody | yes |
| min_target_energy | 0.5 | 0.50 | yes |
| min_top1_energy_or_caveat | 0.45 | top1 energy 0.33, caveat shown | yes |
| explanation_grounded | true | ok | yes |

### kpop-party - PASS

Request: `k-pop for a party`

- Docs: party.md, genre_notes.md, mood_bright.md
- Profile: genre=pop, mood=happy, energy=0.81, valence=0.83, acoustic=False, mode=energy-focused, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_genre 'k-pop' -> 'pop' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.94 (high); lowered by: -0.05 1 repair to the plan; -0.01 top score only 99% of max
- Top 5: Sunrise City (8.41, e=0.82, v=0.84), Rooftop Lights (7.46, e=0.76, v=0.81), Gym Hero (6.27, e=0.93, v=0.77), Fuego en la Plaza (5.13, e=0.86, v=0.88), Concrete Psalms (5.02, e=0.80, v=0.62)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| profile_genre | "pop" | pop | yes |
| repair_contains | "k-pop" | favorite_genre 'k-pop' -> 'pop' (alias from knowledge base) | yes |
| min_avg_energy | 0.7 | 0.83 | yes |
| min_avg_valence | 0.65 | 0.78 | yes |
| explanation_grounded | true | ok | yes |

### sad-energetic - PASS

Request: `sad but energetic`

- Docs: mood_low.md, mood_driven.md, rainy_day.md
- Profile: genre=blues, mood=sad, energy=0.56, valence=0.26, acoustic=False, mode=mood-first, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 3 (using #1); caveats: No song in the catalog fits both the style and the energy you asked for; the closest matches are shown.
- Confidence: 0.62 (medium); lowered by: -0.20 2 self-check retries; -0.10 weak retrieval match (top doc score 2.36); -0.08 top score only 86% of max
- Top 5: Rust in the Rain (7.35, e=0.33, v=0.22), Afterglow Static (4.34, e=0.30, v=0.28), Night Drive Loop (3.87, e=0.75, v=0.49), Tempest Overture (2.59, e=0.72, v=0.30), Ironclad Fury (2.04, e=0.97, v=0.18)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| max_target_valence | 0.4 | 0.26 | yes |
| min_target_energy | 0.5 | 0.56 | yes |
| any_top3_mood_in | ["sad", "melancholy", "moody", "angry", "dramatic"] | sad,melancholy,moody | yes |
| min_top1_energy_or_caveat | 0.45 | top1 energy 0.33, caveat shown | yes |
| explanation_grounded | true | ok | yes |

### country-heartbreak - PASS

Request: `country songs about heartbreak`

- Docs: mood_low.md, road_trip.md, mood_bright.md
- Profile: genre=country, mood=sad, energy=0.56, valence=0.52, acoustic=False, mode=mood-first, diverse=False
- Plan source: offline; explanation: template
- Repairs: favorite_mood 'heartbreak' -> 'sad' (alias from knowledge base)
- Attempts: 1 (using #1); caveats: none
- Confidence: 0.66 (medium); lowered by: -0.26 top score only 57% of max; -0.05 1 repair to the plan; -0.03 weak retrieval match (top doc score 3.44)
- Top 5: Rust in the Rain (4.87, e=0.33, v=0.22), Night Drive Loop (4.58, e=0.75, v=0.49), Dust Road Letters (4.12, e=0.58, v=0.70), Afterglow Static (3.58, e=0.30, v=0.28), Hollow Porch Light (3.46, e=0.68, v=0.58)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| profile_genre | "country" | country | yes |
| profile_mood | "sad" | sad | yes |
| genre_in_top3_or_caveat | "country" | blues,synthwave,country | yes |
| any_top3_mood_in | ["sad", "melancholy", "moody"] | sad,moody,hopeful | yes |
| explanation_grounded | true | ok | yes |

### quiet-rock - PASS

Request: `rock but not too loud`

- Docs: road_trip.md, workout.md, genre_notes.md
- Profile: genre=rock, mood=happy, energy=0.50, valence=0.68, acoustic=False, mode=energy-focused, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 3 (using #3); caveats: The catalog has no close match for the genre or mood you named together with the rest of the request.
- Confidence: 0.44 (low); lowered by: -0.20 top score only 66% of max; -0.20 2 self-check retries; -0.16 weak retrieval match (top doc score 1.45)
- Top 5: Island Slowdown (5.63, e=0.55, v=0.85), Dust Road Letters (5.57, e=0.58, v=0.70), Velvet Hours (5.32, e=0.52, v=0.66), Midnight Coding (4.68, e=0.42, v=0.56), Focus Flow (4.54, e=0.40, v=0.59)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| max_top1_energy_or_caveat | 0.65 | top1 energy 0.55, caveat shown | yes |
| genre_in_top3_or_caveat | "rock" | reggae,country,r&b, caveat shown | yes |
| explanation_grounded | true | ok | yes |

### vague - PASS

Request: `play me some songs`

- Docs: (none)
- Profile: genre=lofi, mood=chill, energy=0.50, valence=0.60, acoustic=False, mode=balanced, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 1 (using #1); caveats: Your request didn't match any mood, activity or genre notes, so these are general picks - try adding a mood, activity or genre.
- Confidence: 0.71 (medium); lowered by: -0.25 no knowledge doc matched the request; -0.04 top score only 94% of max
- Top 5: Midnight Coding (7.97, e=0.42, v=0.56), Library Rain (7.58, e=0.35, v=0.60), Focus Flow (6.87, e=0.40, v=0.59), Spacewalk Thoughts (5.83, e=0.28, v=0.65), Coffee Shop Stories (5.21, e=0.37, v=0.71)

| Property | Expected | Actual | Pass |
|---|---|---|---|
| has_caveat | true | 1 caveat(s) | yes |
| explanation_grounded | true | ok | yes |

### reject-empty - PASS

Request: `""`

Rejected by rule `empty`: Tell me what you'd like to hear, e.g. 'upbeat songs for a road trip'.

| Property | Expected | Actual | Pass |
|---|---|---|---|
| rejected | "empty" | empty | yes |

### reject-too-long - PASS

Request: `I want some songs for a long drive through the mountains with my family, something that everyone in the car can enjoy...`

Rejected by rule `too_long`: Please keep requests under 300 characters.

| Property | Expected | Actual | Pass |
|---|---|---|---|
| rejected | "too_long" | too_long | yes |

### reject-weather - PASS

Request: `what's the weather tomorrow`

Rejected by rule `off_topic`: I can only help with music recommendations - try describing a mood, activity, or genre.

| Property | Expected | Actual | Pass |
|---|---|---|---|
| rejected | "off_topic" | off_topic | yes |

### reject-code - PASS

Request: `write me a python function that sorts a list`

Rejected by rule `off_topic`: I can only help with music recommendations - try describing a mood, activity, or genre.

| Property | Expected | Actual | Pass |
|---|---|---|---|
| rejected | "off_topic" | off_topic | yes |
