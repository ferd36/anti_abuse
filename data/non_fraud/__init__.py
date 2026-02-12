"""
Normal (legitimate) usage patterns for the anti-abuse ATO system.

Generates interaction events that respect temporal invariants and match
the patterns defined in USAGE_PATTERNS.md.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta

from core.enums import InteractionType
from core.models import User, UserInteraction
from data.config_utils import get_cfg

from .active_job_seeker import active_job_seeker
from .career_update import career_update
from .casual_browser import casual_browser
from .content_consumer import content_consumer
from .dormant_account import dormant_account
from .exec_delegation import exec_delegation
from .new_user_onboarding import new_user_onboarding
from .recruiter import recruiter
from .regular_networker import regular_networker
from .returning_user import returning_user
from .weekly_check_in import weekly_check_in

PATTERN_NAMES = (
    "casual_browser",
    "active_job_seeker",
    "recruiter",
    "regular_networker",
    "returning_user",
    "new_user_onboarding",
    "weekly_check_in",
    "content_consumer",
    "career_update",
    "exec_delegation",
    "dormant_account",
)

_GENERATORS = {
    "casual_browser": casual_browser,
    "active_job_seeker": active_job_seeker,
    "career_update": career_update,
    "recruiter": recruiter,
    "regular_networker": regular_networker,
    "returning_user": returning_user,
    "new_user_onboarding": new_user_onboarding,
    "weekly_check_in": weekly_check_in,
    "content_consumer": content_consumer,
    "exec_delegation": exec_delegation,
    "dormant_account": dormant_account,
}

# Pattern weights for regular users who don't match special cases (new/returning)
# Recruiters are a distinct user type and always get the recruiter pattern
# Weights are proportions in [0, 1]
_DEFAULT_PATTERN_WEIGHTS = {
    "casual_browser": 0.26,
    "active_job_seeker": 0.11,
    "regular_networker": 0.26,
    "weekly_check_in": 0.16,
    "content_consumer": 0.21,
}


def generate_legitimate_events(
    users: list[User],
    all_user_ids: list[str],
    window_start: datetime,
    now: datetime,
    counter: int,
    rng: random.Random,
    user_primary_ua: dict[str, str],
    fake_ids: set[str],
    *,
    config: dict | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> tuple[list[UserInteraction], int]:
    """
    Generate legitimate interaction events for non-fake users.

    Respects temporal invariants:
    - ACCOUNT_CREATION first
    - LOGIN before other activity in each session
    - VIEW before MESSAGE/CONNECT when reaching out
    - No DOWNLOAD_ADDRESS_BOOK for normal users
    - CLOSE_ACCOUNT only for inactive users, at the end

    Returns:
        (events, counter) - events sorted by timestamp.
    """
    cfg = config or {}
    events: list[UserInteraction] = []
    legit_users = [u for u in users if u.user_id not in fake_ids]
    total = len(legit_users)
    processed = 0

    pattern_weights = get_cfg(cfg, "usage_patterns", "pattern_weights", default=_DEFAULT_PATTERN_WEIGHTS) or _DEFAULT_PATTERN_WEIGHTS
    weights_keys = [k for k, v in pattern_weights.items() if v > 0]
    weights_vals = [pattern_weights[k] for k in weights_keys]
    if not weights_keys:
        weights_keys = list(_DEFAULT_PATTERN_WEIGHTS.keys())
        weights_vals = list(_DEFAULT_PATTERN_WEIGHTS.values())

    for user in users:
        if user.user_id in fake_ids:
            continue

        ua = user_primary_ua.get(user.user_id, "Mozilla/5.0 Chrome/120")
        days_since_join = (now - user.join_date).days

        user_type = getattr(user, "user_type", "regular")
        if user_type == "recruiter":
            pattern = "recruiter"
        elif days_since_join <= 7:
            pattern = "new_user_onboarding"
        elif days_since_join >= 30 and rng.random() < get_cfg(cfg, "usage_patterns", "returning_user_pct", default=0.05):
            pattern = "returning_user"
        elif days_since_join >= 14 and rng.random() < get_cfg(cfg, "usage_patterns", "career_update_pct", default=0.03):
            pattern = "career_update"
        elif user.country in ("US", "GB", "CA", "AU") and rng.random() < get_cfg(cfg, "usage_patterns", "exec_delegation_pct", default=0.02):
            pattern = "exec_delegation"
        elif rng.random() < get_cfg(cfg, "usage_patterns", "dormant_account_pct", default=0.06):
            pattern = "dormant_account"
        else:
            pattern = rng.choices(weights_keys, weights=weights_vals, k=1)[0]

        user_window_start = max(window_start, user.join_date)
        if user_window_start >= now:
            continue

        # 1. ACCOUNT_CREATION (always first)
        counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = user_window_start
        events.append(UserInteraction(
            interaction_id=f"evt-{counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=user.registration_ip,
            ip_type=user.ip_type,
            metadata={"user_agent": ua, "ip_country": user.registration_country},
        ))

        # 2. Pattern-specific sessions
        gen = _GENERATORS[pattern]
        pattern_events, counter = gen(
            user, all_user_ids, window_start, now, counter, rng, ua,
            config=cfg,
        )
        events.extend(pattern_events)

        # 3. CLOSE_ACCOUNT for inactive users (terminal)
        if not user.is_active and pattern_events:
            last_ts = max(e.timestamp for e in pattern_events)
            close_ts = min(last_ts + timedelta(minutes=rng.randint(5, 60)), now)
            counter += 1
            events.append(UserInteraction(
                interaction_id=f"evt-{counter:08d}",
                user_id=user.user_id,
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=close_ts,
                ip_address=user.ip_address,
                ip_type=user.ip_type,
                metadata={"user_agent": ua, "ip_country": user.registration_country},
            ))
        elif not user.is_active and not pattern_events:
            close_ts = min(create_ts + timedelta(minutes=rng.randint(5, 60)), now)
            counter += 1
            events.append(UserInteraction(
                interaction_id=f"evt-{counter:08d}",
                user_id=user.user_id,
                interaction_type=InteractionType.CLOSE_ACCOUNT,
                timestamp=close_ts,
                ip_address=user.ip_address,
                ip_type=user.ip_type,
                metadata={"user_agent": ua, "ip_country": user.registration_country},
            ))

        processed += 1
        if progress_callback is not None:
            progress_callback(processed, total, len(events))

    events.sort(key=lambda e: e.timestamp)
    return events, counter


__all__ = [
    "PATTERN_NAMES",
    "generate_legitimate_events",
]
