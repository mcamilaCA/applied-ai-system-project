"""
Streamlit web app for the Music Recommender Simulation.

Wraps recommender.py in an interactive UI: the user builds a taste profile
with widgets in the sidebar, and gets ranked song recommendations with a
per-feature score breakdown, without touching any code.

Run with:
    streamlit run src/app.py
"""

import os

import streamlit as st
from dotenv import load_dotenv

from recommender import recommend_songs
from planner import PlanningError, configure_logging
from rag import KnowledgeBase, LLMClient, RAGEngine

load_dotenv()
configure_logging()

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def score_color(score):
    if score > 80:
        return "green"
    if score < 40:
        return "red"
    return "yellow"


@st.cache_data
def get_songs():
    from recommender import load_songs

    return load_songs(DATA_PATH)


@st.cache_resource
def get_rag_engine():
    songs = get_songs()
    catalog_genres = {song["genre"] for song in songs if song.get("genre")}
    catalog_moods = {song["mood"] for song in songs if song.get("mood")}
    return RAGEngine(
        knowledge_base=KnowledgeBase.load(),
        llm_client=LLMClient(),
        catalog_genres=catalog_genres,
        catalog_moods=catalog_moods,
    )


def unique_sorted(songs, field):
    return sorted({song[field] for song in songs if song.get(field)})


st.set_page_config(page_title="Music Recommender", page_icon="🎵", layout="centered")

songs = get_songs()

if "ai_explanations" not in st.session_state:
    st.session_state.ai_explanations = {}

st.title("🎵 Music Recommender")
st.caption("Tell us what you like and we'll rank the catalog for you.")

with st.expander("✨ Or just describe your taste in your own words (AI-powered)", expanded=True):
    st.caption(
        "Retrieves matching genre/mood reference notes, then an LLM turns your description "
        "into a profile below — same validation as filling out the form by hand."
    )
    nl_query = st.text_input(
        "What are you in the mood for?",
        placeholder="upbeat, nostalgic, early-2000s pop",
        key="nl_query",
    )
    if st.button("Parse with AI", width="stretch") and nl_query.strip():
        try:
            parsed = get_rag_engine().parse_taste_query(nl_query)
        except RuntimeError as error:
            st.error(str(error))
        except ValueError as error:
            st.error(f"The AI's response couldn't be parsed as a profile: {error}")
        else:
            prefs = dict(parsed.profile)
            prefs["danceability"] = 0.5
            prefs["k"] = 5
            st.session_state.user_prefs = prefs
            st.session_state.rag_sources = parsed.sources
            st.session_state.ai_explanations = {}

genres = unique_sorted(songs, "genre")
moods = unique_sorted(songs, "mood")
decades = unique_sorted(songs, "release_decade")

with st.sidebar, st.form("profile_form", border=True):
    st.header("Your taste profile")

    genre = st.selectbox("Favorite genre", genres)
    mood = st.selectbox("Favorite mood", moods)
    energy = st.slider("Energy", 0.0, 1.0, 0.7, 0.05)
    acoustic_choice = st.segmented_control(
        "Do you like acoustic songs?", ["Yes", "No"], default="Yes", required=True
    )

    st.subheader("Optional preferences")
    decade_choice = st.selectbox("Preferred decade", ["Any"] + decades)
    instrumental_choice = st.segmented_control(
        "Instrumental tracks?", ["Any", "Yes", "No"], default="Any", required=True
    )
    clean_only_choice = st.segmented_control(
        "Clean lyrics only?", ["Any", "Yes", "No"], default="Any", required=True
    )
    prefer_popular_choice = st.segmented_control(
        "Prefer popular songs?", ["Any", "Yes", "No"], default="Any", required=True
    )
    danceability = st.slider("Preferred danceability (tie-breaker)", 0.0, 1.0, 0.5, 0.05)

    k = st.slider("How many recommendations?", 1, min(10, len(songs)), 5)

    submitted = st.form_submit_button("Get recommendations", width="stretch")

if submitted:
    st.session_state.user_prefs = {
        "genre": genre,
        "mood": mood,
        "energy": energy,
        "likes_acoustic": acoustic_choice == "Yes",
        "preferred_decade": None if decade_choice == "Any" else decade_choice,
        "wants_instrumental": {"Any": None, "Yes": True, "No": False}[instrumental_choice],
        "clean_only": clean_only_choice == "Yes",
        "prefer_popular": prefer_popular_choice == "Yes",
        "danceability": danceability,
        "k": k,
    }
    st.session_state.pop("rag_sources", None)
    st.session_state.ai_explanations = {}

if "user_prefs" not in st.session_state:
    st.info("Set your preferences in the sidebar and click **Get recommendations** to see your matches.")
else:
    prefs = st.session_state.user_prefs

    st.subheader("Your profile")
    # .get() with defaults rather than direct indexing: a manually-filled-out form always sets
    # every key, but an AI-parsed profile only includes what the listener actually expressed an
    # opinion about, so optional keys (and even genre/mood, if the LLM ever misfires) may be absent.
    st.write(
        f"**Genre:** {prefs.get('genre', '(not set)')} · **Mood:** {prefs.get('mood', '(not set)')} · "
        f"**Energy:** {prefs.get('energy', 'no preference')} · "
        f"**Acoustic:** {'Yes' if prefs.get('likes_acoustic') else ('No' if prefs.get('likes_acoustic') is False else 'no preference')} · "
        f"**Decade:** {prefs.get('preferred_decade') or 'Any'} · "
        f"**Instrumental:** {'Any' if prefs.get('wants_instrumental') is None else ('Yes' if prefs.get('wants_instrumental') else 'No')} · "
        f"**Clean only:** {'Yes' if prefs.get('clean_only') else 'Any'} · "
        f"**Prefer popular:** {'Yes' if prefs.get('prefer_popular') else 'Any'}"
    )
    if st.session_state.get("rag_sources"):
        st.caption("✨ AI-parsed, grounded on: " + ", ".join(st.session_state.rag_sources))

    try:
        recommendations, notices = recommend_songs(prefs, songs, k=prefs.get("k", 5))
    except PlanningError as error:
        st.error(f"Could not build recommendations: {error}")
        st.stop()

    for notice in notices:
        (st.warning if notice.level == "warning" else st.info)(notice.message)

    st.subheader("🎧 Top recommendations")

    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        medal = MEDALS.get(rank, "🎶")
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{medal} #{rank} — {song['title']}** by {song['artist']}")
            with col2:
                st.metric("Score", f":{score_color(score)}[{score:.2f}%]")
            tab1, tab2 = st.tabs(["Why this song?", "✨ AI explanation"])
            with tab1:
                st.code(explanation.strip(), language=None)
            with tab2:
                cached = st.session_state.ai_explanations.get(song["id"])
                if st.button("Generate explanation", key=f"explain-{song['id']}"):
                    try:
                        cached = get_rag_engine().explain_with_context(song["title"], song["artist"], explanation)
                    except RuntimeError as error:
                        st.error(str(error))
                        cached = None
                    else:
                        st.session_state.ai_explanations[song["id"]] = cached
                if cached:
                    st.write(cached.text)
                    if cached.sources:
                        st.caption("Grounded on: " + ", ".join(cached.sources))

    if not recommendations:
        st.info("No songs matched your filters. Try relaxing 'Clean lyrics only' or your decade preference.")
