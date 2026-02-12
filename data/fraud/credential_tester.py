"""Credential Tester: validates stolen credentials without exploiting the accounts.

The attacker has a bulk list of leaked credentials and probes which ones
still work.  Each compromised account gets a single login (maybe one
failed attempt), optionally one page view to confirm the account is live,
then nothing.  Sessions last under 60 seconds.

The attacker is building a verified credential list to sell — not
exploiting the accounts directly.  The signal is many accounts showing
a single successful login from the same hosting IP with no follow-up
activity.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import (
    make_event,
    pick_attacker_country,
    pick_hosting_ip,
)

# Bot UAs commonly used by credential-testing scripts
_TESTER_USER_AGENTS = [
    "python-requests/2.31.0",
    "Go-http-client/2.0",
    "okhttp/4.12.0",
    "axios/1.6.2",
    "Mozilla/5.0 Chrome/120",
]


def credential_tester(
    victim_ids: list[str],
    victim_countries: list[str],
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Batch credential validation: same hosting IP tests 5-10 accounts in
    rapid succession.  Each account gets login (+ optional page view),
    then the attacker moves on.

    Args:
        victim_ids:       Accounts whose credentials are being tested.
        victim_countries: Home countries of those accounts.
        all_user_ids:     Full user population (for optional view targets).
        base_time:        Start of the testing campaign.
        counter:          Global event counter.
        rng:              Seeded random generator.

    Returns:
        (events, counter)
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    ua = rng.choice(_TESTER_USER_AGENTS)
    ts = base_time

    for victim_id, victim_country in zip(victim_ids, victim_countries):
        attacker_country = pick_attacker_country(victim_country, rng)

        # 0-1 failed login attempts before success
        if rng.random() < get_cfg(config, "fraud", "credential_tester", "failed_login_first_pct", default=0.3):
            counter += 1
            events.append(make_event(
                counter, victim_id, InteractionType.LOGIN, ts, ip,
                metadata={
                    "attack_pattern": "credential_tester",
                    "attacker_country": attacker_country,
                    "ip_country": attacker_country,
                    "user_agent": ua,
                    "login_success": False,
                },
            ))
            ts += timedelta(seconds=rng.randint(2, 8))

        # Successful login
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.LOGIN, ts, ip,
            metadata={
                "attack_pattern": "credential_tester",
                "attacker_country": attacker_country,
                "ip_country": attacker_country,
                "user_agent": ua,
                "login_success": True,
            },
        ))

        # ~40% of the time, view a single page to confirm account is live
        if rng.random() < get_cfg(config, "fraud", "credential_tester", "page_view_after_login_pct", default=0.4):
            ts += timedelta(seconds=rng.randint(3, 15))
            targets = [uid for uid in all_user_ids if uid != victim_id]
            counter += 1
            events.append(make_event(
                counter, victim_id, InteractionType.VIEW_USER_PAGE, ts, ip,
                target_user_id=rng.choice(targets),
                metadata={
                    "attack_pattern": "credential_tester",
                    "ip_country": attacker_country,
                    "user_agent": ua,
                },
            ))

        # Short gap before testing the next account (5-30 seconds)
        ts += timedelta(seconds=rng.randint(5, 30))

    return events, counter
