"""Recruiter: Frequent sessions, SEARCH_CANDIDATES → VIEW × many → CONNECT × many."""

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

_SEARCH_QUERIES = [
    {"role": "software_engineer", "location": "remote"},
    {"role": "senior_developer", "skills": "python"},
    {"role": "product_manager", "industry": "tech"},
    {"role": "data_scientist", "experience_years": "3+"},
    {"role": "frontend_developer", "skills": "react"},
    {"role": "devops", "skills": "kubernetes"},
]


def recruiter(
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
    """Steady volume: candidate search → profile views → connection requests per session."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    days_available = (now - max(window_start, user.join_date)).days
    if days_available < 1:
        return events, counter

    num_sessions = min(10, max(3, days_available * 2 // 3))
    for _ in range(num_sessions):
        ts = max(window_start, user.join_date) + timedelta(
            days=rng.randint(0, max(0, days_available - 1)),
            hours=rng.randint(9, 11),
            minutes=rng.randint(0, 59),
        )
        if ts >= now:
            continue
        counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

        # Candidate search first (recruiter-specific)
        num_searches = rng.randint(1, 4)
        for _ in range(num_searches):
            counter += 1
            ts += timedelta(seconds=rng.randint(15, 90))
            meta = dict(rng.choice(_SEARCH_QUERIES))
            meta["results_count"] = rng.randint(20, 200)
            events.append(make_legit_event(
                counter, user.user_id, InteractionType.SEARCH_CANDIDATES, ts, ip, ip_type,
                country, user_agent, metadata=meta, max_ts=now,
            ))

        num_pairs = rng.randint(15, 40)
        targets = pick_targets(user.user_id, all_user_ids, num_pairs, rng)
        for target in targets:
            counter, ts = add_view_then_connect_or_message(
                events, user.user_id, ts, ip, ip_type, country, user_agent,
                target, counter, rng, do_connect=True, do_message=(rng.random() < get_cfg(config, "usage_patterns", "recruiter", "message_on_connect_pct", default=0.2)),
                max_ts=now,
            )

    return events, counter
