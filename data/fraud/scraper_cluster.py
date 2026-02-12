"""Scraper Cluster: coordinated IP cluster scrapes user profile pages.

Three scraping strategies:
  - "alphabetical": pages visited in display-name alphabetical order,
    a telltale sign of iterating a sorted directory dump.
  - "regular_interval": pages visited at machine-precise fixed intervals,
    a strong bot fingerprint regardless of target ordering.
  - "coordinated": the target space is partitioned across scrapers so
    each account's individual volume looks moderate, but the aggregate
    covers the full directory. Timing jitter is added to mimic humans.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType

from ._common import (
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)

# Bot-like user agents frequently seen in scraping infrastructure
_SCRAPER_USER_AGENTS = [
    "python-requests/2.31.0",
    "Go-http-client/2.0",
    "Java/17.0.9",
    "node-fetch/3.3.2",
    "axios/1.6.2",
    "Apache-HttpClient/5.3",
    "Mozilla/5.0 Chrome/120",
]

STRATEGIES = ("alphabetical", "regular_interval", "coordinated")


def scraper_cluster(
    scraper_ids: list[str],
    scraper_countries: list[str],
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    user_display_names: dict[str, str] | None = None,
    strategy: str | None = None,
) -> tuple[list, int]:
    """
    Coordinated scraping cluster: multiple taken-over accounts from related
    hosting IPs systematically view user profile pages.

    Args:
        scraper_ids:        User IDs of the compromised accounts doing the scraping.
        scraper_countries:  Home countries of the scraper accounts.
        all_user_ids:       Full user population (scrape targets drawn from here).
        base_time:          Campaign start time.
        counter:            Global event counter.
        rng:                Seeded random generator.
        user_display_names: {user_id: display_name} for alphabetical ordering.
        strategy:           Force a strategy; random if None.

    Returns:
        (events, counter) — the scraping events and updated counter.
    """
    events: list = []
    if strategy is None:
        strategy = rng.choice(STRATEGIES)

    attacker_country = pick_attacker_country(scraper_countries[0], rng)

    # All scrapers share a small pool of related hosting IPs
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(scraper_ids) + 1, 5))]

    # Build target list — every user except the scrapers themselves
    scraper_set = set(scraper_ids)
    targets = [uid for uid in all_user_ids if uid not in scraper_set]

    # Sort targets based on strategy before slicing
    if strategy == "alphabetical":
        if user_display_names:
            targets.sort(key=lambda uid: user_display_names.get(uid, uid).lower())
        else:
            targets.sort()
    elif strategy == "coordinated":
        targets.sort()
    else:
        rng.shuffle(targets)

    total_pages = rng.randint(200, 600)
    pages_to_scrape = targets[:total_pages]

    ts = base_time

    # --- Phase 1: each scraper logs in from a hosting IP ---
    latest_login_ts = ts
    for idx, sid in enumerate(scraper_ids):
        ip = cluster_ips[idx % len(cluster_ips)]
        login_ts = ts + timedelta(minutes=rng.randint(0, 30))
        login_evts, counter, success_ts = make_login_with_failures(
            sid, login_ts, ip, counter, rng, "scraper_cluster",
            extra_metadata={"attacker_country": attacker_country},
        )
        events.extend(login_evts)
        latest_login_ts = max(latest_login_ts, success_ts)

    # --- Phase 2: scrape only after all scrapers have logged in ---
    scrape_start = latest_login_ts + timedelta(minutes=rng.randint(2, 15))

    strategy_fn = {
        "alphabetical": _scrape_alphabetical,
        "regular_interval": _scrape_regular_interval,
        "coordinated": _scrape_coordinated,
    }[strategy]

    scrape_evts, counter = strategy_fn(
        scraper_ids, pages_to_scrape, cluster_ips,
        scrape_start, counter, rng, attacker_country,
    )
    events.extend(scrape_evts)

    return events, counter


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------

def _scrape_alphabetical(
    scraper_ids: list[str],
    targets: list[str],
    cluster_ips: list[str],
    ts: datetime,
    counter: int,
    rng: random.Random,
    attacker_country: str,
) -> tuple[list, int]:
    """
    Walk through targets in the pre-sorted alphabetical order.
    Very uniform timing (3-8 s between views) — classic bot signature.
    A secondary scraper may pick up mid-way to simulate shift changes.
    """
    events: list = []
    primary_scraper = scraper_ids[0]
    ip = cluster_ips[0]
    ua = rng.choice(_SCRAPER_USER_AGENTS)

    # Occasionally a second scraper picks up the remaining work
    switch_point = (
        rng.randint(len(targets) // 2, len(targets) - 1)
        if len(scraper_ids) > 1
        else len(targets)
    )

    base_interval = rng.uniform(3, 8)

    for i, target in enumerate(targets):
        if i == switch_point and len(scraper_ids) > 1:
            primary_scraper = scraper_ids[1]
            ip = cluster_ips[1 % len(cluster_ips)]
            ua = rng.choice(_SCRAPER_USER_AGENTS)

        jitter = rng.uniform(-0.5, 0.5)
        view_ts = ts + timedelta(seconds=(base_interval + jitter) * i)
        counter += 1
        events.append(make_event(
            counter, primary_scraper, InteractionType.VIEW_USER_PAGE, view_ts, ip,
            target_user_id=target,
            metadata={
                "attack_pattern": "scraper_cluster",
                "scrape_strategy": "alphabetical",
                "ip_country": attacker_country,
                "user_agent": ua,
                "scrape_index": i,
            },
        ))

    return events, counter


def _scrape_regular_interval(
    scraper_ids: list[str],
    targets: list[str],
    cluster_ips: list[str],
    ts: datetime,
    counter: int,
    rng: random.Random,
    attacker_country: str,
) -> tuple[list, int]:
    """
    One or two scrapers viewing pages at perfectly regular intervals.
    Machine-precise timing is the main detection signal.
    """
    events: list = []
    interval_seconds = rng.choice([5, 10, 15, 20, 30])

    for i, target in enumerate(targets):
        scraper_idx = i % len(scraper_ids)
        sid = scraper_ids[scraper_idx]
        ip = cluster_ips[scraper_idx % len(cluster_ips)]

        view_ts = ts + timedelta(seconds=interval_seconds * i)
        counter += 1
        events.append(make_event(
            counter, sid, InteractionType.VIEW_USER_PAGE, view_ts, ip,
            target_user_id=target,
            metadata={
                "attack_pattern": "scraper_cluster",
                "scrape_strategy": "regular_interval",
                "ip_country": attacker_country,
                "user_agent": rng.choice(_SCRAPER_USER_AGENTS),
                "interval_seconds": interval_seconds,
            },
        ))

    return events, counter


def _scrape_coordinated(
    scraper_ids: list[str],
    targets: list[str],
    cluster_ips: list[str],
    ts: datetime,
    counter: int,
    rng: random.Random,
    attacker_country: str,
) -> tuple[list, int]:
    """
    Scrapers partition the sorted target space into segments so each
    account's individual volume looks moderate. They run concurrently
    with added jitter to mimic organic browsing.
    """
    events: list = []
    num_scrapers = len(scraper_ids)

    chunk_size = len(targets) // max(num_scrapers, 1)

    for scraper_idx, sid in enumerate(scraper_ids):
        ip = cluster_ips[scraper_idx % len(cluster_ips)]
        ua = rng.choice(_SCRAPER_USER_AGENTS)

        start = scraper_idx * chunk_size
        end = start + chunk_size if scraper_idx < num_scrapers - 1 else len(targets)
        segment = targets[start:end]

        # Each scraper starts at a slightly different time
        scraper_offset = timedelta(minutes=rng.randint(0, 15))
        base_interval = rng.uniform(8, 20)

        for i, target in enumerate(segment):
            jitter = rng.uniform(-3, 3)
            view_ts = ts + scraper_offset + timedelta(seconds=(base_interval + jitter) * i)
            counter += 1
            events.append(make_event(
                counter, sid, InteractionType.VIEW_USER_PAGE, view_ts, ip,
                target_user_id=target,
                metadata={
                    "attack_pattern": "scraper_cluster",
                    "scrape_strategy": "coordinated",
                    "ip_country": attacker_country,
                    "user_agent": ua,
                    "segment_index": scraper_idx,
                },
            ))

    return events, counter
