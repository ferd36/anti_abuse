"""Tests for core.validate: validate_corpus and enforce_temporal_invariants."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile
from core.validate import enforce_temporal_invariants, validate_corpus


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.fixture
def users(now: datetime) -> list[User]:
    return [
        User(
            user_id="u-0001",
            email="a@b.com",
            join_date=now - timedelta(days=30),
            country="US",
            ip_address="1.2.3.4",
            registration_ip="1.2.3.4",
            registration_country="US",
            address="",
            ip_type=IPType.RESIDENTIAL,
            language="en",
        ),
        User(
            user_id="u-0002",
            email="b@b.com",
            join_date=now - timedelta(days=20),
            country="US",
            ip_address="1.2.3.5",
            registration_ip="1.2.3.5",
            registration_country="US",
            address="",
            ip_type=IPType.RESIDENTIAL,
            language="en",
        ),
    ]


@pytest.fixture
def profiles(users: list[User], now: datetime) -> list[UserProfile]:
    join1 = users[0].join_date
    join2 = users[1].join_date
    return [
        UserProfile(
            user_id="u-0001",
            display_name="Alice",
            headline="",
            summary="",
            connections_count=10,
            profile_created_at=join1 + timedelta(minutes=5),
        ),
        UserProfile(
            user_id="u-0002",
            display_name="Bob",
            headline="",
            summary="",
            connections_count=5,
            profile_created_at=join2 + timedelta(minutes=5),
        ),
    ]


class TestValidateCorpus:
    def test_valid_corpus_passes(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        interactions = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        validate_corpus(users, profiles, interactions)

    def test_profile_references_nonexistent_user_fails(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        bad_profile = UserProfile(
            user_id="u-9999",
            display_name="Ghost",
            headline="",
            summary="",
            connections_count=0,
            profile_created_at=now,
        )
        with pytest.raises(AssertionError, match="references non-existent user"):
            validate_corpus(users, profiles + [bad_profile], [])

    def test_interaction_target_references_nonexistent_user_fails(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        interactions = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-9999",
            ),
        ]
        with pytest.raises(AssertionError, match="target_user_id.*references non-existent"):
            validate_corpus(users, profiles, interactions)

    def test_duplicate_interaction_id_fails(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        interactions = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0002",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.5",
                ip_type=IPType.RESIDENTIAL,
            ),
        ]
        with pytest.raises(AssertionError, match="Duplicate interaction_id"):
            validate_corpus(users, profiles, interactions)

    def test_duplicate_email_fails(
        self, profiles: list[UserProfile], now: datetime
    ) -> None:
        users_bad = [
            User(
                user_id="u-0001",
                email="same@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                registration_ip="1.2.3.4",
                registration_country="US",
                address="",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            ),
            User(
                user_id="u-0002",
                email="same@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.5",
                registration_ip="1.2.3.5",
                registration_country="US",
                address="",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            ),
        ]
        with pytest.raises(AssertionError, match="Duplicate email"):
            validate_corpus(users_bad, profiles, [])

    def test_profile_created_before_join_fails(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        bad_profile = UserProfile(
            user_id="u-0001",
            display_name="Alice",
            headline="",
            summary="",
            connections_count=0,
            profile_created_at=users[0].join_date - timedelta(days=1),
        )
        with pytest.raises(AssertionError, match="profile_created_at.*must be >= .*join_date"):
            validate_corpus(users, [bad_profile], [])


class TestEnforceTemporalInvariants:
    def test_valid_sequence_passes(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
        ]
        enforce_temporal_invariants(events)

    def test_close_account_must_be_last_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
        ]
        with pytest.raises(AssertionError, match="CLOSE_ACCOUNT must be last"):
            enforce_temporal_invariants(events)

    def test_fraud_events_require_login_first(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                target_user_id="u-0002",
                metadata={"attack_pattern": "smash_grab"},
            ),
        ]
        with pytest.raises(AssertionError, match="fraud events must have LOGIN, PHISHING_LOGIN, or SESSION_LOGIN first"):
            enforce_temporal_invariants(events)

    def test_fraud_activity_before_first_login_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.DOWNLOAD_ADDRESS_BOOK,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab"},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab", "login_success": True},
            ),
        ]
        with pytest.raises(AssertionError, match="before first login"):
            enforce_temporal_invariants(events)

    def test_fraud_close_account_not_last_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab", "login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab"},
            ),
            UserInteraction(
                interaction_id="evt-3",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                target_user_id="u-0002",
                metadata={"attack_pattern": "smash_grab"},
            ),
        ]
        with pytest.raises(AssertionError, match="CLOSE_ACCOUNT must be last"):
            enforce_temporal_invariants(events)

    def test_non_fraud_account_creation_not_first_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(days=1),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.ACCOUNT_CREATION,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
        ]
        with pytest.raises(AssertionError, match="ACCOUNT_CREATION must be first"):
            enforce_temporal_invariants(events)

    def test_non_fraud_download_address_book_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.DOWNLOAD_ADDRESS_BOOK,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
        ]
        with pytest.raises(AssertionError, match="DOWNLOAD_ADDRESS_BOOK"):
            enforce_temporal_invariants(events)

    def test_non_fraud_message_without_view_fails(self, now: datetime) -> None:
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        with pytest.raises(AssertionError, match="without preceding VIEW_USER_PAGE"):
            enforce_temporal_invariants(events)

    def test_interaction_user_id_nonexistent_fails(
        self, users: list[User], profiles: list[UserProfile], now: datetime
    ) -> None:
        interactions = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-9999",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
        ]
        with pytest.raises(AssertionError, match="user_id.*references non-existent"):
            validate_corpus(users, profiles, interactions)

    def test_fraud_event_timestamp_before_login_fails(self, now: datetime) -> None:
        """Event after first LOGIN but with timestamp before LOGIN raises."""
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab"},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                target_user_id="u-0002",
                metadata={"attack_pattern": "smash_grab"},
            ),
        ]
        with pytest.raises(AssertionError, match="before first login"):
            enforce_temporal_invariants(events)

    def test_non_fraud_session_without_successful_login_skipped(
        self, now: datetime
    ) -> None:
        """Session with only failed LOGIN is skipped (no raise)."""
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": False},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.VIEW_USER_PAGE,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        enforce_temporal_invariants(events)

    def test_fraud_message_before_login_fails(self, now: datetime) -> None:
        """MESSAGE_USER before any LOGIN raises."""
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                target_user_id="u-0002",
                metadata={"attack_pattern": "smash_grab"},
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.HOSTING,
                metadata={"attack_pattern": "smash_grab", "login_success": True},
            ),
        ]
        with pytest.raises(AssertionError, match="before first login"):
            enforce_temporal_invariants(events)

    def test_non_fraud_connect_without_view_fails(self, now: datetime) -> None:
        """CONNECT_WITH_USER for target without preceding VIEW raises."""
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.ACCOUNT_CREATION,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-3",
                user_id="u-0001",
                interaction_type=InteractionType.CONNECT_WITH_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        with pytest.raises(AssertionError, match="without preceding VIEW_USER_PAGE"):
            enforce_temporal_invariants(events)

    def test_non_fraud_message_before_view_timestamp_fails(self, now: datetime) -> None:
        """MESSAGE_USER with timestamp before VIEW for same target raises."""
        events = [
            UserInteraction(
                interaction_id="evt-1",
                user_id="u-0001",
                interaction_type=InteractionType.ACCOUNT_CREATION,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={"login_success": True},
            ),
            UserInteraction(
                interaction_id="evt-3",
                user_id="u-0001",
                interaction_type=InteractionType.VIEW_USER_PAGE,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
            UserInteraction(
                interaction_id="evt-4",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now - timedelta(minutes=5),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        with pytest.raises(AssertionError, match="before VIEW|without preceding VIEW"):
            enforce_temporal_invariants(events)

