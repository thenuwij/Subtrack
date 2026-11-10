"""Which features a user sees.

Payments (bills and safe to spend) is the core product and always on. The
other features are parked extras: off unless the user turns them on in
Settings, and their data is kept either way.
"""

from typing import Literal, get_args

from sqlalchemy.orm import Session

from app.models import UserPreference

Feature = Literal["spending", "payments", "goals", "workspace"]
ALL_FEATURES: tuple[Feature, ...] = get_args(Feature)
CORE_FEATURES: frozenset[Feature] = frozenset({"payments"})


def enabled_features(pref: UserPreference | None) -> list[Feature]:
    """Return the core features plus any chosen extras, in a stable order."""
    chosen = set(pref.enabled_features or ()) if pref else set()
    on = chosen | CORE_FEATURES
    return [feature for feature in ALL_FEATURES if feature in on]


def feature_enabled(db: Session, user_id: str, feature: Feature) -> bool:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    return feature in enabled_features(pref)
