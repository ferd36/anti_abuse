"""Content Consumer: Many views, few messages or connections."""

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


def content_consumer(
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
    """Read-heavy: LOGIN → VIEW × many, rarely CONNECT or MESSAGE."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = rng.randint(2, 8)
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, max(0, days_available - 1)),
            hours=rng.randint(8, 22),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        num_views = rng.randint(8, 25)
        targets = pick_targets(user.user_id, all_user_ids, num_views, rng)
        for i, target in enumerate(targets):
            counter += 1
            ts += timedelta(seconds=rng.randint(15, 90))
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.VIEW_USER_PAGE, ts, ip, ip_type,
                country, user_agent, target_user_id=target, max_ts=now,
            ))
            if rng.random() < get_cfg(config, "normal_patterns", "content_consumer", "connect_after_view_pct", default=0.05):
                counter += 1
                ts += timedelta(seconds=rng.randint(10, 60))
                events.append(make_legit_event(
                    counter, user.user_id, InteractionType.CONNECT_WITH_USER, ts, ip, ip_type,
                    country, user_agent, target_user_id=target, max_ts=now,
                ))
            elif rng.random() < get_cfg(config, "normal_patterns", "content_consumer", "message_after_view_pct", default=0.15):
                counter += 1
                ts += timedelta(seconds=rng.randint(5, 45))
                itype = rng.choice([InteractionType.LIKE, InteractionType.REACT])
                meta = {} if itype == InteractionType.LIKE else {"reaction_type": rng.choice(["like", "celebrate", "support", "love"])}
                events.append(make_legit_event(
                    counter, user.user_id, itype, ts, ip, ip_type,
                    country, user_agent, target_user_id=target, metadata=meta, max_ts=now,
                ))
    return events, counter
