"""New User Onboarding: High activity in first 1-3 days, UPLOAD_ADDRESS_BOOK optional."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction

from ._common import (
    add_login,
    add_view_then_connect_or_message,
    make_legit_event,
    pick_target,
    pick_targets,
)
from data.config_utils import get_cfg


def new_user_onboarding(
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
    """Concentrated activity: profile updates, maybe UPLOAD_ADDRESS_BOOK, CONNECT × several."""
    events: list[UserInteraction] = []
    ip, ip_type = user.ip_address, user.ip_type
    country = user.country

    join_date = max(window_start, user.join_date)
    ts = join_date + timedelta(seconds=rng.randint(60, 600))

    counter, ts = add_login(events, user.user_id, ts, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)

    if rng.random() < get_cfg(config, "usage_patterns", "new_user_onboarding", "profile_update_pct", default=0.5):
        counter += 1
        ts += timedelta(seconds=rng.randint(30, 120))
        # New users set up headline (job title) or summary
        itype = rng.choice([InteractionType.UPDATE_HEADLINE, InteractionType.UPDATE_SUMMARY])
        events.append(make_legit_event(
            counter, user.user_id, itype, ts, ip, ip_type,
            country, user_agent, max_ts=now,
        ))
    if rng.random() < get_cfg(config, "usage_patterns", "new_user_onboarding", "upload_address_book_pct", default=0.4):
        counter += 1
        ts += timedelta(seconds=rng.randint(60, 180))
        events.append(make_legit_event(
            counter, user.user_id, InteractionType.UPLOAD_ADDRESS_BOOK, ts, ip, ip_type,
            country, user_agent,
            metadata={"contact_count": rng.randint(50, 400)},
            max_ts=now,
        ))
    num_connects = rng.randint(3, 12)
    targets = pick_targets(user.user_id, all_user_ids, num_connects, rng)
    for target in targets:
        counter, ts = add_view_then_connect_or_message(
            events, user.user_id, ts, ip, ip_type, country, user_agent,
            target, counter, rng, do_connect=True, do_message=(rng.random() < get_cfg(config, "usage_patterns", "new_user_onboarding", "message_on_connect_pct", default=0.2)),
            max_ts=now,
        )

    if (now - join_date).days >= 1:
        ts2 = join_date + timedelta(days=1, hours=rng.randint(8, 20))
        if ts2 < now:
            counter, ts2 = add_login(events, user.user_id, ts2, ip, ip_type, country, user_agent, counter, rng, max_ts=now, config=config)
            for _ in range(rng.randint(2, 6)):
                t = pick_target(user.user_id, all_user_ids, rng=rng)
                if t:
                    counter, ts2 = add_view_then_connect_or_message(
                        events, user.user_id, ts2, ip, ip_type, country, user_agent,
                        t, counter, rng, do_connect=True, do_message=False,
                        max_ts=now,
                    )

    return events, counter
