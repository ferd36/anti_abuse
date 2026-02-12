"""Sleeper Agent: compromised early, kept alive with periodic logins, activated later.

The attacker compromises the account and changes the password weeks
before using it.  During the dormancy period, they log in every few
days — just enough to keep the session valid — with no other activity.
When the sleeper is finally activated, it executes a spam campaign.

Key signals:
  - Password change from a foreign hosting IP.
  - A long series of login-only sessions (no other activity) at
    suspiciously regular intervals.
  - Sudden transition from dormant to active (download + spam).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from ._common import (
    SPAM_METADATA,
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def sleeper_agent(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
) -> tuple[list, int]:
    """
    Phase 1 — Compromise: login + change password.
    Phase 2 — Dormancy: periodic login-only check-ins over 2-4 weeks.
    Phase 3 — Activation: login → download address book → spam campaign.

    Args:
        victim_id:       The compromised account.
        victim_country:  Home country of the victim.
        all_user_ids:    Full user population (spam targets).
        base_time:       Time of the initial compromise.
        counter:         Global event counter.
        rng:             Seeded random generator.

    Returns:
        (events, counter)
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ts = base_time

    # =================================================================
    # Phase 1 — Compromise: login + change password
    # =================================================================
    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "sleeper_agent",
        extra_metadata={"attacker_country": attacker_country},
    )
    events.extend(login_evts)

    ts += timedelta(minutes=rng.randint(2, 15))
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.CHANGE_PASSWORD, ts, ip,
        metadata={
            "attack_pattern": "sleeper_agent",
            "ip_country": attacker_country,
        },
    ))

    # =================================================================
    # Phase 2 — Dormancy: login-only check-ins every 2-5 days
    # =================================================================
    dormancy_weeks = rng.randint(2, 4)
    num_checkins = rng.randint(6, 12)
    dormancy_span = timedelta(weeks=dormancy_weeks)

    # Space check-ins roughly evenly across the dormancy window with jitter
    base_interval_hours = (dormancy_span.total_seconds() / 3600) / num_checkins

    for i in range(num_checkins):
        jitter_hours = rng.uniform(-base_interval_hours * 0.2, base_interval_hours * 0.2)
        checkin_ts = ts + timedelta(hours=base_interval_hours * (i + 1) + jitter_hours)
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.LOGIN, checkin_ts, ip,
            metadata={
                "attack_pattern": "sleeper_agent",
                "attacker_country": attacker_country,
                "ip_country": attacker_country,
                "login_success": True,
                "checkin_sequence": i + 1,
            },
        ))

    # =================================================================
    # Phase 3 — Activation: login → download → spam
    # =================================================================
    ts += dormancy_span + timedelta(hours=rng.randint(1, 12))

    # Activation login (may switch to a different hosting IP)
    activation_ip = pick_hosting_ip(rng)
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.LOGIN, ts, activation_ip,
        metadata={
            "attack_pattern": "sleeper_agent",
            "attacker_country": attacker_country,
            "ip_country": attacker_country,
            "login_success": True,
            "activation": True,
        },
    ))

    # Download address book
    ts += timedelta(minutes=rng.randint(3, 15))
    counter += 1
    events.append(make_event(
        counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, activation_ip,
        metadata={
            "attack_pattern": "sleeper_agent",
            "contact_count": rng.randint(50, 400),
            "ip_country": attacker_country,
        },
    ))

    # Spam campaign — moderate volume
    targets = [uid for uid in all_user_ids if uid != victim_id]
    rng.shuffle(targets)
    num_spam = rng.randint(30, 80)
    spam_targets = targets[:num_spam]
    spam_window = timedelta(hours=rng.uniform(1, 4))

    for i, target in enumerate(spam_targets):
        offset = spam_window * (i / max(num_spam - 1, 1))
        msg_ts = ts + timedelta(minutes=5) + offset
        counter += 1
        meta = dict(rng.choice(SPAM_METADATA))
        meta["ip_country"] = attacker_country
        meta["attack_pattern"] = "sleeper_agent"
        events.append(make_event(
            counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, activation_ip,
            target_user_id=target,
            metadata=meta,
        ))

    return events, counter
