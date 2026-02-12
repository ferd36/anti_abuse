"""Credential Stuffer: same IP hits 3–5 accounts in quick succession."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from data.config_utils import get_cfg
from ._common import (
    SPAM_METADATA,
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)


def credential_stuffer(
    victim_ids: list[str],
    victim_countries: list[str],
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Same attacker IP hits 3-5 accounts in quick succession.
    Each victim: login → download contacts → moderate spam.
    Some accounts closed, some not.
    """
    events: list = []
    ip = pick_hosting_ip(rng)
    ts = base_time

    for idx, (victim_id, victim_country) in enumerate(zip(victim_ids, victim_countries)):
        targets = [uid for uid in all_user_ids if uid != victim_id]
        attacker_country = pick_attacker_country(victim_country, rng)

        ts += timedelta(minutes=rng.randint(2, 15))
        login_evts, counter, ts = make_login_with_failures(
            victim_id, ts, ip, counter, rng, "credential_stuffer",
            extra_metadata={
                "batch_index": idx + 1,
                "batch_size": len(victim_ids),
                "attacker_country": attacker_country,
            },
        )
        events.extend(login_evts)

        ts += timedelta(minutes=rng.randint(2, 8))
        counter += 1
        events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, ip,
                                metadata={"attack_pattern": "credential_stuffer",
                                          "contact_count": rng.randint(30, 300),
                                          "ip_country": attacker_country}))

        num_spam = rng.randint(20, 60)
        rng.shuffle(targets)
        spam_targets = targets[:num_spam]
        spam_window = timedelta(hours=rng.uniform(0.5, 2))
        for i, target in enumerate(spam_targets):
            offset = spam_window * (i / max(num_spam - 1, 1))
            msg_ts = ts + timedelta(minutes=3) + offset
            counter += 1
            meta = dict(rng.choice(SPAM_METADATA))
            meta["ip_country"] = attacker_country
            meta["attack_pattern"] = "credential_stuffer"
            events.append(make_event(counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, ip,
                                    target_user_id=target,
                                    metadata=meta))

        if rng.random() < get_cfg(config, "fraud", "credential_stuffer", "close_account_pct", default=0.5):
            close_ts = events[-1].timestamp + timedelta(minutes=rng.randint(5, 20))
            counter += 1
            events.append(make_event(counter, victim_id, InteractionType.CLOSE_ACCOUNT, close_ts, ip,
                                    metadata={"attack_pattern": "credential_stuffer",
                                              "ip_country": attacker_country}))

        ts = events[-1].timestamp + timedelta(minutes=rng.randint(10, 60))

    return events, counter
