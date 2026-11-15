# Human Evaluation

Generated 2026-11-15 from real offline runs (`python -m src.agent "<request>" --offline`). The automated eval checks properties; this sheet checks whether a person would actually be happy with the results.

## How to rate

Rate each request against these criteria:

1. **Fits the request's vibe.** Do the songs match the mood, activity and energy the request describes?
2. **Explanation is accurate.** It only mentions songs that are really in the results, and what it says matches their scoring reasons. The explanation and reasons for each run are under [Run details](#run-details).
3. **I would actually play these.** Would I put these songs on for this situation?

Scales:

- **Fits request? (1-5):** 1 = wrong vibe, 2 = mostly off, 3 = mixed, 4 = good with one weak pick, 5 = exactly right.
- **Explanation accurate? (Y/N):** Y only if every claim matches the results and reasons.
- **Pass/Fail:** Pass if Fits >= 4, the explanation is accurate, and I would play them.

## Ratings

| # | Request | Top 3 songs | Confidence | Fits request? (1-5) | Explanation accurate? (Y/N) | Pass/Fail | My notes |
|---|---|---|---|---|---|---|---|
| 1 | something chill for studying on a rainy night | 1. Midnight Coding - LoRoom<br>2. Library Rain - Paper Lanterns<br>3. Focus Flow - LoRoom | 0.99 (high) |5|Y|Pass|  Perfect for a study sesh |
| 2 | hype songs for the gym | 1. Gym Hero - Max Pulse<br>2. Sunrise City - Neon Echo<br>3. Fuego en la Plaza - Los Faroles | 0.87 (high) | 5|Y|Pass|It's definetly meant for a gym sesh  |
| 3 | sad songs but not too slow | 1. Rust in the Rain - Delta Marrow<br>2. Afterglow Static - Kaito Mere<br>3. Night Drive Loop - Neon Echo | 0.66 (medium) |5|Y  |Pass  |Good for a depressing day  |
| 4 | k-pop for a party | 1. Sunrise City - Neon Echo<br>2. Rooftop Lights - Indigo Parade<br>3. Gym Hero - Max Pulse | 0.94 (high) |2|N|Failed  |Failed to meet the vibes even though logically makes sense  |
| 5 | relaxing jazz for a dinner party | 1. Coffee Shop Stories - Slow Stereo<br>2. Focus Flow - LoRoom<br>3. Midnight Coding - LoRoom | 0.92 (high) |5| Y |Pass  |Meets the vibes of a cozy jazz dinner party  |
| 6 | music for a road trip with friends | 1. Dust Road Letters - June Harlan<br>2. Rooftop Lights - Indigo Parade<br>3. Sunrise City - Neon Echo | 0.87 (high) |5| y| Pass |Good for a roadtrip  |

**Human evaluation summary:** 5 of 6 passed; average fit 4.2/5. The agent struggled
with mixed requests like "sad but not too slow," where mood and energy pull in
opposite directions.

## Run details

### 1. something chill for studying on a rainy night

- **Docs retrieved:** rainy_day.md, studying.md, road_trip.md
- **Profile:** lofi / chill, energy 0.41, valence 0.53, acoustic, mode balanced
- **Repairs:** none
- **Self-check:** 1 attempt(s), used #1
- **Confidence:** 0.99 (high) - top score 98% of max, no repairs, no retries; lowered by: -0.01 top score only 98% of max
- **Top 3 with scoring reasons:**
  1. Midnight Coding - LoRoom (lofi, chill, energy 0.42), score 8.33 / 8.5: genre match: lofi (+2.50); mood match: chill (+2.00); energy 0.42 vs target 0.41 (+2.00); valence 0.56 vs target 0.53 (+1.48); acousticness 0.71, likes acoustic (+0.35)
  2. Library Rain - Paper Lanterns (lofi, chill, energy 0.35), score 8.25 / 8.5: genre match: lofi (+2.50); mood match: chill (+2.00); energy 0.35 vs target 0.41 (+1.91); valence 0.60 vs target 0.53 (+1.41); acousticness 0.86, likes acoustic (+0.43)
  3. Focus Flow - LoRoom (lofi, focused, energy 0.40), score 7.32 / 8.5: genre match: lofi (+2.50); mood family match: focused ~ chill (+1.00); energy 0.40 vs target 0.41 (+2.00); valence 0.59 vs target 0.53 (+1.43); acousticness 0.78, likes acoustic (+0.39)
- **Explanation shown to the user:**

  ```text
  Based on [rainy_day.md, studying.md, road_trip.md], I looked for lofi / chill songs around energy 0.41 and valence 0.53 with an acoustic sound.
  #1 Midnight Coding by LoRoom: genre match: lofi, mood match: chill, energy 0.42 vs target 0.41.
  #2 Library Rain by Paper Lanterns: genre match: lofi, mood match: chill, energy 0.35 vs target 0.41.
  #3 Focus Flow by LoRoom: genre match: lofi, energy 0.40 vs target 0.41, valence 0.59 vs target 0.53.
  #4 Spacewalk Thoughts by Orbit Bloom: mood match: chill, energy 0.28 vs target 0.41, related genre: ambient ~ lofi.
  #5 Coffee Shop Stories by Slow Stereo: energy 0.37 vs target 0.41, related genre: jazz ~ lofi, mood family match: relaxed ~ chill.
  ```

### 2. hype songs for the gym

- **Docs retrieved:** workout.md, mood_driven.md
- **Profile:** pop / energetic, energy 0.89, valence 0.62, electric, mode energy-focused
- **Repairs:** favorite_mood 'hype' -> 'energetic'
- **Self-check:** 1 attempt(s), used #1
- **Confidence:** 0.87 (high) - top score 87% of max, 1 repair, no retries; lowered by: -0.08 top score only 87% of max; -0.05 1 repair to the plan
- **Top 3 with scoring reasons:**
  1. Gym Hero - Max Pulse (pop, intense, energy 0.93), score 7.39 / 8.5: genre match: pop (+1.50); mood family match: intense ~ energetic (+0.75); energy 0.93 vs target 0.89 (+3.92); valence 0.77 vs target 0.62 (+0.75); acousticness 0.05, prefers non-acoustic (+0.47)
  2. Sunrise City - Neon Echo (pop, happy, energy 0.82), score 6.22 / 8.5: genre match: pop (+1.50); no mood match: happy (+0.00); energy 0.82 vs target 0.89 (+3.76); valence 0.84 vs target 0.62 (+0.55); acousticness 0.18, prefers non-acoustic (+0.41)
  3. Fuego en la Plaza - Los Faroles (latin, energetic, energy 0.86), score 6.17 / 8.5: no genre match: latin (+0.00); mood match: energetic (+1.50); energy 0.86 vs target 0.89 (+3.96); valence 0.88 vs target 0.62 (+0.43); acousticness 0.45, prefers non-acoustic (+0.28)
- **Explanation shown to the user:**

  ```text
  Based on [workout.md, mood_driven.md], I looked for pop / energetic songs around energy 0.89 and valence 0.62 with an electric sound.
  #1 Gym Hero by Max Pulse: energy 0.93 vs target 0.89, genre match: pop, mood family match: intense ~ energetic.
  #2 Sunrise City by Neon Echo: energy 0.82 vs target 0.89, genre match: pop, valence 0.84 vs target 0.62.
  #3 Fuego en la Plaza by Los Faroles: energy 0.86 vs target 0.89, mood match: energetic, valence 0.88 vs target 0.62.
  #4 Storm Runner by Voltline: energy 0.91 vs target 0.89, valence 0.48 vs target 0.62, mood family match: intense ~ energetic.
  #5 Concrete Psalms by Verse Theory: energy 0.80 vs target 0.89, valence 0.62 vs target 0.62, mood family match: confident ~ energetic.
  ```

### 3. sad songs but not too slow

- **Docs retrieved:** mood_low.md, rainy_day.md, sleep.md
- **Profile:** blues / sad, energy 0.50, valence 0.23, acoustic, mode mood-first
- **Repairs:** none
- **Self-check:** 3 attempt(s), used #1; caveat: No song in the catalog fits both the style and the energy you asked for; the closest matches are shown.
- **Confidence:** 0.66 (medium) - top score 93% of max, no repairs, 2 retries; lowered by: -0.20 2 self-check retries; -0.10 weak retrieval match (top doc score 2.36); -0.04 top score only 93% of max
- **Top 3 with scoring reasons:**
  1. Rust in the Rain - Delta Marrow (blues, sad, energy 0.33), score 7.94 / 8.5: genre match: blues (+1.50); mood match: sad (+3.50); energy 0.33 vs target 0.50 (+1.05); valence 0.22 vs target 0.23 (+1.50); acousticness 0.78, likes acoustic (+0.39)
  2. Afterglow Static - Kaito Mere (electronic, melancholy, energy 0.30), score 4.15 / 8.5: no genre match: electronic (+0.00); mood family match: melancholy ~ sad (+1.75); energy 0.30 vs target 0.50 (+0.91); valence 0.28 vs target 0.23 (+1.45); acousticness 0.08, likes acoustic (+0.04)
  3. Night Drive Loop - Neon Echo (synthwave, moody, energy 0.75), score 3.19 / 8.5: no genre match: synthwave (+0.00); mood family match: moody ~ sad (+1.75); energy 0.75 vs target 0.50 (+0.69); valence 0.49 vs target 0.23 (+0.64); acousticness 0.22, likes acoustic (+0.11)
- **Explanation shown to the user:**

  ```text
  Based on [mood_low.md, rainy_day.md, sleep.md], I looked for blues / sad songs around energy 0.50 and valence 0.23 with an acoustic sound.
  #1 Rust in the Rain by Delta Marrow: mood match: sad, genre match: blues, valence 0.22 vs target 0.23.
  #2 Afterglow Static by Kaito Mere: mood family match: melancholy ~ sad, valence 0.28 vs target 0.23, energy 0.30 vs target 0.50.
  #3 Night Drive Loop by Neon Echo: mood family match: moody ~ sad, energy 0.75 vs target 0.50, valence 0.49 vs target 0.23.
  #4 Tempest Overture by Varga Chamber Ensemble: valence 0.30 vs target 0.23, energy 0.72 vs target 0.50, acousticness 0.95, likes acoustic.
  #5 Coffee Shop Stories by Slow Stereo: energy 0.37 vs target 0.50, related genre: jazz ~ blues, acousticness 0.89, likes acoustic.
  Note: No song in the catalog fits both the style and the energy you asked for; the closest matches are shown.
  ```

### 4. k-pop for a party

- **Docs retrieved:** party.md, genre_notes.md, mood_bright.md
- **Profile:** pop / happy, energy 0.81, valence 0.83, electric, mode energy-focused
- **Repairs:** favorite_genre 'k-pop' -> 'pop'
- **Self-check:** 1 attempt(s), used #1
- **Confidence:** 0.94 (high) - top score 99% of max, 1 repair, no retries; lowered by: -0.05 1 repair to the plan; -0.01 top score only 99% of max
- **Top 3 with scoring reasons:**
  1. Sunrise City - Neon Echo (pop, happy, energy 0.82), score 8.41 / 8.5: genre match: pop (+1.50); mood match: happy (+1.50); energy 0.82 vs target 0.81 (+4.00); valence 0.84 vs target 0.83 (+1.00); acousticness 0.18, prefers non-acoustic (+0.41)
  2. Rooftop Lights - Indigo Parade (indie pop, happy, energy 0.76), score 7.46 / 8.5: related genre: indie pop ~ pop (+0.75); mood match: happy (+1.50); energy 0.76 vs target 0.81 (+3.88); valence 0.81 vs target 0.83 (+1.00); acousticness 0.35, prefers non-acoustic (+0.33)
  3. Gym Hero - Max Pulse (pop, intense, energy 0.93), score 6.27 / 8.5: genre match: pop (+1.50); no mood match: intense (+0.00); energy 0.93 vs target 0.81 (+3.34); valence 0.77 vs target 0.83 (+0.96); acousticness 0.05, prefers non-acoustic (+0.47)
- **Explanation shown to the user:**

  ```text
  Based on [party.md, genre_notes.md, mood_bright.md], I looked for pop / happy songs around energy 0.81 and valence 0.83 with an electric sound.
  #1 Sunrise City by Neon Echo: energy 0.82 vs target 0.81, genre match: pop, mood match: happy.
  #2 Rooftop Lights by Indigo Parade: energy 0.76 vs target 0.81, mood match: happy, valence 0.81 vs target 0.83.
  #3 Gym Hero by Max Pulse: energy 0.93 vs target 0.81, genre match: pop, valence 0.77 vs target 0.83.
  #4 Fuego en la Plaza by Los Faroles: energy 0.86 vs target 0.81, valence 0.88 vs target 0.83, acousticness 0.45, prefers non-acoustic.
  #5 Concrete Psalms by Verse Theory: energy 0.80 vs target 0.81, valence 0.62 vs target 0.83, acousticness 0.12, prefers non-acoustic.
  ```

### 5. relaxing jazz for a dinner party

- **Docs retrieved:** mood_calm.md, party.md, sleep.md
- **Profile:** jazz / relaxed, energy 0.53, valence 0.70, acoustic, mode mood-first
- **Repairs:** favorite_mood 'relaxing' -> 'relaxed'
- **Self-check:** 1 attempt(s), used #1
- **Confidence:** 0.92 (high) - top score 95% of max, 1 repair, no retries; lowered by: -0.05 1 repair to the plan; -0.03 top score only 95% of max
- **Top 3 with scoring reasons:**
  1. Coffee Shop Stories - Slow Stereo (jazz, relaxed, energy 0.37), score 8.04 / 8.5: genre match: jazz (+1.50); mood match: relaxed (+3.50); energy 0.37 vs target 0.53 (+1.09); valence 0.71 vs target 0.70 (+1.50); acousticness 0.89, likes acoustic (+0.45)
  2. Focus Flow - LoRoom (lofi, focused, energy 0.40), score 5.39 / 8.5: related genre: lofi ~ jazz (+0.75); mood family match: focused ~ relaxed (+1.75); energy 0.40 vs target 0.53 (+1.21); valence 0.59 vs target 0.70 (+1.29); acousticness 0.78, likes acoustic (+0.39)
  3. Midnight Coding - LoRoom (lofi, chill, energy 0.42), score 5.31 / 8.5: related genre: lofi ~ jazz (+0.75); mood family match: chill ~ relaxed (+1.75); energy 0.42 vs target 0.53 (+1.29); valence 0.56 vs target 0.70 (+1.17); acousticness 0.71, likes acoustic (+0.35)
- **Explanation shown to the user:**

  ```text
  Based on [mood_calm.md, party.md, sleep.md], I looked for jazz / relaxed songs around energy 0.53 and valence 0.70 with an acoustic sound.
  #1 Coffee Shop Stories by Slow Stereo: mood match: relaxed, genre match: jazz, valence 0.71 vs target 0.70.
  #2 Focus Flow by LoRoom: mood family match: focused ~ relaxed, valence 0.59 vs target 0.70, energy 0.40 vs target 0.53.
  #3 Midnight Coding by LoRoom: mood family match: chill ~ relaxed, energy 0.42 vs target 0.53, valence 0.56 vs target 0.70.
  #4 Library Rain by Paper Lanterns: mood family match: chill ~ relaxed, valence 0.60 vs target 0.70, energy 0.35 vs target 0.53.
  #5 Spacewalk Thoughts by Orbit Bloom: mood family match: chill ~ relaxed, valence 0.65 vs target 0.70, energy 0.28 vs target 0.53.
  ```

### 6. music for a road trip with friends

- **Docs retrieved:** road_trip.md, party.md
- **Profile:** country / happy, energy 0.73, valence 0.73, electric, mode balanced
- **Repairs:** none
- **Self-check:** 1 attempt(s), used #1
- **Confidence:** 0.87 (high) - top score 78% of max, no repairs, no retries; lowered by: -0.13 top score only 78% of max
- **Top 3 with scoring reasons:**
  1. Dust Road Letters - June Harlan (country, hopeful, energy 0.58), score 6.62 / 8.5: genre match: country (+2.50); mood family match: hopeful ~ happy (+1.00); energy 0.58 vs target 0.73 (+1.51); valence 0.70 vs target 0.73 (+1.48); acousticness 0.74, prefers non-acoustic (+0.13)
  2. Rooftop Lights - Indigo Parade (indie pop, happy, energy 0.76), score 5.69 / 8.5: no genre match: indie pop (+0.00); mood match: happy (+2.00); energy 0.76 vs target 0.73 (+1.98); valence 0.81 vs target 0.73 (+1.38); acousticness 0.35, prefers non-acoustic (+0.33)
  3. Sunrise City - Neon Echo (pop, happy, energy 0.82), score 5.51 / 8.5: no genre match: pop (+0.00); mood match: happy (+2.00); energy 0.82 vs target 0.73 (+1.81); valence 0.84 vs target 0.73 (+1.29); acousticness 0.18, prefers non-acoustic (+0.41)
- **Explanation shown to the user:**

  ```text
  Based on [road_trip.md, party.md], I looked for country / happy songs around energy 0.73 and valence 0.73 with an electric sound.
  #1 Dust Road Letters by June Harlan: genre match: country, energy 0.58 vs target 0.73, valence 0.70 vs target 0.73.
  #2 Rooftop Lights by Indigo Parade: mood match: happy, energy 0.76 vs target 0.73, valence 0.81 vs target 0.73.
  #3 Sunrise City by Neon Echo: mood match: happy, energy 0.82 vs target 0.73, valence 0.84 vs target 0.73.
  #4 Hollow Porch Light by Wren & Willow: energy 0.68 vs target 0.73, related genre: folk ~ country, valence 0.58 vs target 0.73.
  #5 Island Slowdown by Roots Harbor: energy 0.55 vs target 0.73, valence 0.85 vs target 0.73, mood family match: carefree ~ happy.
  ```
