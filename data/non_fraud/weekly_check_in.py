"""Weekly Check-in: ~1 session/week, LOGIN → VIEW × 1-5."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction

from ._common import (
    add_login,
    make_legit_event,
    pick_targets,
)


def weekly_check_in(
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
    """Minimal sessions: ~1 login/week, 1-5 profile views."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = max(1, days_available // 7)
    for i in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=i * 7 + rng.randint(0, 2),
            hours=rng.randint(9, 18),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        num_views = rng.randint(1, 5)
        targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
        for target in targets:
            counter += 1
            ts += timedelta(seconds=rng.randint(20, 120))
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.VIEW_USER_PAGE, ts, ip, ip_type,
                country, user_agent, target_user_id=target, max_ts=now,
            ))
    return events, counter
