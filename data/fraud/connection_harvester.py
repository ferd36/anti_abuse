"""Connection Harvester: blasts connection requests to inflate network size.

The attacker takes over a legitimate account and sends a burst of
CONNECT_WITH_USER requests to dozens or hundreds of users.  The goal
is to inflate the compromised account's network so it appears more
trustworthy for future spear-phishing or scam campaigns.

Key signals:
  - Sudden spike of 50-200 CONNECT_WITH_USER events from one account.
  - All from a foreign hosting IP.
  - An account that previously had low connection activity.
  - May download the address book first (to find targets), or just
    blast requests to random users.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import (
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def connection_harvester(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Login → optional address-book download → mass connection requests.
    Account is left open to maintain the inflated network.

    Args:
        victim_id:       The compromised account used for harvesting.
        victim_country:  Home country of the victim.
        all_user_ids:    Full user population (connection targets).
        base_time:       Campaign start time.
        counter:         Global event counter.
        rng:             Seeded random generator.

    Returns:
        (events, counter)
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    # --- Login ---
    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "connection_harvester",
        extra_metadata={"attacker_country": attacker_country},
    )
    events.extend(login_evts)

    # --- Optional: download address book to find high-value targets ---
    if rng.random() < get_cfg(config, "fraud", "connection_harvester", "download_address_book_pct", default=0.5):
        ts += timedelta(minutes=rng.randint(2, 10))
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
            metadata={
                "attack_pattern": "connection_harvester",
                "contact_count": rng.randint(50, 400),
                "ip_country": attacker_country,
            },
        ))

    # --- Blast connection requests ---
    ts += timedelta(minutes=rng.randint(3, 15))

    targets = [uid for uid in all_user_ids if uid != victim_id]
    rng.shuffle(targets)
    num_requests = rng.randint(50, 200)
    connect_targets = targets[:num_requests]

    # Requests are sent in a burst over 1-4 hours
    burst_window = timedelta(hours=rng.uniform(1, 4))

    for i, target in enumerate(connect_targets):
        offset = burst_window * (i / max(num_requests - 1, 1))
        connect_ts = ts + offset
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CONNECT_WITH_USER, connect_ts, ip,
            target_user_id=target,
            metadata={
                "attack_pattern": "connection_harvester",
                "ip_country": attacker_country,
                "batch_index": i + 1,
            },
        ))

    return events, counter
