"""Job Posting Scam: create fake jobs, harvest applications via APPLY_TO_JOB."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import make_event, make_login_with_failures, pick_hosting_ip


def job_posting_scam(
    scammer_ids: list[str],
    victim_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Scammers create job postings, victims VIEW_JOB and APPLY_TO_JOB.
    Some applications redirect to phishing URLs.
    """
    cfg = config or {}
    countries = get_cfg(cfg, "fraud", "default_attacker_countries", default=["RU", "CN", "NG", "UA", "RO"])
    app_min = get_cfg(cfg, "fraud", "job_posting_scam", "applications_per_job_min", default=10)
    app_max = get_cfg(cfg, "fraud", "job_posting_scam", "applications_per_job_max", default=100)
    phishing_pct = get_cfg(cfg, "fraud", "job_posting_scam", "phishing_redirect_pct", default=0.4)
    events: list = []
    ts = base_time

    for sid in scammer_ids:
        country = rng.choice(countries)
        ip = pick_hosting_ip(rng)
        ts += timedelta(minutes=rng.randint(1, 10))
        login_evts, counter, ts = make_login_with_failures(
            sid, ts, ip, counter, rng, "job_posting_scam",
            extra_metadata={"ip_country": country},
        )
        events.extend(login_evts)
        ts += timedelta(minutes=rng.randint(2, 8))

        job_id = f"job-{counter:06d}"
        counter += 1
        events.append(make_event(
            counter, sid, InteractionType.CREATE_JOB_POSTING, ts, ip,
            metadata={"attack_pattern": "job_posting_scam", "job_id": job_id, "job_title": "Senior Engineer", "ip_country": country},
        ))
        ts += timedelta(minutes=rng.randint(5, 30))

        n_apps = rng.randint(app_min, app_max)
        applicants = rng.sample(victim_user_ids, min(n_apps, len(victim_user_ids)))
        for vid in applicants:
            country = rng.choice(countries)
            ip = pick_hosting_ip(rng)
            ts += timedelta(minutes=rng.randint(1, 10))
            counter += 1
            events.append(make_event(
                counter, vid, InteractionType.LOGIN, ts, ip,
                metadata={"attack_pattern": "job_posting_scam", "ip_country": country, "login_success": True},
            ))
            ts += timedelta(minutes=rng.randint(1, 5))
            counter += 1
            meta = {"attack_pattern": "job_posting_scam", "job_id": job_id, "ip_country": country}
            if rng.random() < phishing_pct:
                meta["phishing_url"] = "https://fake-careers.com/apply"
            events.append(make_event(
                counter, vid, InteractionType.VIEW_JOB, ts, ip,
                metadata=meta,
            ))
            ts += timedelta(minutes=rng.randint(1, 5))
            counter += 1
            events.append(make_event(
                counter, vid, InteractionType.APPLY_TO_JOB, ts, ip,
                metadata=meta,
            ))

    return events, counter
