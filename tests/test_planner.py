import logging
import math

import pytest

from src.planner import PlanningError, plan_user_prefs
from src.recommender import recommend_songs, score_song

CATALOG_GENRES = {"pop", "lofi"}
CATALOG_MOODS = {"happy", "chill"}


def make_songs():
    return [
        {
            "genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 0.2,
            "danceability": 0.8, "title": "Test Pop Track", "artist": "Test Artist",
        },
        {
            "genre": "lofi", "mood": "chill", "energy": 0.4, "acousticness": 0.9,
            "danceability": 0.5, "title": "Chill Lofi Loop", "artist": "Test Artist",
        },
    ]


def test_valid_input_produces_no_notices():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert notices == []
    assert cleaned["genre"] == "pop"
    assert cleaned["energy"] == 0.8


def test_nan_energy_is_excluded_instead_of_corrupting_the_score():
    prefs = {"genre": "pop", "mood": "happy", "energy": float("nan"), "likes_acoustic": False}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["_skip_energy"] is True
    assert any(n.level == "warning" and n.field == "energy" for n in notices)

    results, _ = recommend_songs(prefs, make_songs(), k=2)
    assert results
    for _, score, _ in results:
        assert not math.isnan(score)


def test_boolean_under_acousticness_key_is_recovered():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": True}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["likes_acoustic"] is True
    assert any(n.level == "warning" and n.field == "acousticness" for n in notices)


def test_numeric_acousticness_is_used_as_fine_grained_target():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 0.6}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["target_acousticness"] == 0.6
    assert "likes_acoustic" not in cleaned
    assert not cleaned.get("_skip_acousticness")
    assert any(n.level == "info" and n.field == "acousticness" for n in notices)


def test_out_of_range_numeric_acousticness_is_excluded():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 1.5}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["_skip_acousticness"] is True
    assert "target_acousticness" not in cleaned
    assert any(n.level == "warning" and n.field == "acousticness" for n in notices)


def test_nan_acousticness_is_excluded_instead_of_corrupting_the_score():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": float("nan")}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["_skip_acousticness"] is True
    assert any(n.level == "warning" and n.field == "acousticness" for n in notices)


def test_numeric_acousticness_target_is_honored_by_score_song():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 0.6}
    cleaned, _ = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)
    song = {
        "genre": "pop", "mood": "happy", "energy": 0.8, "acousticness": 0.6,
        "danceability": 0.8,
    }

    _, reasons = score_song(cleaned, song)

    assert any("vs target 0.60" in reason for reason in reasons)


def test_trailing_whitespace_in_genre_is_trimmed():
    prefs = {"genre": "pop ", "mood": "happy", "energy": 0.8, "likes_acoustic": False}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["genre"] == "pop"
    assert any(n.level == "info" and n.field == "genre" for n in notices)


def test_missing_genre_raises_planning_error():
    prefs = {"mood": "happy", "energy": 0.8}

    with pytest.raises(PlanningError):
        plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)


def test_genre_typo_warns_but_still_ranks():
    prefs = {"genre": "popp", "mood": "happy", "energy": 0.8, "likes_acoustic": False}
    cleaned, notices = plan_user_prefs(prefs, CATALOG_GENRES, CATALOG_MOODS)

    assert cleaned["genre"] == "popp"  # strict-match design preserved, not fuzzy-corrected
    assert any(n.level == "warning" and n.field == "genre" for n in notices)

    results, _ = recommend_songs(prefs, make_songs(), k=2)
    assert results


def test_recommend_songs_returns_results_and_notices():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}
    results, notices = recommend_songs(prefs, make_songs(), k=2)

    assert notices == []
    assert len(results) == 2
    assert results[0][0]["genre"] == "pop"


def test_notices_are_logged_to_the_planner_logger(caplog):
    prefs = {"genre": "pop", "mood": "happy", "energy": float("nan"), "likes_acoustic": False}

    with caplog.at_level(logging.INFO, logger="recommender.planner"):
        recommend_songs(prefs, make_songs(), k=2)

    assert any("energy" in record.message.lower() for record in caplog.records)
