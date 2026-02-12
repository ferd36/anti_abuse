"""Core domain types shared across data, db, api, and ml."""

from core.constants import (
    GENERATION_PATTERN_CLEAN,
    INTERACTION_WINDOW_DAYS,
    NUM_FAKE_ACCOUNTS,
    NUM_USERS,
    VALID_ACCOUNT_TIERS,
    VALID_COUNTRIES,
    VALID_LANGUAGES,
)
from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile
from core.validate import enforce_temporal_invariants, validate_corpus

__all__ = [
    "enforce_temporal_invariants",
    "GENERATION_PATTERN_CLEAN",
    "InteractionType",
    "INTERACTION_WINDOW_DAYS",
    "IPType",
    "NUM_FAKE_ACCOUNTS",
    "NUM_USERS",
    "User",
    "UserInteraction",
    "UserProfile",
    "VALID_ACCOUNT_TIERS",
    "VALID_COUNTRIES",
    "VALID_LANGUAGES",
    "validate_corpus",
]
