"""Casual Browser: 1-2 sessions/week, LOGIN → VIEW × 2-5, maybe MESSAGE × 0-1."""

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


def casual_browser(
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
    """1-2 logins/week, 2-10 profile views per session, occasional message."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = max(1, min(2, days_available // 4))
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, days_available - 1) if days_available > 1 else 0,
            hours=rng.randint(8, 20),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        num_views = rng.randint(2, 5)
        targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
        for target in targets:
            counter += 1
            ts += timedelta(seconds=rng.randint(15, 120))
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.VIEW_USER_PAGE, ts, ip, ip_type,
                country, user_agent, target_user_id=target, max_ts=now,
            ))
        if targets and rng.random() < get_cfg(config, "normal_patterns", "casual_browser", "message_after_view_pct", default=0.3):
            target = targets[0]
            counter += 1
            ts += timedelta(seconds=rng.randint(30, 120))
            _casual_messages = [
                "Hey, saw your update—looks great!",
                "Nice profile! Thought I'd say hi.",
                "Thanks for the connect. Let's chat sometime.",
            ]
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.MESSAGE_USER, ts, ip, ip_type,
                country, user_agent, target_user_id=target,
                metadata={
                    "message_length": rng.randint(30, 150),
                    "is_spam": False,
                    "message_text": rng.choice(_casual_messages),
                },
                max_ts=now,
            ))
        elif targets and rng.random() < get_cfg(config, "normal_patterns", "casual_browser", "like_react_after_view_pct", default=0.4):
            target = rng.choice(targets)
            counter += 1
            ts += timedelta(seconds=rng.randint(10, 60))
            itype = rng.choice([InteractionType.LIKE, InteractionType.REACT])
            meta = {} if itype == InteractionType.LIKE else {"reaction_type": rng.choice(["like", "celebrate", "support"])}
            events.append(make_legit_event(
                counter, user.user_id, itype, ts, ip, ip_type,
                country, user_agent, target_user_id=target, metadata=meta, max_ts=now,
            ))

    return events, counter
