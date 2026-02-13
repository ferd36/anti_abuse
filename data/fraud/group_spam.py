"""Group Spam: JOIN_GROUP then POST_IN_GROUP for spam content."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def group_spam(
    spammer_ids: list[str],
    groups_joined_by_user: dict[str, tuple[str, ...]],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Spammers log in, JOIN_GROUP (if not already), then POST_IN_GROUP.
    Uses groups_joined from profile to know which groups each user can post in.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    posts_min = get_cfg(cfg, "fraud", "group_spam", "posts_per_group_min", default=3)
    posts_max = get_cfg(cfg, "fraud", "group_spam", "posts_per_group_max", default=15)
    events: list = []
    ts = base_time

    for sid in spammer_ids:
        country = rng.choice(countries)
        ip = pick_hosting_ip(rng)
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            sid, ts, ip, counter, rng, "group_spam",
            extra_metadata={"ip_country": country},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(2, 8))

        groups = groups_joined_by_user.get(sid, ())
        if not groups:
            continue
        for gid in groups:
            country = rng.choice(countries)
            ts += timedelta(minutes=rng.randint(1, 5))
            counter += 1
            events.append(make_event(
                counter, sid, InteractionType.JOIN_GROUP, ts, ip,
                metadata={"attack_pattern": "group_spam", "group_id": gid, "ip_country": country},
            ))
            n_posts = rng.randint(posts_min, posts_max)
            for _ in range(n_posts):
                ts += timedelta(minutes=rng.randint(5, 60))
                counter += 1
                events.append(make_event(
                    counter, sid, InteractionType.POST_IN_GROUP, ts, ip,
                    metadata={"attack_pattern": "group_spam", "group_id": gid, "ip_country": rng.choice(countries), "post_content": "Check this out!"},
                ))

    return events, counter
