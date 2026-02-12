"""
Cross-entity and temporal invariant validation.

Validates relational invariants (user_id refs, uniqueness) and temporal
invariants (CLOSE_ACCOUNT terminal, LOGIN before activity, etc.) at batch
construction time before persistence.
"""

from __future__ import annotations

from datetime import datetime

from core.enums import InteractionType
from core.models import User, UserInteraction, UserProfile


def _is_fraud_event(e: UserInteraction) -> bool:
    """True if event has fraud metadata (attack_pattern or attacker_country)."""
    m = e.metadata or {}
    return bool(m.get("attack_pattern") or m.get("attacker_country"))


def _events_by_user(events: list[UserInteraction]) -> dict[str, list[UserInteraction]]:
    """Group events by user_id, sorted by timestamp."""
    by_user: dict[str, list[UserInteraction]] = {}
    for evt in events:
        by_user.setdefault(evt.user_id, []).append(evt)
    for uid in by_user:
        by_user[uid].sort(key=lambda x: x.timestamp)
    return by_user


def _enforce_fraud_temporal_invariants(events: list[UserInteraction]) -> None:
    """
    Validate temporal invariants for fraud (ATO) events.
    Raises AssertionError on violation.
    """
    by_user = _events_by_user(events)
    for user_id, user_events in by_user.items():
        if not user_events:
            continue
        first_login_idx: int | None = None
        for i, e in enumerate(user_events):
            if e.interaction_type == InteractionType.LOGIN:
                first_login_idx = i
                break
        if first_login_idx is None:
            raise AssertionError(f"User {user_id}: fraud events must have at least one LOGIN")
        first_login_ts = user_events[first_login_idx].timestamp
        for i, e in enumerate(user_events):
            if i < first_login_idx:
                if e.interaction_type != InteractionType.LOGIN:
                    raise AssertionError(
                        f"User {user_id}: {e.interaction_type} at index {i} before first LOGIN"
                    )
            else:
                if e.timestamp < first_login_ts:
                    raise AssertionError(
                        f"User {user_id}: {e.interaction_type} at {e.timestamp} before LOGIN at {first_login_ts}"
                    )
        has_login = False
        for e in user_events:
            if e.interaction_type == InteractionType.LOGIN:
                has_login = True
            elif e.interaction_type == InteractionType.MESSAGE_USER:
                if not has_login:
                    raise AssertionError(
                        f"User {user_id}: MESSAGE_USER at {e.timestamp} without preceding LOGIN"
                    )
        if any(e.interaction_type == InteractionType.CLOSE_ACCOUNT for e in user_events):
            last = user_events[-1]
            if last.interaction_type != InteractionType.CLOSE_ACCOUNT:
                raise AssertionError(
                    f"User {user_id}: CLOSE_ACCOUNT must be last, got {last.interaction_type}"
                )


def _enforce_non_fraud_temporal_invariants(events: list[UserInteraction]) -> None:
    """
    Validate temporal invariants for legitimate (non-fraud) events.
    Raises AssertionError on violation.
    """
    by_user = _events_by_user(events)
    for user_id, user_events in by_user.items():
        if not user_events:
            continue
        if any(e.interaction_type == InteractionType.ACCOUNT_CREATION for e in user_events):
            first = user_events[0]
            if first.interaction_type != InteractionType.ACCOUNT_CREATION:
                raise AssertionError(
                    f"User {user_id}: ACCOUNT_CREATION must be first, got {first.interaction_type}"
                )
        for e in user_events:
            if e.interaction_type == InteractionType.DOWNLOAD_ADDRESS_BOOK:
                raise AssertionError(
                    f"User {user_id}: normal users must not have DOWNLOAD_ADDRESS_BOOK"
                )
        if any(e.interaction_type == InteractionType.CLOSE_ACCOUNT for e in user_events):
            last = user_events[-1]
            if last.interaction_type != InteractionType.CLOSE_ACCOUNT:
                raise AssertionError(
                    f"User {user_id}: CLOSE_ACCOUNT must be last, got {last.interaction_type}"
                )
        session_starts: list[int] = []
        for i, e in enumerate(user_events):
            if e.interaction_type == InteractionType.LOGIN and e.metadata.get("login_success") is True:
                session_starts.append(i)
        session_starts.append(len(user_events))
        seen_views: dict[str, datetime] = {}
        for s in range(len(session_starts) - 1):
            start, end = session_starts[s], session_starts[s + 1]
            session = user_events[start:end]
            login_ts: datetime | None = None
            for e in session:
                if e.interaction_type == InteractionType.LOGIN and e.metadata.get("login_success") is True:
                    login_ts = e.timestamp
                    break
            if login_ts is None:
                continue
            for e in session:
                if e.interaction_type != InteractionType.LOGIN and e.timestamp < login_ts:
                    raise AssertionError(
                        f"User {user_id}: activity {e.interaction_type} at {e.timestamp} "
                        f"before session LOGIN at {login_ts}"
                    )
            for e in session:
                if e.interaction_type == InteractionType.VIEW_USER_PAGE and e.target_user_id:
                    seen_views[e.target_user_id] = e.timestamp
                elif e.interaction_type in (InteractionType.MESSAGE_USER, InteractionType.CONNECT_WITH_USER):
                    if e.target_user_id:
                        if e.target_user_id not in seen_views:
                            raise AssertionError(
                                f"User {user_id}: {e.interaction_type} for {e.target_user_id} "
                                "without preceding VIEW_USER_PAGE"
                            )
                        if e.timestamp < seen_views[e.target_user_id]:
                            raise AssertionError(
                                f"User {user_id}: {e.interaction_type} at {e.timestamp} "
                                f"before VIEW at {seen_views[e.target_user_id]}"
                            )


def enforce_temporal_invariants(interactions: list[UserInteraction]) -> None:
    """
    Enforce temporal invariants on a batch of interactions.
    For each user: applies fraud invariants to fraud events, non-fraud invariants
    to non-fraud events. Users with mixed events are validated per subsequence.
    Raises AssertionError on violation.
    """
    by_user = _events_by_user(interactions)
    user_ids = set(by_user.keys())
    for uid in user_ids:
        user_events = by_user[uid]
        fraud_events = [e for e in user_events if _is_fraud_event(e)]
        non_fraud_events = [e for e in user_events if not _is_fraud_event(e)]
        if fraud_events:
            _enforce_fraud_temporal_invariants(fraud_events)
        if non_fraud_events:
            _enforce_non_fraud_temporal_invariants(non_fraud_events)


def validate_corpus(
    users: list[User],
    profiles: list[UserProfile],
    interactions: list[UserInteraction],
) -> None:
    """
    Validate cross-entity invariants on a corpus.

    Checks:
      - Every profile.user_id exists in users.
      - Every interaction.user_id exists in users.
      - Every non-null interaction.target_user_id exists in users.
      - interaction_id is unique across interactions.
      - User.email is unique across users.
      - profile_created_at >= user.join_date for each profile.
    Raises AssertionError on violation.
    """
    user_ids = {u.user_id for u in users}
    user_by_id = {u.user_id: u for u in users}
    emails_seen: set[str] = set()
    interaction_ids: set[str] = set()

    for u in users:
        assert u.email not in emails_seen, f"Duplicate email: {u.email!r}"
        emails_seen.add(u.email)

    for p in profiles:
        assert p.user_id in user_ids, (
            f"Profile for {p.user_id!r} references non-existent user"
        )
        user = user_by_id[p.user_id]
        if p.profile_created_at < user.join_date:
            raise AssertionError(
                f"Profile for {p.user_id}: profile_created_at ({p.profile_created_at}) "
                f"must be >= user.join_date ({user.join_date})"
            )

    for i in interactions:
        assert i.user_id in user_ids, (
            f"Interaction {i.interaction_id}: user_id {i.user_id!r} references non-existent user"
        )
        if i.target_user_id is not None:
            assert i.target_user_id in user_ids, (
                f"Interaction {i.interaction_id}: target_user_id {i.target_user_id!r} "
                "references non-existent user"
            )
        assert i.interaction_id not in interaction_ids, (
            f"Duplicate interaction_id: {i.interaction_id!r}"
        )
        interaction_ids.add(i.interaction_id)
