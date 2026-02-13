"""Coordinated Like Inflation: clusters of fake accounts artificially boost likes on a post."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def coordinated_like_inflation(
    liker_ids: list[str],
    target_user_id: str,
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Multiple fake accounts from a hosting IP cluster log in, then all send
    LIKE to the same target user (post author). Coordinated artificial boosting.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    cluster_max = get_cfg(cfg, "fraud", "coordinated_like_inflation", "cluster_ips_max", default=4)
    like_min = get_cfg(cfg, "fraud", "coordinated_like_inflation", "like_window_min_minutes", default=2)
    like_max = get_cfg(cfg, "fraud", "coordinated_like_inflation", "like_window_max_minutes", default=15)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(liker_ids) + 1, cluster_max))]
    ts = base_time

    # Each liker logs in from cluster IP
    for idx, lid in enumerate(liker_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 15))
        login_evts, counter, ts = make_login_with_failures(
            lid, ts, ip, counter, rng, "coordinated_like_inflation",
            extra_metadata={"ip_country": country, "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(2, 10))

    # All likers send LIKE to the same target (coordinated, tight time window)
    like_window = timedelta(minutes=rng.randint(like_min, like_max))
    for idx, lid in enumerate(liker_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        offset = like_window * (idx / max(len(liker_ids) - 1, 1))
        like_ts = ts + offset
        counter += 1
        events.append(make_event(
            counter, lid, InteractionType.LIKE, like_ts, ip,
            target_user_id=target_user_id,
            metadata={
                "attack_pattern": "coordinated_like_inflation",
                "ip_country": country,
                "ip_cluster": True,
                "post_author": target_user_id,
            },
        ))

    return events, counter
