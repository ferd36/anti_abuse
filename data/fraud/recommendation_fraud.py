"""Recommendation Fraud: bulk GIVE_RECOMMENDATION to inflate credibility."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def recommendation_fraud(
    recommender_ids: list[str],
    target_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Recommenders log in from cluster IPs and give recommendations to targets.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    cluster_max = get_cfg(cfg, "fraud", "recommendation_fraud", "cluster_ips_max", default=4)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(recommender_ids) + 1, cluster_max))]
    ts = base_time

    for idx, rid in enumerate(recommender_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            rid, ts, ip, counter, rng, "recommendation_fraud",
            extra_metadata={"ip_country": country, "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(1, 5))

    for tid in target_user_ids:
        country = rng.choice(countries)
        rid = rng.choice(recommender_ids)
        ip = cluster_ips[recommender_ids.index(rid) % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(2, 15))
        counter += 1
        events.append(make_event(
            counter, rid, InteractionType.GIVE_RECOMMENDATION, ts, ip,
            target_user_id=tid,
            metadata={
                "attack_pattern": "recommendation_fraud",
                "recommendation_text": "Highly recommend! Great professional.",
                "ip_country": country,
            },
        ))

    return events, counter
