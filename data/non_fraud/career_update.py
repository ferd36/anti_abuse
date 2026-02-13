"""Career Update: User logs in primarily to update profile (job change, marriage).

Lightweight pattern: 1-2 sessions of LOGIN → UPDATE_HEADLINE / UPDATE_SUMMARY /
CHANGE_LAST_NAME. No browsing or messaging. Typical when user changes jobs
or gets married and updates their name.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction

from ._common import (
    add_login,
    make_legit_event,
)
from data.config_utils import get_cfg


def career_update(
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
    """LOGIN → UPDATE_HEADLINE or UPDATE_SUMMARY or CHANGE_LAST_NAME. 1-2 sessions."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 14:
        return events, counter

    num_sessions = rng.randint(1, 2)
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(14, max(14, days_available - 1)),
            hours=rng.randint(8, 20),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        # Primary update: job change (headline), profile refresh (summary), or marriage (name)
        t1 = get_cfg(config, "normal_patterns", "career_update", "update_type_headline", default=0.55)
        t2 = get_cfg(config, "normal_patterns", "career_update", "update_type_summary", default=0.85)
        roll = rng.random()
        if roll < t1:
            itype = InteractionType.UPDATE_HEADLINE
            meta = {"reason": "job_change"}
        elif roll < t2:
            itype = InteractionType.UPDATE_SUMMARY
            meta = {"reason": "profile_refresh"}
        else:
            itype = InteractionType.CHANGE_LAST_NAME
            meta = {"reason": "marriage"}

        counter += 1
        ts += timedelta(seconds=rng.randint(30, 120))
        events.append(make_legit_event(
            counter, user.user_id, itype, ts, ip, ip_type,
            country, user_agent, metadata=meta, max_ts=now,
        ))

        second_pct = get_cfg(config, "normal_patterns", "career_update", "second_update_in_session_pct", default=0.30)
        if rng.random() < second_pct:
            counter += 1
            ts += timedelta(seconds=rng.randint(20, 60))
            other = rng.choice([InteractionType.UPDATE_HEADLINE, InteractionType.UPDATE_SUMMARY])
            events.append(make_legit_event(
                counter, user.user_id, other, ts, ip, ip_type,
                country, user_agent, metadata={"reason": "profile_refresh"}, max_ts=now,
            ))

    return events, counter
