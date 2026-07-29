import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

try:
    # Bare import: works when src/ itself is on sys.path (streamlit's script
    # loading, or `PYTHONPATH=src python -m src.main`, both used elsewhere in
    # this file's docstrings/README).
    from planner import Notice, log_notices, plan_user_prefs
except ImportError:
    # Package-qualified import: works when the repo root is on sys.path and
    # this module is loaded as src.recommender (e.g. `from src.recommender
    # import ...` in tests/test_recommender.py).
    from src.planner import Notice, log_notices, plan_user_prefs

# Point-weighting strategy (must sum to 1.0).
# Genre and mood are categorical (all-or-nothing match), so they carry more
# weight than the continuous, self-correcting energy/acousticness distances.
# See README "How The System Works" for the reasoning behind this ordering.
# Decade (categorical) and instrumentalness (continuous) are newer, optional
# preferences: a listener who doesn't state one gets full credit on it (see
# `instrumental_target` / decade handling in `_score_core`), so the weight
# below only ever discriminates between songs once a listener opts in.
WEIGHT_GENRE = 0.30
WEIGHT_MOOD = 0.25
WEIGHT_ENERGY = 0.15
WEIGHT_ACOUSTICNESS = 0.10
WEIGHT_INSTRUMENTALNESS = 0.10
WEIGHT_DECADE = 0.10

# # EXPERIMENT: energy doubled (0.20->0.40) and genre halved (0.35->0.175)
# # relative to the baseline above, then all four proportionally renormalized
# # by their raw sum (1.025) so they still total exactly 1.0:
# #   0.175/1.025 = 7/41, 0.30/1.025 = 12/41, 0.40/1.025 = 16/41, 0.15/1.025 = 6/41
# WEIGHT_GENRE = 7 / 41
# WEIGHT_MOOD = 12 / 41
# WEIGHT_ENERGY = 16 / 41
# WEIGHT_ACOUSTICNESS = 6 / 41

# assert abs(WEIGHT_GENRE + WEIGHT_MOOD + WEIGHT_ENERGY + WEIGHT_ACOUSTICNESS - 1.0) < 1e-9, \
#     "Weights must sum to 1.0"


# Target acousticness anchors for a boolean "likes acoustic" preference.
# 0.85/0.15 rather than 1.0/0.0 so the most extreme catalog outliers don't
# swallow all the credit relative to songs that are still clearly acoustic/electronic.
ACOUSTIC_TARGET_LIKED = 0.85
ACOUSTIC_TARGET_DISLIKED = 0.15

# Same 0.85/0.15 anchoring, applied to the newer "wants instrumental" preference.
INSTRUMENTAL_TARGET_LIKED = 0.85
INSTRUMENTAL_TARGET_DISLIKED = 0.15


def acoustic_target(likes_acoustic: bool) -> float:
    """Maps a boolean acoustic preference to its target acousticness anchor."""
    return ACOUSTIC_TARGET_LIKED if likes_acoustic else ACOUSTIC_TARGET_DISLIKED


def instrumental_target(wants_instrumental: Optional[bool]) -> Optional[float]:
    """
    Maps an optional "wants instrumental" preference to its target instrumentalness
    anchor. None means the listener has no opinion, and is passed straight through
    so `_score_core` can give every song full credit on this dimension instead of
    penalizing songs for a preference nobody stated.
    """
    if wants_instrumental is None:
        return None
    return INSTRUMENTAL_TARGET_LIKED if wants_instrumental else INSTRUMENTAL_TARGET_DISLIKED


def _score_core(
    genre: str,
    mood: str,
    energy: float,
    acousticness: float,
    favorite_genre: str,
    favorite_mood: str,
    target_energy: float,
    target_acousticness: float,
    mood_tags: Optional[List[str]] = None,
    instrumentalness: float = 0.0,
    target_instrumentalness: Optional[float] = None,
    release_decade: Optional[str] = None,
    favorite_decade: Optional[str] = None,
    skip_energy: bool = False,
    skip_acousticness: bool = False,
) -> Tuple[float, List[str]]:
    """
    Shared scoring formula used by both the OOP (Recommender) and functional
    (score_song) APIs, so the two paths can never drift out of sync.
    Returns a 0-100 score plus a human-readable reason per feature.

    mood_tags/instrumentalness/release_decade and their targets are all optional
    so existing callers (like the starter tests) that don't supply them still get
    the original genre/mood/energy/acousticness behavior, unaffected.

    skip_energy/skip_acousticness let the planner (src/planner.py) exclude a
    dimension that came in invalid (e.g. NaN energy) instead of letting it
    corrupt the score: the dimension gets full credit, the same "doesn't
    discriminate" treatment already used for an unset instrumentalness/decade
    preference.
    """
    if genre == favorite_genre:
        genre_match = 1.0
    else:
        genre_match = 0.0

    if mood == favorite_mood:
        mood_match = 1.0
        mood_note = "✅ match"
    elif favorite_mood in (mood_tags or []):
        mood_match = 0.5
        mood_note = "🟡 partial match (via mood tags)"
    else:
        mood_match = 0.0
        mood_note = "❌ no match"

    if skip_energy:
        energy_similarity = 1.0
        energy_note = "⚪ excluded (invalid input)"
    else:
        energy_similarity = 1.0 - abs(energy - target_energy)
        energy_note = (
            f"similarity {energy_similarity:.2f} (song {energy:.2f} vs target {target_energy:.2f})"
        )

    if skip_acousticness:
        acoustic_similarity = 1.0
        acoustic_note = "⚪ excluded (invalid input)"
    else:
        acoustic_similarity = 1.0 - abs(acousticness - target_acousticness)
        acoustic_note = (
            f"similarity {acoustic_similarity:.2f} (song {acousticness:.2f} vs target {target_acousticness:.2f})"
        )

    # No stated preference => full credit, so this dimension never discriminates
    # between songs unless the listener actually opts in.
    if target_instrumentalness is None:
        instrumental_similarity = 1.0
        instrumental_note = "⚪ no preference"
    else:
        instrumental_similarity = 1.0 - abs(instrumentalness - target_instrumentalness)
        instrumental_note = (
            f"similarity {instrumental_similarity:.2f} "
            f"(song {instrumentalness:.2f} vs target {target_instrumentalness:.2f})"
        )

    if favorite_decade is None:
        decade_match = 1.0
        decade_note = "⚪ no preference"
    else:
        decade_match = 1.0 if release_decade == favorite_decade else 0.0
        decade_note = (
            f"{'✅ match' if decade_match else '❌ no match'} "
            f"({release_decade} vs {favorite_decade})"
        )

    score = 100 * (
        WEIGHT_GENRE * genre_match
        + WEIGHT_MOOD * mood_match
        + WEIGHT_ENERGY * energy_similarity
        + WEIGHT_ACOUSTICNESS * acoustic_similarity
        + WEIGHT_INSTRUMENTALNESS * instrumental_similarity
        + WEIGHT_DECADE * decade_match
    )

    reasons = [
        f"🎸 Genre   {'✅ match' if genre_match else '❌ no match'} "
        f"({genre} vs {favorite_genre}): +{WEIGHT_GENRE * genre_match * 100:.1f} pts",
        f"🎭 Mood    {mood_note} "
        f"({mood} vs {favorite_mood}): +{WEIGHT_MOOD * mood_match * 100:.1f} pts",
        f"⚡ Energy  {energy_note}: +{WEIGHT_ENERGY * energy_similarity * 100:.1f} pts",
        f"🎻 Acoustic {acoustic_note}: +{WEIGHT_ACOUSTICNESS * acoustic_similarity * 100:.1f} pts",
        f"🎤 Instrumentalness {instrumental_note}: +{WEIGHT_INSTRUMENTALNESS * instrumental_similarity * 100:.1f} pts",
        f"📅 Decade  {decade_note}: +{WEIGHT_DECADE * decade_match * 100:.1f} pts",
    ]
    return score, reasons


@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    # Newer catalog attributes. All default to neutral values so existing
    # callers (like the starter tests) that only set the fields above still
    # construct a valid, unpenalized Song.
    popularity: float = 50.0
    release_decade: str = ""
    mood_tags: List[str] = field(default_factory=list)
    explicit_content: bool = False
    instrumentalness: float = 0.0

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    # Optional: only used as a tie-breaker, so callers that don't care about
    # danceability (like the starter tests) aren't forced to supply it.
    preferred_danceability: float = 0.5
    # Optional newer preferences. None/False means "no opinion" and is scored
    # as full credit (decade/instrumentalness) or simply ignored (clean_only,
    # prefer_popular), so callers that don't set these keep the original behavior.
    preferred_decade: Optional[str] = None
    wants_instrumental: Optional[bool] = None
    clean_only: bool = False
    prefer_popular: bool = False

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Returns the top-k songs for a user, ranked by score with danceability/popularity as tie-breakers."""
        target_acousticness = acoustic_target(user.likes_acoustic)
        target_instrumentalness = instrumental_target(user.wants_instrumental)

        candidates = self.songs
        if user.clean_only:
            candidates = [song for song in candidates if not song.explicit_content]

        def sort_key(song: Song) -> Tuple[float, float, float]:
            score, _ = _score_core(
                song.genre, song.mood, song.energy, song.acousticness,
                user.favorite_genre, user.favorite_mood, user.target_energy, target_acousticness,
                mood_tags=song.mood_tags,
                instrumentalness=song.instrumentalness, target_instrumentalness=target_instrumentalness,
                release_decade=song.release_decade, favorite_decade=user.preferred_decade,
            )
            # Tie-breakers only: closer danceability wins first, then higher
            # popularity if the listener opted into `prefer_popular`.
            dance_tie_break = -abs(song.danceability - user.preferred_danceability)
            popularity_tie_break = song.popularity if user.prefer_popular else 0.0
            return (score, dance_tie_break, popularity_tie_break)

        ranked = sorted(candidates, key=sort_key, reverse=True)
        return ranked[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Builds a human-readable, per-feature breakdown of a song's score for a user."""
        target_acousticness = acoustic_target(user.likes_acoustic)
        target_instrumentalness = instrumental_target(user.wants_instrumental)
        score, reasons = _score_core(
            song.genre, song.mood, song.energy, song.acousticness,
            user.favorite_genre, user.favorite_mood, user.target_energy, target_acousticness,
            mood_tags=song.mood_tags,
            instrumentalness=song.instrumentalness, target_instrumentalness=target_instrumentalness,
            release_decade=song.release_decade, favorite_decade=user.preferred_decade,
        )
        lines = [f"🎧 {song.title} — ⭐ {score:.1f}/100"]
        lines.extend(f"   {reason}" for reason in reasons)
        return "\n".join(lines)

def load_songs(csv_path: str) -> List[Dict]:
    """
    Loads songs from a CSV file.
    Required by src/main.py
    """
    numeric_fields = {"energy", "tempo_bpm", "valence", "danceability", "acousticness", "popularity", "instrumentalness"}
    songs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["id"] = int(row["id"])
            for field_name in numeric_fields:
                if field_name in row:
                    row[field_name] = float(row[field_name])
            if "mood_tags" in row:
                row["mood_tags"] = row["mood_tags"].split("|") if row["mood_tags"] else []
            if "explicit_content" in row:
                row["explicit_content"] = row["explicit_content"] == "True"
            songs.append(row)
    return songs

def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences.
    Required by recommend_songs() and src/main.py

    user_prefs supports: genre, mood, energy, likes_acoustic, target_acousticness,
    preferred_decade, wants_instrumental (all optional except genre/mood/energy).
    likes_acoustic/wants_instrumental/preferred_decade are optional so callers
    (like the starter main.py profile) that don't specify them still get a
    sensible neutral score instead of a crash.

    target_acousticness, when present, is a fine-grained 0-1 target set by
    src/planner.py's plan_user_prefs from a numeric "acousticness" preference;
    it takes precedence over the coarser liked/disliked anchor derived from
    likes_acoustic.

    _skip_energy/_skip_acousticness are set by src/planner.py's plan_user_prefs
    when the corresponding raw value was invalid (e.g. NaN, wrong type); when
    set, a safe placeholder is used instead of converting the invalid value,
    and the dimension is excluded from scoring rather than corrupting it.
    """
    skip_energy = bool(user_prefs.get("_skip_energy"))
    skip_acousticness = bool(user_prefs.get("_skip_acousticness"))

    if "target_acousticness" in user_prefs:
        target_acousticness = user_prefs["target_acousticness"]
    else:
        likes_acoustic = user_prefs.get("likes_acoustic")
        if skip_acousticness or likes_acoustic is None:
            target_acousticness = 0.5
        else:
            target_acousticness = acoustic_target(likes_acoustic)

    target_energy = 0.5 if skip_energy else float(user_prefs.get("energy", 0.5))

    return _score_core(
        song.get("genre"),
        song.get("mood"),
        float(song.get("energy", 0.0)),
        float(song.get("acousticness", 0.0)),
        user_prefs.get("genre"),
        user_prefs.get("mood"),
        target_energy,
        target_acousticness,
        mood_tags=song.get("mood_tags"),
        instrumentalness=float(song.get("instrumentalness", 0.0)),
        target_instrumentalness=instrumental_target(user_prefs.get("wants_instrumental")),
        release_decade=song.get("release_decade"),
        favorite_decade=user_prefs.get("preferred_decade"),
        skip_energy=skip_energy,
        skip_acousticness=skip_acousticness,
    )

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> Tuple[List[Tuple[Dict, float, str]], List[Notice]]:
    """
    Functional implementation of the recommendation logic.
    Required by src/main.py

    Before scoring, raw user_prefs is validated and cleaned by
    src/planner.py's plan_user_prefs: missing/invalid genre or mood raises
    PlanningError (no safe fallback), while missing/invalid energy or
    acousticness are excluded from scoring instead of corrupting it. Every
    decision is logged and returned as a Notice so callers can surface it.

    Returns (results, notices) instead of just results.
    """
    catalog_genres = {song["genre"] for song in songs if song.get("genre")}
    catalog_moods = {song["mood"] for song in songs if song.get("mood")}
    cleaned_prefs, notices = plan_user_prefs(user_prefs, catalog_genres, catalog_moods)
    log_notices(notices)

    preferred_danceability = cleaned_prefs.get("danceability")
    prefer_popular = cleaned_prefs.get("prefer_popular", False)

    if cleaned_prefs.get("clean_only"):
        songs = [song for song in songs if not song.get("explicit_content")]

    scored = []
    for song in songs:
        score, reasons = score_song(cleaned_prefs, song)
        if preferred_danceability is None:
            dance_tie_break = 0.0
        else:
            dance_tie_break = -abs(float(song.get("danceability", 0.0)) - preferred_danceability)
        popularity_tie_break = float(song.get("popularity", 0.0)) if prefer_popular else 0.0
        scored.append((song, score, reasons, dance_tie_break, popularity_tie_break))

    scored.sort(key=lambda item: (item[1], item[3], item[4]), reverse=True)
    results = [
        (song, score, "\n".join(f"   {reason}" for reason in reasons))
        for song, score, reasons, _, _ in scored[:k]
    ]
    return results, notices
