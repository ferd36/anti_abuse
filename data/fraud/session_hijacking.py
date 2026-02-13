"""Session Hijacking: victim's session token stolen, SESSION_LOGIN from attacker IP."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, pick_attacker_country, pick_hosting_ip


def session_hijacking(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Attacker uses stolen session token to SESSION_LOGIN, then performs actions.
    Victim-based: victim's account is hijacked.
    """
    cfg = config or {}
    actions_min = get_cfg(cfg, "fraud", "session_hijacking", "actions_after_hijack_min", default=5)
    actions_max = get_cfg(cfg, "fraud", "session_hijacking", "actions_after_hijack_max", default=30)
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    targets = [uid for uid in all_user_ids if uid != victim_id]
    if not targets:
        return events, counter

    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.SESSION_LOGIN, ts, ip,
        metadata={"attack_pattern": "session_hijacking", "ip_country": attacker_country, "session_stolen": True},
    ))
    ts += timedelta(minutes=rng.randint(1, 5))

    n_actions = rng.randint(actions_min, actions_max)
    for _ in range(n_actions):
        ts += timedelta(minutes=rng.randint(2, 30))
        counter += 1
        target = rng.choice(targets)
        events.append(make_event(
            counter, victim_id, InteractionType.VIEW_USER_PAGE, ts, ip,
            target_user_id=target,
            metadata={"attack_pattern": "session_hijacking", "ip_country": attacker_country},
        ))

    return events, counter
