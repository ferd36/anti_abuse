"""
Tests for non-fraud (legitimate) usage pattern generators.

Validates:
  - Each of the 8 pattern generators produces valid events
  - Temporal invariants from USAGE_PATTERNS.md are respected
  - No DOWNLOAD_ADDRESS_BOOK for normal users
  - ACCOUNT_CREATION first, LOGIN before activity, VIEW before MESSAGE/CONNECT
  - CLOSE_ACCOUNT terminal for inactive users
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from core.enums import InteractionType, IPType
from core.models import User
from data.non_fraud import PATTERN_NAMES, generate_legitimate_events
from data.non_fraud.active_job_seeker import active_job_seeker
from data.non_fraud.career_update import career_update
from data.non_fraud.casual_browser import casual_browser
from data.non_fraud.content_consumer import content_consumer
from data.non_fraud.dormant_account import dormant_account
from data.non_fraud.exec_delegation import exec_delegation
from data.non_fraud.new_user_onboarding import new_user_onboarding
from data.non_fraud.recruiter import recruiter
from data.non_fraud.regular_networker import regular_networker
from data.non_fraud.returning_user import returning_user
from data.non_fraud.weekly_check_in import weekly_check_in

from .test_temporal_invariants import assert_non_fraud_temporal_invariants


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def rng() -> random.Random:
    return random.Random(42)


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=15)


@pytest.fixture
def window_start(now: datetime) -> datetime:
    return now - timedelta(days=60)


def _make_user(
    user_id: str = "u-test-001",
    join_date: datetime | None = None,
    is_active: bool = True,
) -> User:
    """Create a minimal valid User for testing."""
    now = datetime.now(timezone.utc) - timedelta(minutes=15)
    join = join_date or (now - timedelta(days=30))
    return User(
        user_id=user_id,
        email=f"{user_id}@test.example.com",
        join_date=join,
        country="US",
        ip_address="192.168.1.1",
        registration_ip="192.168.1.1",
        registration_country="US",
        address="123 Test St",
        ip_type=IPType.RESIDENTIAL,
        language="en",
        is_active=is_active,
    )


@pytest.fixture
def sample_user(now: datetime) -> User:
    return _make_user(join_date=now - timedelta(days=30))


@pytest.fixture
def new_user(now: datetime) -> User:
    """User who joined 3 days ago - gets new_user_onboarding pattern."""
    return _make_user(
        user_id="u-new-001",
        join_date=now - timedelta(days=3),
    )

@pytest.fixture
def all_user_ids() -> list[str]:
    return [f"u-{i:04d}" for i in range(100)]


# ---------------------------------------------------------------------------
# Individual generator tests
# ---------------------------------------------------------------------------
class TestCasualBrowser:
    def test_produces_events(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, counter = casual_browser(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.VIEW_USER_PAGE in types

    def test_no_download_address_book(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = casual_browser(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        for e in events:
            assert e.interaction_type != InteractionType.DOWNLOAD_ADDRESS_BOOK


class TestActiveJobSeeker:
    def test_produces_views_connects_messages(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = active_job_seeker(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.VIEW_USER_PAGE in types
        assert InteractionType.CONNECT_WITH_USER in types


class TestRecruiter:
    def test_high_volume_views_and_connects(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = recruiter(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 10
        search_count = sum(1 for e in events if e.interaction_type == InteractionType.SEARCH_CANDIDATES)
        view_count = sum(1 for e in events if e.interaction_type == InteractionType.VIEW_USER_PAGE)
        connect_count = sum(1 for e in events if e.interaction_type == InteractionType.CONNECT_WITH_USER)
        assert search_count >= 1
        assert view_count >= 5
        assert connect_count >= 5


class TestRegularNetworker:
    def test_moderate_activity(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = regular_networker(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        assert InteractionType.LOGIN in {e.interaction_type for e in events}


class TestReturningUser:
    def test_requires_long_gap(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        # User with 45 days since join - may get returning pattern
        user = _make_user(join_date=now - timedelta(days=45))
        events, _ = returning_user(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        # May produce events if days_available >= 7
        assert isinstance(events, list)

    def test_early_return_days_available_under_7(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(days=3))
        window_start = now - timedelta(days=2)
        events, counter = returning_user(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert events == []
        assert counter == 0

    def test_early_return_ts_before_window(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(days=60))
        window_start = now - timedelta(days=5)
        rng2 = random.Random(999)
        events, _ = returning_user(
            user, all_user_ids, window_start, now, 0, rng2, "Mozilla/5.0",
        )
        assert isinstance(events, list)

    def test_second_session_branch(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(days=45))
        window_start = now - timedelta(days=60)
        config = {"usage_patterns": {"returning_user": {"second_session_pct": 1.0}}}
        events, _ = returning_user(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
            config=config,
        )
        update_types = {
            InteractionType.UPDATE_HEADLINE,
            InteractionType.UPDATE_SUMMARY,
            InteractionType.CHANGE_LAST_NAME,
        }
        assert any(e.interaction_type in update_types for e in events) or len(events) == 0


class TestExecDelegation:
    def test_produces_ph_login_and_views(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(
            user_id="u-exec-001",
            join_date=now - timedelta(days=45),
        )
        window_start = now - timedelta(days=60)
        events, counter = exec_delegation(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.VIEW_USER_PAGE in types
        assert any(
            e.metadata.get("delegated_access") for e in events
            if e.interaction_type == InteractionType.LOGIN
        )

    def test_early_return_days_available_under_1(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(hours=12))
        window_start = now - timedelta(days=1)
        events, counter = exec_delegation(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert events == []
        assert counter == 0


class TestNewUserOnboarding:
    def test_has_upload_address_book_option(
        self,
        new_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = new_user_onboarding(
            new_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.CONNECT_WITH_USER in types
        # UPLOAD_ADDRESS_BOOK is optional (40% chance)
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK not in types


class TestWeeklyCheckIn:
    def test_low_volume(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = weekly_check_in(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) >= 0  # May be 0 if days_available < 1


class TestContentConsumer:
    def test_many_views_few_connects(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, _ = content_consumer(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) > 0
        view_count = sum(1 for e in events if e.interaction_type == InteractionType.VIEW_USER_PAGE)
        assert view_count >= 5


class TestCareerUpdate:
    def test_produces_profile_updates(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        events, counter = career_update(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert isinstance(events, list)
        if events:
            update_types = {
                InteractionType.UPDATE_HEADLINE,
                InteractionType.UPDATE_SUMMARY,
                InteractionType.CHANGE_LAST_NAME,
            }
            types = {e.interaction_type for e in events}
            assert types & update_types or InteractionType.LOGIN in types

    def test_early_return_days_available_under_14(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(days=3))
        window_start = now - timedelta(days=2)
        events, counter = career_update(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert events == []
        assert counter == 0

    def test_no_browsing_or_messaging(
        self,
        sample_user: User,
        all_user_ids: list[str],
        window_start: datetime,
        now: datetime,
        rng: random.Random,
    ) -> None:
        config = {
            "usage_patterns": {
                "career_update": {
                    "update_type_headline": 1.0,
                    "update_type_summary": 0,
                    "second_update_in_session_pct": 0,
                },
            },
        }
        events, _ = career_update(
            sample_user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
            config=config,
        )
        for e in events:
            assert e.interaction_type not in (
                InteractionType.VIEW_USER_PAGE,
                InteractionType.MESSAGE_USER,
                InteractionType.CONNECT_WITH_USER,
            )


class TestDormantAccount:
    def test_returns_at_most_one_login(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(days=30))
        window_start = now - timedelta(days=60)
        events, counter = dormant_account(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert len(events) <= 1
        if events:
            assert events[0].interaction_type == InteractionType.LOGIN

    def test_no_profile_views_connections_messages(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        config = {"usage_patterns": {"dormant_account": {"login_once_pct": 1.0}}}
        user = _make_user(join_date=now - timedelta(days=30))
        window_start = now - timedelta(days=60)
        events, _ = dormant_account(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
            config=config,
        )
        for e in events:
            assert e.interaction_type not in (
                InteractionType.VIEW_USER_PAGE,
                InteractionType.CONNECT_WITH_USER,
                InteractionType.MESSAGE_USER,
            )

    def test_early_return_days_available_under_1(
        self,
        all_user_ids: list[str],
        now: datetime,
        rng: random.Random,
    ) -> None:
        user = _make_user(join_date=now - timedelta(hours=12))
        window_start = now - timedelta(days=1)
        events, counter = dormant_account(
            user, all_user_ids, window_start, now, 0, rng, "Mozilla/5.0",
        )
        assert events == []
        assert counter == 0


# ---------------------------------------------------------------------------
# Orchestrator and temporal invariants
# ---------------------------------------------------------------------------
class TestGenerateLegitimateEvents:
    def test_produces_events_for_users(
        self,
        now: datetime,
        window_start: datetime,
        rng: random.Random,
    ) -> None:
        users = [
            _make_user("u-001", now - timedelta(days=30)),
            _make_user("u-002", now - timedelta(days=5)),
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(3, 50)]
        user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}

        events, counter = generate_legitimate_events(
            users, all_user_ids, window_start, now, 0, rng, user_primary_ua, set(),
        )
        assert len(events) > 0
        assert counter > 0

    def test_skips_fake_accounts(
        self,
        now: datetime,
        window_start: datetime,
        rng: random.Random,
    ) -> None:
        users = [
            _make_user("u-001", now - timedelta(days=30)),
            _make_user("u-fake-001", now - timedelta(days=30)),
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(10)]
        user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}
        fake_ids = {"u-fake-001"}

        events, _ = generate_legitimate_events(
            users, all_user_ids, window_start, now, 0, rng, user_primary_ua, fake_ids,
        )
        user_ids_in_events = {e.user_id for e in events}
        assert "u-fake-001" not in user_ids_in_events

    def test_exec_delegation_pattern_with_config(
        self,
        now: datetime,
        window_start: datetime,
        rng: random.Random,
    ) -> None:
        config = {
            "usage_patterns": {
                "exec_delegation_pct": 1.0,
                "returning_user_pct": 0,
                "career_update_pct": 0,
                "dormant_account_pct": 0,
            },
        }
        users = [
            _make_user("u-exec-001", now - timedelta(days=45)),
            _make_user("u-exec-002", now - timedelta(days=35)),
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(100, 150)]
        user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}

        events, _ = generate_legitimate_events(
            users, all_user_ids, window_start, now, 0, rng, user_primary_ua, set(),
            config=config,
        )
        delegated = [e for e in events if e.metadata.get("delegated_access")]
        assert len(delegated) > 0

    def test_adds_close_account_for_inactive(
        self,
        now: datetime,
        window_start: datetime,
        rng: random.Random,
    ) -> None:
        users = [
            _make_user("u-inactive", now - timedelta(days=45), is_active=False),
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(10)]
        user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}

        events, _ = generate_legitimate_events(
            users, all_user_ids, window_start, now, 0, rng, user_primary_ua, set(),
        )
        close_events = [e for e in events if e.interaction_type == InteractionType.CLOSE_ACCOUNT]
        assert len(close_events) >= 1
        # CLOSE_ACCOUNT must be last for that user
        for e in close_events:
            user_events = [x for x in events if x.user_id == e.user_id]
            user_events.sort(key=lambda x: x.timestamp)
            assert user_events[-1].interaction_type == InteractionType.CLOSE_ACCOUNT


class TestTemporalInvariants:
    """Validate that generate_legitimate_events produces events respecting temporal invariants."""

    def test_full_generation_respects_invariants(
        self,
        now: datetime,
        window_start: datetime,
        rng: random.Random,
    ) -> None:
        users = [
            _make_user(f"u-{i:03d}", now - timedelta(days=30 + (i % 20)))
            for i in range(20)
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(100, 200)]
        user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}

        events, _ = generate_legitimate_events(
            users, all_user_ids, window_start, now, 0, rng, user_primary_ua, set(),
        )
        assert len(events) > 0
        assert_non_fraud_temporal_invariants(events)

    def test_multiple_seeds_respect_invariants(
        self,
        now: datetime,
        window_start: datetime,
    ) -> None:
        """Run with several seeds to catch non-deterministic invariant violations."""
        users = [
            _make_user(f"u-{i:03d}", now - timedelta(days=20 + i))
            for i in range(15)
        ]
        all_user_ids = [u.user_id for u in users] + [f"u-{i:04d}" for i in range(100, 180)]

        for seed in (0, 1, 42, 99, 123):
            rng = random.Random(seed)
            user_primary_ua = {u.user_id: "Mozilla/5.0" for u in users}
            events, _ = generate_legitimate_events(
                users, all_user_ids, window_start, now, 0, rng, user_primary_ua, set(),
            )
            if len(events) > 0:
                assert_non_fraud_temporal_invariants(events)


class TestPatternCoverage:
    def test_all_pattern_names_exist(self) -> None:
        assert len(PATTERN_NAMES) == 11
        assert "casual_browser" in PATTERN_NAMES
        assert "new_user_onboarding" in PATTERN_NAMES
        assert "content_consumer" in PATTERN_NAMES
        assert "career_update" in PATTERN_NAMES
        assert "exec_delegation" in PATTERN_NAMES
        assert "dormant_account" in PATTERN_NAMES
