# VibeMatch Evaluation Results

- Generated: 2026-11-15 13:48
- Mode: **offline**
- 15 cases x 3 runs each = 45 agent runs

## Summary

| Metric | Value |
|---|---|
| Cases passed | 15/15 (100%) |
| Properties passed | 52/52 (100%) |
| Consistency (identical top 5 / rejection across 3 runs) | 15/15 (100%) |
| guardrail rejections (all runs) | 12 (4.0 per pass) |
| repairs (total) (all runs) | 18 (6.0 per pass) |
| runs with >=1 repair (all runs) | 18 (6.0 per pass) |
| self-check retries (all runs) | 18 (6.0 per pass) |
| runs with caveats (all runs) | 12 (4.0 per pass) |

## Cases

| Case | Category | Request | Result | Properties | Consistent |
|---|---|---|---|---|---|
| study-rain | normal | something chill for studying on a rainy night | PASS | 5/5 | yes |
| gym-hype | normal | hype songs for the gym | PASS | 4/4 | yes |
| sleep-calm | normal | calm music to help me fall asleep | PASS | 5/5 | yes |
| road-trip | normal | upbeat songs for a road trip with friends | PASS | 4/4 | yes |
| metal-lifting | normal | angry heavy metal for lifting weights | PASS | 5/5 | yes |
| sad-not-slow | edge | sad songs but not too slow | PASS | 5/5 | yes |
| kpop-party | edge | k-pop for a party | PASS | 5/5 | yes |
| sad-energetic | edge | sad but energetic | PASS | 5/5 | yes |
| country-heartbreak | edge | country songs about heartbreak | PASS | 5/5 | yes |
| quiet-rock | edge | rock but not too loud | PASS | 3/3 | yes |
| vague | edge | play me some songs | PASS | 2/2 | yes |
| reject-empty | reject | "" | PASS | 1/1 | yes |
| reject-too-long | reject | I want some songs for a long drive through the mountains ... | PASS | 1/1 | yes |
| reject-weather | reject | what's the weather tomorrow | PASS | 1/1 | yes |
| reject-code | reject | write me a python function that sorts a list | PASS | 1/1 | yes |

## Details (run 1 of each case)

### study-rain - PASS

Request: `something chill for studying on a rainy night`

- Docs: rainy_day.md, studying.md, road_trip.md
- Profile: genre=lofi, mood=chill, energy=0.41, valence=0.53, acoustic=True, mode=balanced, diverse=False
- Plan source: offline; explanation: template
- Repairs: none
- Attempts: 1 (using #1); caveats: none
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
