#!/usr/bin/env python3
"""
Generate mock data and populate the SQLite database.

Usage:
    python generate.py                    # Creates anti_abuse.db, 100k users
    python generate.py --users 5000       # 5k users
    python generate.py --fraud-pct 1.0     # 1% fraud rate
    python generate.py --memory            # Uses in-memory DB (for testing)

Removes previous anti_abuse.db if it exists before creating a new one.
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from core.constants import NUM_USERS

from config import DATASET_CONFIG


from core.validate import (
    compute_connections_from_interactions,
    enforce_temporal_invariants,
    validate_corpus,
)
from db.repository import Repository
from data.fraud import generate_malicious_events
from data.mock_data import (
    _enforce_close_account_invariant,
    add_accept_events_for_connects,
    generate_all,
    update_profiles_connections,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock data and populate DB")
    parser.add_argument(
        "--users",
        type=int,
        default=NUM_USERS,
        help=f"Number of users to generate (default: {NUM_USERS:,})",
    )
    parser.add_argument(
        "--fraud-pct",
        type=float,
        default=0.5,
        help="Target percentage of users as fraud victims (default: 0.5)",
    )
    parser.add_argument("--memory", action="store_true", help="Use in-memory database")
    args = parser.parse_args()

    assert 0 < args.fraud_pct <= 100, "fraud-pct must be in (0, 100]"
    assert args.users >= 1, "users must be >= 1"

    db_path: str | Path
    if args.memory:
        db_path = ":memory:"
        print("Using in-memory database.")
    else:
        db_path = Path(__file__).parent / "anti_abuse.db"
        if db_path.exists():
            db_path.unlink()
            print(f"Removed previous database: {db_path}")
        print(f"Database path: {db_path}")

    t0 = time.time()
    users, profiles, interactions = generate_all(
        seed=42, num_users=args.users, config=DATASET_CONFIG
    )
    gen_time = time.time() - t0
    print(f"\nData generation took {gen_time:.2f}s")

    t0 = time.time()
    repo = Repository(db_path)

    print("\n" + "=" * 50)
    print(f"MALICIOUS DATA (target fraud: {args.fraud_pct}%)")
    print("=" * 50)
    user_countries = {u.user_id: u.country for u in users}
    user_connections_count = {p.user_id: p.connections_count for p in profiles}
    user_display_names = {p.user_id: p.display_name for p in profiles}
    user_headlines = {p.user_id: p.headline for p in profiles}
    user_ids = [u.user_id for u in users]
    user_is_active = {u.user_id: u.is_active for u in users}
    fake_account_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "fake_account"]
    account_farming_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "account_farming"]
    harassment_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "coordinated_harassment"]
    like_inflation_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "coordinated_like_inflation"]
    profile_cloning_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "profile_cloning"]
    endorsement_inflation_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "endorsement_inflation"]
    recommendation_fraud_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "recommendation_fraud"]
    job_scam_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "job_posting_scam"]
    invitation_spam_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "invitation_spam"]
    group_spam_user_ids = [u.user_id for u in users if getattr(u, "generation_pattern", "") == "group_spam"]
    user_groups_joined = {p.user_id: p.groups_joined for p in profiles}
    fraud_events, victim_to_pattern = generate_malicious_events(
        user_ids, user_countries,
        user_connections_count=user_connections_count,
        user_is_active=user_is_active,
        user_display_names=user_display_names,
        user_headlines=user_headlines,
        fake_account_user_ids=fake_account_user_ids,
        account_farming_user_ids=account_farming_user_ids,
        harassment_user_ids=harassment_user_ids,
        like_inflation_user_ids=like_inflation_user_ids,
        profile_cloning_user_ids=profile_cloning_user_ids,
        endorsement_inflation_user_ids=endorsement_inflation_user_ids,
        recommendation_fraud_user_ids=recommendation_fraud_user_ids,
        job_scam_user_ids=job_scam_user_ids,
        invitation_spam_user_ids=invitation_spam_user_ids,
        group_spam_user_ids=group_spam_user_ids,
        user_groups_joined=user_groups_joined,
        seed=99,
        fraud_pct=args.fraud_pct,
        config=DATASET_CONFIG,
    )

    all_interactions = sorted(
        interactions + fraud_events,
        key=lambda i: i.timestamp,
    )
    rng = random.Random(99)
    all_interactions = add_accept_events_for_connects(all_interactions, rng, accept_rate=0.6)
    all_interactions = _enforce_close_account_invariant(all_interactions)
    connections_count = compute_connections_from_interactions(all_interactions)
    profiles = update_profiles_connections(profiles, connections_count)
    validate_corpus(users, profiles, all_interactions)
    enforce_temporal_invariants(all_interactions)

    print("\nInserting users...")
    repo.insert_users_batch(users)
    print(f"  Users in DB: {repo.count_users()}")

    print("Inserting profiles...")
    repo.insert_profiles_batch(profiles)

    print("Inserting interactions...")
    repo.insert_interactions_batch(all_interactions)
    insert_time = time.time() - t0
    print(f"  Interactions in DB: {repo.count_interactions()}")
    print(f"\nDB insertion took {insert_time:.2f}s")

    for victim_id, pattern in victim_to_pattern.items():
        repo.update_user_generation_pattern(victim_id, pattern)

    deleted = repo.enforce_close_account_invariant()
    if deleted:
        print(f"  Pruned {deleted} events that occurred after CLOSE_ACCOUNT")
    deactivated = repo.deactivate_users_with_close_account()
    if deactivated:
        print(f"  Deactivated {deactivated} users with CLOSE_ACCOUNT")

    print("\n" + "=" * 50)
    print("SUMMARY (legitimate + malicious)")
    print("=" * 50)
    print(f"  Total users:        {repo.count_users()}")
    print(f"  Active users:       {len(repo.get_active_user_ids())}")
    print(f"  Total interactions: {repo.count_interactions()}")
    print("\n  Interactions by type:")
    counts = repo.count_interactions_by_type()
    max_count = max(counts.values()) if counts else 0
    width = max(6, len(f"{max_count:,}"))
    for itype, count in sorted(counts.items()):
        print(f"    {itype:30s} {count:>{width},}")

    repo.close()
    print(f"\nDone. Database: {db_path}")


if __name__ == "__main__":
    main()
