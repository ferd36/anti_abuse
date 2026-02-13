"""Ad Engagement Fraud: bot accounts generate AD_VIEW and AD_CLICK."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def ad_engagement_fraud(
    bot_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Bot accounts log in and generate fake AD_VIEW and AD_CLICK events.
    Uses fishy accounts (e.g. fake_account) as bots.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    cluster_max = get_cfg(cfg, "fraud", "ad_engagement_fraud", "cluster_ips_max", default=4)
    clicks_min = get_cfg(cfg, "fraud", "ad_engagement_fraud", "clicks_per_ad_min", default=10)
    clicks_max = get_cfg(cfg, "fraud", "ad_engagement_fraud", "clicks_per_ad_max", default=500)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(bot_ids) + 1, cluster_max))]
    ts = base_time

    for idx, bid in enumerate(bot_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 5))
        login_evts, counter, ts = make_login_with_failures(
            bid, ts, ip, counter, rng, "ad_engagement_fraud",
            extra_metadata={"ip_country": country, "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(1, 3))

    ad_id = f"ad-{rng.randint(1000, 9999)}"
    n_clicks = rng.randint(clicks_min, clicks_max)
    for _ in range(n_clicks):
        country = rng.choice(countries)
        bid = rng.choice(bot_ids)
        ip = cluster_ips[bot_ids.index(bid) % len(cluster_ips)]
        ts += timedelta(seconds=rng.randint(2, 30))
        counter += 1
        events.append(make_event(
            counter, bid, InteractionType.AD_VIEW, ts, ip,
            metadata={"attack_pattern": "ad_engagement_fraud", "ad_id": ad_id, "ip_country": country},
        ))
        ts += timedelta(seconds=rng.randint(1, 10))
        counter += 1
        events.append(make_event(
            counter, bid, InteractionType.AD_CLICK, ts, ip,
            metadata={"attack_pattern": "ad_engagement_fraud", "ad_id": ad_id, "ip_country": country},
        ))

    return events, counter
