"""Active Job Seeker: Several sessions/week, VIEW × many → CONNECT × 5-15 → MESSAGE × 1-5."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction

from data.config_utils import get_cfg
from ._common import (
    add_login,
    add_view_then_connect_or_message,
    make_legit_event,
    pick_targets,
)


def active_job_seeker(
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
    """High activity spread over days: many views, connects, personalised messages."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = min(6, max(2, days_available))
    did_headline_update = False
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, max(0, days_available - 1)),
            hours=rng.randint(8, 18),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        # ~20% chance to update headline when changing jobs (e.g. landed new role)
        if not did_headline_update and rng.random() < get_cfg(config, "usage_patterns", "active_job_seeker", "headline_update_pct", default=0.20):
            counter += 1
            ts += timedelta(seconds=rng.randint(30, 90))
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.UPDATE_HEADLINE, ts, ip, ip_type,
                country, user_agent, metadata={"reason": "job_change"}, max_ts=now,
            ))
            did_headline_update = True

        num_views = rng.randint(8, 25)
        targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
        for i, target in enumerate(targets):
            do_connect = i < rng.randint(5, 15)
            do_message = do_connect and i < rng.randint(1, 5)
            counter, ts = add_view_then_connect_or_message(
                events, user.user_id, ts, ip, ip_type, country, user_agent,
                target, counter, rng, do_connect=do_connect, do_message=do_message,
                max_ts=now,
            )

    return events, counter
