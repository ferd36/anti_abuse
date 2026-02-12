"""Login Storm: 5–15 failed logins, then success, download, close."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from ._common import (
    make_event,
    make_login_with_many_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def login_storm(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
) -> tuple[list, int]:
    """
    Many failed login attempts (5-15), then success, download, close.
    Emphasizes login_failures_before_success + closure at the end.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    login_evts, counter, ts = make_login_with_many_failures(
        victim_id, ts, ip, counter, rng, "login_storm",
        min_failures=5,
        max_failures=15,
        extra_metadata={"attacker_country": attacker_country},
    )
    events.extend(login_evts)

    ts += timedelta(minutes=rng.randint(1, 5))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
                            metadata={"attack_pattern": "login_storm",
                                      "contact_count": rng.randint(50, 300),
                                      "ip_country": attacker_country}))

    ts += timedelta(minutes=rng.randint(1, 10))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.CLOSE_ACCOUNT, ts, ip,
                            metadata={"attack_pattern": "login_storm",
                                      "ip_country": attacker_country}))

    return events, counter
