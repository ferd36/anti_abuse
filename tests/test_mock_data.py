"""
Tests for the mock data generator.

Validates:
  - Correct number of users generated.
  - All domain invariants hold on generated data.
  - Interaction distributions are reasonable.
  - Data can round-trip through the database.
"""

import pytest
from datetime import datetime, timezone

from config import DatasetConfig
from db.repository import Repository
from core.constants import GENERATION_PATTERN_CLEAN, NUM_FAKE_ACCOUNTS
from core.enums import InteractionType, IPType
from data.mock_data import _fishy_counts, generate_all

TEST_NUM_USERS = 100

# Config with higher inactive_pct so test_some_inactive gets >= 2 inactive users deterministically
_TEST_CONFIG = DatasetConfig(users={"inactive_pct": 0.10})

# Generate once for the module (fast with reduced user count)
@pytest.fixture(scope="module")
def dataset():
    users, profiles, interactions = generate_all(
        seed=42, num_users=TEST_NUM_USERS, config=_TEST_CONFIG
    )
    return users, profiles, interactions


_FISHY_COUNTS = _fishy_counts(_TEST_CONFIG.to_dict())
TOTAL_USERS = TEST_NUM_USERS + sum(_FISHY_COUNTS)


class TestGeneratedUsers:
    def test_count(self, dataset) -> None:
        users, _, _ = dataset
        assert len(users) == TOTAL_USERS

    def test_unique_ids(self, dataset) -> None:
        users, _, _ = dataset
        ids = [u.user_id for u in users]
        assert len(set(ids)) == TOTAL_USERS

    def test_unique_emails(self, dataset) -> None:
        users, _, _ = dataset
        emails = [u.email for u in users]
        assert len(set(emails)) == TOTAL_USERS

    def test_some_inactive(self, dataset) -> None:
        users, _, _ = dataset
        fake_ids = {u.user_id for u in users[-NUM_FAKE_ACCOUNTS:]}
        regular = [u for u in users if u.user_id not in fake_ids]
        inactive = [u for u in regular if not u.is_active]
        # ~10% inactive (from _TEST_CONFIG) -> expect 2-25% of regular users (binomial variance)
        assert 0.02 * TEST_NUM_USERS <= len(inactive) <= 0.25 * TEST_NUM_USERS

    def test_some_hosting_ips(self, dataset) -> None:
        users, _, _ = dataset
        hosting = [u for u in users if u.ip_type == IPType.HOSTING]
        # ~10% legit + fishy use hosting -> expect 5-55% of total (more fishy = more hosting)
        assert 0.05 * TOTAL_USERS <= len(hosting) <= 0.55 * TOTAL_USERS

    def test_all_join_dates_in_past(self, dataset) -> None:
        users, _, _ = dataset
        now = datetime.now(timezone.utc)
        for u in users:
            assert u.join_date <= now

    def test_regular_users_have_clean_generation_pattern(self, dataset) -> None:
        users, _, _ = dataset
        fishy_patterns = {
            "fake_account", "pharmacy_phishing", "covert_porn",
            "account_farming", "coordinated_harassment", "coordinated_like_inflation",
            "profile_cloning", "endorsement_inflation", "recommendation_fraud",
            "job_posting_scam", "invitation_spam", "group_spam",
        }
        for u in users:
            if u.generation_pattern in fishy_patterns:
                assert u.generation_pattern in fishy_patterns
            else:
                assert u.generation_pattern == GENERATION_PATTERN_CLEAN


class TestGeneratedProfiles:
    def test_count(self, dataset) -> None:
        _, profiles, _ = dataset
        assert len(profiles) == TOTAL_USERS

    def test_one_per_user(self, dataset) -> None:
        users, profiles, _ = dataset
        user_ids = {u.user_id for u in users}
        profile_ids = {p.user_id for p in profiles}
        assert user_ids == profile_ids


class TestGeneratedInteractions:
    def test_minimum_interactions(self, dataset) -> None:
        _, _, interactions = dataset
        # Regular users: 5+ each; fake accounts: 1 each
        assert len(interactions) >= 5 * TEST_NUM_USERS + NUM_FAKE_ACCOUNTS

    def test_all_interaction_types_present(self, dataset) -> None:
        _, _, interactions = dataset
        types_seen = {i.interaction_type for i in interactions}
        # At minimum, we should see the common types
        assert InteractionType.LOGIN in types_seen
        assert InteractionType.MESSAGE_USER in types_seen
        assert InteractionType.VIEW_USER_PAGE in types_seen
        assert InteractionType.LIKE in types_seen or InteractionType.REACT in types_seen
        assert (
            InteractionType.UPDATE_HEADLINE in types_seen
            or InteractionType.UPDATE_SUMMARY in types_seen
            or InteractionType.CHANGE_LAST_NAME in types_seen
        )
        assert InteractionType.SEARCH_CANDIDATES in types_seen

    def test_target_user_constraints(self, dataset) -> None:
        _, _, interactions = dataset
        for i in interactions:
            if i.interaction_type in {
                InteractionType.MESSAGE_USER,
                InteractionType.VIEW_USER_PAGE,
                InteractionType.CONNECT_WITH_USER,
                InteractionType.LIKE,
                InteractionType.REACT,
            }:
                assert i.target_user_id is not None
                assert i.target_user_id != i.user_id
            elif i.interaction_type in {
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
            }:
                assert i.target_user_id is None

    def test_timestamps_in_order(self, dataset) -> None:
        _, _, interactions = dataset
        for i in range(1, len(interactions)):
            assert interactions[i].timestamp >= interactions[i - 1].timestamp

    def test_all_timestamps_in_past(self, dataset) -> None:
        _, _, interactions = dataset
        now = datetime.now(timezone.utc)
        for i in interactions:
            assert i.timestamp <= now


class TestDatabaseRoundTrip:
    def test_full_round_trip(self, dataset) -> None:
        users, profiles, interactions = dataset
        repo = Repository(":memory:")
        try:
            repo.insert_users_batch(users)
            assert repo.count_users() == TOTAL_USERS

            repo.insert_profiles_batch(profiles)

            repo.insert_interactions_batch(interactions)
            assert repo.count_interactions() == len(interactions)

            # Verify a sample user round-trips correctly
            original = users[0]
            fetched = repo.get_user(original.user_id)
            assert fetched is not None
            assert fetched.email == original.email
            assert fetched.country == original.country
            assert fetched.ip_type == original.ip_type

            # Verify interaction counts by type are consistent
            counts = repo.count_interactions_by_type()
            total = sum(counts.values())
            assert total == len(interactions)
        finally:
            repo.close()
