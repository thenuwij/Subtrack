"""The four features a user can switch on at onboarding or in Settings."""

from typing import Literal, get_args

from sqlalchemy.orm import Session

from app.models import UserPreference

Feature = Literal["spending", "payments", "goals", "workspace"]
ALL_FEATURES: tuple[Feature, ...] = get_args(Feature)


def enabled_features(pref: UserPreference | None) -> list[Feature]:
    """Return the user's features in a stable order; no choice yet means all."""
    chosen = set(pref.enabled_features or ()) if pref else set()
    if not chosen:
        return list(ALL_FEATURES)
    return [feature for feature in ALL_FEATURES if feature in chosen]


def feature_enabled(db: Session, user_id: str, feature: Feature) -> bool:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    return feature in enabled_features(pref)
