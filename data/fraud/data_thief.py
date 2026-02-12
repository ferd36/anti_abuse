"""Data Thief: pure data exfiltration, login → download → close, no spam."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from ._common import (
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def data_thief(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
) -> tuple[list, int]:
    """
    Pure data exfiltration: login → download address book → close account.
    No spam. Fast and quiet.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "data_thief",
        extra_metadata={"attacker_country": attacker_country, "user_agent": "python-requests/2.31"},
    )
    events.extend(login_evts)

    ts += timedelta(minutes=rng.randint(1, 5))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
                            metadata={"attack_pattern": "data_thief",
                                      "contact_count": rng.randint(100, 1000),
                                      "ip_country": attacker_country}))

    ts += timedelta(minutes=rng.randint(1, 10))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.CLOSE_ACCOUNT, ts, ip,
                            metadata={"attack_pattern": "data_thief",
                                      "ip_country": attacker_country}))

    return events, counter
