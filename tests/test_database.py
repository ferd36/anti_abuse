"""
Unit tests for the Repository (SQLite database layer).

Tests cover:
  - Schema creation.
  - CRUD operations for Users, Profiles, Interactions.
  - Query operations (by type, by user, by time range).
  - Pre-condition enforcement.
  - Search, connections, close-account invariant, limit branches.
  - ISO timestamp helpers (_dt_to_iso, _iso_to_dt).
"""

import pytest
from datetime import datetime, timedelta, timezone

from db.repository import Repository, _dt_to_iso, _iso_to_dt
from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile


# ===================================================================
# Fixtures
# ===================================================================
@pytest.fixture
def repo() -> Repository:
    """In-memory repository for testing."""
    r = Repository(":memory:")
    yield r
    r.close()


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.fixture
def sample_user(now: datetime) -> User:
    return User(
        user_id="u-0001",
        email="alice@example.com",
        join_date=now - timedelta(days=30),
        country="US",
        ip_address="203.0.113.1",
        registration_ip="203.0.113.1",
        registration_country="US",
        address="123 Main St",
        ip_type=IPType.RESIDENTIAL,
        language="en",
        is_active=True,
    )


@pytest.fixture
def sample_user_2(now: datetime) -> User:
    return User(
        user_id="u-0002",
        email="bob@example.com",
        join_date=now - timedelta(days=20),
        country="GB",
        ip_address="198.51.100.1",
        registration_ip="198.51.100.1",
        registration_country="GB",
        address="1 High St, London",
        ip_type=IPType.RESIDENTIAL,
        language="en",
        is_active=True,
    )


@pytest.fixture
def sample_profile(now: datetime) -> UserProfile:
    return UserProfile(
        user_id="u-0001",
        display_name="Alice Smith",
        headline="Engineer",
        summary="Loves code.",
        connections_count=10,
        profile_created_at=now - timedelta(days=29),
    )


# ===================================================================
# User CRUD
# ===================================================================
class TestUserCRUD:
    def test_insert_and_get_user(self, repo: Repository, sample_user: User) -> None:
        repo.insert_user(sample_user)
        fetched = repo.get_user("u-0001")
        assert fetched is not None
        assert fetched.user_id == sample_user.user_id
        assert fetched.email == sample_user.email
        assert fetched.country == sample_user.country
        assert fetched.ip_type == sample_user.ip_type

    def test_get_nonexistent_user(self, repo: Repository) -> None:
        assert repo.get_user("u-9999") is None

    def test_insert_batch(self, repo: Repository, sample_user: User, sample_user_2: User) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        assert repo.count_users() == 2

    def test_get_all_users(self, repo: Repository, sample_user: User, sample_user_2: User) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        all_users = repo.get_all_users()
        assert len(all_users) == 2

    def test_update_user_generation_pattern(
        self, repo: Repository, sample_user: User
    ) -> None:
        repo.insert_user(sample_user)
        repo.update_user_generation_pattern("u-0001", "smash_grab")
        fetched = repo.get_user("u-0001")
        assert fetched is not None
        assert fetched.generation_pattern == "smash_grab"

    def test_get_active_user_ids(self, repo: Repository, now: datetime) -> None:
        active = User(
            user_id="u-active",
            email="active@x.com",
            join_date=now - timedelta(days=5),
            country="US",
            ip_address="1.2.3.4",
            registration_ip="1.2.3.4",
            registration_country="US",
            address="",
            ip_type=IPType.RESIDENTIAL,
            language="en",
            is_active=True,
        )
        inactive = User(
            user_id="u-inactive",
            email="inactive@x.com",
            join_date=now - timedelta(days=5),
            country="US",
            ip_address="1.2.3.5",
            registration_ip="1.2.3.5",
            registration_country="US",
            address="",
            ip_type=IPType.RESIDENTIAL,
            language="en",
            is_active=False,
        )
        repo.insert_users_batch([active, inactive])
        active_ids = repo.get_active_user_ids()
        assert "u-active" in active_ids
        assert "u-inactive" not in active_ids


# ===================================================================
# Profile CRUD
# ===================================================================
class TestProfileCRUD:
    def test_insert_and_get_profile(
        self, repo: Repository, sample_user: User, sample_profile: UserProfile
    ) -> None:
        repo.insert_user(sample_user)
        repo.insert_profile(sample_profile)
        fetched = repo.get_profile("u-0001")
        assert fetched is not None
        assert fetched.display_name == "Alice Smith"
        assert fetched.connections_count == 10

    def test_get_nonexistent_profile(self, repo: Repository) -> None:
        assert repo.get_profile("u-9999") is None

    def test_insert_profiles_batch(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        profiles = [
            UserProfile(
                user_id="u-0001",
                display_name="Alice",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now - timedelta(days=29),
            ),
            UserProfile(
                user_id="u-0002",
                display_name="Bob",
                headline="",
                summary="",
                connections_count=0,
                profile_created_at=now - timedelta(days=19),
            ),
        ]
        repo.insert_profiles_batch(profiles)
        assert repo.get_profile("u-0001") is not None
        assert repo.get_profile("u-0002") is not None


# ===================================================================
# Interaction CRUD
# ===================================================================
class TestInteractionCRUD:
    def test_insert_and_get_interactions(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interaction = UserInteraction(
            interaction_id="evt-0001",
            user_id="u-0001",
            interaction_type=InteractionType.LOGIN,
            timestamp=now,
            ip_address="203.0.113.1",
            ip_type=IPType.RESIDENTIAL,
        )
        repo.insert_interaction(interaction)
        results = repo.get_interactions_by_user("u-0001")
        assert len(results) == 1
        assert results[0].interaction_type == InteractionType.LOGIN

    def test_insert_batch_and_count(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        interactions = [
            UserInteraction(
                interaction_id=f"evt-{i:04d}",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=i),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )
            for i in range(5)
        ]
        repo.insert_interactions_batch(interactions)
        assert repo.count_interactions() == 5

    def test_get_by_type(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        interactions = [
            UserInteraction(
                interaction_id="evt-login",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-msg",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        repo.insert_interactions_batch(interactions)
        logins = repo.get_interactions_by_type(InteractionType.LOGIN)
        assert len(logins) == 1
        assert logins[0].interaction_id == "evt-login"

    def test_get_in_time_range(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id=f"evt-{i}",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(days=i),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )
            for i in range(10)
        ]
        repo.insert_interactions_batch(interactions)
        # Get last 3 days
        results = repo.get_interactions_in_range(
            now - timedelta(days=3), now
        )
        assert len(results) == 4  # days 0, 1, 2, 3

    def test_count_by_type(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
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
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-3",
                user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER,
                timestamp=now,
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
        ]
        repo.insert_interactions_batch(interactions)
        counts = repo.count_interactions_by_type()
        assert counts["login"] == 2
        assert counts["message_user"] == 1

    def test_interactions_with_metadata(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interaction = UserInteraction(
            interaction_id="evt-meta",
            user_id="u-0001",
            interaction_type=InteractionType.LOGIN,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            metadata={"user_agent": "Chrome/120", "session_id": "abc123"},
        )
        repo.insert_interaction(interaction)
        results = repo.get_interactions_by_user("u-0001")
        assert results[0].metadata["user_agent"] == "Chrome/120"
        assert results[0].metadata["session_id"] == "abc123"


# ===================================================================
# ISO timestamp helpers
# ===================================================================
class TestIsoHelpers:
    def test_dt_to_iso_utc(self) -> None:
        dt = datetime(2024, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        iso = _dt_to_iso(dt)
        assert "+00:00" in iso
        assert "2024-06-15" in iso

    def test_dt_to_iso_non_utc_normalizes(self) -> None:
        # EST is UTC-5
        est = timezone(timedelta(hours=-5))
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=est)
        iso = _dt_to_iso(dt)
        # Should be normalized to UTC (17:00 UTC)
        assert "+00:00" in iso
        parsed = datetime.fromisoformat(iso)
        assert parsed.hour == 17

    def test_iso_to_dt_with_timezone(self) -> None:
        iso = "2024-06-15T12:30:00+00:00"
        dt = _iso_to_dt(iso)
        assert dt.tzinfo is not None
        assert dt.year == 2024
        assert dt.hour == 12

    def test_iso_to_dt_naive_assumes_utc(self) -> None:
        iso = "2024-06-15T12:30:00"
        dt = _iso_to_dt(iso)
        assert dt.tzinfo == timezone.utc

    def test_iso_to_dt_non_utc_normalizes(self) -> None:
        # Parse a non-UTC timestamp; should be converted to UTC
        iso = "2024-06-15T12:00:00+05:00"
        dt = _iso_to_dt(iso)
        assert dt.hour == 7  # 12:00 +05:00 = 07:00 UTC

    def test_round_trip(self) -> None:
        original = datetime(2024, 1, 15, 8, 45, 30, tzinfo=timezone.utc)
        iso = _dt_to_iso(original)
        restored = _iso_to_dt(iso)
        assert restored == original


# ===================================================================
# Interaction queries with limit
# ===================================================================
class TestInteractionLimits:
    def test_get_by_user_with_limit(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id=f"evt-{i:04d}",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=i),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )
            for i in range(5)
        ]
        repo.insert_interactions_batch(interactions)
        results = repo.get_interactions_by_user("u-0001", limit=2)
        assert len(results) == 2

    def test_get_by_type_with_limit(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id=f"evt-{i:04d}",
                user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=i),
                ip_address="1.2.3.4",
                ip_type=IPType.RESIDENTIAL,
            )
            for i in range(5)
        ]
        repo.insert_interactions_batch(interactions)
        results = repo.get_interactions_by_type(InteractionType.LOGIN, limit=3)
        assert len(results) == 3


# ===================================================================
# Connections
# ===================================================================
class TestConnections:
    def test_get_connections_bidirectional(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        # u-0001 sent connection request to u-0002
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-conn",
            user_id="u-0001",
            interaction_type=InteractionType.CONNECT_WITH_USER,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        ))
        # u-0002 accepted
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-accept",
            user_id="u-0002",
            interaction_type=InteractionType.ACCEPT_CONNECTION_REQUEST,
            timestamp=now + timedelta(seconds=60),
            ip_address="1.2.3.5",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0001",
        ))
        # From u-0001's perspective
        conns_1 = repo.get_connections("u-0001")
        assert len(conns_1) == 1
        assert conns_1[0]["user_id"] == "u-0002"

        # From u-0002's perspective (reverse direction)
        conns_2 = repo.get_connections("u-0002")
        assert len(conns_2) == 1
        assert conns_2[0]["user_id"] == "u-0001"

    def test_get_connections_empty(
        self, repo: Repository, sample_user: User
    ) -> None:
        repo.insert_user(sample_user)
        conns = repo.get_connections("u-0001")
        assert conns == []

    def test_get_connections_with_profile(
        self, repo: Repository, sample_user: User, sample_user_2: User,
        sample_profile: UserProfile, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        repo.insert_profile(sample_profile)  # profile for u-0001
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-conn",
            user_id="u-0002",
            interaction_type=InteractionType.CONNECT_WITH_USER,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0001",
        ))
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-accept",
            user_id="u-0001",
            interaction_type=InteractionType.ACCEPT_CONNECTION_REQUEST,
            timestamp=now + timedelta(seconds=60),
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        ))
        conns = repo.get_connections("u-0002")
        assert len(conns) == 1
        assert conns[0]["display_name"] == "Alice Smith"
        assert conns[0]["headline"] == "Engineer"
        assert conns[0]["country"] == "US"
        assert conns[0]["is_active"] is True

    def test_get_connections_without_profile_falls_back_to_user_id(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        # No profile for u-0002; u-0001 sent, u-0002 accepted
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-conn",
            user_id="u-0001",
            interaction_type=InteractionType.CONNECT_WITH_USER,
            timestamp=now,
            ip_address="1.2.3.4",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        ))
        repo.insert_interaction(UserInteraction(
            interaction_id="evt-accept",
            user_id="u-0002",
            interaction_type=InteractionType.ACCEPT_CONNECTION_REQUEST,
            timestamp=now + timedelta(seconds=60),
            ip_address="1.2.3.5",
            ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0001",
        ))
        conns = repo.get_connections("u-0001")
        assert len(conns) == 1
        # display_name falls back to user_id when profile is missing
        assert conns[0]["display_name"] == "u-0002"
        assert conns[0]["headline"] == ""


# ===================================================================
# Search users
# ===================================================================
class TestSearchUsers:
    def _setup_users(self, repo: Repository, now: datetime) -> None:
        users = [
            User(
                user_id="u-0001", email="alice@example.com",
                join_date=now - timedelta(days=30), country="US",
                ip_address="1.2.3.4", registration_ip="1.2.3.4",
                registration_country="US", address="",
                ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
            ),
            User(
                user_id="u-0002", email="bob@example.com",
                join_date=now - timedelta(days=20), country="GB",
                ip_address="1.2.3.5", registration_ip="1.2.3.5",
                registration_country="GB", address="",
                ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
            ),
            User(
                user_id="u-0003", email="charlie@example.com",
                join_date=now - timedelta(days=10), country="DE",
                ip_address="1.2.3.6", registration_ip="1.2.3.6",
                registration_country="DE", address="",
                ip_type=IPType.HOSTING, language="de", is_active=False,
            ),
        ]
        repo.insert_users_batch(users)
        profiles = [
            UserProfile(
                user_id="u-0001", display_name="Alice Smith",
                headline="Engineer", summary="",
                connections_count=10,
                profile_created_at=now - timedelta(days=29),
            ),
            UserProfile(
                user_id="u-0002", display_name="Bob Jones",
                headline="Manager", summary="",
                connections_count=5,
                profile_created_at=now - timedelta(days=19),
            ),
        ]
        repo.insert_profiles_batch(profiles)

    def test_search_no_query(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users()
        assert result["total"] == 3
        assert len(result["users"]) == 3
        assert result["page"] == 1

    def test_search_with_query_by_email(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="alice")
        assert result["total"] >= 1
        user_ids = [u["user_id"] for u in result["users"]]
        assert "u-0001" in user_ids

    def test_search_with_query_by_country(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="DE")
        assert result["total"] >= 1
        user_ids = [u["user_id"] for u in result["users"]]
        assert "u-0003" in user_ids

    def test_search_with_query_by_display_name(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="Alice")
        assert result["total"] >= 1

    def test_search_pagination(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(page=1, per_page=2)
        assert len(result["users"]) == 2
        assert result["total"] == 3

        result_p2 = repo.search_users(page=2, per_page=2)
        assert len(result_p2["users"]) == 1

    def test_search_no_results(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="zzzznotfound")
        assert result["total"] == 0
        assert len(result["users"]) == 0

    def test_search_user_without_profile_uses_fallbacks(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="u-0003")
        assert result["total"] >= 1
        u3 = [u for u in result["users"] if u["user_id"] == "u-0003"][0]
        # u-0003 has no profile -> display_name falls back to user_id
        assert u3["display_name"] == "u-0003"
        assert u3["headline"] == ""
        assert u3["connections_count"] == 0

    def test_search_pagination_with_query(self, repo: Repository, now: datetime) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(query="example", page=1, per_page=1)
        assert len(result["users"]) == 1
        assert result["total"] == 3  # all match example.com

    def test_search_with_empty_user_ids_filter_returns_empty(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(user_ids_filter=[])
        assert result["total"] == 0
        assert result["users"] == []

    def test_search_with_user_ids_filter(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.search_users(user_ids_filter=["u-0001", "u-0003"])
        assert result["total"] == 2
        user_ids = [u["user_id"] for u in result["users"]]
        assert "u-0001" in user_ids
        assert "u-0003" in user_ids


# ===================================================================
# get_user_ids_matching, get_users_by_ids_ordered
# ===================================================================
class TestUserIdsMatchingAndOrdered:
    def _setup_users(self, repo: Repository, now: datetime) -> None:
        users = [
            User(
                user_id="u-0001", email="alice@example.com",
                join_date=now - timedelta(days=30), country="US",
                ip_address="1.2.3.4", registration_ip="1.2.3.4",
                registration_country="US", address="",
                ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
            ),
            User(
                user_id="u-0002", email="bob@example.com",
                join_date=now - timedelta(days=20), country="GB",
                ip_address="1.2.3.5", registration_ip="1.2.3.5",
                registration_country="GB", address="",
                ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
            ),
            UserProfile(
                user_id="u-0001", display_name="Alice Smith",
                headline="Engineer", summary="",
                connections_count=10,
                profile_created_at=now - timedelta(days=29),
            ),
            UserProfile(
                user_id="u-0002", display_name="Bob Jones",
                headline="Manager", summary="",
                connections_count=5,
                profile_created_at=now - timedelta(days=19),
            ),
        ]
        repo.insert_users_batch([u for u in users if isinstance(u, User)])
        repo.insert_profiles_batch([p for p in users if isinstance(p, UserProfile)])

    def test_get_user_ids_matching_empty_filter(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.get_user_ids_matching(user_ids_filter=[])
        assert result == []

    def test_get_user_ids_matching_with_query(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.get_user_ids_matching(query="alice")
        assert "u-0001" in result

    def test_get_user_ids_matching_with_filter(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.get_user_ids_matching(
            query="example", user_ids_filter=["u-0001", "u-0002"]
        )
        assert "u-0001" in result
        assert "u-0002" in result

    def test_get_users_by_ids_ordered_empty(self, repo: Repository) -> None:
        assert repo.get_users_by_ids_ordered([]) == []

    def test_get_users_by_ids_ordered(
        self, repo: Repository, now: datetime
    ) -> None:
        self._setup_users(repo, now)
        result = repo.get_users_by_ids_ordered(["u-0002", "u-0001"])
        assert len(result) == 2
        assert result[0]["user_id"] == "u-0002"
        assert result[1]["user_id"] == "u-0001"


# ===================================================================
# deactivate_users_with_close_account
# ===================================================================
class TestDeactivateUsersWithCloseAccount:
    def test_deactivates_users_with_close_account(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        interactions = [
            UserInteraction(
                interaction_id="evt-1", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-close", user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        updated = repo.deactivate_users_with_close_account()
        assert updated == 1
        user = repo.get_user("u-0001")
        assert user is not None and user.is_active is False
        user2 = repo.get_user("u-0002")
        assert user2 is not None and user2.is_active is True

    def test_deactivate_none_when_no_close(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id="evt-1", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now, ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        updated = repo.deactivate_users_with_close_account()
        assert updated == 0


# ===================================================================
# Count interactions by type for user
# ===================================================================
class TestCountByTypeForUser:
    def test_count_interactions_by_type_for_user(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        interactions = [
            UserInteraction(
                interaction_id="evt-1", user_id="u-0001",
                interaction_type=InteractionType.LOGIN, timestamp=now,
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-2", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-3", user_id="u-0001",
                interaction_type=InteractionType.MESSAGE_USER, timestamp=now,
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
                target_user_id="u-0002",
            ),
            UserInteraction(
                interaction_id="evt-4", user_id="u-0002",
                interaction_type=InteractionType.LOGIN, timestamp=now,
                ip_address="1.2.3.5", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        counts = repo.count_interactions_by_type_for_user("u-0001")
        assert counts["login"] == 2
        assert counts["message_user"] == 1
        # u-0002's login should not be counted
        assert sum(counts.values()) == 3

    def test_count_empty(self, repo: Repository, sample_user: User) -> None:
        repo.insert_user(sample_user)
        counts = repo.count_interactions_by_type_for_user("u-0001")
        assert counts == {}


# ===================================================================
# Enforce close-account invariant
# ===================================================================
class TestEnforceCloseAccountInvariant:
    def test_deletes_events_after_close(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id="evt-1", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=3),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-close", user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-after", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        assert repo.count_interactions() == 3

        deleted = repo.enforce_close_account_invariant()
        assert deleted == 1
        assert repo.count_interactions() == 2

        # The event after close should be gone
        remaining_ids = [
            i.interaction_id for i in repo.get_interactions_by_user("u-0001")
        ]
        assert "evt-after" not in remaining_ids
        assert "evt-1" in remaining_ids
        assert "evt-close" in remaining_ids

    def test_no_close_events_deletes_nothing(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id=f"evt-{i}", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=i),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            )
            for i in range(3)
        ]
        repo.insert_interactions_batch(interactions)
        deleted = repo.enforce_close_account_invariant()
        assert deleted == 0
        assert repo.count_interactions() == 3

    def test_close_is_last_event_deletes_nothing(
        self, repo: Repository, sample_user: User, now: datetime
    ) -> None:
        repo.insert_user(sample_user)
        interactions = [
            UserInteraction(
                interaction_id="evt-1", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-close", user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        deleted = repo.enforce_close_account_invariant()
        assert deleted == 0

    def test_multiple_users_independent(
        self, repo: Repository, sample_user: User, sample_user_2: User, now: datetime
    ) -> None:
        repo.insert_users_batch([sample_user, sample_user_2])
        interactions = [
            # u-0001: close then event after
            UserInteraction(
                interaction_id="evt-u1-close", user_id="u-0001",
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=now - timedelta(hours=3),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            UserInteraction(
                interaction_id="evt-u1-after", user_id="u-0001",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=1),
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            ),
            # u-0002: normal events (no close)
            UserInteraction(
                interaction_id="evt-u2-login", user_id="u-0002",
                interaction_type=InteractionType.LOGIN,
                timestamp=now - timedelta(hours=2),
                ip_address="1.2.3.5", ip_type=IPType.RESIDENTIAL,
            ),
        ]
        repo.insert_interactions_batch(interactions)
        deleted = repo.enforce_close_account_invariant()
        assert deleted == 1
        # u-0002's event should still be there
        u2_events = repo.get_interactions_by_user("u-0002")
        assert len(u2_events) == 1
