"""The four features a user can switch on at onboarding or in Settings."""

from typing import Literal, get_args

from app.models import UserPreference

Feature = Literal["spending", "payments", "goals", "workspace"]
ALL_FEATURES: tuple[Feature, ...] = get_args(Feature)


def enabled_features(pref: UserPreference | None) -> list[Feature]:
    """Return the user's features in a stable order; no choice yet means all."""
    chosen = set(pref.enabled_features or ()) if pref else set()
    if not chosen:
        return list(ALL_FEATURES)
    return [feature for feature in ALL_FEATURES if feature in chosen]
