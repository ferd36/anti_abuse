"""Profile Cloning: impersonate victim via VIEW, CONNECT, MESSAGE."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def profile_cloning(
    cloner_ids: list[str],
    victim_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Cloners log in, view victim profiles, optionally connect, then message.
    Impersonates victim with cloned profile.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    connect_pct = get_cfg(cfg, "fraud", "profile_cloning", "connect_before_message_pct", default=0.7)
    msg_min = get_cfg(cfg, "fraud", "profile_cloning", "messages_per_victim_min", default=3)
    msg_max = get_cfg(cfg, "fraud", "profile_cloning", "messages_per_victim_max", default=15)
    events: list = []
    ts = base_time

    for cid in cloner_ids:
        country = rng.choice(countries)
        ip = pick_hosting_ip(rng)
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            cid, ts, ip, counter, rng, "profile_cloning",
            extra_metadata={"ip_country": country},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(2, 8))

        for vid in victim_user_ids:
            ts += timedelta(minutes=rng.randint(1, 5))
            counter += 1
            events.append(make_event(
                counter, cid, InteractionType.VIEW_USER_PAGE, ts, ip,
                target_user_id=vid,
                metadata={"attack_pattern": "profile_cloning", "ip_country": country},
            ))
            if rng.random() < connect_pct:
                ts += timedelta(minutes=rng.randint(1, 3))
                counter += 1
                events.append(make_event(
                    counter, cid, InteractionType.CONNECT_WITH_USER, ts, ip,
                    target_user_id=vid,
                    metadata={"attack_pattern": "profile_cloning", "ip_country": country},
                ))
            n_msgs = rng.randint(msg_min, msg_max)
            for _ in range(n_msgs):
                ts += timedelta(minutes=rng.randint(5, 30))
                counter += 1
                events.append(make_event(
                    counter, cid, InteractionType.MESSAGE_USER, ts, ip,
                    target_user_id=vid,
                    metadata={"attack_pattern": "profile_cloning", "ip_country": country, "message_length": 50},
                ))

    return events, counter
