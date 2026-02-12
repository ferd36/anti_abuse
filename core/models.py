"""
Domain entities for the anti-abuse ATO system.

Each entity enforces invariants in __post_init__ and pre-conditions
on mutating methods via assertions.

Entities:
  - User: core account identity
  - UserProfile: public-facing profile data
  - UserInteraction: single logged interaction event
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.enums import (
    VALID_ACCOUNT_TIERS,
    VALID_COUNTRIES,
    VALID_LANGUAGES,
    VALID_USER_TYPES,
    InteractionType,
    IPType,
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


# ===================================================================
# User
# ===================================================================
@dataclass(frozen=True)
class User:
    """
    Core account identity for a platform user.

    Invariants:
      - user_id is a non-empty string.
      - email matches a basic email pattern.
      - join_date is a timezone-aware UTC datetime.
      - join_date is not in the future.
      - country is a valid ISO 3166-1 alpha-2 code from the allowed set.
      - ip_address is a valid IPv4 address.
      - registration_ip is the IPv4 address used at account creation (join_date).
      - registration_country is where the user signed up; equals country unless moved.
      - address is current address string; for moved users, reflects new location.
      - ip_type is a valid IPType enum member.
      - language is a valid language code from the allowed set.
      - is_active is a boolean.
      - email_verified, two_factor_enabled, phone_verified are booleans.
      - last_password_change_at, if provided, is timezone-aware, not in the future,
        and >= join_date.
      - account_tier is one of VALID_ACCOUNT_TIERS.
      - failed_login_streak >= 0.
      - user_type is one of VALID_USER_TYPES (regular or recruiter).
    """

    user_id: str
    email: str
    join_date: datetime
    country: str
    ip_address: str
    registration_ip: str  # IP used at account creation (matches registration_country)
    registration_country: str  # Where user signed up; differs from country when moved
    address: str  # Current address; for moved users, reflects new location
    ip_type: IPType
    language: str
    is_active: bool = True
    generation_pattern: str = "clean"  # source of truth: "clean" or attack pattern name
    email_verified: bool = True
    two_factor_enabled: bool = False
    last_password_change_at: datetime | None = None
    account_tier: str = "free"
    failed_login_streak: int = 0
    phone_verified: bool = False
    user_type: str = "regular"  # "regular" | "recruiter"

    def __post_init__(self) -> None:
        # --- user_id ---
        assert isinstance(self.user_id, str) and len(self.user_id) > 0, (
            f"user_id must be a non-empty string, got {self.user_id!r}"
        )

        # --- email ---
        assert isinstance(self.email, str) and _EMAIL_RE.match(self.email), (
            f"email must match basic email pattern, got {self.email!r}"
        )

        # --- join_date ---
        assert isinstance(self.join_date, datetime), (
            f"join_date must be a datetime, got {type(self.join_date)}"
        )
        assert self.join_date.tzinfo is not None, (
            "join_date must be timezone-aware (UTC)"
        )
        assert self.join_date <= datetime.now(timezone.utc), (
            f"join_date must not be in the future, got {self.join_date}"
        )

        # --- country ---
        assert self.country in VALID_COUNTRIES, (
            f"country must be one of {VALID_COUNTRIES}, got {self.country!r}"
        )

        # --- ip_address ---
        assert isinstance(self.ip_address, str) and _IPV4_RE.match(self.ip_address), (
            f"ip_address must be a valid IPv4 address, got {self.ip_address!r}"
        )

        # --- registration_ip ---
        assert isinstance(self.registration_ip, str) and _IPV4_RE.match(self.registration_ip), (
            f"registration_ip must be a valid IPv4 address, got {self.registration_ip!r}"
        )

        # --- registration_country ---
        assert self.registration_country in VALID_COUNTRIES, (
            f"registration_country must be one of {VALID_COUNTRIES}, got {self.registration_country!r}"
        )

        # --- address ---
        assert isinstance(self.address, str), (
            f"address must be a string, got {type(self.address)}"
        )

        # --- ip_type ---
        assert isinstance(self.ip_type, IPType), (
            f"ip_type must be an IPType enum, got {self.ip_type!r}"
        )

        # --- language ---
        assert self.language in VALID_LANGUAGES, (
            f"language must be one of {VALID_LANGUAGES}, got {self.language!r}"
        )

        # --- is_active ---
        assert isinstance(self.is_active, bool), (
            f"is_active must be a boolean, got {type(self.is_active)}"
        )

        # --- generation_pattern ---
        assert isinstance(self.generation_pattern, str) and len(self.generation_pattern) > 0, (
            f"generation_pattern must be a non-empty string, got {self.generation_pattern!r}"
        )

        # --- email_verified ---
        assert isinstance(self.email_verified, bool), (
            f"email_verified must be a boolean, got {type(self.email_verified)}"
        )

        # --- two_factor_enabled ---
        assert isinstance(self.two_factor_enabled, bool), (
            f"two_factor_enabled must be a boolean, got {type(self.two_factor_enabled)}"
        )

        # --- last_password_change_at ---
        if self.last_password_change_at is not None:
            assert isinstance(self.last_password_change_at, datetime), (
                f"last_password_change_at must be a datetime, got {type(self.last_password_change_at)}"
            )
            assert self.last_password_change_at.tzinfo is not None, (
                "last_password_change_at must be timezone-aware"
            )
            assert self.last_password_change_at <= datetime.now(timezone.utc), (
                "last_password_change_at must not be in the future"
            )
            assert self.last_password_change_at >= self.join_date, (
                "last_password_change_at must be >= join_date"
            )

        # --- account_tier ---
        assert self.account_tier in VALID_ACCOUNT_TIERS, (
            f"account_tier must be one of {VALID_ACCOUNT_TIERS}, got {self.account_tier!r}"
        )

        # --- failed_login_streak ---
        assert isinstance(self.failed_login_streak, int) and self.failed_login_streak >= 0, (
            f"failed_login_streak must be >= 0, got {self.failed_login_streak}"
        )

        # --- phone_verified ---
        assert isinstance(self.phone_verified, bool), (
            f"phone_verified must be a boolean, got {type(self.phone_verified)}"
        )

        # --- user_type ---
        assert self.user_type in VALID_USER_TYPES, (
            f"user_type must be one of {VALID_USER_TYPES}, got {self.user_type!r}"
        )


# ===================================================================
# UserProfile
# ===================================================================
@dataclass(frozen=True)
class UserProfile:
    """
    Public-facing profile information attached to a User.

    Invariants:
      - user_id is a non-empty string (FK to User).
      - display_name is a non-empty string, max 100 chars, no leading/trailing whitespace.
      - headline is a string, max 200 chars (may be empty).
      - summary is a string, max 2000 chars (may be empty).
      - connections_count >= 0.
      - profile_created_at is timezone-aware and not in the future.
      - last_updated_at >= profile_created_at (if provided).
      - has_profile_photo is a boolean.
      - profile_completeness is a float in [0.0, 1.0].
      - endorsements_count >= 0.
      - profile_views_received >= 0.
      - location_text is a string, max 200 chars.
    """

    user_id: str
    display_name: str
    headline: str
    summary: str
    connections_count: int
    profile_created_at: datetime
    last_updated_at: datetime | None = None
    has_profile_photo: bool = False
    profile_completeness: float = 0.0
    endorsements_count: int = 0
    profile_views_received: int = 0
    location_text: str = ""

    def __post_init__(self) -> None:
        # --- user_id ---
        assert isinstance(self.user_id, str) and len(self.user_id) > 0, (
            f"user_id must be a non-empty string, got {self.user_id!r}"
        )

        # --- display_name ---
        assert isinstance(self.display_name, str) and 0 < len(self.display_name) <= 100, (
            f"display_name must be 1-100 chars, got {len(self.display_name)} chars"
        )
        assert self.display_name == self.display_name.strip(), (
            "display_name must not have leading or trailing whitespace"
        )

        # --- headline ---
        assert isinstance(self.headline, str) and len(self.headline) <= 200, (
            f"headline must be max 200 chars, got {len(self.headline)} chars"
        )

        # --- summary ---
        assert isinstance(self.summary, str) and len(self.summary) <= 2000, (
            f"summary must be max 2000 chars, got {len(self.summary)} chars"
        )

        # --- connections_count ---
        assert isinstance(self.connections_count, int) and self.connections_count >= 0, (
            f"connections_count must be >= 0, got {self.connections_count}"
        )

        # --- profile_created_at ---
        assert isinstance(self.profile_created_at, datetime), (
            f"profile_created_at must be a datetime, got {type(self.profile_created_at)}"
        )
        assert self.profile_created_at.tzinfo is not None, (
            "profile_created_at must be timezone-aware"
        )
        assert self.profile_created_at <= datetime.now(timezone.utc), (
            "profile_created_at must not be in the future"
        )

        # --- last_updated_at ---
        if self.last_updated_at is not None:
            assert isinstance(self.last_updated_at, datetime), (
                f"last_updated_at must be a datetime, got {type(self.last_updated_at)}"
            )
            assert self.last_updated_at.tzinfo is not None, (
                "last_updated_at must be timezone-aware"
            )
            assert self.last_updated_at >= self.profile_created_at, (
                f"last_updated_at ({self.last_updated_at}) must be >= "
                f"profile_created_at ({self.profile_created_at})"
            )

        # --- has_profile_photo ---
        assert isinstance(self.has_profile_photo, bool), (
            f"has_profile_photo must be a boolean, got {type(self.has_profile_photo)}"
        )

        # --- profile_completeness ---
        assert isinstance(self.profile_completeness, (int, float)) and 0.0 <= self.profile_completeness <= 1.0, (
            f"profile_completeness must be in [0.0, 1.0], got {self.profile_completeness}"
        )

        # --- endorsements_count ---
        assert isinstance(self.endorsements_count, int) and self.endorsements_count >= 0, (
            f"endorsements_count must be >= 0, got {self.endorsements_count}"
        )

        # --- profile_views_received ---
        assert isinstance(self.profile_views_received, int) and self.profile_views_received >= 0, (
            f"profile_views_received must be >= 0, got {self.profile_views_received}"
        )

        # --- location_text ---
        assert isinstance(self.location_text, str) and len(self.location_text) <= 200, (
            f"location_text must be max 200 chars, got {len(self.location_text)} chars"
        )


# ===================================================================
# UserInteraction
# ===================================================================
@dataclass(frozen=True)
class UserInteraction:
    """
    A single logged interaction event.

    Invariants:
      - interaction_id is a non-empty string.
      - user_id is a non-empty string (FK to User).
      - interaction_type is a valid InteractionType enum.
      - timestamp is timezone-aware and not in the future.
      - ip_address is a valid IPv4 address.
      - ip_type is a valid IPType enum.
      - target_user_id, when provided, must be a non-empty string
        and must differ from user_id (cannot interact with self).
      - metadata is a dict (may be empty); all keys must be strings.
      - session_id, when provided, must be a non-empty string.

    Pre-conditions on interaction_type vs target_user_id:
      - MESSAGE_USER, VIEW_USER_PAGE, CONNECT_WITH_USER, LIKE, REACT require target_user_id.
      - ACCOUNT_CREATION, LOGIN, CHANGE_PASSWORD, CHANGE_PROFILE, CHANGE_NAME,
        UPDATE_HEADLINE, UPDATE_SUMMARY, CHANGE_LAST_NAME,
        SEARCH_CANDIDATES, UPLOAD_ADDRESS_BOOK, DOWNLOAD_ADDRESS_BOOK, CLOSE_ACCOUNT
        must NOT have target_user_id.
    """

    interaction_id: str
    user_id: str
    interaction_type: InteractionType
    timestamp: datetime
    ip_address: str
    ip_type: IPType
    target_user_id: str | None = None
    metadata: dict = field(default_factory=dict)
    session_id: str | None = None

    # Interactions that require a target user
    _REQUIRES_TARGET = frozenset({
        InteractionType.MESSAGE_USER,
        InteractionType.VIEW_USER_PAGE,
        InteractionType.CONNECT_WITH_USER,
        InteractionType.LIKE,
        InteractionType.REACT,
    })

    # Interactions that must NOT have a target user
    _NO_TARGET = frozenset({
        InteractionType.ACCOUNT_CREATION,
        InteractionType.LOGIN,
        InteractionType.CHANGE_PASSWORD,
        InteractionType.CHANGE_PROFILE,
        InteractionType.CHANGE_NAME,
        InteractionType.UPDATE_HEADLINE,
        InteractionType.UPDATE_SUMMARY,
        InteractionType.CHANGE_LAST_NAME,
        InteractionType.SEARCH_CANDIDATES,
        InteractionType.UPLOAD_ADDRESS_BOOK,
        InteractionType.DOWNLOAD_ADDRESS_BOOK,
        InteractionType.CLOSE_ACCOUNT,
    })

    def __post_init__(self) -> None:
        # --- interaction_id ---
        assert isinstance(self.interaction_id, str) and len(self.interaction_id) > 0, (
            f"interaction_id must be a non-empty string, got {self.interaction_id!r}"
        )

        # --- user_id ---
        assert isinstance(self.user_id, str) and len(self.user_id) > 0, (
            f"user_id must be a non-empty string, got {self.user_id!r}"
        )

        # --- interaction_type ---
        assert isinstance(self.interaction_type, InteractionType), (
            f"interaction_type must be InteractionType, got {self.interaction_type!r}"
        )

        # --- timestamp ---
        assert isinstance(self.timestamp, datetime), (
            f"timestamp must be a datetime, got {type(self.timestamp)}"
        )
        assert self.timestamp.tzinfo is not None, (
            "timestamp must be timezone-aware (UTC)"
        )
        assert self.timestamp <= datetime.now(timezone.utc), (
            f"timestamp must not be in the future, got {self.timestamp}"
        )

        # --- ip_address ---
        assert isinstance(self.ip_address, str) and _IPV4_RE.match(self.ip_address), (
            f"ip_address must be a valid IPv4 address, got {self.ip_address!r}"
        )

        # --- ip_type ---
        assert isinstance(self.ip_type, IPType), (
            f"ip_type must be an IPType enum, got {self.ip_type!r}"
        )

        # --- target_user_id logic ---
        if self.interaction_type in self._REQUIRES_TARGET:
            assert self.target_user_id is not None and len(self.target_user_id) > 0, (
                f"{self.interaction_type.value} requires a non-empty target_user_id"
            )
            assert self.target_user_id != self.user_id, (
                f"target_user_id must differ from user_id "
                f"(cannot interact with self), both are {self.user_id!r}"
            )
        elif self.interaction_type in self._NO_TARGET:
            assert self.target_user_id is None, (
                f"{self.interaction_type.value} must not have a target_user_id, "
                f"got {self.target_user_id!r}"
            )

        # --- metadata ---
        assert isinstance(self.metadata, dict), (
            f"metadata must be a dict, got {type(self.metadata)}"
        )
        for k in self.metadata:
            assert isinstance(k, str), (
                f"metadata keys must be strings, got key {k!r} with type {type(k)}"
            )

        # --- session_id ---
        if self.session_id is not None:
            assert isinstance(self.session_id, str) and len(self.session_id) > 0, (
                f"session_id, when provided, must be a non-empty string, got {self.session_id!r}"
            )
