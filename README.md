# 🎵 Tunefy — Music Recommender Simulation with RAG & Reliability

## Original Project (Modules 1–3): Tunefy

This project's original, Modules 1–3 form was **Tunefy**, a purely deterministic song recommender. Given a listener's genre, mood, energy, and acousticness preferences, it scored every song in a catalog with a weighted, distance-based formula ("how close is this song's energy/acousticness to what the user wants?" rather than a hard yes/no cutoff) and returned the top-ranked matches, using danceability only to break ties. There was no AI in the loop at that stage — just a scoring function over structured input, built to be simple, testable, and fully predictable.

Everything below this point — the validation layer, the natural-language interface, the grounded explanations, and the reliability harness — is new work built *on top of* that unchanged deterministic core.

---

## Title and Summary

**Tunefy** recommends songs from a catalog of 600 real tracks based on a listener's taste, and explains *why* each song was picked instead of just handing back a black-box list. It matters because recommenders are usually judged on whether their picks feel right, but rarely let a user check the reasoning — Tunefy's score breakdown and AI explanations are both meant to be checkable, not just plausible-sounding.

On top of the original scoring engine, this phase adds three things: a listener can type their taste in plain English instead of filling out a form, each recommendation can get a short natural-language explanation grounded in retrieved reference notes, and a reliability harness checks that the new LLM-backed features behave consistently and don't invent facts.

## Architecture Overview

See [`diagrams/system_diagram.mmd`](diagrams/system_diagram.mmd) (and the class-level view in [`diagrams/uml_diagram.mmd`](diagrams/uml_diagram.mmd)). At a high level:

```
User (preferences or NL query)
        │
        ▼
   Agent / Orchestrator  ──query──▶  Retriever (KnowledgeBase)
 (RAGEngine + Recommender) ◀─docs──
        │
        ├──prompt + context──▶ LLM Client ──generated text──▶ (back to Agent)
        │
        ▼
   Output: ranked recommendations + optional grounded explanation
        │
        ▼
      User
```

- **Agent/Orchestrator** — `RAGEngine` (`src/rag.py`) handles anything that touches the LLM (parsing a free-text query, generating an explanation); `Recommender`/`plan_user_prefs` (`src/recommender.py`, `src/planner.py`) handle the deterministic scoring and input validation. The two are deliberately decoupled: RAG output is just another `user_prefs` dict, validated through the exact same planning step a manually-typed profile goes through.
- **Retriever** — `KnowledgeBase` (`data/knowledge_base.json`) does plain keyword/tag retrieval over a small set of genre, mood, and vocabulary reference notes, used both to ground the NL-parser's interpretation of a phrase and to give the explanation generator source material it's allowed to cite.
- **LLM Client** — a thin Groq wrapper (`src/rag.py`), the only place in the system that talks to an external API.
- **Testing & Evaluation loop** (right side of the diagram) — `tests/*.py` regression-test the deterministic core and the AI surfaces' surrounding logic against fake LLM responses, while `src/reliability.py` runs real golden cases (`data/eval_cases.json`) through the live LLM and scores consistency/groundedness into `logs/reliability_report.md`. A human reviewer reads that report and either ships as-is or feeds problems back into a prompt/data/code fix — the loop the diagram draws from `Evaluator → Report → Human → Fix → Agent`.

## Setup Instructions

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Enable the AI features with a free Groq API key (console.groq.com — no credit card required):

   ```bash
   export GROQ_API_KEY=your-key-here
   ```

   Without it, the CLI and web app still run end-to-end on a hardcoded example profile — only the natural-language box and AI explanation tabs are unavailable, and they fail with a clear message rather than crashing.

4. Run the CLI, from the project root:

   ```bash
   python src/main.py
   ```

5. Or run the web app instead:

   ```bash
   streamlit run src/app.py
   ```

   This opens a page where you can set genre, mood, energy, and other preferences with sliders/dropdowns in the sidebar, see ranked recommendations with a score breakdown for each song, describe your taste in your own words in the "✨" box above the results, and open an "✨ AI explanation" tab on each recommendation card.

6. Run the tests:

   ```bash
   pytest
   ```

   This covers the deterministic core, the planner, and the AI features' surrounding logic (retrieval, JSON parsing, consistency/groundedness scoring) against fake LLM responses — no `GROQ_API_KEY` or network access needed.

7. (Optional, needs `GROQ_API_KEY`) Run the live reliability harness:

   ```bash
   python -m src.reliability
   ```

   Scores the golden cases in `data/eval_cases.json` against the real LLM and writes `logs/reliability_report.md`.

## Sample Interactions

**1. Messy structured input, caught by the planning/validation layer.** Input: `{"genre": "pop ", "mood": "happy", "energy": float("nan"), "acousticness": True}` — a trailing space, an out-of-range energy value, and a boolean typed under the wrong field name.

```
INFO: [genre] trimmed whitespace from genre ('pop ' -> 'pop')
WARNING: [energy] energy value nan is invalid (must be a number in [0, 1]);
         excluding energy from scoring instead of letting it corrupt the ranking
WARNING: [acousticness] found a boolean under 'acousticness' (True); treating it
         as likes_acoustic=True (pass a numeric 0-1 value under 'acousticness'
         for a fine-grained target instead)

#1 Sunflower — Post Malone & Swae Lee   score=94.5
#2 Levitating — Dua Lipa                score=93.8
#3 Havana — Camila Cabello              score=93.2
```

Instead of a silently corrupted or meaningless ranking, every problem is explained and the ranking is still meaningful.

**2. Natural-language taste query (RAG taste parser), fed straight into the same scorer.** Input: `"I want something upbeat and nostalgic, kind of like early-2000s pop."`

```
Parsed profile: {'genre': 'pop', 'mood': 'nostalgic', 'energy': 0.8, 'preferred_decade': '2000s'}
Grounded on: genre-pop, energy-vocabulary, decade-vocabulary, genre-indie-pop

🥇 #1 Since U Been Gone — Kelly Clarkson   72.0/100
🥈 #2 Chicken Fried — Zac Brown Band       68.5/100
🥉 #3 4th Avenue Cafe — Lamp               68.0/100
```

**3. Grounded explanation for a top recommendation.** Input: profile `{"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}`, top pick "Blinding Lights" (99.2/100).

```
Blinding Lights fits your taste perfectly: it's a pop track with a happy,
upbeat vibe that matches your target mood, and its energy level is spot-on
at 0.80. The song's polished, electronic production and bright hooks give
it a high-energy feel, while the acoustic similarity score shows it's
comfortably close to the sound you enjoy.

Grounded on: genre-jazz, artist-neon-echo, genre-pop
```

(Note the "genre-jazz" and "artist-neon-echo" sources retrieved here are mostly irrelevant to Blinding Lights — a real example of the keyword-retriever pulling loosely-related notes; see Testing Summary.)

## Design Decisions

- **Distance-based scoring instead of thresholds.** Energy and acousticness are scored by how close they are to the target, not by a pass/fail cutoff, because "close enough" felt like the more honest signal for continuous features. Trade-off: it means two very different-sounding songs can post nearly the same score if their numbers land in the same neighborhood.
- **Genre and mood weighted highest (55% combined).** This encodes an assumption — that most listeners care more about genre/mood than energy/acousticness — rather than something learned per-user. Trade-off: a listener who actually prioritizes energy over genre gets recommendations that don't reflect that, and the system has no way to find out.
- **Genre/mood matching stays case-sensitive and exact**, on purpose, even though it's the most common source of "no match." Loosening it would hide real mismatches (e.g. "Pop" vs "indie pop") behind fuzzy string logic that's harder to reason about. The planner's whitespace-trimming is a deliberate, narrow exception to this, not a general fuzzy-match layer.
- **Validation lives in its own layer (`planner.py`), separate from scoring.** Rather than scattering `if`-checks through the scoring function, every raw preference is cleaned and explained *before* scoring ever runs, and every decision is both returned as a `Notice` and logged to `logs/recommender.log`. Trade-off: an extra indirection step, but it means the scorer itself can stay simple and assume clean input.
- **RAG output goes through the same validation as manual input**, instead of getting special-cased. An LLM-parsed profile with a bad field is treated exactly like a user typo — same `PlanningError`/`Notice` path. Trade-off: it means the system doesn't (yet) tell a listener "the AI misread you" versus "you typed something odd" — those failure modes currently look identical.
- **Explanations are constrained to cite only the score breakdown and retrieved notes**, never free-form knowledge about the song or artist. This trades away more colorful, informative-sounding explanations for ones that are actually checkable against a source — directly because the alternative (an unchecked LLM claim) is worse than the plain point breakdown it replaces.
- **Retrieval is keyword/tag overlap, not embeddings.** Simple, dependency-light, and easy to debug by reading the knowledge base directly. Trade-off, visible in Sample Interaction 3 above: it can pull in a loosely-related note (like a wrong genre reference) just because it shares a word, and it will miss a genuinely relevant note that happens to use different wording.

## Testing Summary

`pytest` (37 tests across `tests/test_recommender.py`, `tests/test_planner.py`, `tests/test_rag.py`, `tests/test_reliability.py`) passes fully offline, using fake LLM responses for anything AI-related — this is the regression net for the deterministic core and for the RAG/reliability code's own logic (parsing, retrieval, scoring math), independent of whether the real API is up or a real model's behavior drifts.

**What worked:** the deterministic core (score_song, planner validation) behaved consistently across every messy-input case tried by hand (NaN energy, a trailing-space genre, a preference typed under the wrong field name) — each one now produces a clear notice instead of a silently wrong ranking. Running the live reliability harness (`python -m src.reliability`) against the real Groq API, all three natural-language parsing cases came back fully consistent (1.00) across repeated runs and correctly recovered the expected genre.

**What didn't:** the harness's one real-API check that regularly fails is the grounded-explanation case — groundedness averaged ~0.40 against a 0.5 threshold across repeated runs (pass rate 4/5 overall). Looking at the actual generated text (Sample Interaction 3), the explanation isn't fabricating anything, but the keyword-overlap groundedness metric doesn't reliably reward a paraphrase that says the same thing as the source notes in different words — and separately, the retriever sometimes surfaces a barely-related note (like a wrong-genre reference) that then gets counted as "grounded on," which is itself a retrieval-quality problem rather than a generation one.

**What I learned:** consistency and groundedness are genuinely separate failure modes, not one "is the AI working" score — this system is highly consistent but only middlingly grounded, and a single pass/fail number would have hidden that. It also became clear that the evaluation code needs the same scrutiny as the feature it's grading: a keyword-overlap heuristic is transparent and cheap, but it can be wrong in both directions (under-crediting a good paraphrase, over-crediting an unrelated but keyword-adjacent note), so a failing eval case doesn't automatically mean the underlying feature is broken.

## Reflection

Building the validation layer *before* adding the LLM made something click: most of what gets called "AI reliability" here turned out to be the same data-hygiene problem the deterministic core already had (a NaN, a typo, a mismatched field name), just one step further upstream — the exact same messy input that used to silently corrupt a score would have just as silently produced a bad prompt. The harder, genuinely new problem was realizing that testing generative output needs different tools than testing deterministic code: there's no single assertEqual for "did this explanation invent something," so the reliability harness itself — the consistency and groundedness checkers — had to be designed, and then treated with just as much skepticism as the feature it was checking.

For the graded responsible-AI reflection — how I collaborated with AI, one helpful and one flawed AI suggestion, and this system's limitations — see [`model_card.md`](model_card.md).
