"""
Shared infrastructure for legitimate (non-fraud) usage pattern generators.

All events use residential IPs, the user's country, and respect temporal
invariants: ACCOUNT_CREATION first, LOGIN before other activity,
VIEW before MESSAGE/CONNECT when reaching out to someone.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType
from core.models import UserInteraction
from data.config_utils import get_cfg


def clamp_ts(ts: datetime, max_ts: datetime | None) -> datetime:
    """Clamp timestamp to max_ts so events never exceed 'now' (avoids model assertion)."""
    if max_ts is None:
        return ts
    return min(ts, max_ts)


def make_legit_event(
    counter: int,
    user_id: str,
    itype: InteractionType,
    ts: datetime,
    ip: str,
    ip_type: IPType,
    user_country: str,
    user_agent: str,
    target_user_id: str | None = None,
    metadata: dict | None = None,
    max_ts: datetime | None = None,
) -> UserInteraction:
    """Create a legitimate user interaction (evt- prefix, no attack_pattern)."""
    ts = clamp_ts(ts, max_ts)
    meta = metadata or {}
    meta["user_agent"] = meta.get("user_agent", user_agent)
    meta["ip_country"] = meta.get("ip_country", user_country)
    return UserInteraction(
        interaction_id=f"evt-{counter:08d}",
        user_id=user_id,
        interaction_type=itype,
        timestamp=ts,
        ip_address=ip,
        ip_type=ip_type,
        target_user_id=target_user_id,
        metadata=meta,
    )


def pick_target(
    user_id: str,
    all_user_ids: list[str],
    exclude: set[str] | None = None,
    *,
    rng: random.Random,
) -> str | None:
    """Pick a random target user different from user_id. Returns None if no valid target.
    Callers must pass rng for reproducible results."""
    exclude = exclude or set()
    candidates = [uid for uid in all_user_ids if uid != user_id and uid not in exclude]
    if not candidates:
        return None
    return rng.choice(candidates)


def pick_targets(
    user_id: str,
    all_user_ids: list[str],
    n: int,
    rng: random.Random,
) -> list[str]:
    """Pick n unique target users different from user_id."""
    candidates = [uid for uid in all_user_ids if uid != user_id]
    if len(candidates) <= n:
        return candidates.copy()
    return rng.sample(candidates, n)


def add_login(
    events: list[UserInteraction],
    user_id: str,
    ts: datetime,
    ip: str,
    ip_type: IPType,
    user_country: str,
    user_agent: str,
    counter: int,
    rng: random.Random,
    max_ts: datetime | None = None,
    *,
    config: dict | None = None,
) -> tuple[int, datetime]:
    """Append LOGIN event(s). Returns (counter, ts). ~3% have one failed attempt first."""
    if rng.random() < get_cfg(config, "common", "login_failure_before_success_pct", default=0.03):
        counter += 1
        events.append(make_legit_event(
            counter, user_id, InteractionType.LOGIN, ts, ip, ip_type,
            user_country, user_agent, metadata={"login_success": False}, max_ts=max_ts,
        ))
        ts += timedelta(seconds=rng.randint(5, 30))
    counter += 1
    events.append(make_legit_event(
        counter, user_id, InteractionType.LOGIN, ts, ip, ip_type,
        user_country, user_agent, metadata={"login_success": True}, max_ts=max_ts,
    ))
    return counter, ts


def add_view_then_connect_or_message(
    events: list[UserInteraction],
    user_id: str,
    ts: datetime,
    ip: str,
    ip_type: IPType,
    user_country: str,
    user_agent: str,
    target: str,
    counter: int,
    rng: random.Random,
    do_connect: bool = True,
    do_message: bool = False,
    max_ts: datetime | None = None,
) -> tuple[int, datetime]:
    """
    Add VIEW_USER_PAGE (temporal invariant: view before reach out),
    then optionally CONNECT_WITH_USER and/or MESSAGE_USER.
    """
    counter += 1
    ts += timedelta(seconds=rng.randint(10, 90))
    events.append(make_legit_event(
        counter, user_id, InteractionType.VIEW_USER_PAGE, ts, ip, ip_type,
        user_country, user_agent, target_user_id=target, max_ts=max_ts,
    ))
    if do_connect:
        counter += 1
        ts += timedelta(seconds=rng.randint(5, 60))
        events.append(make_legit_event(
            counter, user_id, InteractionType.CONNECT_WITH_USER, ts, ip, ip_type,
            user_country, user_agent, target_user_id=target, max_ts=max_ts,
        ))
    if do_message:
        counter += 1
        ts += timedelta(seconds=rng.randint(10, 120))
        msg_len = rng.randint(30, 200)
        _legit_messages = [
            "Hi! I saw your profile and thought we might have some overlap in interests.",
            "Thanks for connecting! Would love to hear more about your work.",
            "Great to meet you here. Happy to help if you have any questions.",
            "Thanks for the add! Looking forward to staying in touch.",
        ]
        events.append(make_legit_event(
            counter, user_id, InteractionType.MESSAGE_USER, ts, ip, ip_type,
            user_country, user_agent, target_user_id=target,
            metadata={
                "message_length": msg_len,
                "is_spam": False,
                "message_text": rng.choice(_legit_messages),
            },
            max_ts=max_ts,
        ))
    return counter, ts
