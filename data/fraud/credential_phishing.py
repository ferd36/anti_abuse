"""Credential Phishing: victim submits credentials to fake page, PHISHING_LOGIN."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import make_event, pick_attacker_country, pick_hosting_ip


def credential_phishing(
    victim_id: str,
    victim_country: str,
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Victim submits credentials to phishing site (PHISHING_LOGIN).
    Optionally attacker then logs in with stolen creds (capture_then_login_pct).
    """
    cfg = config or {}
    capture_then_login = get_cfg(cfg, "fraud", "credential_phishing", "capture_then_login_pct", default=0.8)
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.PHISHING_LOGIN, ts, ip,
        metadata={"attack_pattern": "credential_phishing", "ip_country": attacker_country, "phishing_site": "fake-login.net"},
    ))

    if rng.random() < capture_then_login:
        ts += timedelta(hours=rng.randint(1, 48))
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.LOGIN, ts, ip,
            metadata={"attack_pattern": "credential_phishing", "ip_country": attacker_country, "login_success": True},
        ))

    return events, counter
