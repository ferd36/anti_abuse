"""Stealth Takeover: failures on hosting → success → login from another country → wait → close from residential."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from ._common import (
    ALT_USER_AGENTS,
    make_event,
    make_login_with_many_failures,
    pick_distinct_countries,
    pick_hosting_ip,
    pick_residential_ip,
)


def stealth_takeover(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
) -> tuple[list, int]:
    """
    Several login failures (hosting) -> success -> login from another country
    with different UA -> wait a few days -> download address book ->
    close from yet another country via residential IP.
    """
    events: list = []
    countries = pick_distinct_countries(victim_country, 3, rng)
    country_a, country_b, country_c = countries[0], countries[1], countries[2]

    ip_hosting_1 = pick_hosting_ip(rng)
    ip_hosting_2 = pick_hosting_ip(rng)
    ip_residential = pick_residential_ip(rng)
    alt_ua = rng.choice(ALT_USER_AGENTS)

    ts = base_time

    login_evts, counter, ts = make_login_with_many_failures(
        victim_id, ts, ip_hosting_1, counter, rng, "stealth_takeover",
        min_failures=3,
        max_failures=8,
        extra_metadata={"attacker_country": country_a},
    )
    events.extend(login_evts)

    ts += timedelta(hours=rng.randint(2, 12))
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.LOGIN, ts, ip_hosting_2,
        metadata={
            "attack_pattern": "stealth_takeover",
            "attacker_country": country_b,
            "user_agent": alt_ua,
            "login_success": True,
        },
    ))

    ts += timedelta(days=rng.randint(2, 5), hours=rng.randint(0, 12))

    ts += timedelta(minutes=rng.randint(5, 60))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip_hosting_2,
                            metadata={"attack_pattern": "stealth_takeover",
                                      "contact_count": rng.randint(50, 400),
                                      "ip_country": country_b}))

    ts += timedelta(minutes=rng.randint(10, 120))
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.CLOSE_ACCOUNT, ts, ip_residential,
        metadata={"attack_pattern": "stealth_takeover",
                  "ip_country": country_c},
        ip_type=IPType.RESIDENTIAL,
    ))

    return events, counter
