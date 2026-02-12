"""Country Hopper: logins from 3–4 countries over a week, then download and spam."""

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


def country_hopper(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    close_account: bool = False,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Attacker logs in from 3-4 different countries over a week, then
    downloads address book and spams from yet another country.
    """
    events: list = []
    targets = [uid for uid in all_user_ids if uid != victim_id]
    ts = base_time

    num_countries = rng.randint(3, 4)
    ips = [pick_hosting_ip(rng) for _ in range(num_countries + 1)]

    for i in range(num_countries):
        login_ts = ts + timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 23))
        hop_country = pick_attacker_country(victim_country, rng)
        login_evts, counter, login_ts = make_login_with_failures(
            victim_id, login_ts, ips[i], counter, rng, "country_hopper",
            extra_metadata={"hop_sequence": i + 1, "attacker_country": hop_country},
        )
        events.extend(login_evts)

        if rng.random() < get_cfg(config, "fraud", "country_hopper", "view_during_hop_pct", default=0.6):
            view_ts = login_ts + timedelta(minutes=rng.randint(5, 120))
            counter += 1
            events.append(make_event(counter, victim_id, InteractionType.VIEW_USER_PAGE, view_ts, ips[i],
                                    target_user_id=rng.choice(targets),
                                    metadata={"attack_pattern": "country_hopper",
                                              "ip_country": hop_country}))

    attack_ip = ips[-1]
    final_country = pick_attacker_country(victim_country, rng)
    ts += timedelta(days=7, hours=rng.randint(0, 12))
    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, attack_ip, counter, rng, "country_hopper",
        extra_metadata={"attacker_country": final_country},
    )
    events.extend(login_evts)

    ts += timedelta(minutes=rng.randint(3, 15))
    counter += 1
    events.append(make_event(counter, victim_id, InteractionType.DOWNLOAD_ADDRESS_BOOK, ts, attack_ip,
                            metadata={"attack_pattern": "country_hopper",
                                      "contact_count": rng.randint(50, 400),
                                      "ip_country": final_country}))

    num_spam = rng.randint(40, 100)
    rng.shuffle(targets)
    spam_targets = targets[:num_spam]
    spam_window = timedelta(hours=rng.uniform(2, 6))
    for i, target in enumerate(spam_targets):
        offset = spam_window * (i / max(num_spam - 1, 1))
        msg_ts = ts + timedelta(minutes=5) + offset
        counter += 1
        meta = dict(rng.choice(SPAM_METADATA))
        meta["ip_country"] = final_country
        meta["attack_pattern"] = "country_hopper"
        events.append(make_event(counter, victim_id, InteractionType.MESSAGE_USER, msg_ts, attack_ip,
                                target_user_id=target,
                                metadata=meta))

    if close_account:
        ts = events[-1].timestamp + timedelta(minutes=rng.randint(5, 30))
        counter += 1
        events.append(make_event(counter, victim_id, InteractionType.CLOSE_ACCOUNT, ts, attack_ip,
                                metadata={"attack_pattern": "country_hopper",
                                          "ip_country": final_country}))

    return events, counter
