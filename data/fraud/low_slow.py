"""Low & Slow: patient attack, dormant 2–5 days, then gradual spam over 2–3 days."""

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


def low_and_slow(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
) -> tuple[list, int]:
    """
    Patient attack: login → dormant 2-5 days → gradual spam over 2-3 days.
    Never closes the account.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "low_slow",
        extra_metadata={"attacker_country": attacker_country},
    )
    events.extend(login_evts)

    dormant_days = rng.randint(2, 5)
    num_views = rng.randint(3, 8)
    targets = [uid for uid in all_user_ids if uid != victim_id]
    for _ in range(num_views):
        view_ts = ts + timedelta(hours=rng.randint(6, dormant_days * 24))
        counter += 1
        events.append(make_event(counter, victim_id, InteractionType.VIEW_USER_PAGE, view_ts, ip,
                                target_user_id=rng.choice(targets),
                                metadata={"attack_pattern": "low_slow",
                                          "ip_country": attacker_country}))

    ts += timedelta(days=dormant_days, hours=rng.randint(1, 12))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
                            metadata={"attack_pattern": "low_slow",
                                      "contact_count": rng.randint(30, 300),
                                      "ip_country": attacker_country}))

    num_spam = rng.randint(15, 40)
    spam_days = rng.randint(2, 3)
    rng.shuffle(targets)
    spam_targets = targets[:num_spam]

    for i, target in enumerate(spam_targets):
        msg_ts = ts + timedelta(hours=rng.randint(1, spam_days * 24))
        counter += 1
        meta = dict(rng.choice(SPAM_METADATA))
        meta["ip_country"] = attacker_country
        meta["attack_pattern"] = "low_slow"
        events.append(make_event(counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, ip,
                                target_user_id=target,
                                metadata=meta))

    return events, counter
