"""Returning User: Long gap, then 1-2 sessions with low activity."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction

from data.config_utils import get_cfg
from ._common import (
    add_login,
    make_legit_event,
    pick_targets,
)


def returning_user(
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
    """Long gap since last activity, then LOGIN → VIEW × few → maybe CHANGE_PROFILE."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 7:
        return events, counter

    ts = now - timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 23))
    if ts < max(window_start, user.join_date):
        return events, counter

    counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

    num_views = rng.randint(1, 5)
    targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
    for target in targets:
        counter += 1
        ts += timedelta(seconds=rng.randint(20, 180))
        events.append(make_legit_event(
            counter, user.user_id, InteractionType.VIEW_USER_PAGE, ts, ip, ip_type,
            country, user_agent, target_user_id=target, max_ts=now,
        ))
    if rng.random() < get_cfg(config, "normal_patterns", "returning_user", "second_session_pct", default=0.4):
        counter += 1
        ts += timedelta(seconds=rng.randint(30, 120))
        # Life events: job change, profile refresh, or marital name change
        choice = rng.choice(["headline", "summary", "last_name"])
        if choice == "headline":
            itype = InteractionType.UPDATE_HEADLINE
            meta = {"reason": "job_change"}
        elif choice == "summary":
            itype = InteractionType.UPDATE_SUMMARY
            meta = {"reason": "profile_refresh"}
        else:
            itype = InteractionType.CHANGE_LAST_NAME
            meta = {"reason": "marriage"}
        events.append(make_legit_event(
            counter, user.user_id, itype, ts, ip, ip_type,
            country, user_agent, metadata=meta, max_ts=now,
        ))
    return events, counter
