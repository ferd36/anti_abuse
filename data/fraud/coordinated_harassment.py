"""Coordinated Harassment: clusters of fake accounts target same users with harassing messages."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import (
    HARASSMENT_METADATA,
    make_event,
    make_login_with_failures,
    pick_hosting_ip,
)


def coordinated_harassment(
    harasser_ids: list[str],
    target_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Multiple fake accounts from a hosting IP cluster log in, then all send
    harassing messages to the same target users. Coordinated attack.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    cluster_max = get_cfg(cfg, "fraud", "coordinated_harassment", "cluster_ips_max", default=4)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(harasser_ids) + 1, cluster_max))]
    ts = base_time

    # Each harasser logs in from cluster IP
    for idx, hid in enumerate(harasser_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 15))
        login_evts, counter, ts = make_login_with_failures(
            hid, ts, ip, counter, rng, "coordinated_harassment",
            extra_metadata={"ip_country": country, "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(2, 10))

    # All harassers send messages to the same targets (coordinated)
    for target in target_user_ids:
        for idx, hid in enumerate(harasser_ids):
            country = rng.choice(countries)
            ip = cluster_ips[idx % len(cluster_ips)]
            ts += timedelta(minutes=rng.randint(1, 5))
            counter += 1
            meta = dict(rng.choice(HARASSMENT_METADATA))
            meta["attack_pattern"] = "coordinated_harassment"
            meta["ip_country"] = country
            meta["ip_cluster"] = True
            meta["target_user_id"] = target
            events.append(make_event(
                counter, hid, InteractionType.MESSAGE_USER, ts, ip,
                target_user_id=target,
                metadata=meta,
            ))
        ts += timedelta(minutes=rng.randint(1, 3))

    return events, counter
