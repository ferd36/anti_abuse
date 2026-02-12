"""Smash & Grab: fast attack, login → download → mass spam → close in 1–6 hours."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from ._common import (
    SPAM_METADATA,
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def smash_and_grab(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    close_account: bool = True,
) -> tuple[list, int]:
    """
    Fast attack: login → download address book → mass spam → close.
    All within 1-6 hours.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "smash_grab",
        extra_metadata={"attacker_country": attacker_country},
    )
    events.extend(login_evts)

    ts += timedelta(minutes=rng.randint(5, 20))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
                            metadata={"attack_pattern": "smash_grab",
                                      "contact_count": rng.randint(50, 500),
                                      "ip_country": attacker_country}))

    num_spam = rng.randint(80, 200)
    spam_window = timedelta(hours=rng.uniform(1, 3))
    targets = [uid for uid in all_user_ids if uid != victim_id]
    rng.shuffle(targets)
    spam_targets = targets[:num_spam]

    for i, target in enumerate(spam_targets):
        offset = spam_window * (i / max(num_spam - 1, 1))
        msg_ts = ts + timedelta(minutes=2) + offset
        counter += 1
        meta = dict(rng.choice(SPAM_METADATA))
        meta["ip_country"] = attacker_country
        meta["attack_pattern"] = "smash_grab"
        events.append(make_event(counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, ip,
                                target_user_id=target,
                                metadata=meta))

    if close_account:
        ts = events[-1].timestamp + timedelta(minutes=rng.randint(10, 60))
        counter += 1
        events.append(make_event(counter, victim_id, InteractionType.CLOSE_ACCOUNT, ts, ip,
                                metadata={"attack_pattern": "smash_grab",
                                          "ip_country": attacker_country}))

    return events, counter
