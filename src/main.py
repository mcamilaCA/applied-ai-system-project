"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

import os

from dotenv import load_dotenv
from tabulate import tabulate

from recommender import UserProfile, load_songs, recommend_songs
from planner import PlanningError, configure_logging
from rag import KnowledgeBase, LLMClient, RAGEngine

load_dotenv()

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
NOTICE_ICONS = {"warning": "⚠️", "info": "ℹ️"}

# Fed to RAGEngine.parse_taste_query when GROQ_API_KEY is set, so this file
# doubles as a runnable example of the AI taste-parser -- see build_user_prefs().
NL_QUERY_EXAMPLE = "I want something upbeat and nostalgic, kind of like early-2000s pop."


def build_user_prefs() -> dict:
    """
    Builds the profile dict that gets scored against the catalog. If
    GROQ_API_KEY is set, demonstrates the RAG taste-parser by running
    NL_QUERY_EXAMPLE through it instead of using a hardcoded profile;
    otherwise falls back to the original hardcoded structured profile so this
    still runs end-to-end without an API key.
    """
    if not os.environ.get("GROQ_API_KEY"):
        print("ℹ️  GROQ_API_KEY not set -- using the hardcoded example profile "
              "instead of the AI taste parser.\n")
        return {
            "genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False,
            "preferred_decade": "2020s", "wants_instrumental": False,
            "clean_only": True, "prefer_popular": True,
        }

    print(f"✨ GROQ_API_KEY found -- parsing taste from: {NL_QUERY_EXAMPLE!r}\n")
    engine = RAGEngine(knowledge_base=KnowledgeBase.load(), llm_client=LLMClient())
    parsed = engine.parse_taste_query(NL_QUERY_EXAMPLE)
    print(f"   Parsed profile: {parsed.profile}")
    print(f"   Grounded on: {', '.join(parsed.sources) or '(no matching reference docs)'}\n")
    return parsed.profile


def main() -> None:
    configure_logging()
    songs = load_songs("data/songs.csv")

    # Starter example profiles, still handy for exercising the planner's stress-test paths:
    # user_prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 0.2}
    # user_prefs = {"genre": "pop ", "mood": "happy", "energy": 0.8, "acousticness": True}
    # user_prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": True}
    # user_prefs = {"genre": "pop", "mood": "happy", "energy": float("nan"), "acousticness": 0.3}
    # user_prefs = {"genre": "lofi", "mood": "chill", "energy": 0.4, "acousticness": True, "danceability": 1.0}
    # user_prefs = {"genre": "lofi", "mood": "chill", "energy": 0.4, "acousticness": 0.8, "wants_instrumental": True, "preferred_decade": "1990s", "clean_only": True}
    user_prefs = build_user_prefs()

    try:
        recommendations, notices = recommend_songs(user_prefs, songs, k=5)
    except PlanningError as error:
        print(f"\n❌ Could not build recommendations: {error}\n")
        return

    print()
    print("=" * 70)
    print("🎵  YOUR TOP SONG RECOMMENDATIONS  🎵")
    print("=" * 70)
    for notice in notices:
        print(f"{NOTICE_ICONS[notice.level]} {notice.message}")
    if notices:
        print("=" * 70)
    # genre/mood are guaranteed present here (recommend_songs raises PlanningError above
    # otherwise); energy/likes_acoustic are optional, so .get() avoids a KeyError on an
    # AI-parsed profile that only includes what the listener actually expressed an opinion about.
    print(f"👤 Profile: genre={user_prefs['genre']} | mood={user_prefs['mood']} | "
          f"energy={user_prefs.get('energy', 'no preference')} | "
          f"likes_acoustic={user_prefs.get('likes_acoustic', 'no preference')}")
    print(
        f"   decade={user_prefs.get('preferred_decade', 'any')} | "
        f"wants_instrumental={user_prefs.get('wants_instrumental', 'no preference')} | "
        f"clean_only={user_prefs.get('clean_only', False)} | "
        f"prefer_popular={user_prefs.get('prefer_popular', False)}"
    )
    print("=" * 70)
    print()

    rows = []
    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        medal = MEDALS.get(rank, "🎶")
        why = "\n".join(line.strip() for line in explanation.strip().split("\n"))
        rows.append([f"{medal} #{rank}", song["title"], song["artist"], f"{score:.1f}/100", why])

    print(tabulate(rows, headers=["Rank", "Song", "Artist", "Score", "Why"], tablefmt="fancy_grid"))
    print("\n🎧 Enjoy the music!\n")


if __name__ == "__main__":
    main()
