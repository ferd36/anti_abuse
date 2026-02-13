"""Romance Scam: extended MESSAGE_USER thread to defraud victim."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, pick_hosting_ip, pick_residential_ip


def romance_scam(
    victim_id: str,
    scammer_id: str,
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Scammer sends extended message thread to victim over days/weeks.
    Victim-based: victim is the target of the scam.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    msg_min = get_cfg(cfg, "fraud", "romance_scam", "messages_per_victim_min", default=20)
    msg_max = get_cfg(cfg, "fraud", "romance_scam", "messages_per_victim_max", default=100)
    days_min = get_cfg(cfg, "fraud", "romance_scam", "duration_days_min", default=7)
    days_max = get_cfg(cfg, "fraud", "romance_scam", "duration_days_max", default=60)
    events: list = []
    n_msgs = rng.randint(msg_min, msg_max)
    duration_days = rng.randint(days_min, days_max)
    ts = base_time

    ip = pick_residential_ip(rng)
    counter += 1
    events.append(make_event(
        counter, scammer_id, InteractionType.LOGIN, ts, ip,
        metadata={"attack_pattern": "romance_scam", "ip_country": rng.choice(countries), "login_success": True},
        ip_type=IPType.RESIDENTIAL,
    ))
    ts += timedelta(minutes=rng.randint(5, 30))

    for i in range(n_msgs):
        interval_minutes = (duration_days * 24 * 60) // n_msgs
        ts += timedelta(minutes=rng.randint(max(1, interval_minutes // 2), interval_minutes))
        ip = pick_residential_ip(rng)
        counter += 1
        phase = "initial" if i < n_msgs // 3 else ("middle" if i < 2 * n_msgs // 3 else "ask")
        events.append(make_event(
            counter, scammer_id, InteractionType.MESSAGE_USER, ts, ip,
            target_user_id=victim_id,
            metadata={"attack_pattern": "romance_scam", "ip_country": rng.choice(countries), "scam_phase": phase},
        ))

    return events, counter
