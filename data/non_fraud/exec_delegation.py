"""
Exec Delegation: CEO/exec creates account, then remote secretary in Philippines
accesses it repeatedly. Looks like ATO (country mismatch, repeated logins from
abroad) but is a false positive — legitimate delegated access.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType
from core.models import User, UserInteraction

from data.config_utils import get_cfg
from ._common import (
    add_view_then_connect_or_message,
    make_legit_event,
    pick_targets,
)

# Philippines IPs (residential/BPO) — secretary's location
_PH_IPS = [
    "121.58.205.34",
    "112.198.78.91",
    "49.146.122.55",
    "175.158.33.12",
    "110.54.201.89",
]


def _add_login_from_ph(
    events: list,
    user_id: str,
    ts: datetime,
    ip: str,
    user_agent: str,
    counter: int,
    max_ts: datetime | None,
) -> tuple[int, datetime]:
    """Append LOGIN from Philippines. Returns (counter, ts)."""
    counter += 1
    events.append(make_legit_event(
        counter, user_id, InteractionType.LOGIN, ts, ip, IPType.RESIDENTIAL,
        "PH", user_agent,
        metadata={"login_success": True, "delegated_access": True},
        max_ts=max_ts,
    ))
    return counter, ts


def exec_delegation(
    user: User,
    all_user_ids: list[str],
    window_start: datetime,
    now: datetime,
    counter: int,
    rng: random.Random,
    user_agent: str,
    *,
    config: dict | None = None,
) -> tuple[list[UserInteraction], int]:
    """
    CEO/exec creates account (handled by caller). Secretary in Philippines
    logs in repeatedly, does VIEW/CONNECT/MESSAGE. Country mismatch and
    hosting-like patterns mimic ATO but are legitimate delegated access.
    """
    events: list[UserInteraction] = []
    ph_ip = rng.choice(_PH_IPS)

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    # Secretary logs in 2–4 times per week over several weeks
    num_sessions = min(20, max(6, days_available))
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, max(0, days_available - 1)),
            hours=rng.randint(8, 18),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue

        counter, ts = _add_login_from_ph(
            events, user.user_id, ts, ph_ip, user_agent, counter, max_ts=now
        )

        # Secretary does typical exec-assistant work: views, connects, occasional messages
        num_actions = rng.randint(3, 15)
        targets = pick_targets(user.user_id, all_user_ids, num_actions, rng)
        for target in targets:
            counter, ts = add_view_then_connect_or_message(
                events, user.user_id, ts, ph_ip, IPType.RESIDENTIAL, "PH",
                user_agent, target, counter, rng,
                do_connect=True, do_message=(rng.random() < get_cfg(config, "normal_patterns", "exec_delegation", "message_on_connect_pct", default=0.15)),
                max_ts=now,
            )

    return events, counter
