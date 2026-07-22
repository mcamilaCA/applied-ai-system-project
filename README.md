# 🎵 Music Recommender Simulation

## How The System Works

The system aims to recommend songs to user's based on their preferences & likings. For each song, details like genre, mood, energy and acousticness are translated into a score with the end goal of achieving a high compatibililty with a user's profile, the higher the score, the more likely a song is to be liked by the user.

For this, user statistics will be used to define: favorite mood, their most frequently listened energy levels and whether or not they like acoustic music. 

Instead of using thresholds, recommender calculates distance-based rewards prioritizing answering "how close is this feature to what the user wants to hear?". Once each weighted score is calculated, a ranking of all songs scores is computed to decide which songs are the ones with higher likelihood to be liked by the user and they are returned. If there is a tie of songs with the same score, danceability preferences are used to determine the one to be given to the user.

This being said, the weights that will be used for each attribute are:
1. genre: 35%
2. mood: 30%
3. energy: 20%
4. acousticness: 15% 

As seen by the weigthts above, the system has a bias for genre and mood - since it assumes every user gives a higher priority to genre than to mood or any of the other atributes. In an ideal system, it might ask for users preference, update the weights accordingly and store that data internally.

Before any of that scoring happens, a validation/planning step (`src/planner.py`) checks the raw preferences first. A missing or invalid genre/mood has no sensible fallback, so it's rejected outright with a clear error instead of producing a ranking. A missing or invalid energy/acousticness value (like the `NaN` or wrong-field-name cases below) gets excluded from scoring instead of silently corrupting it, and every decision the planner makes is logged to `logs/recommender.log` and surfaced to the listener as a notice, so a messy preference no longer produces a confident-looking but meaningless list with no explanation.

---

## AI Features (RAG + Reliability)

Two AI-powered additions sit on top of the deterministic scoring above -- neither one touches the scoring math itself, so the core recommender stays exactly as testable and predictable as before.

**1. Natural-language taste parser.** Instead of filling out the sidebar form, you can describe your taste in plain English ("upbeat, nostalgic, early-2000s pop"). `RAGEngine.parse_taste_query` (`src/rag.py`) retrieves matching genre/mood/vocabulary notes from a small local knowledge base (`data/knowledge_base.json`), then asks an LLM to turn the description into the same structured preferences dict the form produces. That dict is validated by the exact same `plan_user_prefs` pipeline a manually-typed profile goes through, so a malformed field coming out of the LLM gets caught the same way a typo would.

**2. Grounded explanations.** Each recommendation already comes with a raw per-feature point breakdown. Optionally, `RAGEngine.explain_with_context` turns that breakdown into a short natural-language paragraph, using the same knowledge base for extra genre/artist context -- and is explicitly instructed to only state things the breakdown or retrieved notes actually support, so it can't invent facts about a song.

**Setup:** both features need a free Groq API key (console.groq.com -- no credit card required). Export it before running the app or the CLI example:

```bash
export GROQ_API_KEY=your-key-here
```

Without it, everything else (the structured form, the CLI's hardcoded example) still works fine -- only the AI-powered paths are unavailable, and they fail with a clear message rather than crashing.

**3. Reliability harness.** Because an LLM is now in the loop, `src/reliability.py` checks two things the deterministic core never needed checking: whether repeated calls with the same input stay *consistent*, and whether generated text stays *grounded* in what it retrieved rather than inventing details. Run it with:

```bash
python -m src.reliability
```

This runs the golden cases in `data/eval_cases.json` and writes a scored report to `logs/reliability_report.md` (also printed to the console). See `model_card.md` for more on what it measures and its current limitations.

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.main
```

### Running the Web App

To interact with the recommender in a browser instead of the CLI:

```bash
streamlit run src/app.py
```

This opens a page where you can set your genre, mood, energy, and other preferences with sliders/dropdowns in the sidebar, and see ranked recommendations with a score breakdown for each song. There's also an "✨ Or just describe your taste in your own words" box above the results (needs `GROQ_API_KEY`, see above) and a "✨ AI explanation" tab on each recommendation card.

### Running Tests

Run the tests with:

```bash
pytest
```

This includes `tests/test_rag.py` and `tests/test_reliability.py`, which cover the AI features' surrounding logic (retrieval, JSON parsing, consistency/groundedness scoring) against fake LLM responses -- no `GROQ_API_KEY` or network access needed for `pytest` to pass. Only the live paths (the Streamlit AI box/tabs, `python -m src.reliability`) need a real key.

You can add more tests in `tests/test_recommender.py`.

---

## Sample Recommendation Output

Paste a sample of your recommender's output here as a text block so a reader can see what it produces:

```
======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=pop | mood=happy | energy=0.8 | accousticness=0.2
======================================================================

🥇 #1  Sunrise City — Neon Echo
   ⭐ Score: 94.8/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.98 (song 0.82 vs target 0.80): +19.6 pts
   🎻 Acoustic similarity 0.68 (song 0.18 vs target 0.50): +10.2 pts
----------------------------------------------------------------------
🥈 #2  Rooftop Lights — Indigo Parade
   ⭐ Score: 61.9/100
   🎸 Genre   ❌ no match (indie pop vs pop): +0.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.96 (song 0.76 vs target 0.80): +19.2 pts
   🎻 Acoustic similarity 0.85 (song 0.35 vs target 0.50): +12.8 pts
----------------------------------------------------------------------
🥉 #3  Gym Hero — Max Pulse
   ⭐ Score: 60.7/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ❌ no match (intense vs happy): +0.0 pts
   ⚡ Energy  similarity 0.87 (song 0.93 vs target 0.80): +17.4 pts
   🎻 Acoustic similarity 0.55 (song 0.05 vs target 0.50): +8.2 pts
----------------------------------------------------------------------
🎶 #4  Night Drive Loop — Neon Echo
   ⭐ Score: 29.8/100
   🎸 Genre   ❌ no match (synthwave vs pop): +0.0 pts
   🎭 Mood    ❌ no match (moody vs happy): +0.0 pts
   ⚡ Energy  similarity 0.95 (song 0.75 vs target 0.80): +19.0 pts
   🎻 Acoustic similarity 0.72 (song 0.22 vs target 0.50): +10.8 pts
----------------------------------------------------------------------
🎶 #5  Island Drift — Solar Tide
   ⭐ Score: 29.5/100
   🎸 Genre   ❌ no match (reggae vs pop): +0.0 pts
   🎭 Mood    ❌ no match (carefree vs happy): +0.0 pts
   ⚡ Energy  similarity 0.80 (song 0.60 vs target 0.80): +16.0 pts
   🎻 Acoustic similarity 0.90 (song 0.40 vs target 0.50): +13.5 pts
----------------------------------------------------------------------

🎧 Enjoy the music!

```

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or demo video link here -->

---

## Stress Tests:
1. 
  Input: user_prefs = {"genre": "pop ", "mood": "happy", "energy": 0.8, "accousticness": True}

  Output
  ```
  ======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=pop  | mood=happy | energy=0.8 | accousticness=True
======================================================================

🥇 #1  Rooftop Lights — Indigo Parade
   ⭐ Score: 61.9/100
   🎸 Genre   ❌ no match (indie pop vs pop ): +0.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.96 (song 0.76 vs target 0.80): +19.2 pts
   🎻 Acoustic similarity 0.85 (song 0.35 vs target 0.50): +12.8 pts
----------------------------------------------------------------------
🥈 #2  Sunrise City — Neon Echo
   ⭐ Score: 59.8/100
   🎸 Genre   ❌ no match (pop vs pop ): +0.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.98 (song 0.82 vs target 0.80): +19.6 pts
   🎻 Acoustic similarity 0.68 (song 0.18 vs target 0.50): +10.2 pts
----------------------------------------------------------------------
🥉 #3  Night Drive Loop — Neon Echo
   ⭐ Score: 29.8/100
   🎸 Genre   ❌ no match (synthwave vs pop ): +0.0 pts
   🎭 Mood    ❌ no match (moody vs happy): +0.0 pts
   ⚡ Energy  similarity 0.95 (song 0.75 vs target 0.80): +19.0 pts
   🎻 Acoustic similarity 0.72 (song 0.22 vs target 0.50): +10.8 pts
----------------------------------------------------------------------
🎶 #4  Island Drift — Solar Tide
   ⭐ Score: 29.5/100
   🎸 Genre   ❌ no match (reggae vs pop ): +0.0 pts
   🎭 Mood    ❌ no match (carefree vs happy): +0.0 pts
   ⚡ Energy  similarity 0.80 (song 0.60 vs target 0.80): +16.0 pts
   🎻 Acoustic similarity 0.90 (song 0.40 vs target 0.50): +13.5 pts
----------------------------------------------------------------------
🎶 #5  Concrete Sermon — MC Vantage
   ⭐ Score: 28.7/100
   🎸 Genre   ❌ no match (hip-hop vs pop ): +0.0 pts
   🎭 Mood    ❌ no match (confident vs happy): +0.0 pts
   ⚡ Energy  similarity 1.00 (song 0.80 vs target 0.80): +20.0 pts
   🎻 Acoustic similarity 0.58 (song 0.08 vs target 0.50): +8.7 pts
----------------------------------------------------------------------

🎧 Enjoy the music!
  ```
2. 
  Input: user_prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "accousticness": True}

  Output
  ```
  ======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=pop | mood=happy | energy=0.8 | accousticness=True
======================================================================

🥇 #1  Sunrise City — Neon Echo
   ⭐ Score: 94.8/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.98 (song 0.82 vs target 0.80): +19.6 pts
   🎻 Acoustic similarity 0.68 (song 0.18 vs target 0.50): +10.2 pts
----------------------------------------------------------------------
🥈 #2  Rooftop Lights — Indigo Parade
   ⭐ Score: 61.9/100
   🎸 Genre   ❌ no match (indie pop vs pop): +0.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.96 (song 0.76 vs target 0.80): +19.2 pts
   🎻 Acoustic similarity 0.85 (song 0.35 vs target 0.50): +12.8 pts
----------------------------------------------------------------------
🥉 #3  Gym Hero — Max Pulse
   ⭐ Score: 60.7/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ❌ no match (intense vs happy): +0.0 pts
   ⚡ Energy  similarity 0.87 (song 0.93 vs target 0.80): +17.4 pts
   🎻 Acoustic similarity 0.55 (song 0.05 vs target 0.50): +8.2 pts
----------------------------------------------------------------------
🎶 #4  Night Drive Loop — Neon Echo
   ⭐ Score: 29.8/100
   🎸 Genre   ❌ no match (synthwave vs pop): +0.0 pts
   🎭 Mood    ❌ no match (moody vs happy): +0.0 pts
   ⚡ Energy  similarity 0.95 (song 0.75 vs target 0.80): +19.0 pts
   🎻 Acoustic similarity 0.72 (song 0.22 vs target 0.50): +10.8 pts
----------------------------------------------------------------------
🎶 #5  Island Drift — Solar Tide
   ⭐ Score: 29.5/100
   🎸 Genre   ❌ no match (reggae vs pop): +0.0 pts
   🎭 Mood    ❌ no match (carefree vs happy): +0.0 pts
   ⚡ Energy  similarity 0.80 (song 0.60 vs target 0.80): +16.0 pts
   🎻 Acoustic similarity 0.90 (song 0.40 vs target 0.50): +13.5 pts
----------------------------------------------------------------------

🎧 Enjoy the music!
  ```
3. 
  Input: user_prefs = {"genre": "pop", "mood": "happy", "energy": float("nan"), "accousticness": 0.3}
  
  Output
  ```
======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=pop | mood=happy | energy=nan | accousticness=0.3
======================================================================

🥇 #1  Sunrise City — Neon Echo
   ⭐ Score: nan/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity nan (song 0.82 vs target nan): +nan pts
   🎻 Acoustic similarity 0.68 (song 0.18 vs target 0.50): +10.2 pts
----------------------------------------------------------------------
🥈 #2  Midnight Coding — LoRoom
   ⭐ Score: nan/100
   🎸 Genre   ❌ no match (lofi vs pop): +0.0 pts
   🎭 Mood    ❌ no match (chill vs happy): +0.0 pts
   ⚡ Energy  similarity nan (song 0.42 vs target nan): +nan pts
   🎻 Acoustic similarity 0.79 (song 0.71 vs target 0.50): +11.8 pts
----------------------------------------------------------------------
🥉 #3  Storm Runner — Voltline
   ⭐ Score: nan/100
   🎸 Genre   ❌ no match (rock vs pop): +0.0 pts
   🎭 Mood    ❌ no match (intense vs happy): +0.0 pts
   ⚡ Energy  similarity nan (song 0.91 vs target nan): +nan pts
   🎻 Acoustic similarity 0.60 (song 0.10 vs target 0.50): +9.0 pts
----------------------------------------------------------------------
🎶 #4  Library Rain — Paper Lanterns
   ⭐ Score: nan/100
   🎸 Genre   ❌ no match (lofi vs pop): +0.0 pts
   🎭 Mood    ❌ no match (chill vs happy): +0.0 pts
   ⚡ Energy  similarity nan (song 0.35 vs target nan): +nan pts
   🎻 Acoustic similarity 0.64 (song 0.86 vs target 0.50): +9.6 pts
----------------------------------------------------------------------
🎶 #5  Gym Hero — Max Pulse
   ⭐ Score: nan/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ❌ no match (intense vs happy): +0.0 pts
   ⚡ Energy  similarity nan (song 0.93 vs target nan): +nan pts
   🎻 Acoustic similarity 0.55 (song 0.05 vs target 0.50): +8.2 pts
----------------------------------------------------------------------

🎧 Enjoy the music!
  ```
1. 
  Input: user_prefs = {"genre": "lofi", "mood": "chill", "energy": 0.4, "accousticness": True, "danceability": 1.0}

  Output
  ```
  ======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=lofi | mood=chill | energy=0.4 | accousticness=True
======================================================================

🥇 #1  Midnight Coding — LoRoom
   ⭐ Score: 96.4/100
   🎸 Genre   ✅ match (lofi vs lofi): +35.0 pts
   🎭 Mood    ✅ match (chill vs chill): +30.0 pts
   ⚡ Energy  similarity 0.98 (song 0.42 vs target 0.40): +19.6 pts
   🎻 Acoustic similarity 0.79 (song 0.71 vs target 0.50): +11.8 pts
----------------------------------------------------------------------
🥈 #2  Library Rain — Paper Lanterns
   ⭐ Score: 93.6/100
   🎸 Genre   ✅ match (lofi vs lofi): +35.0 pts
   🎭 Mood    ✅ match (chill vs chill): +30.0 pts
   ⚡ Energy  similarity 0.95 (song 0.35 vs target 0.40): +19.0 pts
   🎻 Acoustic similarity 0.64 (song 0.86 vs target 0.50): +9.6 pts
----------------------------------------------------------------------
🥉 #3  Focus Flow — LoRoom
   ⭐ Score: 65.8/100
   🎸 Genre   ✅ match (lofi vs lofi): +35.0 pts
   🎭 Mood    ❌ no match (focused vs chill): +0.0 pts
   ⚡ Energy  similarity 1.00 (song 0.40 vs target 0.40): +20.0 pts
   🎻 Acoustic similarity 0.72 (song 0.78 vs target 0.50): +10.8 pts
----------------------------------------------------------------------
🎶 #4  Spacewalk Thoughts — Orbit Bloom
   ⭐ Score: 56.3/100
   🎸 Genre   ❌ no match (ambient vs lofi): +0.0 pts
   🎭 Mood    ✅ match (chill vs chill): +30.0 pts
   ⚡ Energy  similarity 0.88 (song 0.28 vs target 0.40): +17.6 pts
   🎻 Acoustic similarity 0.58 (song 0.92 vs target 0.50): +8.7 pts
----------------------------------------------------------------------
🎶 #5  Dust Road Home — Copper Wagon
   ⭐ Score: 30.8/100
   🎸 Genre   ❌ no match (country vs lofi): +0.0 pts
   🎭 Mood    ❌ no match (nostalgic vs chill): +0.0 pts
   ⚡ Energy  similarity 0.90 (song 0.50 vs target 0.40): +18.0 pts
   🎻 Acoustic similarity 0.85 (song 0.65 vs target 0.50): +12.8 pts
----------------------------------------------------------------------

🎧 Enjoy the music!
  ```
5. 
  Input: user_prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "accousticness": 0.2}


  Output
  ```
  ======================================================================
🎵  YOUR TOP SONG RECOMMENDATIONS  🎵
======================================================================
👤 Profile: genre=pop | mood=happy | energy=0.8 | accousticness=0.2
======================================================================

🥇 #1  Sunrise City — Neon Echo
   ⭐ Score: 94.8/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.98 (song 0.82 vs target 0.80): +19.6 pts
   🎻 Acoustic similarity 0.68 (song 0.18 vs target 0.50): +10.2 pts
----------------------------------------------------------------------
🥈 #2  Rooftop Lights — Indigo Parade
   ⭐ Score: 61.9/100
   🎸 Genre   ❌ no match (indie pop vs pop): +0.0 pts
   🎭 Mood    ✅ match (happy vs happy): +30.0 pts
   ⚡ Energy  similarity 0.96 (song 0.76 vs target 0.80): +19.2 pts
   🎻 Acoustic similarity 0.85 (song 0.35 vs target 0.50): +12.8 pts
----------------------------------------------------------------------
🥉 #3  Gym Hero — Max Pulse
   ⭐ Score: 60.7/100
   🎸 Genre   ✅ match (pop vs pop): +35.0 pts
   🎭 Mood    ❌ no match (intense vs happy): +0.0 pts
   ⚡ Energy  similarity 0.87 (song 0.93 vs target 0.80): +17.4 pts
   🎻 Acoustic similarity 0.55 (song 0.05 vs target 0.50): +8.2 pts
----------------------------------------------------------------------
🎶 #4  Night Drive Loop — Neon Echo
   ⭐ Score: 29.8/100
   🎸 Genre   ❌ no match (synthwave vs pop): +0.0 pts
   🎭 Mood    ❌ no match (moody vs happy): +0.0 pts
   ⚡ Energy  similarity 0.95 (song 0.75 vs target 0.80): +19.0 pts
   🎻 Acoustic similarity 0.72 (song 0.22 vs target 0.50): +10.8 pts
----------------------------------------------------------------------
🎶 #5  Island Drift — Solar Tide
   ⭐ Score: 29.5/100
   🎸 Genre   ❌ no match (reggae vs pop): +0.0 pts
   🎭 Mood    ❌ no match (carefree vs happy): +0.0 pts
   ⚡ Energy  similarity 0.80 (song 0.60 vs target 0.80): +16.0 pts
   🎻 Acoustic similarity 0.90 (song 0.40 vs target 0.50): +13.5 pts
----------------------------------------------------------------------

🎧 Enjoy the music!
  ```

## Reflection

See [`model_card.md`](model_card.md) for the full writeup on intended use, data, strengths, limitations/bias, evaluation, and personal reflection.




