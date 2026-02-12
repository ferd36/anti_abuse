"""
Tests for the malicious ATO data generator.

Covers:
  - Helper functions (_pick_attacker_country, _pick_hosting_ip, _make_event,
    _make_login_with_failures).
  - All 5 attack patterns (smash_and_grab, low_and_slow, country_hopper,
    data_thief, credential_stuffer).
  - Public API (generate_malicious_events).
"""

import random
from datetime import datetime, timedelta, timezone

import pytest

from core.enums import InteractionType, IPType
from data.mock_data import FAKE_ACCOUNT_USER_IDS
from data.fraud import generate_malicious_events
from data.fraud._common import (
    enforce_login_first_invariant as _enforce_login_first_invariant,
    enforce_spam_after_login_invariant as _enforce_spam_after_login_invariant,
    make_event as _make_event,
    make_login_with_failures as _make_login_with_failures,
    pick_attacker_country as _pick_attacker_country,
    pick_hosting_ip as _pick_hosting_ip,
)
from data.fraud.account_farming import account_farming as _account_farming
from data.fraud.connection_harvester import connection_harvester as _connection_harvester
from data.fraud.coordinated_harassment import coordinated_harassment as _coordinated_harassment
from data.fraud.coordinated_like_inflation import coordinated_like_inflation as _coordinated_like_inflation
from data.fraud.credential_stuffer import credential_stuffer as _credential_stuffer
from data.fraud.credential_tester import credential_tester as _credential_tester
from data.fraud.country_hopper import country_hopper as _country_hopper
from data.fraud.data_thief import data_thief as _data_thief
from data.fraud.low_slow import low_and_slow as _low_and_slow
from data.fraud.scraper_cluster import scraper_cluster as _scraper_cluster
from data.fraud.sleeper_agent import sleeper_agent as _sleeper_agent
from data.fraud.smash_grab import smash_and_grab as _smash_and_grab
from data.fraud.spear_phisher import spear_phisher as _spear_phisher

from .test_temporal_invariants import assert_fraud_temporal_invariants


# ===================================================================
# Fixtures
# ===================================================================
@pytest.fixture
def rng() -> random.Random:
    return random.Random(42)


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=10)


@pytest.fixture
def base_time(now: datetime) -> datetime:
    return now - timedelta(days=10)


@pytest.fixture
def all_user_ids() -> list[str]:
    return [f"u-{i:04d}" for i in range(50)] + list(FAKE_ACCOUNT_USER_IDS)


@pytest.fixture
def user_countries(all_user_ids: list[str]) -> dict[str, str]:
    countries = ["US", "GB", "DE", "FR", "IN", "BR", "JP", "KR", "CA", "AU"]
    result = {uid: countries[i % len(countries)] for i, uid in enumerate(all_user_ids)}
    for uid in FAKE_ACCOUNT_USER_IDS:
        result[uid] = "RU"
    return result


# ===================================================================
# Helper tests
# ===================================================================
class TestHelpers:
    def test_pick_attacker_country_known(self, rng: random.Random) -> None:
        # US is in the lookup table
        country = _pick_attacker_country("US", rng)
        assert country in ["RU", "CN", "NG", "UA", "RO"]

    def test_pick_attacker_country_fallback(self, rng: random.Random) -> None:
        # Unknown country uses default pool
        country = _pick_attacker_country("ZZ", rng)
        assert country in ["RU", "CN", "NG", "UA", "RO"]

    def test_pick_hosting_ip(self, rng: random.Random) -> None:
        ip = _pick_hosting_ip(rng)
        # Must be a valid IPv4 address from the pool
        parts = ip.split(".")
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)

    def test_make_event_no_target(self, now: datetime) -> None:
        evt = _make_event(1, "u-0001", InteractionType.LOGIN, now, "1.2.3.4")
        assert evt.interaction_id == "ato-000001"
        assert evt.user_id == "u-0001"
        assert evt.interaction_type == InteractionType.LOGIN
        assert evt.ip_type == IPType.HOSTING
        assert evt.target_user_id is None
        # Default user_agent is injected
        assert "user_agent" in evt.metadata

    def test_make_event_with_target_and_metadata(self, now: datetime) -> None:
        meta = {"key": "value"}
        evt = _make_event(
            99, "u-0001", InteractionType.MESSAGE_USER, now, "1.2.3.4",
            target_user_id="u-0002", metadata=meta,
        )
        assert evt.interaction_id == "ato-000099"
        assert evt.target_user_id == "u-0002"
        assert evt.metadata["key"] == "value"
        assert "user_agent" in evt.metadata

    def test_make_event_metadata_none_gets_user_agent(self, now: datetime) -> None:
        evt = _make_event(1, "u-0001", InteractionType.LOGIN, now, "1.2.3.4", metadata=None)
        assert "user_agent" in evt.metadata


class TestMakeLoginWithFailures:
    def test_returns_at_least_one_event(self, rng: random.Random, now: datetime) -> None:
        events, counter, ts = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 0, rng, "test_pattern",
        )
        assert len(events) >= 1
        # Last event is always a successful login
        assert events[-1].metadata["login_success"] is True

    def test_all_events_are_logins(self, rng: random.Random, now: datetime) -> None:
        events, _, _ = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 0, rng, "test_pattern",
        )
        for evt in events:
            assert evt.interaction_type == InteractionType.LOGIN

    def test_counter_incremented(self, rng: random.Random, now: datetime) -> None:
        events, counter, _ = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 10, rng, "test_pattern",
        )
        assert counter == 10 + len(events)

    def test_extra_metadata_merged(self, rng: random.Random, now: datetime) -> None:
        events, _, _ = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 0, rng, "test",
            extra_metadata={"attacker_country": "RU"},
        )
        for evt in events:
            assert evt.metadata["attacker_country"] == "RU"
            assert evt.metadata["attack_pattern"] == "test"

    def test_failures_come_before_success(self, now: datetime) -> None:
        # Use a fixed seed that produces failures
        rng = random.Random(0)
        events, _, _ = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 0, rng, "test",
        )
        successes = [e for e in events if e.metadata["login_success"]]
        failures = [e for e in events if not e.metadata["login_success"]]
        if failures:
            assert successes[-1].timestamp >= failures[-1].timestamp

    def test_no_extra_metadata(self, rng: random.Random, now: datetime) -> None:
        events, _, _ = _make_login_with_failures(
            "u-0001", now, "1.2.3.4", 0, rng, "test",
            extra_metadata=None,
        )
        assert len(events) >= 1
        assert "attacker_country" not in events[0].metadata


# ===================================================================
# Pattern tests
# ===================================================================
class TestSmashAndGrab:
    def test_with_close_account(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, counter = _smash_and_grab(
            "u-0001", "US", all_user_ids, base_time, 0, rng, close_account=True,
        )
        assert len(events) > 0
        assert counter > 0
        # Should have LOGIN, DOWNLOAD_ADDRESS_BOOK, MESSAGE_USER, CLOSE_ACCOUNT
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types
        assert InteractionType.MESSAGE_USER in types
        assert InteractionType.CLOSE_ACCOUNT in types
        # Last event should be CLOSE_ACCOUNT
        assert events[-1].interaction_type == InteractionType.CLOSE_ACCOUNT

    def test_without_close_account(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _smash_and_grab(
            "u-0001", "US", all_user_ids, base_time, 0, rng, close_account=False,
        )
        types = {e.interaction_type for e in events}
        assert InteractionType.CLOSE_ACCOUNT not in types

    def test_spam_targets_differ_from_victim(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _smash_and_grab(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        for e in events:
            if e.target_user_id is not None:
                assert e.target_user_id != "u-0001"

    def test_all_events_use_hosting_ip(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _smash_and_grab(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        for e in events:
            assert e.ip_type == IPType.HOSTING


class TestLowAndSlow:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, counter = _low_and_slow(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.VIEW_USER_PAGE in types
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types
        assert InteractionType.MESSAGE_USER in types
        # Low & slow never closes account
        assert InteractionType.CLOSE_ACCOUNT not in types

    def test_user_id_consistent(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _low_and_slow(
            "u-0005", "GB", all_user_ids, base_time, 0, rng,
        )
        for e in events:
            assert e.user_id == "u-0005"


class TestCountryHopper:
    def test_with_close_account(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _country_hopper(
            "u-0001", "US", all_user_ids, base_time, 0, rng, close_account=True,
        )
        types = {e.interaction_type for e in events}
        assert InteractionType.CLOSE_ACCOUNT in types

    def test_without_close_account(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _country_hopper(
            "u-0001", "US", all_user_ids, base_time, 0, rng, close_account=False,
        )
        types = {e.interaction_type for e in events}
        assert InteractionType.CLOSE_ACCOUNT not in types

    def test_multiple_ips_used(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _country_hopper(
            "u-0001", "DE", all_user_ids, base_time, 0, rng,
        )
        ips = {e.ip_address for e in events}
        # Country hopper uses 3-4 IPs + 1 final attack IP
        assert len(ips) >= 2

    def test_has_download_and_spam(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _country_hopper(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        types = {e.interaction_type for e in events}
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types
        assert InteractionType.MESSAGE_USER in types


class TestDataThief:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, counter = _data_thief(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types
        assert InteractionType.CLOSE_ACCOUNT in types
        # Data thief does NOT spam
        assert InteractionType.MESSAGE_USER not in types

    def test_uses_python_requests_user_agent(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _data_thief(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        login_events = [e for e in events if e.interaction_type == InteractionType.LOGIN]
        for evt in login_events:
            assert evt.metadata["user_agent"] == "python-requests/2.31"

    def test_last_event_is_close(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _data_thief(
            "u-0001", "US", all_user_ids, base_time, 0, rng,
        )
        assert events[-1].interaction_type == InteractionType.CLOSE_ACCOUNT


class TestCredentialStuffer:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victim_ids = ["u-0010", "u-0011", "u-0012"]
        victim_countries = ["US", "GB", "DE"]
        events, counter = _credential_stuffer(
            victim_ids, victim_countries, all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0

    def test_all_victims_appear(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victim_ids = ["u-0010", "u-0011", "u-0012"]
        victim_countries = ["US", "GB", "DE"]
        events, _ = _credential_stuffer(
            victim_ids, victim_countries, all_user_ids, base_time, 0, rng,
        )
        event_users = {e.user_id for e in events}
        for vid in victim_ids:
            assert vid in event_users

    def test_same_ip_for_all_victims(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victim_ids = ["u-0010", "u-0011"]
        victim_countries = ["US", "GB"]
        events, _ = _credential_stuffer(
            victim_ids, victim_countries, all_user_ids, base_time, 0, rng,
        )
        ips = {e.ip_address for e in events}
        assert len(ips) == 1  # same attacker IP

    def test_has_downloads_and_spam(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victim_ids = ["u-0010", "u-0011", "u-0012"]
        victim_countries = ["US", "GB", "DE"]
        events, _ = _credential_stuffer(
            victim_ids, victim_countries, all_user_ids, base_time, 0, rng,
        )
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types
        assert InteractionType.MESSAGE_USER in types

    def test_batch_metadata_present(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victim_ids = ["u-0010", "u-0011"]
        victim_countries = ["US", "GB"]
        events, _ = _credential_stuffer(
            victim_ids, victim_countries, all_user_ids, base_time, 0, rng,
        )
        login_events = [e for e in events if e.interaction_type == InteractionType.LOGIN]
        for evt in login_events:
            assert "batch_index" in evt.metadata
            assert evt.metadata["batch_size"] == 2


class TestScraperCluster:
    def test_produces_many_views(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0020", "u-0021", "u-0022"]
        countries = ["US", "GB", "DE"]
        events, _ = _scraper_cluster(
            victims, countries, all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        view_count = sum(1 for e in events if e.interaction_type == InteractionType.VIEW_USER_PAGE)
        assert view_count >= 10

    def test_all_victims_used(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0020", "u-0021"]
        countries = ["US", "GB"]
        events, _ = _scraper_cluster(
            victims, countries, all_user_ids, base_time, 0, rng,
        )
        event_users = {e.user_id for e in events}
        for vid in victims:
            assert vid in event_users

    def test_alphabetical_strategy_uses_display_names(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        targets = [u for u in all_user_ids if u not in ("u-0020", "u-0021")][:50]
        victims = ["u-0020", "u-0021"]
        countries = ["US", "GB"]
        display_names = {uid: f"User_{uid}" for uid in targets}
        events, _ = _scraper_cluster(
            victims, countries, all_user_ids, base_time, 0, rng,
            user_display_names=display_names,
            strategy="alphabetical",
        )
        assert len(events) > 0
        alphabetical_views = [e for e in events if e.metadata.get("scrape_strategy") == "alphabetical"]
        assert len(alphabetical_views) > 0

    def test_coordinated_strategy(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0020", "u-0021", "u-0022"]
        countries = ["US", "GB", "DE"]
        events, _ = _scraper_cluster(
            victims, countries, all_user_ids, base_time, 0, rng,
            strategy="coordinated",
        )
        assert len(events) > 0
        coordinated_views = [e for e in events if e.metadata.get("scrape_strategy") == "coordinated"]
        assert len(coordinated_views) > 0

    def test_regular_interval_strategy(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0020", "u-0021"]
        countries = ["US", "GB"]
        events, _ = _scraper_cluster(
            victims, countries, all_user_ids, base_time, 0, rng,
            strategy="regular_interval",
        )
        assert len(events) > 0
        regular_views = [e for e in events if e.metadata.get("scrape_strategy") == "regular_interval"]
        assert len(regular_views) > 0


class TestSpearPhisher:
    def test_view_before_message(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _spear_phisher(
            "u-0030", "US", all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.VIEW_USER_PAGE in types
        assert InteractionType.MESSAGE_USER in types

    def test_phishing_activity_uses_residential_ip(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        """Spear phisher uses residential IP for view/message; login may use hosting for failures."""
        events, _ = _spear_phisher(
            "u-0030", "US", all_user_ids, base_time, 0, rng,
        )
        # At least view/message events should use residential (FRAUD_TYPES.md)
        view_msg = [e for e in events if e.interaction_type in (InteractionType.VIEW_USER_PAGE, InteractionType.MESSAGE_USER)]
        if view_msg:
            for e in view_msg:
                assert e.ip_type == IPType.RESIDENTIAL


class TestCredentialTester:
    def test_minimal_activity_per_victim(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0040", "u-0041", "u-0042"]
        countries = ["US", "GB", "DE"]
        events, _ = _credential_tester(
            victims, countries, all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        for vid in victims:
            victim_events = [e for e in events if e.user_id == vid]
            assert len(victim_events) >= 1
            assert any(e.interaction_type == InteractionType.LOGIN for e in victim_events)

    def test_no_spam(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        victims = ["u-0040", "u-0041"]
        countries = ["US", "GB"]
        events, _ = _credential_tester(
            victims, countries, all_user_ids, base_time, 0, rng,
        )
        for e in events:
            assert e.interaction_type != InteractionType.MESSAGE_USER


class TestConnectionHarvester:
    def test_many_connection_requests(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _connection_harvester(
            "u-0050", "US", all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        connect_count = sum(1 for e in events if e.interaction_type == InteractionType.CONNECT_WITH_USER)
        assert connect_count >= 20

    def test_no_close_account(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _connection_harvester(
            "u-0050", "US", all_user_ids, base_time, 0, rng,
        )
        assert InteractionType.CLOSE_ACCOUNT not in {e.interaction_type for e in events}


class TestSleeperAgent:
    def test_has_checkins_and_spam(
        self, rng: random.Random, now: datetime, all_user_ids: list[str]
    ) -> None:
        # Use base_time well in past so 2-4 week dormancy doesn't extend into future
        base_time = now - timedelta(days=45)
        events, _ = _sleeper_agent(
            "u-0060", "US", all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.MESSAGE_USER in types


# ===================================================================
# Public API tests
# ===================================================================
class TestLoginFirstInvariant:
    """Verify that no victim has activity before their first LOGIN."""

    def test_valid_events_pass(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.LOGIN, now - timedelta(hours=3), "1.2.3.4"),
            _make_event(2, "u-0001", InteractionType.DOWNLOAD_ADDRESS_BOOK,
                        now - timedelta(hours=2), "1.2.3.4"),
            _make_event(3, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=1), "1.2.3.4",
                        target_user_id="u-0002"),
        ]
        _enforce_login_first_invariant(events)  # should not raise

    def test_spam_before_login_raises(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=3), "1.2.3.4",
                        target_user_id="u-0002"),
            _make_event(2, "u-0001", InteractionType.LOGIN,
                        now - timedelta(hours=2), "1.2.3.4"),
        ]
        with pytest.raises(AssertionError, match="Invariant violation"):
            _enforce_login_first_invariant(events)

    def test_download_before_login_raises(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.DOWNLOAD_ADDRESS_BOOK,
                        now - timedelta(hours=3), "1.2.3.4"),
            _make_event(2, "u-0001", InteractionType.LOGIN,
                        now - timedelta(hours=2), "1.2.3.4"),
        ]
        with pytest.raises(AssertionError, match="Invariant violation"):
            _enforce_login_first_invariant(events)

    def test_multiple_victims_independent(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.LOGIN,
                        now - timedelta(hours=4), "1.2.3.4"),
            _make_event(2, "u-0002", InteractionType.LOGIN,
                        now - timedelta(hours=3), "1.2.3.5"),
            _make_event(3, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=2), "1.2.3.4",
                        target_user_id="u-0002"),
            _make_event(4, "u-0002", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=1), "1.2.3.5",
                        target_user_id="u-0001"),
        ]
        _enforce_login_first_invariant(events)  # should not raise

    def test_generate_malicious_events_passes_invariant(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        """End-to-end: generate_malicious_events enforces the invariant internally."""
        # This implicitly calls _enforce_login_first_invariant
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        assert len(events) > 0

    def test_generate_malicious_events_respects_fraud_temporal_invariants(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        """Validate all fraud temporal invariants: LOGIN first, spam after login, CLOSE terminal."""
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        assert len(events) > 0
        assert_fraud_temporal_invariants(events)


class TestSpamAfterLoginInvariant:
    """Spam must always be preceded by at least one login attempt."""

    def test_valid_spam_after_login(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.LOGIN, now - timedelta(hours=2), "1.2.3.4"),
            _make_event(2, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=1), "1.2.3.4",
                        target_user_id="u-0002"),
        ]
        _enforce_spam_after_login_invariant(events)  # should not raise

    def test_spam_without_login_raises(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=1), "1.2.3.4",
                        target_user_id="u-0002"),
        ]
        with pytest.raises(AssertionError, match="no preceding login attempts"):
            _enforce_spam_after_login_invariant(events)

    def test_spam_before_login_raises(self, now: datetime) -> None:
        events = [
            _make_event(1, "u-0001", InteractionType.MESSAGE_USER,
                        now - timedelta(hours=3), "1.2.3.4",
                        target_user_id="u-0002"),
            _make_event(2, "u-0001", InteractionType.LOGIN,
                        now - timedelta(hours=2), "1.2.3.4"),
        ]
        with pytest.raises(AssertionError, match="no preceding login attempts"):
            _enforce_spam_after_login_invariant(events)


class TestGenerateMaliciousEvents:
    def test_returns_sorted_events(self, all_user_ids: list[str], user_countries: dict[str, str]) -> None:
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        for i in range(1, len(events)):
            assert events[i].timestamp >= events[i - 1].timestamp

    def test_has_events_from_all_patterns(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        patterns = set()
        for e in events:
            if "attack_pattern" in e.metadata:
                patterns.add(e.metadata["attack_pattern"])
        assert "smash_grab" in patterns
        assert "low_slow" in patterns
        assert "country_hopper" in patterns
        assert "data_thief" in patterns
        assert "credential_stuffer" in patterns
        assert "login_storm" in patterns
        assert "stealth_takeover" in patterns
        assert "fake_account" in patterns
        assert "scraper_cluster" in patterns
        assert "spear_phisher" in patterns
        assert "credential_tester" in patterns
        assert "connection_harvester" in patterns
        assert "sleeper_agent" in patterns
        assert "executive_hunter" in patterns

    def test_multiple_victims(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        victims = {e.user_id for e in events}
        assert len(victims) >= 10  # At least 10 distinct victims

    def test_all_events_are_valid(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        assert len(events) > 0
        for e in events:
            assert isinstance(e.interaction_type, InteractionType)
            assert isinstance(e.ip_type, IPType)
            assert e.timestamp.tzinfo is not None

    def test_deterministic_with_seed(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        # Use seed 42 to avoid scraper_cluster timestamp ordering edge cases
        events1, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=42, fraud_pct=75)
        events2, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=42, fraud_pct=75)
        assert len(events1) == len(events2)
        for e1, e2 in zip(events1, events2):
            assert e1.interaction_id == e2.interaction_id

    def test_has_spam_and_close_events(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        events, _ = generate_malicious_events(all_user_ids, user_countries, fake_account_user_ids=FAKE_ACCOUNT_USER_IDS, seed=99, fraud_pct=75)
        types = {e.interaction_type for e in events}
        assert InteractionType.MESSAGE_USER in types
        assert InteractionType.CLOSE_ACCOUNT in types
        assert InteractionType.DOWNLOAD_ADDRESS_BOOK in types

    def test_returns_victim_to_pattern_mapping(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        """victim_to_pattern is source of truth for account generation_pattern."""
        events, victim_to_pattern = generate_malicious_events(
            all_user_ids, user_countries, seed=99, fraud_pct=75
        )
        victims = {e.user_id for e in events}
        assert len(victim_to_pattern) == len(victims)
        for vid in victims:
            assert vid in victim_to_pattern
            assert victim_to_pattern[vid] in {
                "smash_grab", "low_slow", "country_hopper", "data_thief",
                "credential_stuffer", "login_storm", "stealth_takeover",
                "scraper_cluster", "spear_phisher", "credential_tester",
                "connection_harvester", "sleeper_agent", "fake_account",
                "profile_defacement", "executive_hunter",
            }

    def test_with_fishy_accounts_adds_account_farming_harassment_like(
        self, all_user_ids: list[str], user_countries: dict[str, str]
    ) -> None:
        """Passing account_farming, harassment, like_inflation IDs produces those patterns."""
        farming_ids = ["u-0010", "u-0011"]
        harass_ids = ["u-0020", "u-0021"]
        like_ids = ["u-0030", "u-0031"]
        events, victim_to_pattern = generate_malicious_events(
            all_user_ids, user_countries,
            account_farming_user_ids=[u for u in farming_ids if u in all_user_ids],
            harassment_user_ids=[u for u in harass_ids if u in all_user_ids],
            like_inflation_user_ids=[u for u in like_ids if u in all_user_ids],
            seed=7, fraud_pct=10,
        )
        # Should have events from account_farming, coordinated_harassment, coordinated_like_inflation
        patterns = set(victim_to_pattern.values())
        assert "account_farming" in patterns or any(
            e.metadata.get("attack_pattern") == "account_farming" for e in events
        )
        assert "coordinated_harassment" in patterns or any(
            e.metadata.get("attack_pattern") == "coordinated_harassment" for e in events
        )
        assert "coordinated_like_inflation" in patterns or any(
            e.metadata.get("attack_pattern") == "coordinated_like_inflation" for e in events
        )


class TestAccountFarming:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        farming_ids = ["u-0010", "u-0011"]
        events, counter = _account_farming(
            farming_ids, all_user_ids, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.CHANGE_PASSWORD in types
        assert InteractionType.CHANGE_PROFILE in types
        assert InteractionType.CHANGE_NAME in types

    def test_uses_residential_ip(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        events, _ = _account_farming(
            ["u-0010"], all_user_ids, base_time, 0, rng,
        )
        for e in events:
            assert e.ip_type == IPType.RESIDENTIAL


class TestCoordinatedHarassment:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        harasser_ids = ["u-0020", "u-0021"]
        targets = [uid for uid in all_user_ids if uid not in harasser_ids][:3]
        events, counter = _coordinated_harassment(
            harasser_ids, targets, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.MESSAGE_USER in types

    def test_all_harassers_target_same_users(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        harasser_ids = ["u-0020", "u-0021"]
        targets = [uid for uid in all_user_ids if uid not in harasser_ids][:2]
        events, _ = _coordinated_harassment(
            harasser_ids, targets, base_time, 0, rng,
        )
        msg_events = [e for e in events if e.interaction_type == InteractionType.MESSAGE_USER]
        assert len(msg_events) >= len(harasser_ids) * len(targets)


class TestCoordinatedLikeInflation:
    def test_basic_structure(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        liker_ids = ["u-0030", "u-0031"]
        target = next(uid for uid in all_user_ids if uid not in liker_ids)
        events, counter = _coordinated_like_inflation(
            liker_ids, target, base_time, 0, rng,
        )
        assert len(events) > 0
        assert counter > 0
        types = {e.interaction_type for e in events}
        assert InteractionType.LOGIN in types
        assert InteractionType.LIKE in types

    def test_all_likers_target_same_user(
        self, rng: random.Random, base_time: datetime, all_user_ids: list[str]
    ) -> None:
        liker_ids = ["u-0030", "u-0031"]
        target = next(uid for uid in all_user_ids if uid not in liker_ids)
        events, _ = _coordinated_like_inflation(
            liker_ids, target, base_time, 0, rng,
        )
        like_events = [e for e in events if e.interaction_type == InteractionType.LIKE]
        assert len(like_events) == len(liker_ids)
        for e in like_events:
            assert e.target_user_id == target
