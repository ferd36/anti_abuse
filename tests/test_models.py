"""
Unit tests for domain models: User, UserProfile, UserInteraction.

Tests cover:
  - Valid construction.
  - All invariant violations.
  - Pre-condition enforcement on interaction types.
"""

import pytest
from datetime import datetime, timedelta, timezone

from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile


# ===================================================================
# Fixtures
# ===================================================================
@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.fixture
def valid_user(now: datetime) -> User:
    return User(
        user_id="u-0001",
        email="alice@example.com",
        join_date=now - timedelta(days=30),
        country="US",
        ip_address="203.0.113.1",
        ip_type=IPType.RESIDENTIAL,
        language="en",
        is_active=True,
    )


@pytest.fixture
def valid_profile(now: datetime) -> UserProfile:
    join = now - timedelta(days=30)
    return UserProfile(
        user_id="u-0001",
        display_name="Alice Smith",
        headline="Software Engineer",
        summary="Loves coding.",
        connections_count=42,
        profile_created_at=join + timedelta(minutes=5),
        last_updated_at=join + timedelta(days=10),
    )


@pytest.fixture
def valid_interaction(now: datetime) -> UserInteraction:
    return UserInteraction(
        interaction_id="evt-0001",
        user_id="u-0001",
        interaction_type=InteractionType.LOGIN,
        timestamp=now,
        ip_address="203.0.113.1",
        ip_type=IPType.RESIDENTIAL,
    )


# ===================================================================
# User tests
# ===================================================================
class TestUser:
    def test_valid_creation(self, valid_user: User) -> None:
        assert valid_user.user_id == "u-0001"
        assert valid_user.email == "alice@example.com"
        assert valid_user.is_active is True
        assert valid_user.user_type == "regular"

    def test_recruiter_user_type(self, now: datetime) -> None:
        user = User(
            user_id="u-rec1",
            email="recruiter@hr.com",
            join_date=now,
            country="US",
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            language="en",
            user_type="recruiter",
        )
        assert user.user_type == "recruiter"

    def test_invalid_user_type_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="user_type must be one of"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                user_type="invalid",
            )

    def test_empty_user_id_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="user_id must be a non-empty string"):
            User(
                user_id="",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_invalid_email_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="email must match"):
            User(
                user_id="u-0001",
                email="not-an-email",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_future_join_date_fails(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(AssertionError, match="join_date must not be in the future"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=future,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_naive_join_date_fails(self) -> None:
        with pytest.raises(AssertionError, match="timezone-aware"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=datetime(2024, 1, 1),
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_invalid_country_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="country must be one of"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="XX",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_invalid_ip_address_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="ip_address must be a valid IPv4"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="999.999.999.999",
                ip_type=IPType.RESIDENTIAL,
                language="en",
            )

    def test_invalid_language_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="language must be one of"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="zz",
            )

    def test_ip_type_must_be_enum(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="ip_type must be an IPType"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type="residential",  # type: ignore
                language="en",
            )

    def test_is_active_defaults_to_true(self, now: datetime) -> None:
        user = User(
            user_id="u-0001",
            email="a@b.com",
            join_date=now,
            country="US",
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            language="en",
        )
        assert user.is_active is True

    def test_negative_failed_login_streak_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="failed_login_streak must be >= 0"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                failed_login_streak=-1,
            )

    def test_empty_generation_pattern_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="generation_pattern must be a non-empty string"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                generation_pattern="",
            )

    def test_invalid_account_tier_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="account_tier"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                account_tier="invalid",
            )

    def test_naive_last_password_change_at_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="last_password_change_at must be timezone-aware"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                last_password_change_at=datetime(2024, 1, 1),
            )

    def test_last_password_change_before_join_fails(self, now: datetime) -> None:
        join = now - timedelta(days=30)
        pw_change = join - timedelta(days=1)
        with pytest.raises(AssertionError, match="last_password_change_at must be >= join_date"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=join,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                last_password_change_at=pw_change,
            )

    def test_last_password_change_in_future_fails(self, now: datetime) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(AssertionError, match="last_password_change_at must not be in the future"):
            User(
                user_id="u-0001",
                email="a@b.com",
                join_date=now,
                country="US",
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                language="en",
                last_password_change_at=future,
            )


# ===================================================================
# UserProfile tests
# ===================================================================
class TestUserProfile:
    def test_valid_creation(self, valid_profile: UserProfile) -> None:
        assert valid_profile.user_id == "u-0001"
        assert valid_profile.display_name == "Alice Smith"
        assert valid_profile.connections_count == 42

    def test_empty_display_name_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="display_name must be 1-100 chars"):
            UserProfile(
                user_id="u-0001",
                display_name="",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
            )

    def test_display_name_too_long_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="display_name must be 1-100 chars"):
            UserProfile(
                user_id="u-0001",
                display_name="x" * 101,
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
            )

    def test_headline_too_long_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="headline must be max 200"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="x" * 201,
                summary="",
                connections_count=0,
                profile_created_at=now,
            )

    def test_summary_too_long_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="summary must be max 2000"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="x" * 2001,
                connections_count=0,
                profile_created_at=now,
            )

    def test_negative_connections_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="connections_count must be >= 0"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=-1,
                profile_created_at=now,
            )

    def test_naive_profile_created_at_fails(self) -> None:
        with pytest.raises(AssertionError, match="timezone-aware"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=datetime(2024, 1, 1),
            )

    def test_last_updated_before_created_fails(self, now: datetime) -> None:
        created = now - timedelta(days=10)
        with pytest.raises(AssertionError, match="last_updated_at .* must be >="):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=created,
                last_updated_at=created - timedelta(days=1),
            )

    def test_last_updated_at_none_is_ok(self, now: datetime) -> None:
        profile = UserProfile(
            user_id="u-0001",
            display_name="Alice",
            headline="",
            summary="",
            connections_count=0,
            profile_created_at=now,
            last_updated_at=None,
        )
        assert profile.last_updated_at is None

    def test_profile_completeness_out_of_range_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="profile_completeness must be in"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
                profile_completeness=1.5,
            )

    def test_profile_completeness_negative_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="profile_completeness must be in"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
                profile_completeness=-0.1,
            )

    def test_profile_created_at_future_fails(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(AssertionError, match="profile_created_at must not be in the future"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=future,
            )

    def test_display_name_with_whitespace_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="display_name must not have leading or trailing whitespace"):
            UserProfile(
                user_id="u-0001",
                display_name=" Alice ",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
            )

    def test_location_text_too_long_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="location_text must be max 200"):
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now,
                location_text="x" * 201,
            )


# ===================================================================
# UserInteraction tests
# ===================================================================
class TestUserInteraction:
    def test_valid_login(self, valid_interaction: UserInteraction) -> None:
        assert valid_interaction.interaction_type == InteractionType.LOGIN
        assert valid_interaction.target_user_id is None

    def test_like_requires_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.LIKE,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        )
        assert i.target_user_id == "u-0002"

    def test_react_requires_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.REACT,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
            metadata={"reaction_type": "celebrate"},
        )
        assert i.target_user_id == "u-0002"

    def test_like_without_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="requires a non-empty target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LIKE,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id=None,
            )

    def test_valid_message_with_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.MESSAGE_USER,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        )
        assert i.target_user_id == "u-0002"

    def test_message_without_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="requires a non-empty target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id=None,
            )

    def test_view_page_without_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="requires a non-empty target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.VIEW_USER_PAGE,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_connect_without_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="requires a non-empty target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.CONNECT_WITH_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_self_interaction_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="cannot interact with self"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0001",
            )

    def test_login_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )

    def test_close_account_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )

    def test_upload_address_book_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.UPLOAD_ADDRESS_BOOK,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )

    def test_download_address_book_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.DOWNLOAD_ADDRESS_BOOK,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )

    def test_future_timestamp_fails(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(AssertionError, match="timestamp must not be in the future"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=future,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_naive_timestamp_fails(self) -> None:
        with pytest.raises(AssertionError, match="timezone-aware"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=datetime(2024, 1, 1),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_invalid_ip_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="ip_address must be a valid IPv4"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="not-an-ip",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_empty_interaction_id_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="interaction_id must be a non-empty"):
            UserInteraction(
                interaction_id="",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )

    def test_metadata_defaults_to_empty_dict(self, valid_interaction: UserInteraction) -> None:
        assert valid_interaction.metadata == {}

    def test_metadata_non_string_key_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="metadata keys must be strings"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata={42: "invalid"},  # type: ignore
            )

    def test_metadata_with_content(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.LOGIN,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            metadata={"user_agent": "Chrome"},
        )
        assert i.metadata == {"user_agent": "Chrome"}

    def test_empty_target_user_id_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="requires a non-empty target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="",
            )

    def test_empty_session_id_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="session_id.*must be a non-empty"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                session_id="",
            )

    def test_metadata_must_be_dict(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="metadata must be a dict"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                metadata="not-a-dict",  # type: ignore
            )

    def test_update_headline_no_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.UPDATE_HEADLINE,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            metadata={"reason": "job_change"},
        )
        assert i.target_user_id is None

    def test_change_last_name_no_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.CHANGE_LAST_NAME,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            metadata={"reason": "marriage"},
        )
        assert i.target_user_id is None

    def test_search_candidates_no_target(self, now: datetime) -> None:
        i = UserInteraction(
            interaction_id="evt-0002",
            user_id="u-0001",
            interaction_type=InteractionType.SEARCH_CANDIDATES,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            metadata={"role": "engineer", "results_count": 42},
        )
        assert i.target_user_id is None

    def test_update_headline_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.UPDATE_HEADLINE,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )

    def test_account_creation_with_target_fails(self, now: datetime) -> None:
        with pytest.raises(AssertionError, match="must not have a target_user_id"):
            UserInteraction(
                interaction_id="evt-0002",
                user_id="u-0001",
                interaction_type=InteractionType.ACCOUNT_CREATION,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            )
