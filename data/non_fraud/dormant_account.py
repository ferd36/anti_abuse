"""Dormant Account: Created account but never actively used it.

User signed up, maybe logged in once to verify, then never returned.
No profile views, connections, or messages.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.models import User, UserInteraction

from ._common import add_login
from data.config_utils import get_cfg


def dormant_account(
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
    """Account creation only, or creation + 1 login shortly after. No other activity."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    join_date = max(window_start, user.join_date)
    days_available = (now - join_date).days
    if days_available < 1:
        return events, counter

    login_once_pct = get_cfg(config, "normal_patterns", "dormant_account", "login_once_pct", default=0.70)
    if rng.random() < login_once_pct:
        ts = join_date + timedelta(
            hours=rng.randint(1, 48),
            minutes=rng.randint(0, 59),
        )
        if ts < now:
            counter, _ = add_login(
                events, user.user_id, ts, ip, ip_type, country, user_agent,
                counter, rng, max_ts=now, config=config,
            )

    return events, counter
