"""Profile Defacement: attacker logs in and defaces the victim's profile/name.

The attacker compromises the account and changes the victim's visible identity:
  - Display name (CHANGE_NAME)
  - Headline and/or summary (CHANGE_PROFILE)
  - Optionally password (CHANGE_PASSWORD) to lock out the victim

Typical use: scam pages, brand impersonation, or revenge. The account is left
open so the defaced profile is visible to the victim's connections.

Key signals:
  - Login from hosting IP in a different country.
  - Burst of CHANGE_PROFILE and CHANGE_NAME shortly after login.
  - No messaging or minimal activity — the abuse is the profile itself.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import (
    ALT_USER_AGENTS,
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def profile_defacement(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Login → deface profile (name, headline, summary) → optionally change password.
    Account left open. No spam or other abuse.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ua = rng.choice(ALT_USER_AGENTS)
    ts = base_time

    # --- Phase 1: login ---
    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "profile_defacement",
        extra_metadata={
            "attacker_country": attacker_country,
            "user_agent": ua,
        },
    )
    events.extend(login_evts)

    meta_base = {
        "attack_pattern": "profile_defacement",
        "ip_country": attacker_country,
        "user_agent": ua,
    }

    # --- Phase 2: deface profile (name, headline, summary) ---
    ts += timedelta(minutes=rng.randint(2, 15))

    # Always change name (primary defacement)
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.CHANGE_NAME, ts, ip,
        metadata={**meta_base, "defacement_type": "display_name"},
        ip_type=IPType.HOSTING,
    ))
    ts += timedelta(minutes=rng.randint(1, 5))

    # Usually change profile (headline/summary)
    if rng.random() < get_cfg(config, "fraud", "profile_defacement", "change_profile_pct", default=0.85):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_PROFILE, ts, ip,
            metadata={**meta_base, "defacement_type": "headline_summary"},
            ip_type=IPType.HOSTING,
        ))
        ts += timedelta(minutes=rng.randint(1, 5))

    # ~40% lock out the victim by changing password
    if rng.random() < get_cfg(config, "fraud", "profile_defacement", "change_password_pct", default=0.40):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_PASSWORD, ts, ip,
            metadata=meta_base,
            ip_type=IPType.HOSTING,
        ))

    return events, counter
