"""Endorsement Inflation: bulk ENDORSE_SKILL to inflate credibility."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def endorsement_inflation(
    endorser_ids: list[str],
    target_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Endorsers log in from cluster IPs and endorse targets' skills in bulk.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    cluster_max = get_cfg(cfg, "fraud", "endorsement_inflation", "cluster_ips_max", default=4)
    endorsements_min = get_cfg(cfg, "fraud", "endorsement_inflation", "endorsements_per_skill_min", default=5)
    endorsements_max = get_cfg(cfg, "fraud", "endorsement_inflation", "endorsements_per_skill_max", default=20)
    events: list = []
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(endorser_ids) + 1, cluster_max))]
    ts = base_time

    for idx, eid in enumerate(endorser_ids):
        country = rng.choice(countries)
        ip = cluster_ips[idx % len(cluster_ips)]
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            eid, ts, ip, counter, rng, "endorsement_inflation",
            extra_metadata={"ip_country": country, "ip_cluster": True},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(1, 5))

    skills = ["python", "leadership", "data_analysis", "project_management"]
    for tid in target_user_ids:
        for skill in skills:
            n = rng.randint(endorsements_min, endorsements_max)
            for _ in range(min(n, len(endorser_ids))):
                eid = rng.choice(endorser_ids)
                ip = cluster_ips[endorser_ids.index(eid) % len(cluster_ips)]
                ts += timedelta(seconds=rng.randint(10, 60))
                counter += 1
                events.append(make_event(
                    counter, eid, InteractionType.ENDORSE_SKILL, ts, ip,
                    target_user_id=tid,
                    metadata={"attack_pattern": "endorsement_inflation", "skill_id": skill, "ip_country": rng.choice(countries)},
                ))

    return events, counter
