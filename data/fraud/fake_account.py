"""Fake Account: IP ring account, dormant then US login → change password → spam."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import (
    SPAM_METADATA,
    US_HOSTING_IPS,
    make_event,
    pick_hosting_ip,
)


def fake_account(
    victim_id: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Fake account flow: account was created by IP ring (already in mock_data).
    Dormant period (time gap). Then:
    1. Login from US hosting
    2. Change password
    3. Change profile / name
    4. Login from another country
    5. Upload big address book
    6. Spam
    """
    events: list = []
    ip_us = rng.choice(US_HOSTING_IPS)
    other_country = rng.choice(["CN", "NG", "UA", "RO"])
    ip_other = pick_hosting_ip(rng)
    ts = base_time

    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.LOGIN, ts, ip_us,
        metadata={
            "attack_pattern": "fake_account",
            "attacker_country": "US",
            "ip_country": "US",
            "login_success": True,
        },
    ))
    ts += timedelta(minutes=rng.randint(2, 10))

    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.CHANGE_PASSWORD, ts, ip_us,
        metadata={"attack_pattern": "fake_account", "ip_country": "US"},
    ))
    ts += timedelta(minutes=rng.randint(1, 5))

    if rng.random() < get_cfg(config, "fraud", "fake_account", "change_profile_pct", default=0.7):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_PROFILE, ts, ip_us,
            metadata={"attack_pattern": "fake_account", "ip_country": "US"},
        ))
        ts += timedelta(minutes=rng.randint(1, 3))
    if rng.random() < get_cfg(config, "fraud", "fake_account", "change_name_pct", default=0.6):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_NAME, ts, ip_us,
            metadata={"attack_pattern": "fake_account", "ip_country": "US"},
        ))
        ts += timedelta(minutes=rng.randint(1, 3))

    ts += timedelta(hours=rng.randint(2, 24))
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.LOGIN, ts, ip_other,
        metadata={
            "attack_pattern": "fake_account",
            "attacker_country": other_country,
            "ip_country": other_country,
            "login_success": True,
        },
    ))
    ts += timedelta(minutes=rng.randint(3, 15))

    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.UPLOAD_ADDRESS_BOOK, ts, ip_other,
        metadata={
            "attack_pattern": "fake_account",
            "ip_country": other_country,
            "contact_count": rng.randint(2000, 8000),
        },
    ))
    ts += timedelta(minutes=rng.randint(5, 30))

    targets = [uid for uid in all_user_ids if uid != victim_id]
    rng.shuffle(targets)
    num_spam = rng.randint(50, 150)
    spam_targets = targets[:num_spam]
    spam_window = timedelta(hours=rng.uniform(1, 4))
    for i, target in enumerate(spam_targets):
        offset = spam_window * (i / max(num_spam - 1, 1))
        msg_ts = ts + offset
        counter += 1
        meta = dict(rng.choice(SPAM_METADATA))
        meta["ip_country"] = other_country
        meta["attack_pattern"] = "fake_account"
        events.append(make_event(
            counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, ip_other,
            target_user_id=target,
            metadata=meta,
        ))

    return events, counter
