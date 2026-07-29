# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

Tunefy

---

## 2. Intended Use  

This system is for those who like to discover new hits that they will (probably) like. Based on user preferences, it analyzes the songs stored and provides the user with a top 5 of new songs they might want to give a try. 

The system is currently a class project, and as such, assumptions such as importance of user preferences are made to simplify the development process.

---

## 3. How the Model Works  

Genre and mood are required; everything else is optional. A listener can also specify energy, whether they like acoustic music (or, for finer control, a specific 0-1 acousticness target instead), a preferred release decade, whether they want instrumental tracks, a "clean only" filter, and a preferred danceability level. Leaving an optional preference out never penalizes a song on that dimension — it just stops that dimension from being able to discriminate between songs.

Every song gets a single score out of 100, built from six weighted dimensions:

1. **Genre — 30%.** Categorical: exact match or nothing. If a song's genre doesn't match but the song's free-text `mood_tags` happen to include the listener's favorite mood, that's scored under mood (below), not genre — genre itself has no partial-credit path.
2. **Mood — 25%.** Categorical, with one partial-credit exception: a song whose primary mood doesn't match the listener's but whose `mood_tags` (e.g. "nostalgic", "aggressive", "bright") include it still earns half of mood's points.
3. **Energy — 15%** and **4. Acousticness — 10%.** Continuous, distance-based: the closer a song's value is to the target, the more of the available points it earns, even without a perfect match.
5. **Instrumentalness — 10%** and **6. Release decade — 10%.** Same distance/match logic as energy and mood, but optional — a listener with no opinion gets full credit on that dimension for every song, so these two only start separating songs once the listener actually states a preference.

Two things sit outside the score entirely: a "clean only" preference filters out explicit-content songs before scoring rather than docking points from them, and preferred danceability plus an opt-in "prefer popular" flag are only ever used to break a tie between two songs that already have the same score — they never add points on their own.

Genre and mood comparisons are strict, case-sensitive, exact-string matches by design (see section 6 for the trade-off this creates). The one exception the system does make automatically is trimming leading/trailing whitespace, handled by the validation layer described next.

Before any of that scoring happens, a validation/planning step (`src/planner.py`) checks the raw preferences first: a missing or invalid genre/mood has no sensible fallback, so it's rejected outright with a clear error instead of producing a ranking, while a missing or invalid energy/acousticness value is excluded from scoring instead of silently corrupting it — every decision is logged to `logs/recommender.log` and surfaced to the listener as a notice.

---

## 4. Data  

**Update:** the catalog has since been rebuilt from an 18-fictional-song starter set into 600 real, licensed-artist songs — 30 genres (pop, hip-hop, rock, latin, EDM, R&B, k-pop, country, afrobeats, indie, reggaeton, jazz, classical, metal, folk, blues, gospel, punk, funk, lofi, dream pop, synthwave, shoegaze, city pop, bossa nova, french house, ambient, darkwave, phonk, and amapiano), with exactly 20 songs in every genre. Each row now also carries `popularity`, `release_decade`, `mood_tags` (free-text tags used for the mood partial-credit path in section 3), `explicit_content`, and `instrumentalness`, on top of the original genre/mood/energy/tempo/valence/danceability/acousticness fields.

Genre is perfectly even by construction, but mood and decade are not. Moods range from "confident" and "moody" (70 songs each) down to "focused" (only 10 songs) — 13 moods total. Decade skews heavily toward 1990s-2010s (roughly 350 of the 600 songs), with a long thin tail of single-digit-count decades reaching back to the 1680s for older classical pieces — a listener who sets `preferred_decade` to one of those thin decades will only ever have a handful of songs to choose from, regardless of how well they match on everything else. 41 of 600 songs (~7%) are flagged `explicit_content`, which only matters if a listener turns on the `clean_only` filter.

There's still musical taste missing: no dedicated "sad"/melancholic mood bucket (closest is "moody" or "nostalgic"), and no holiday or spoken-word/podcast-adjacent content. But the earlier gap — most genres having only one song, so there was no real "second option" within a genre — is gone: every genre now has 20 songs to rank among.

---

## 5. Strengths  

**Update:** now that every genre has 20 songs instead of just one or two, the old caveat about only pop/lofi listeners having real competition among their matches no longer applies — any listener's favorite genre now has 20 candidates for the energy/acousticness/decade preferences to actually rank among, instead of the outcome being decided by there only being one song that fits the label at all.

The scoring still correctly captures the "how close is this song to what I want" feeling for energy and acousticness on real songs. A listener who wants high-energy, non-acoustic, happy pop reliably surfaces bright, upbeat, electronic-leaning real tracks ("Blinding Lights," "Sunflower," "Levitating") over songs that only match the genre label but feel different energy-wise, and a mellow, chill, acoustic-leaning lofi listener surfaces calmer, more acoustic real tracks (e.g. by Nujabes, Kupla) at the top instead. The written explanation attached to each recommendation still lines up with the actual score breakdown, so a listener can see exactly why a song was picked.

With 20 songs per genre, exact or near-exact score ties are now common — a spot check against one profile found 131 distinct groups of songs tied at the same rounded score — so the danceability/`prefer_popular` tie-breakers (section 3) are exercised far more often than they were on the original 18-song catalog, where ties essentially never happened.

---

## 6. Limitations and Bias 

Genre and mood together are 55% of the score (30% + 25%), so a wrong or mismatched label on either one still keeps a song out of a strong position, even though that's down from the 65% the original weighting used. Genre matching is a strict, case-sensitive exact string comparison, so a listener typing "RnB" instead of the catalog's "R&B" — or "hiphop" instead of "hip-hop" — gets zero genre credit; the planner only trims whitespace, it doesn't normalize spelling, case, or punctuation.

**Update:** genre is no longer imbalanced (every genre has exactly 20 songs — see section 4), so the old "pop fan vs. heavy-metal fan" bias from a lopsided catalog is gone. What's replaced it: mood is still imbalanced (confident/moody at 70 songs each vs. focused at 10), and decade is heavily skewed toward 1990s-2010s, so a listener combining a common genre/mood with an uncommon `preferred_decade` can still end up with very few real options, even though the genre/mood axes themselves are now fair.

**Update:** the specific silent-failure bugs below (NaN energy, the mismatched `acousticness`/`likes_acoustic` field name, and the trailing-space genre typo) are no longer silent. A validation/planning step (`src/planner.py`) now runs before scoring: it either excludes an invalid continuous preference (energy/acousticness) from scoring and logs a warning, or, for a missing/invalid genre or mood where there's no safe fallback, rejects the request outright with a clear error instead of returning a ranked list. See section 7 and section 8 for what's still open.

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

**Update:** I re-ran all four of these exact inputs after adding the planning/logging layer. The `NaN` energy case no longer produces a `NaN` score — energy is excluded from scoring and a warning notice explains why. The `acousticness: True/False` case is now recognized as a likely `likes_acoustic` value and applied, with a notice explaining the correction. The trailing-space genre case is trimmed before matching, so `"pop "` behaves like `"pop"` again. The danceability-tie-break case is unchanged (still a genuine design limitation, not a bug — see section 8).

**Update (re-verified on the 600-song catalog, section 4):** re-ran the same messy input — `{"genre": "pop ", "mood": "happy", "energy": nan, "acousticness": True}` — against the current catalog. All three notices still fire (whitespace trimmed, NaN energy excluded, boolean acousticness recovered as `likes_acoustic`), and the result is still a meaningful top-3 ("Sunflower," "Levitating," "Havana") rather than a corrupted or CSV-order list, so the fixes hold at the new scale. Separately, a lofi/chill profile with `danceability=0.8`, `prefer_popular=True`, and `clean_only=True` now visibly changes the ranking via the tie-breakers, confirming the "ties essentially never happen" note above is specific to the old, much smaller catalog — see section 5 for the tie-count check.

---

## 8. Future Work  

For additional features, I'd want to let listeners describe their taste with more nuance than one exact genre and one exact mood, like picking a couple of genres they enjoy, or rating how important each preference is to them, plus maybe a tempo or "lyrics vs instrumental" preference, since those get completely ignored right now.

For explaining recommendations, I'd want to move past the raw point breakdown and instead call out, in a sentence or two, the one or two reasons a song was picked ("this made the list mostly because it matches your mood and energy, even though it's a different genre than usual"), so the reasoning reads more like a friend's recommendation and less like a receipt.

**Update:** this is now implemented as an opt-in "✨ AI explanation" alongside the raw breakdown — see section 10.

For diversity, I'd want to add a genre/mood "closeness" map so related styles get partial credit instead of zero (so a pop fan can still get credit for indie pop, for example), and maybe deliberately slip in one or two songs outside the listener's usual pattern so the recommendations don't just reinforce the same narrow slice of the catalog every time.

**Update:** mood now has a partial version of this — a song whose primary mood doesn't match but whose `mood_tags` include the listener's favorite mood earns half credit instead of zero (section 3). Genre still has no such path (an indie-pop fan gets zero genre credit from a pop song even though they're related), and deliberate diversity injection is still unimplemented.

For handling messier or more complex tastes, I'd want the system to clean up user input before scoring it, trimming extra spaces, ignoring letter case, catching typos or mismatched field names instead of silently ignoring them, and refusing to produce a ranked list at all if a preference like energy comes in undefined, rather than quietly returning a meaningless order. I'd also want a bigger, more evenly spread catalog so listeners with less common tastes have more than one song to choose from.

**Update:** most of the input-cleaning half of this is now implemented (whitespace trimming, mismatched-field-name recovery for acousticness, excluding invalid continuous values from scoring, and hard-rejecting a missing genre/mood instead of silently ranking). I deliberately kept genre/mood as case-sensitive exact matches rather than adding case-insensitivity here, since that strictness was an intentional earlier design choice (see "How The System Works" in the README), not a bug — though it does mean "RnB" vs. "R&B" still fails to match (section 6). The catalog itself is also no longer thin: it's grown from 18 fictional songs to 600 real ones across 30 evenly-sized genres (section 4). What's still open: the genre closeness map and deliberate diversity injection, plus the mood/decade imbalance noted in section 6.

---

## 9. AI Features: RAG + Reliability

Two AI-powered features sit on top of the deterministic scoring described in section 3, neither of which changes the scoring itself:

1. **Natural-language taste parser.** A listener can describe their taste in plain English instead of filling out the form. This is retrieval-augmented: the description is first matched against a small local knowledge base (`data/knowledge_base.json` — short reference notes on each catalog genre, a mood-word glossary, and energy/acousticness/decade vocabulary mappings) to ground how words like "upbeat" or "retro" should be interpreted, and only then handed to an LLM to produce a structured preferences dict. That dict is validated by the exact same `plan_user_prefs` pipeline (section 3) a manually-typed profile goes through — a malformed field coming out of the LLM (wrong type, unrecognized genre) gets caught the same way a typo would, rather than needing separate validation logic.
2. **Grounded explanations.** Optionally, the raw per-feature point breakdown for a recommendation can be turned into a short natural-language paragraph. The prompt explicitly restricts the model to only the score breakdown and retrieved reference notes as source material, specifically to prevent it from inventing details about a song or artist that aren't actually supported.

**Why grounding matters here specifically:** the recommender's whole value proposition (section 5) is that a listener can trust the "why" behind a pick. An ungrounded LLM explanation that sounds confident but states something untrue would undermine that more than the old plain point-breakdown ever could, since it reads as more authoritative while being less checkable.

**Reliability harness.** Introducing an LLM call means, for the first time, the same input can produce a different output on two different runs, and generated text is capable of inventing details the retrieval step didn't actually support. `src/reliability.py` runs a small set of golden cases (`data/eval_cases.json`) through three checks:
- A profile-score regression case: exact-match top-song check against the deterministic core, no LLM involved — a sanity guard that nothing above accidentally broke section 3's scoring.
- NL-parse cases: does the parsed profile match the expected genre/preference, and how *consistent* is the parse across repeated runs of the same query (`ConsistencyChecker`)?
- An explanation case: how *grounded* is the generated text in the score breakdown and retrieved notes it was allowed to draw on (`GroundednessChecker`, a keyword-overlap heuristic, not another LLM call), and how consistent is repeated generation?

Run `python -m src.reliability` to produce `logs/reliability_report.md`.

**Limitations of this iteration:** the knowledge base is small (~20 documents, one per catalog genre plus a few vocabulary docs) and retrieval is plain keyword/tag overlap rather than embeddings — transparent and easy to debug, but it will miss a query that's semantically related but shares no words with any document. The eval set is five cases, enough to catch an obvious regression but not enough to characterize the AI features' behavior broadly. `GroundednessChecker`'s keyword-overlap scoring will also under-score a paraphrase that's genuinely grounded but doesn't reuse the source wording, and over-score a claim that happens to share common words with the context without actually being supported by them. Link-based "find something similar to this song" input (YouTube/Spotify links) and catalog expansion were both considered for this iteration and deliberately deferred to keep scope realistic — see prior brainstorming.

---

## 10. Personal Reflection  

As a music lover, I had always been curious about how the recommendation system worked and, even though I know this is not how full scale algorithms are, it did serve to open my eyes and demistify its complexity. Now I have a better understanding of how it might work, and even though it still feels like magic, at least I am able to imagine what goes behind the scenes.

I was surprised to learn how there are multiple scores (& different ways to set up scoring systems), and my brain is still processing how we get to a likeability score based on data like genre and others, but I hope with more time working with it, it will become more intuitive. 
