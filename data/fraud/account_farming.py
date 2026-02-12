"""Account Farming: hosting IPs create empty accounts, sold to buyers who take over.

Clusters of hosting IPs create many empty accounts. Credentials are sold.
Buyers log in from different IPs (residential), change password, fill with bogus profiles.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, pick_hosting_ip, pick_residential_ip


def account_farming(
    farming_user_ids: list[str],
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    For each farmed account: buyer logs in (different IP than creator), changes
    password, fills profile with bogus content. The ACCOUNT_CREATION from hosting
    is done in mock_data.
    """
    cfg = config or {}
    hours_min = get_cfg(cfg, "fraud", "account_farming", "hours_between_accounts_min", default=2)
    hours_max = get_cfg(cfg, "fraud", "account_farming", "hours_between_accounts_max", default=12)
    update_headline_pct = get_cfg(cfg, "fraud", "account_farming", "update_headline_pct", default=0.7)
    update_summary_pct = get_cfg(cfg, "fraud", "account_farming", "update_summary_pct", default=0.5)

    events: list = []
    buyer_ip = pick_residential_ip(rng)
    ts = base_time

    for fid in farming_user_ids:
        ts += timedelta(hours=rng.randint(hours_min, hours_max), minutes=rng.randint(0, 59))

        counter += 1
        events.append(make_event(
            counter, fid, InteractionType.LOGIN, ts, buyer_ip,
            metadata={
                "attack_pattern": "account_farming",
                "ip_country": "US",
                "login_success": True,
                "buyer_takeover": True,
            },
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(2, 15))

        counter += 1
        events.append(make_event(
            counter, fid, InteractionType.CHANGE_PASSWORD, ts, buyer_ip,
            metadata={"attack_pattern": "account_farming", "ip_country": "US"},
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(1, 5))

        counter += 1
        events.append(make_event(
            counter, fid, InteractionType.CHANGE_PROFILE, ts, buyer_ip,
            metadata={"attack_pattern": "account_farming", "ip_country": "US"},
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(1, 3))

        counter += 1
        events.append(make_event(
            counter, fid, InteractionType.CHANGE_NAME, ts, buyer_ip,
            metadata={"attack_pattern": "account_farming", "ip_country": "US"},
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(1, 3))

        if rng.random() < update_headline_pct:
            counter += 1
            events.append(make_event(
                counter, fid, InteractionType.UPDATE_HEADLINE, ts, buyer_ip,
                metadata={"attack_pattern": "account_farming", "ip_country": "US"},
                ip_type=IPType.RESIDENTIAL,
            ))
            ts += timedelta(minutes=rng.randint(1, 2))

        if rng.random() < update_summary_pct:
            counter += 1
            events.append(make_event(
                counter, fid, InteractionType.UPDATE_SUMMARY, ts, buyer_ip,
                metadata={"attack_pattern": "account_farming", "ip_country": "US"},
                ip_type=IPType.RESIDENTIAL,
            ))

    return events, counter
