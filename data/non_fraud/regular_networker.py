"""Regular Networker: 2-3 sessions/week, VIEW × several → CONNECT × 1-3 → MESSAGE × 0-2."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.models import User, UserInteraction

from ._common import (
    add_login,
    add_view_then_connect_or_message,
    pick_targets,
)


def regular_networker(
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
    """Moderate sessions: mix of views, connects, messages."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = min(6, max(2, days_available))
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, max(0, days_available - 1)),
            hours=rng.randint(8, 21),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        num_views = rng.randint(3, 10)
        targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
        for i, target in enumerate(targets):
            do_connect = i < rng.randint(1, 3)
            do_message = do_connect and i < rng.randint(0, 2)
            counter, ts = add_view_then_connect_or_message(
                events, user.user_id, ts, ip, ip_type, country, user_agent,
                target, counter, rng, do_connect=do_connect, do_message=do_message,
                max_ts=now,
            )

    return events, counter
