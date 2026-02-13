"""
System-wide constants for the anti-abuse system.

Domain validation, mock data config, and shared literals.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain validation (used by models, validate)
# ---------------------------------------------------------------------------

VALID_COUNTRIES = frozenset({
    "US", "GB", "CA", "AU", "DE", "FR", "IN", "BR", "JP", "KR",
    "NG", "RU", "CN", "MX", "ZA", "IT", "ES", "NL", "SE", "PL",
    "UA", "RO", "VN", "PH", "ID", "TR", "EG", "PK", "BD", "TH",
})

VALID_LANGUAGES = frozenset({
    "en", "es", "fr", "de", "pt", "ja", "ko", "zh", "hi", "ar",
    "ru", "it", "nl", "sv", "pl", "uk", "ro", "vi", "tl", "id",
    "tr", "th", "bn", "ca", "af",
})

VALID_ACCOUNT_TIERS = frozenset({"free", "premium", "enterprise"})

VALID_USER_TYPES = frozenset({"regular", "recruiter"})

GENERATION_PATTERN_CLEAN = "clean"

# ---------------------------------------------------------------------------
# Mock data config
# ---------------------------------------------------------------------------

NUM_USERS = 100_000
NUM_FAKE_ACCOUNTS = 5
NUM_PHARMACY_ACCOUNTS = 25
NUM_COVERT_PORN_ACCOUNTS = 20
NUM_ACCOUNT_FARMING_ACCOUNTS = 15
NUM_HARASSMENT_ACCOUNTS = 12
NUM_LIKE_INFLATION_ACCOUNTS = 10
NUM_PROFILE_CLONING_ACCOUNTS = 8
NUM_ENDORSEMENT_INFLATION_ACCOUNTS = 12
NUM_RECOMMENDATION_FRAUD_ACCOUNTS = 10
NUM_JOB_SCAM_ACCOUNTS = 6
NUM_INVITATION_SPAM_ACCOUNTS = 15
NUM_GROUP_SPAM_ACCOUNTS = 8
INTERACTION_WINDOW_DAYS = 60
