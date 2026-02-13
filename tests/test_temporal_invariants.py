"""
Shared temporal invariant validation for generated events.

Used by test_non_fraud_generators and test_malicious_data to assert
that generated data respects the temporal rules from USAGE_PATTERNS.md
and FRAUD_TYPES.md.
"""

from __future__ import annotations

from datetime import datetime

from core.enums import InteractionType
from core.models import UserInteraction


def _events_by_user(events: list[UserInteraction]) -> dict[str, list[UserInteraction]]:
    """Group events by user_id, sorted by timestamp."""
    by_user: dict[str, list[UserInteraction]] = {}
    for e in events:
        by_user.setdefault(e.user_id, []).append(e)
    for uid in by_user:
        by_user[uid].sort(key=lambda x: x.timestamp)
    return by_user


# ---------------------------------------------------------------------------
# Non-fraud invariants
# ---------------------------------------------------------------------------

def assert_non_fraud_temporal_invariants(events: list[UserInteraction]) -> None:
    """
    Validate temporal invariants for legitimate (non-fraud) usage patterns.

    Invariants:
    1. ACCOUNT_CREATION is always first for each user.
    2. LOGIN precedes all other activity in each session (no VIEW/MESSAGE/CONNECT
       before a LOGIN in the same session).
    3. VIEW_USER_PAGE precedes MESSAGE_USER and CONNECT_WITH_USER for the same target.
    4. No DOWNLOAD_ADDRESS_BOOK for normal users.
    5. CLOSE_ACCOUNT is terminal (last event for that user).
    """
    by_user = _events_by_user(events)

    for user_id, user_events in by_user.items():
        if not user_events:
            continue

        # 1. ACCOUNT_CREATION first
        first = user_events[0]
        if any(e.interaction_type == InteractionType.ACCOUNT_CREATION for e in user_events):
            assert first.interaction_type == InteractionType.ACCOUNT_CREATION, (
                f"User {user_id}: ACCOUNT_CREATION must be first, got {first.interaction_type}"
            )

        # 4. No DOWNLOAD_ADDRESS_BOOK
        for e in user_events:
            assert e.interaction_type != InteractionType.DOWNLOAD_ADDRESS_BOOK, (
                f"User {user_id}: normal users must not have DOWNLOAD_ADDRESS_BOOK"
            )

        # 5. CLOSE_ACCOUNT terminal
        if any(e.interaction_type == InteractionType.CLOSE_ACCOUNT for e in user_events):
            last = user_events[-1]
            assert last.interaction_type == InteractionType.CLOSE_ACCOUNT, (
                f"User {user_id}: CLOSE_ACCOUNT must be last, got {last.interaction_type}"
            )

        # 2 & 3: Session-based invariants (LOGIN first, VIEW before MESSAGE/CONNECT)
        # Split into sessions: each successful LOGIN starts a new session
        session_starts: list[int] = []
        for i, e in enumerate(user_events):
            if e.interaction_type == InteractionType.LOGIN and e.metadata.get("login_success") is True:
                session_starts.append(i)
        session_starts.append(len(user_events))  # end marker

        # Track seen views across entire user history (VIEW can be in previous session)
        seen_views_global: dict[str, datetime] = {}

        for s in range(len(session_starts) - 1):
            start, end = session_starts[s], session_starts[s + 1]
            session = user_events[start:end]

            # Find successful LOGIN timestamp (may have failed attempt(s) first)
            login_ts: datetime | None = None
            for e in session:
                if e.interaction_type == InteractionType.LOGIN and e.metadata.get("login_success") is True:
                    login_ts = e.timestamp
                    break
            if login_ts is None:
                continue

            session_activity = [e for e in session if e.interaction_type != InteractionType.LOGIN]
            for e in session_activity:
                assert e.timestamp >= login_ts, (
                    f"User {user_id}: activity {e.interaction_type} at {e.timestamp} "
                    f"before session LOGIN at {login_ts}"
                )

            # 3. VIEW before MESSAGE/CONNECT for same target (can be in any prior event)
            for e in session:
                if e.interaction_type == InteractionType.VIEW_USER_PAGE and e.target_user_id:
                    seen_views_global[e.target_user_id] = e.timestamp
                elif e.interaction_type in (InteractionType.MESSAGE_USER, InteractionType.CONNECT_WITH_USER):
                    if e.target_user_id:
                        assert e.target_user_id in seen_views_global, (
                            f"User {user_id}: {e.interaction_type} for {e.target_user_id} "
                            f"without preceding VIEW_USER_PAGE"
                        )
                        assert e.timestamp >= seen_views_global[e.target_user_id], (
                            f"User {user_id}: {e.interaction_type} at {e.timestamp} "
                            f"before VIEW at {seen_views_global[e.target_user_id]}"
                        )


# ---------------------------------------------------------------------------
# Fraud invariants
# ---------------------------------------------------------------------------

def assert_fraud_temporal_invariants(events: list[UserInteraction]) -> None:
    """
    Validate temporal invariants for fraud (ATO) events.

    Invariants:
    1. LOGIN precedes all other activity per victim (no activity before first LOGIN).
    2. MESSAGE_USER (spam) only after at least one LOGIN (success or attempt).
    3. CLOSE_ACCOUNT, if present, is terminal for that user.
    """
    by_user = _events_by_user(events)

    for user_id, user_events in by_user.items():
        if not user_events:
            continue

        # 1. First event per user must be LOGIN (or first activity must follow LOGIN)
        first_login_idx: int | None = None
        for i, e in enumerate(user_events):
            if e.interaction_type == InteractionType.LOGIN:
                first_login_idx = i
                break

        if first_login_idx is not None:
            first_login_ts = user_events[first_login_idx].timestamp
            for i, e in enumerate(user_events):
                if i < first_login_idx:
                    # Only failed LOGINs or PHISHING_LOGIN (victim submits to fake page) can precede first LOGIN
                    assert e.interaction_type in (
                        InteractionType.LOGIN,
                        InteractionType.PHISHING_LOGIN,
                    ), (
                        f"User {user_id}: {e.interaction_type} at index {i} before first LOGIN"
                    )
                else:
                    assert e.timestamp >= first_login_ts, (
                        f"User {user_id}: {e.interaction_type} at {e.timestamp} before LOGIN at {first_login_ts}"
                    )
        else:
            # No LOGIN - allow PHISHING_LOGIN (credential_phishing victim) or SESSION_LOGIN (session_hijacking)
            first = user_events[0]
            assert first.interaction_type in (
                InteractionType.PHISHING_LOGIN,
                InteractionType.SESSION_LOGIN,
            ), (
                f"User {user_id}: fraud events must have LOGIN, PHISHING_LOGIN, or SESSION_LOGIN first, got {first.interaction_type}"
            )

        # 2. MESSAGE_USER only after LOGIN
        has_login = False
        for e in user_events:
            if e.interaction_type == InteractionType.LOGIN:
                has_login = True
            elif e.interaction_type == InteractionType.MESSAGE_USER:
                assert has_login, (
                    f"User {user_id}: MESSAGE_USER at {e.timestamp} without preceding LOGIN"
                )

        # 3. CLOSE_ACCOUNT terminal
        if any(e.interaction_type == InteractionType.CLOSE_ACCOUNT for e in user_events):
            last = user_events[-1]
            assert last.interaction_type == InteractionType.CLOSE_ACCOUNT, (
                f"User {user_id}: CLOSE_ACCOUNT must be last, got {last.interaction_type}"
            )
