"""
Validation/planning layer that sits in front of the recommender's scoring step.

Raw user preferences (from the CLI or the Streamlit sidebar) can be messy:
missing fields, NaN values, wrong types, or typo'd field names. Rather than
letting that bad data silently flow into the score (see the stress tests in
README.md and model_card.md §6-8), `plan_user_prefs` inspects it up front,
decides what to do about each problem, and returns a clean set of preferences
plus a list of Notices describing every decision it made. Every notice is also
written to `logs/recommender.log` so there's a durable record of what happened.
"""

import logging
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Set

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "recommender.log")

PLANNER_LOGGER = logging.getLogger("recommender.planner")


class PlanningError(Exception):
    """Raised when a preference is missing/invalid and there's no safe fallback."""


@dataclass
class Notice:
    level: str  # "info" or "warning"
    field: str
    message: str


def configure_logging() -> None:
    """
    Wires PLANNER_LOGGER to write to logs/recommender.log. Safe to call more
    than once (e.g. from both main.py and app.py) since it checks for an
    existing handler first.
    """
    if PLANNER_LOGGER.handlers:
        return

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handler = logging.FileHandler(LOG_PATH)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    PLANNER_LOGGER.addHandler(handler)
    PLANNER_LOGGER.setLevel(logging.INFO)
    # File is the only destination; don't also dump WARNING+ to stderr via the
    # root logger's handler of last resort. Callers (main.py/app.py) decide
    # how to surface notices to the listener, from the returned Notice list.
    PLANNER_LOGGER.propagate = False


def log_notices(notices: List[Notice]) -> None:
    for notice in notices:
        level = logging.WARNING if notice.level == "warning" else logging.INFO
        PLANNER_LOGGER.log(level, "[%s] %s", notice.field, notice.message)


def _is_real_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _plan_categorical(raw_prefs: Dict, cleaned: Dict, notices: List[Notice], field: str, catalog_values: Set[str]) -> None:
    value = raw_prefs.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PlanningError(
            f"'{field}' is required and must be a non-empty string, got {value!r}"
        )

    stripped = value.strip()
    if stripped != value:
        notices.append(Notice(
            level="info", field=field,
            message=f"trimmed whitespace from {field} ('{value}' -> '{stripped}')",
        ))
    cleaned[field] = stripped

    if stripped not in catalog_values:
        notices.append(Notice(
            level="warning", field=field,
            message=f"{field} '{stripped}' was not found anywhere in the catalog; no exact match is possible",
        ))


def _plan_energy(raw_prefs: Dict, cleaned: Dict, notices: List[Notice]) -> None:
    if "energy" not in raw_prefs:
        cleaned["energy"] = 0.5
        notices.append(Notice(
            level="info", field="energy",
            message="no energy preference given; using neutral default (0.5)",
        ))
        return

    value = raw_prefs["energy"]
    if not _is_real_number(value) or not (0.0 <= value <= 1.0):
        cleaned["_skip_energy"] = True
        notices.append(Notice(
            level="warning", field="energy",
            message=f"energy value {value!r} is invalid (must be a number in [0, 1]); "
                    f"excluding energy from scoring instead of letting it corrupt the ranking",
        ))
    else:
        cleaned["energy"] = float(value)


def _plan_acousticness(raw_prefs: Dict, cleaned: Dict, notices: List[Notice]) -> None:
    likes_acoustic = raw_prefs.get("likes_acoustic")
    acousticness_value = raw_prefs.get("acousticness")

    if likes_acoustic is None and isinstance(acousticness_value, bool):
        # The documented bug: a boolean preference typed under the wrong key
        # ("acousticness") instead of "likes_acoustic" used to be silently
        # ignored entirely. Recover the listener's evident intent instead.
        cleaned["likes_acoustic"] = acousticness_value
        notices.append(Notice(
            level="warning", field="acousticness",
            message=f"found a boolean under 'acousticness' ({acousticness_value!r}); "
                    f"treating it as likes_acoustic={acousticness_value!r} "
                    f"(pass a numeric 0-1 value under 'acousticness' for a fine-grained target instead)",
        ))
        return

    if likes_acoustic is None and acousticness_value is not None:
        # A numeric fine-grained target, as promised by the notice above:
        # bypasses the coarse liked/disliked anchor and scores directly
        # against the listener's requested value.
        if _is_real_number(acousticness_value) and 0.0 <= acousticness_value <= 1.0:
            cleaned["target_acousticness"] = float(acousticness_value)
            notices.append(Notice(
                level="info", field="acousticness",
                message=f"using numeric acousticness={float(acousticness_value)!r} as a fine-grained target",
            ))
        else:
            cleaned["_skip_acousticness"] = True
            notices.append(Notice(
                level="warning", field="acousticness",
                message=f"acousticness value {acousticness_value!r} is invalid (must be a number in [0, 1]); "
                        f"excluding acousticness from scoring instead of letting it corrupt the ranking",
            ))
        return

    if likes_acoustic is None:
        notices.append(Notice(
            level="info", field="likes_acoustic",
            message="no acoustic preference given; using neutral default",
        ))
        return

    if not isinstance(likes_acoustic, bool):
        cleaned["_skip_acousticness"] = True
        notices.append(Notice(
            level="warning", field="likes_acoustic",
            message=f"likes_acoustic value {likes_acoustic!r} is invalid (must be a bool); "
                    f"excluding acousticness from scoring",
        ))


def plan_user_prefs(raw_prefs: Dict, catalog_genres: Set[str], catalog_moods: Set[str]) -> "tuple[Dict, List[Notice]]":
    """
    Validates and cleans raw user preferences before scoring.

    Returns (cleaned_prefs, notices). Raises PlanningError for problems with
    no safe fallback (missing/invalid genre or mood). Never mutates raw_prefs.
    """
    cleaned = dict(raw_prefs)
    notices: List[Notice] = []

    _plan_categorical(raw_prefs, cleaned, notices, "genre", catalog_genres)
    _plan_categorical(raw_prefs, cleaned, notices, "mood", catalog_moods)
    _plan_energy(raw_prefs, cleaned, notices)
    _plan_acousticness(raw_prefs, cleaned, notices)

    return cleaned, notices
