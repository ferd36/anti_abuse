"""Invitation Spam: mass SEND_CONNECTION_REQUEST to harvest graph."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def invitation_spam(
    spammer_ids: list[str],
    target_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Spammers log in from cluster IPs and send mass connection requests.
    """
    cfg = config or {}
    cluster_max = get_cfg(cfg, "fraud", "invitation_spam", "cluster_ips_max", default=4)
    req_min = get_cfg(cfg, "fraud", "invitation_spam", "requests_per_account_min", default=50)
    req_max = get_cfg(cfg, "fraud", "invitation_spam", "requests_per_account_max", default=200)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(spammer_ids) + 1, cluster_max))]
    ts = base_time

    for idx, sid in enumerate(spammer_ids):
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            sid, ts, ip, counter, rng, "invitation_spam",
            extra_metadata={"ip_country": "RU", "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(1, 5))

        n_reqs = rng.randint(req_min, req_max)
        targets = rng.sample(target_user_ids, min(n_reqs, len(target_user_ids)))
        for tid in targets:
            ts += timedelta(seconds=rng.randint(5, 45))
            counter += 1
            events.append(make_event(
                counter, sid, InteractionType.SEND_CONNECTION_REQUEST, ts, ip,
                target_user_id=tid,
                metadata={"attack_pattern": "invitation_spam", "ip_country": "RU", "ip_cluster": True},
            ))

    return events, counter
