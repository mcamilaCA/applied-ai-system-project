# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

Tunefy

---

## 2. Intended Use  

This system is for those who like to discover new hits that they will (probably) like. Based on user preferences, it analyzes the songs stored and provides the user with a top 5 of new songs they might want to give a try. 

The system is currently a class project, and as such, assumptions such as importance of user preferences are made to simplify the development process.

---

## 3. How the Model Works  

This system asks for 4 or 5 user preferences:  genre, mood, energy, acousticness and danceability in order to find songs they will like. 

The probabily of likelyhood is calculated by checking how many of those preferences a song actually lines up with, and giving it more credit the closer the match — a song with the same genre and mood as the listener, and an energy and acoustic feel close to what they asked for, ends up looking like a much stronger pick than a song that only checks one of those boxes.

The model turns the user preferences into a score by handing out points for each trait that lines up with what the listener wants. Genre and mood are treated as "it either matches or it doesn't," so those hand out a full chunk of points or none at all. Energy and how acoustic a song sounds are treated more like a dial — the closer a song's numbers are to what the listener asked for, the more of those points it earns, even if it's not a perfect match. All of the points get combined into a single score out of 100, and songs are shown to the listener in order from the highest score to the lowest.

Main changes in the starter logic are moving away from a loose, case-insensitive comparison for genre and mood to a strict, exact-match comparison; switching from a handful of arbitrary bonus points to a clear, weighted formula where each preference's importance is spelled out as a percentage of the total; treating "likes acoustic songs" as a sliding scale instead of a simple yes/no cutoff; turning danceability into a tie-breaker used only when two songs are otherwise equally good, rather than something that adds to the main score; and adding a plain-language breakdown for every recommendation so a listener can see exactly why a song was suggested to them.

---

## 4. Data  

The catalog has 18 songs in total. It started as a smaller starter set of 10 songs (covering pop, lofi, rock, ambient, jazz, synthwave, and indie pop), and I added 8 more songs on top of that — one each in folk, metal, R&B, EDM, country, hip-hop, classical, and reggae — to give the system a wider range of genres to recommend from. No songs were removed.

Even with that addition, the catalog is still pretty thin once you break it down: pop has 2 songs and lofi has 3, but every other genre — rock, ambient, jazz, synthwave, indie pop, folk, metal, R&B, EDM, country, hip-hop, classical, and reggae — only has a single song representing it. Moods are similarly uneven: chill shows up 3 times, and happy, intense, and nostalgic each show up twice, but moods like relaxed, moody, focused, angry, romantic, euphoric, confident, peaceful, and carefree only appear once. That means for most genres or moods, there's no real "second option" to choose between — the system either has the one song that fits, or it doesn't.

There's also a fair amount of musical taste missing altogether. There's nothing for genres like Latin/reggaeton, K-pop, punk, blues, gospel, or other world/international styles, and no holiday or instrumental/soundtrack music. On the mood side, there's no real "sad" or "melancholic" bucket (the closest is "nostalgic"), and nothing that captures a "meditative" or "aggressive party" vibe distinct from what's already there. So a listener whose taste falls outside this fairly narrow slice won't have much for the system to actually recommend from.

---

## 5. Strengths  

The system works best for listeners whose favorite genre and mood happen to be ones the catalog actually has more than one song for right now, that's mainly pop and lofi/chill. For those listeners, there are enough songs sharing their favorite genre and mood that the energy and acoustic-feel preferences actually get to do their job and separate a great match from an okay one, instead of the recommendation being decided by there just being one song to pick from.

The scoring seems to correctly capture the "how close is this song to what I want" feeling for energy and acousticness. A listener who says they want high-energy, non-acoustic, happy pop reliably gets bright, upbeat, electronic-leaning songs at the top, and a listener who wants mellow, acoustic, chill music gets calm, unplugged-sounding songs at the top, rather than something that merely matches the genre label but feels totally different in energy. The written explanation attached to each recommendation also lines up with the actual score, so a listener can see exactly why a song was picked and that reasoning matches what they'd expect just from listening to it.

When I tried this out with two sample listeners, an upbeat, happy, high-energy pop fan and a mellow, chill, acoustic-leaning lofi fan, the top recommendations for each matched what I'd intuitively expect someone with that taste to enjoy, which was reassuring to see given how simple the underlying scoring really is.

---

## 6. Limitations and Bias 

The way the weights are set up currently makes it so that 65% of the grade is composed genre & mood, which means that if there is a wrong labels for any of those, the song will most likely not be suggested as a very strong option. Since the data is limited and the catalog uses determined punctuation, if the user enters their preferences in a different manner, the system will not be able to pick the up; for example, RnB instead of R&B
Moreover, due to the limited data, the availability of songs of certain range are limited, a user that likes pop will be biased if compared to one that likes heavy metal.

**Update:** the specific silent-failure bugs below (NaN energy, the mismatched `acousticness`/`likes_acoustic` field name, and the trailing-space genre typo) are no longer silent. A validation/planning step (`src/planner.py`) now runs before scoring: it either excludes an invalid continuous preference (energy/acousticness) from scoring and logs a warning, or, for a missing/invalid genre or mood where there's no safe fallback, rejects the request outright with a clear error instead of returning a ranked list. See §7 and §8 for what's still open.

## 7. Evaluation  

The system seems to behave as expected, songs that have similar characteristics than the user preferences are recommended. 

The profiles tested were: 
1. An upbeat pop fan who wants happy, high-energy tracks with a produced/electronic (non-acoustic) sound.
2. A mellow lofi/chill listener wanting low-to-moderate energy and acoustic instrumentation, while also wanting maximally danceable tracks.

I experimented with different weights and the system still recommended the same songs (or the first 3 same songs) but with different weights, which makes me think the recipe for likeness is stable.

Each song recommended showcases their similarity score in refence to the user likes and its ranked by such.

I also tried a handful of "messy" profiles on purpose, to see how the system handles input that isn't perfectly clean, and it exposed a few real weak spots:

- Typing the acoustic preference as `True`/`False` instead of a number gave the exact same recommendations as leaving it out entirely, since the scoring code is actually looking for a differently-named field. In other words, telling the system you like or dislike acoustic songs this way silently does nothing.
- Adding one stray trailing space to the genre ("pop " instead of "pop") was enough to knock the single best match (Sunrise City, previously the clear #1 pick) all the way down, because the genre comparison expects an exact character-for-character match.
- Leaving energy undefined (technically, a `NaN` value) didn't produce an error, but it quietly broke the ranking; every song ended up with an undefined score and the "recommendations" came back in basically the same order they appear in the CSV, not actually ranked by fit at all.
- Asking for maximum danceability alongside a chill/lofi preference had no visible effect on the results, since danceability is only ever consulted to break an exact tie in score, and ties essentially never happen once energy and acousticness are involved.

None of these caused the program to crash, which sounds good on the surface, but it also means a listener could type a slightly-off preference and get back a confident-looking, fully-scored list of "recommendations" that don't actually reflect what they asked for, with nothing telling them something went wrong.

**Update:** I re-ran all four of these exact inputs after adding the planning/logging layer. The `NaN` energy case no longer produces a `NaN` score — energy is excluded from scoring and a warning notice explains why. The `acousticness: True/False` case is now recognized as a likely `likes_acoustic` value and applied, with a notice explaining the correction. The trailing-space genre case is trimmed before matching, so `"pop "` behaves like `"pop"` again. The danceability-tie-break case is unchanged (still a genuine design limitation, not a bug — see §8).
---

## 8. Future Work  

For additional features, I'd want to let listeners describe their taste with more nuance than one exact genre and one exact mood, like picking a couple of genres they enjoy, or rating how important each preference is to them, plus maybe a tempo or "lyrics vs instrumental" preference, since those get completely ignored right now.

For explaining recommendations, I'd want to move past the raw point breakdown and instead call out, in a sentence or two, the one or two reasons a song was picked ("this made the list mostly because it matches your mood and energy, even though it's a different genre than usual"), so the reasoning reads more like a friend's recommendation and less like a receipt.

**Update:** this is now implemented as an opt-in "✨ AI explanation" alongside the raw breakdown — see §10.

For diversity, I'd want to add a genre/mood "closeness" map so related styles get partial credit instead of zero (so a pop fan can still get credit for indie pop, for example), and maybe deliberately slip in one or two songs outside the listener's usual pattern so the recommendations don't just reinforce the same narrow slice of the catalog every time.

For handling messier or more complex tastes, I'd want the system to clean up user input before scoring it, trimming extra spaces, ignoring letter case, catching typos or mismatched field names instead of silently ignoring them, and refusing to produce a ranked list at all if a preference like energy comes in undefined, rather than quietly returning a meaningless order. I'd also want a bigger, more evenly spread catalog so listeners with less common tastes have more than one song to choose from.

**Update:** most of the input-cleaning half of this is now implemented (whitespace trimming, mismatched-field-name recovery for acousticness, excluding invalid continuous values from scoring, and hard-rejecting a missing genre/mood instead of silently ranking). I deliberately kept genre/mood as case-sensitive exact matches rather than adding case-insensitivity here, since that strictness was an intentional earlier design choice (see "How The System Works" in the README), not a bug. What's still open: the genre/mood closeness map, deliberate diversity injection, and the bigger/more evenly spread catalog are all unchanged.

---

## 9. AI Features: RAG + Reliability

Two AI-powered features sit on top of the deterministic scoring described in §3, neither of which changes the scoring itself:

1. **Natural-language taste parser.** A listener can describe their taste in plain English instead of filling out the form. This is retrieval-augmented: the description is first matched against a small local knowledge base (`data/knowledge_base.json` — short reference notes on each catalog genre, a mood-word glossary, and energy/acousticness/decade vocabulary mappings) to ground how words like "upbeat" or "retro" should be interpreted, and only then handed to an LLM to produce a structured preferences dict. That dict is validated by the exact same `plan_user_prefs` pipeline (§3) a manually-typed profile goes through — a malformed field coming out of the LLM (wrong type, unrecognized genre) gets caught the same way a typo would, rather than needing separate validation logic.
2. **Grounded explanations.** Optionally, the raw per-feature point breakdown for a recommendation can be turned into a short natural-language paragraph. The prompt explicitly restricts the model to only the score breakdown and retrieved reference notes as source material, specifically to prevent it from inventing details about a song or artist that aren't actually supported.

**Why grounding matters here specifically:** the recommender's whole value proposition (§5) is that a listener can trust the "why" behind a pick. An ungrounded LLM explanation that sounds confident but states something untrue would undermine that more than the old plain point-breakdown ever could, since it reads as more authoritative while being less checkable.

**Reliability harness.** Introducing an LLM call means, for the first time, the same input can produce a different output on two different runs, and generated text is capable of inventing details the retrieval step didn't actually support. `src/reliability.py` runs a small set of golden cases (`data/eval_cases.json`) through three checks:
- A profile-score regression case: exact-match top-song check against the deterministic core, no LLM involved — a sanity guard that nothing above accidentally broke §3's scoring.
- NL-parse cases: does the parsed profile match the expected genre/preference, and how *consistent* is the parse across repeated runs of the same query (`ConsistencyChecker`)?
- An explanation case: how *grounded* is the generated text in the score breakdown and retrieved notes it was allowed to draw on (`GroundednessChecker`, a keyword-overlap heuristic, not another LLM call), and how consistent is repeated generation?

Run `python -m src.reliability` to produce `logs/reliability_report.md`.

**Limitations of this iteration:** the knowledge base is small (~20 documents, one per catalog genre plus a few vocabulary docs) and retrieval is plain keyword/tag overlap rather than embeddings — transparent and easy to debug, but it will miss a query that's semantically related but shares no words with any document. The eval set is five cases, enough to catch an obvious regression but not enough to characterize the AI features' behavior broadly. `GroundednessChecker`'s keyword-overlap scoring will also under-score a paraphrase that's genuinely grounded but doesn't reuse the source wording, and over-score a claim that happens to share common words with the context without actually being supported by them. Link-based "find something similar to this song" input (YouTube/Spotify links) and catalog expansion were both considered for this iteration and deliberately deferred to keep scope realistic — see prior brainstorming.

---

## 10. Personal Reflection  

As a music lover, I had always been curious about how the recommendation system worked and, even though I know this is not how full scale algorithms are, it did serve to open my eyes and demistify its complexity. Now I have a better understanding of how it might work, and even though it still feels like magic, at least I am able to imagine what goes behind the scenes.

I was surprised to learn how there are multiple scores (& different ways to set up scoring systems), and my brain is still processing how we get to a likeability score based on data like genre and others, but I hope with more time working with it, it will become more intuitive. 
