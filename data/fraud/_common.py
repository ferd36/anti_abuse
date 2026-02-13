"""
Shared infrastructure and helpers for fraud attack pattern generators.

Used by all pattern modules in this package.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType
from core.models import UserInteraction


# ---------------------------------------------------------------------------
# Attacker infrastructure pools
# ---------------------------------------------------------------------------
HOSTING_IPS = [
    "45.33.32.156", "104.131.0.69", "185.220.101.34", "193.118.53.202",
    "34.145.89.12", "52.14.201.166", "139.59.100.11", "142.93.12.88",
    "54.210.33.77", "35.188.42.15", "185.100.87.202", "45.155.205.99",
    "104.248.30.5", "52.207.88.14", "193.32.162.70", "34.89.210.44",
]

RESIDENTIAL_IPS = [
    "78.45.12.89", "92.118.34.156", "188.120.45.78", "95.165.33.201",
    "82.65.91.123", "37.230.117.88", "91.205.72.34", "85.26.155.99",
]

US_HOSTING_IPS = [
    "34.145.89.12", "34.89.210.44", "35.188.42.15", "52.14.201.166",
    "52.207.88.14", "104.131.0.69", "104.248.30.5",
]

ALT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
]

ATTACKER_COUNTRIES_BY_VICTIM = {
    "US": ["RU", "CN", "NG", "UA", "RO"],
    "GB": ["RU", "CN", "NG", "BR", "UA"],
    "CA": ["RU", "CN", "VN", "RO", "NG"],
    "AU": ["CN", "RU", "VN", "ID", "NG"],
    "DE": ["RU", "CN", "UA", "RO", "NG"],
    "FR": ["RU", "CN", "NG", "RO", "UA"],
    "IN": ["RU", "CN", "NG", "RO", "UA"],
    "BR": ["RU", "CN", "NG", "UA", "RO"],
    "JP": ["CN", "RU", "NG", "UA", "KR"],
    "KR": ["CN", "RU", "NG", "JP", "UA"],
}

HARASSMENT_METADATA = [
    {"message_length": 80, "is_spam": True, "message_text": "You're pathetic. Everyone knows what you did. Stop pretending."},
    {"message_length": 65, "is_spam": True, "message_text": "Nobody likes you. You should just disappear. We're watching."},
    {"message_length": 95, "is_spam": True, "message_text": "Think you're so great? Your days are numbered. We'll make sure everyone knows the truth."},
    {"message_length": 72, "is_spam": True, "message_text": "You're a fraud. We've got proof. Time to face the consequences."},
    {"message_length": 58, "is_spam": True, "message_text": "Loser. Why do you even bother? Give up already."},
]

SPAM_METADATA = [
    {"message_length": 45, "contains_url": True, "is_spam": True,
     "message_text": "Check this out! https://bit.ly/xyz123 You won't believe it!"},
    {"message_length": 62, "contains_url": True, "is_spam": True,
     "message_text": "Urgent: Your account needs verification. Click here now: https://verify-site.com"},
    {"message_length": 38, "contains_url": True, "is_spam": True,
     "message_text": "Free money! Visit https://promo.fake today!"},
    {"message_length": 51, "contains_url": True, "is_spam": True,
     "message_text": "You've been selected! Claim your prize: https://winner.lottery"},
    {"message_length": 55, "contains_url": True, "is_spam": True,
     "message_text": "Limited offer! Sign up at https://deal.com before it expires."},
    {"message_length": 40, "contains_url": True, "is_spam": True,
     "message_text": "Important message: https://secure-login.net/check"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pick_attacker_country(victim_country: str, rng: random.Random) -> str:
    pool = ATTACKER_COUNTRIES_BY_VICTIM.get(victim_country, ["RU", "CN", "NG", "UA", "RO"])
    return rng.choice(pool)


def pick_hosting_ip(rng: random.Random) -> str:
    return rng.choice(HOSTING_IPS)


def pick_residential_ip(rng: random.Random) -> str:
    return rng.choice(RESIDENTIAL_IPS)


def pick_distinct_countries(
    victim_country: str, count: int, rng: random.Random
) -> list[str]:
    pool = ATTACKER_COUNTRIES_BY_VICTIM.get(
        victim_country, ["RU", "CN", "NG", "UA", "RO"]
    )
    return rng.sample(pool, min(count, len(pool)))


def make_event(
    counter: int,
    user_id: str,
    itype: InteractionType,
    ts: datetime,
    ip: str,
    target_user_id: str | None = None,
    metadata: dict | None = None,
    ip_type: IPType = IPType.HOSTING,
) -> UserInteraction:
    meta = metadata or {}
    if "user_agent" not in meta:
        meta["user_agent"] = "Mozilla/5.0 Chrome/120"
    return UserInteraction(
        interaction_id=f"fraud-{counter:06d}",
        user_id=user_id,
        interaction_type=itype,
        timestamp=ts,
        ip_address=ip,
        ip_type=ip_type,
        target_user_id=target_user_id,
        metadata=meta,
    )


def make_login_with_failures(
    victim_id: str,
    ts: datetime,
    ip: str,
    counter: int,
    rng: random.Random,
    attack_pattern: str,
    extra_metadata: dict | None = None,
) -> tuple[list[UserInteraction], int, datetime]:
    events: list[UserInteraction] = []
    num_failures = rng.randint(0, 3)

    for _ in range(num_failures):
        counter += 1
        meta = {"user_agent": "Mozilla/5.0 Chrome/120", "attack_pattern": attack_pattern, "login_success": False}
        if extra_metadata:
            meta.update(extra_metadata)
        events.append(make_event(counter, victim_id, InteractionType.LOGIN, ts, ip, metadata=meta))
        ts += timedelta(seconds=rng.randint(5, 45))

    counter += 1
    meta = {"user_agent": "Mozilla/5.0 Chrome/120", "attack_pattern": attack_pattern, "login_success": True}
    if extra_metadata:
        meta.update(extra_metadata)
    events.append(make_event(counter, victim_id, InteractionType.LOGIN, ts, ip, metadata=meta))
    return events, counter, ts


def make_login_with_many_failures(
    victim_id: str,
    ts: datetime,
    ip: str,
    counter: int,
    rng: random.Random,
    attack_pattern: str,
    min_failures: int,
    max_failures: int,
    extra_metadata: dict | None = None,
) -> tuple[list[UserInteraction], int, datetime]:
    events: list[UserInteraction] = []
    num_failures = rng.randint(min_failures, max_failures)

    for _ in range(num_failures):
        counter += 1
        meta = {"user_agent": "Mozilla/5.0 Chrome/120", "attack_pattern": attack_pattern, "login_success": False}
        if extra_metadata:
            meta.update(extra_metadata)
        events.append(make_event(counter, victim_id, InteractionType.LOGIN, ts, ip, metadata=meta))
        ts += timedelta(seconds=rng.randint(5, 45))

    counter += 1
    meta = {"user_agent": "Mozilla/5.0 Chrome/120", "attack_pattern": attack_pattern, "login_success": True}
    if extra_metadata:
        meta.update(extra_metadata)
    events.append(make_event(counter, victim_id, InteractionType.LOGIN, ts, ip, metadata=meta))
    return events, counter, ts


def enforce_login_first_invariant(events: list[UserInteraction]) -> None:
    first_login: dict[str, datetime] = {}
    session_start_types = (InteractionType.LOGIN, InteractionType.SESSION_LOGIN)
    no_login_required = (InteractionType.PHISHING_LOGIN,)  # Victim submits to fake page
    for e in events:
        uid = e.user_id
        if e.interaction_type in session_start_types:
            if uid not in first_login:
                first_login[uid] = e.timestamp
        elif e.interaction_type in no_login_required:
            pass
        else:
            assert uid in first_login and e.timestamp >= first_login[uid], (
                f"Invariant violation: {e.interaction_type.value} for {uid} "
                f"at {e.timestamp} occurs before first login "
                f"at {first_login.get(uid, 'NEVER')}"
            )


def enforce_spam_after_login_invariant(events: list[UserInteraction]) -> None:
    logins_seen: dict[str, int] = {}
    for e in events:
        uid = e.user_id
        if e.interaction_type in (InteractionType.LOGIN, InteractionType.SESSION_LOGIN):
            logins_seen[uid] = logins_seen.get(uid, 0) + 1
        elif e.interaction_type == InteractionType.MESSAGE_USER:
            assert uid in logins_seen and logins_seen[uid] > 0, (
                f"Invariant violation: spam for {uid} at {e.timestamp} "
                f"has no preceding login attempts"
            )
