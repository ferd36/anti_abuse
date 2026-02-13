"""
Malicious data generator.

Victim selection is biased toward users with higher connection counts:
attackers preferentially target high-value accounts with more contacts.

Simulates realistic attack patterns where an attacker obtains a victim's
credentials and takes over their account. All attackers log in from hosting
IPs or a different country than the victim.

Attack patterns (MOs):
  1. "Smash & Grab"   - Login, download address book, mass spam 80-200 contacts
                         in 1-3 hours, close account. All within 24h.
  2. "Low & Slow"     - Login, wait 2-5 days with occasional page views,
                         download address book, spam 15-40 users over 2-3 days.
                         Leave account open.
  3. "Country Hopper"  - Login from 3-4 different countries over a week.
                         Download address book, spam from yet another country.
                         Sometimes close account.
  4. "Data Thief"      - Login, download address book, no spam, close account.
                         Pure data exfiltration.
  5. "Credential Stuffer" - Same attacker IP hits 3-5 victim accounts in quick
                         succession. Each victim gets address book downloaded
                         and moderate spam. Some accounts closed.
  6. "Login Storm"     - 5-15 failed login attempts, then success, download
                         address book, close account.
  7. "Stealth Takeover" - Multiple login failures (hosting), success, login from
                         another country with different UA, wait a few days,
                         download address book, close from yet another country
                         via residential IP.
  8. "Fake Account"    - Fake accounts created by IP rings (shared IPs, one country).
                         Dormant for a while, then login from US hosting changes
                         password, login from another country, upload big address
                         book, spam.
  9. "Scraper Cluster" - Cluster of related hosting IPs takes over 3-4 accounts
                         and uses them to scrape user profile pages. Strategies:
                         alphabetical name order, machine-precise intervals, or
                         coordinated partitioning to hide individual volume.
 10. "Spear Phisher"  - Targeted impersonation via a residential IP. Attacker
                         may tweak the victim's profile/name, then views each
                         target's page before sending a longer, personalised
                         message. Low volume (5-15 targets), account left open.
 11. "Credential Tester" - Validates stolen credentials without exploiting accounts.
                         Same hosting IP tests 5-8 accounts in rapid succession.
                         Each gets a single login (+ maybe one page view), then
                         nothing. Under 60s per account. Building a list to sell.
 12. "Connection Harvester" - Blasts 50-200 CONNECT_WITH_USER requests to inflate
                         the compromised account's network. May download address
                         book first. Account left open for future campaigns.
 13. "Sleeper Agent"   - Account compromised early (password changed), then kept
                        alive with periodic login-only check-ins every few days
                        for 2-4 weeks. Finally activated for a spam campaign.
 14. "Profile Defacement" - Attacker logs in, defaces name/headline/summary,
                        optionally changes password. Account left open. No spam.
 15. "Executive Hunter" - Coordinated cluster of hosting IPs targeting CEOs and
                        Founders with sophisticated spear-phishing. View-then-message
                        pattern with executive-focused content (wire transfers,
                        urgent approvals, board meetings). Low volume per account.
 16. "Account Farming" - Hosting IP clusters create empty accounts, credentials sold.
                        Buyers log in from different IPs, change password, fill bogus profiles.
 17. "Coordinated Harassment" - Clusters of fake accounts target same users with harassing messages.
 18. "Coordinated Like Inflation" - Clusters of fake accounts artificially boost likes on a post.

Public API:
  generate_malicious_events() - orchestrates all patterns and returns events.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from core.enums import InteractionType
from core.models import UserInteraction

_SESSION_GAP = timedelta(minutes=30)

from config import DATASET_CONFIG
from data.config_utils import get_cfg
from ._common import (
    enforce_login_first_invariant,
    enforce_spam_after_login_invariant,
)
from .account_farming import account_farming
from .connection_harvester import connection_harvester
from .coordinated_harassment import coordinated_harassment
from .coordinated_like_inflation import coordinated_like_inflation
from .country_hopper import country_hopper
from .profile_cloning import profile_cloning
from .endorsement_inflation import endorsement_inflation
from .recommendation_fraud import recommendation_fraud
from .job_posting_scam import job_posting_scam
from .invitation_spam import invitation_spam
from .group_spam import group_spam
from .romance_scam import romance_scam
from .session_hijacking import session_hijacking
from .credential_phishing import credential_phishing
from .ad_engagement_fraud import ad_engagement_fraud
from .credential_stuffer import credential_stuffer
from .credential_tester import credential_tester
from .data_thief import data_thief
from .executive_hunter import executive_hunter
from .fake_account import fake_account
from .login_storm import login_storm
from .low_slow import low_and_slow
from .profile_defacement import profile_defacement
from .scraper_cluster import scraper_cluster
from .sleeper_agent import sleeper_agent
from .smash_grab import smash_and_grab
from .spear_phisher import spear_phisher
from .stealth_takeover import stealth_takeover


def _assign_fraud_session_ids(events: list[UserInteraction]) -> None:
    """Assign session_id to fraud events in place. Must be sorted by timestamp."""
    user_counter: dict[str, int] = {}
    user_last_ts: dict[str, datetime] = {}

    for e in events:
        uid = e.user_id
        ts = e.timestamp
        new_session = False
        if uid not in user_counter:
            new_session = True
        elif e.interaction_type == InteractionType.LOGIN:
            new_session = True
        elif (ts - user_last_ts[uid]) > _SESSION_GAP:
            new_session = True
        if new_session:
            user_counter[uid] = user_counter.get(uid, 0) + 1
        user_last_ts[uid] = ts
        object.__setattr__(e, "session_id", f"{uid}-a{user_counter[uid]:04d}")


_FRAUD_PATTERN_ORDER = [
    "smash_grab", "low_slow", "country_hopper", "data_thief", "credential_stuffer",
    "login_storm", "stealth_takeover", "scraper_cluster", "spear_phisher",
    "credential_tester", "connection_harvester", "sleeper_agent", "profile_defacement",
    "executive_hunter",
    "credential_phishing", "session_hijacking", "romance_scam",
]


N_PATTERNS = len(_FRAUD_PATTERN_ORDER)


def _distribute_victims(num_selected: int, config: dict | None = None) -> list[int]:
    """Allocate num_selected across 17 patterns proportionally to weights from config.
    Ensures each pattern gets at least 1 victim when num_selected >= N_PATTERNS."""
    default_weights = DATASET_CONFIG.fraud.get("pattern_weights", {})
    weights_dict = get_cfg(config, "fraud", "pattern_weights", default=default_weights) or default_weights
    weights = [weights_dict.get(p, 0) for p in _FRAUD_PATTERN_ORDER]
    total = sum(weights)
    if num_selected <= 0 or total <= 0:
        return [0] * N_PATTERNS
    if num_selected >= N_PATTERNS:
        allocated = [1] * N_PATTERNS
        remainder = num_selected - N_PATTERNS
        if remainder > 0 and total > 0:
            extra = [int(remainder * w / total) for w in weights]
            rem_extra = remainder - sum(extra)
            for i in range(rem_extra):
                extra[i % N_PATTERNS] += 1
            allocated = [allocated[i] + extra[i] for i in range(N_PATTERNS)]
        return allocated
    allocated = [int(num_selected * w / total) for w in weights]
    remainder = int(num_selected - sum(allocated))
    for i in range(remainder):
        allocated[i % N_PATTERNS] += 1
    return allocated


def generate_malicious_events(
    all_user_ids: list[str],
    user_countries: dict[str, str],
    user_connections_count: dict[str, int] | None = None,
    user_is_active: dict[str, bool] | None = None,
    user_display_names: dict[str, str] | None = None,
    user_headlines: dict[str, str] | None = None,
    fake_account_user_ids: list[str] | None = None,
    account_farming_user_ids: list[str] | None = None,
    harassment_user_ids: list[str] | None = None,
    like_inflation_user_ids: list[str] | None = None,
    profile_cloning_user_ids: list[str] | None = None,
    endorsement_inflation_user_ids: list[str] | None = None,
    recommendation_fraud_user_ids: list[str] | None = None,
    job_scam_user_ids: list[str] | None = None,
    invitation_spam_user_ids: list[str] | None = None,
    group_spam_user_ids: list[str] | None = None,
    user_groups_joined: dict[str, tuple[str, ...]] | None = None,
    seed: int = 99,
    fraud_pct: float = 0.5,
    config: dict | None = None,
) -> tuple[list[UserInteraction], dict[str, str]]:
    """
    Generate attack events for victim accounts across 17 attack patterns.
    Victim count is fraud_pct of user base.

    Args:
        all_user_ids:   List of all user IDs in the system.
        user_countries:  Mapping {user_id: country_code}.
        user_connections_count: Mapping {user_id: connections_count}. When provided,
            victims are preferentially selected from users with higher connection counts.
        user_is_active: Mapping {user_id: is_active}. Inactive (already-closed) users
            are excluded from victim selection.
        user_display_names: Mapping {user_id: display_name}. Used by the scraper_cluster
            alphabetical strategy to sort targets by name.
        fake_account_user_ids: User IDs for fake account pattern (must exist in all_user_ids).
        seed:           Random seed for reproducibility.
        fraud_pct:      Target percentage of users as fraud victims (default: 0.5).
        config:         Dataset config with fraud_pattern_weights for pattern allocation.

    Returns:
        (events, victim_to_pattern) where events are sorted by timestamp and
        victim_to_pattern maps victim user_id -> attack pattern name (source of truth).
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc) - timedelta(days=60)
    counter = 0
    all_events: list[UserInteraction] = []

    num_selected = max(1, int(len(all_user_ids) * fraud_pct / 100))
    num_selected = max(num_selected, N_PATTERNS)

    # Exclude fishy accounts from victim pool (they get their own attack flows)
    fishy_ids = set()
    for ids in (fake_account_user_ids, account_farming_user_ids, harassment_user_ids, like_inflation_user_ids,
                profile_cloning_user_ids, endorsement_inflation_user_ids, recommendation_fraud_user_ids,
                job_scam_user_ids, invitation_spam_user_ids, group_spam_user_ids):
        if ids:
            fishy_ids.update(ids)

    candidates = [uid for uid in all_user_ids if uid not in {"u-000000"} and uid not in fishy_ids]
    if user_is_active:
        candidates = [uid for uid in candidates if user_is_active.get(uid, True)]
    if user_connections_count:
        candidates.sort(
            key=lambda uid: user_connections_count.get(uid, 0),
            reverse=True,
        )
        pool_size = max(num_selected * 3, min(len(candidates), num_selected * 3))
        victim_pool = candidates[:pool_size]
    else:
        rng.shuffle(candidates)
        victim_pool = candidates

    selected = rng.sample(victim_pool, min(num_selected, len(victim_pool)))
    counts = _distribute_victims(len(selected), config)

    victim_to_pattern: dict[str, str] = {}
    offset = 0

    smash_victims = selected[offset : offset + counts[0]]
    offset += counts[0]
    for vid in smash_victims:
        victim_to_pattern[vid] = "smash_grab"
    slow_victims = selected[offset : offset + counts[1]]
    offset += counts[1]
    for vid in slow_victims:
        victim_to_pattern[vid] = "low_slow"
    hopper_victims = selected[offset : offset + counts[2]]
    offset += counts[2]
    for vid in hopper_victims:
        victim_to_pattern[vid] = "country_hopper"
    thief_victims = selected[offset : offset + counts[3]]
    offset += counts[3]
    for vid in thief_victims:
        victim_to_pattern[vid] = "data_thief"
    stuffer_count = counts[4]
    stuffer_batch_1 = selected[offset : offset + (stuffer_count + 1) // 2]
    stuffer_batch_2 = selected[offset + (stuffer_count + 1) // 2 : offset + stuffer_count]
    offset += stuffer_count
    for vid in stuffer_batch_1 + stuffer_batch_2:
        victim_to_pattern[vid] = "credential_stuffer"
    login_storm_victims = selected[offset : offset + counts[5]]
    offset += counts[5]
    for vid in login_storm_victims:
        victim_to_pattern[vid] = "login_storm"
    stealth_victims = selected[offset : offset + counts[6]]
    offset += counts[6]
    for vid in stealth_victims:
        victim_to_pattern[vid] = "stealth_takeover"
    scraper_victims = selected[offset : offset + counts[7]]
    offset += counts[7]
    for vid in scraper_victims:
        victim_to_pattern[vid] = "scraper_cluster"
    spear_victims = selected[offset : offset + counts[8]]
    offset += counts[8]
    for vid in spear_victims:
        victim_to_pattern[vid] = "spear_phisher"
    cred_tester_victims = selected[offset : offset + counts[9]]
    offset += counts[9]
    for vid in cred_tester_victims:
        victim_to_pattern[vid] = "credential_tester"
    conn_harvest_victims = selected[offset : offset + counts[10]]
    offset += counts[10]
    for vid in conn_harvest_victims:
        victim_to_pattern[vid] = "connection_harvester"
    sleeper_victims = selected[offset : offset + counts[11]]
    offset += counts[11]
    for vid in sleeper_victims:
        victim_to_pattern[vid] = "sleeper_agent"
    defacement_victims = selected[offset : offset + counts[12]]
    offset += counts[12]
    for vid in defacement_victims:
        victim_to_pattern[vid] = "profile_defacement"
    exec_hunter_victims = selected[offset : offset + counts[13]]
    offset += counts[13]
    for vid in exec_hunter_victims:
        victim_to_pattern[vid] = "executive_hunter"
    credential_phishing_victims = selected[offset : offset + counts[14]]
    offset += counts[14]
    for vid in credential_phishing_victims:
        victim_to_pattern[vid] = "credential_phishing"
    session_hijacking_victims = selected[offset : offset + counts[15]]
    offset += counts[15]
    for vid in session_hijacking_victims:
        victim_to_pattern[vid] = "session_hijacking"
    romance_scam_victims = selected[offset : offset + counts[16]]

    print("Generating attack patterns...")
    
    # Collect output lines for aligned printing
    output_lines = []

    for i, vid in enumerate(smash_victims):
        base = now - timedelta(days=rng.randint(3, 20), hours=rng.randint(0, 23))
        close = i < 2
        evts, counter = smash_and_grab(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            close_account=close,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Smash & Grab", f"{len(evts)} events, close={close}"))

    for vid in slow_victims:
        base = now - timedelta(days=rng.randint(10, 25), hours=rng.randint(0, 23))
        evts, counter = low_and_slow(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Low & Slow", f"{len(evts)} events"))

    for i, vid in enumerate(hopper_victims):
        base = now - timedelta(days=rng.randint(15, 28), hours=rng.randint(0, 23))
        close = i == 0
        evts, counter = country_hopper(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            close_account=close, config=config,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Country Hopper", f"{len(evts)} events, close={close}"))

    for vid in thief_victims:
        base = now - timedelta(days=rng.randint(5, 20), hours=rng.randint(0, 23))
        evts, counter = data_thief(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Data Thief", f"{len(evts)} events"))

    for batch_idx, batch in enumerate([stuffer_batch_1, stuffer_batch_2], 1):
        base = now - timedelta(days=rng.randint(3, 15), hours=rng.randint(0, 23))
        countries = [user_countries.get(v, "US") for v in batch]
        evts, counter = credential_stuffer(
            batch, countries, all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        ids = ", ".join(batch)
        output_lines.append((ids, f"Credential Stuffer batch {batch_idx}", f"{len(evts)} events"))

    for vid in login_storm_victims:
        base = now - timedelta(days=rng.randint(5, 20), hours=rng.randint(0, 23))
        evts, counter = login_storm(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Login Storm", f"{len(evts)} events"))

    for vid in stealth_victims:
        base = now - timedelta(days=rng.randint(5, 25), hours=rng.randint(0, 23))
        evts, counter = stealth_takeover(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Stealth Takeover", f"{len(evts)} events"))

    if scraper_victims:
        base = now - timedelta(days=rng.randint(3, 14), hours=rng.randint(0, 23))
        scraper_countries = [user_countries.get(v, "US") for v in scraper_victims]
        evts, counter = scraper_cluster(
            scraper_victims, scraper_countries, all_user_ids, base, counter, rng,
            user_display_names=user_display_names,
        )
        all_events.extend(evts)
        strategy_used = "random"
        if evts:
            strategy_used = evts[-1].metadata.get("scrape_strategy", "unknown")
        ids = ", ".join(scraper_victims)
        output_lines.append((ids, f"Scraper Cluster (strategy={strategy_used})", f"{len(evts)} events"))

    for vid in spear_victims:
        base = now - timedelta(days=rng.randint(3, 18), hours=rng.randint(0, 23))
        evts, counter = spear_phisher(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        num_phish_msgs = sum(1 for e in evts if e.interaction_type == InteractionType.MESSAGE_USER)
        output_lines.append((vid, "Spear Phisher", f"{len(evts)} events ({num_phish_msgs} targeted messages)"))

    if cred_tester_victims:
        base = now - timedelta(days=rng.randint(2, 10), hours=rng.randint(0, 23))
        cred_countries = [user_countries.get(v, "US") for v in cred_tester_victims]
        evts, counter = credential_tester(
            cred_tester_victims, cred_countries, all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        ids = ", ".join(cred_tester_victims)
        output_lines.append((ids, "Credential Tester", f"{len(evts)} events"))

    for vid in conn_harvest_victims:
        base = now - timedelta(days=rng.randint(3, 15), hours=rng.randint(0, 23))
        evts, counter = connection_harvester(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        num_connects = sum(1 for e in evts if e.interaction_type == InteractionType.CONNECT_WITH_USER)
        output_lines.append((vid, "Connection Harvester", f"{len(evts)} events ({num_connects} connection requests)"))

    for vid in sleeper_victims:
        base = now - timedelta(days=rng.randint(25, 40), hours=rng.randint(0, 23))
        evts, counter = sleeper_agent(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
        )
        all_events.extend(evts)
        num_checkins = sum(1 for e in evts if e.metadata.get("checkin_sequence"))
        num_spam = sum(1 for e in evts if e.interaction_type == InteractionType.MESSAGE_USER)
        output_lines.append((vid, "Sleeper Agent", f"{len(evts)} events ({num_checkins} check-ins, {num_spam} spam)"))

    for vid in defacement_victims:
        base = now - timedelta(days=rng.randint(3, 20), hours=rng.randint(0, 23))
        evts, counter = profile_defacement(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        num_deface = sum(
            1 for e in evts
            if e.interaction_type in (InteractionType.CHANGE_NAME, InteractionType.CHANGE_PROFILE)
        )
        output_lines.append((vid, "Profile Defacement", f"{len(evts)} events ({num_deface} profile/name changes)"))

    if exec_hunter_victims:
        base = now - timedelta(days=rng.randint(5, 15), hours=rng.randint(0, 23))
        exec_countries = [user_countries.get(v, "US") for v in exec_hunter_victims]
        # Use user_headlines if available, otherwise fall back to display_names
        headlines_map = user_headlines or user_display_names or {}
        evts, counter = executive_hunter(
            exec_hunter_victims, exec_countries, all_user_ids, headlines_map,
            base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        ids = ", ".join(exec_hunter_victims)
        # Count messages sent
        num_messages = sum(1 for e in evts if e.interaction_type == InteractionType.MESSAGE_USER)
        output_lines.append((ids, "Executive Hunter", f"{len(evts)} events ({num_messages} targeted messages)"))

    for vid in credential_phishing_victims:
        base = now - timedelta(days=rng.randint(3, 20), hours=rng.randint(0, 23))
        evts, counter = credential_phishing(
            vid, user_countries.get(vid, "US"), base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        output_lines.append((vid, "Credential Phishing", f"{len(evts)} events"))

    for vid in session_hijacking_victims:
        base = now - timedelta(days=rng.randint(3, 18), hours=rng.randint(0, 23))
        evts, counter = session_hijacking(
            vid, user_countries.get(vid, "US"), all_user_ids, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        num_views = sum(1 for e in evts if e.interaction_type == InteractionType.VIEW_USER_PAGE)
        output_lines.append((vid, "Session Hijacking", f"{len(evts)} events ({num_views} profile views)"))

    scammer_candidates = [u for u in all_user_ids if u not in fishy_ids and u not in selected]
    for vid in romance_scam_victims:
        if not scammer_candidates:
            scammer_candidates = [u for u in all_user_ids if u != vid]
        if not scammer_candidates:
            continue
        scammer_id = rng.choice(scammer_candidates)
        # Romance scam spans 7-60 days; base must be far enough back so events don't exceed now
        base = now - timedelta(days=rng.randint(65, 90), hours=rng.randint(0, 23))
        evts, counter = romance_scam(
            vid, scammer_id, base, counter, rng,
            config=config,
        )
        all_events.extend(evts)
        victim_to_pattern[scammer_id] = "romance_scam"  # scammer is user_id in events
        num_msgs = sum(1 for e in evts if e.interaction_type == InteractionType.MESSAGE_USER)
        output_lines.append((vid, "Romance Scam", f"{len(evts)} events ({num_msgs} messages)"))

    fake_ids = fake_account_user_ids or []
    for vid in fake_ids:
        if vid not in all_user_ids:
            continue
        base = now - timedelta(days=rng.randint(20, 28), hours=rng.randint(0, 23))
        evts, counter = fake_account(vid, all_user_ids, base, counter, rng, config=config)
        all_events.extend(evts)
        victim_to_pattern[vid] = "fake_account"
        output_lines.append((vid, "Fake Account", f"{len(evts)} events"))

    # Account farming: buyer takeover flow
    farming_ids = [uid for uid in (account_farming_user_ids or []) if uid in all_user_ids]
    if farming_ids:
        base = now - timedelta(days=rng.randint(25, 35), hours=rng.randint(0, 23))
        evts, counter = account_farming(farming_ids, all_user_ids, base, counter, rng, config=config)
        all_events.extend(evts)
        ids = ", ".join(farming_ids[:3]) + ("..." if len(farming_ids) > 3 else "")
        output_lines.append((ids, "Account Farming", f"{len(evts)} events ({len(farming_ids)} accounts)"))

    # Coordinated harassment: same targets, multiple harassers
    harass_ids = [uid for uid in (harassment_user_ids or []) if uid in all_user_ids]
    if harass_ids:
        targets = [uid for uid in all_user_ids if uid not in set(harass_ids)]
        rng.shuffle(targets)
        num_targets = get_cfg(config, "fraud", "coordinated_harassment", "num_targets", default=5)
        harass_targets = targets[:min(num_targets, len(targets))]
        base = now - timedelta(days=rng.randint(2, 10), hours=rng.randint(0, 23))
        evts, counter = coordinated_harassment(harass_ids, harass_targets, base, counter, rng, config=config)
        all_events.extend(evts)
        num_msgs = sum(1 for e in evts if e.interaction_type == InteractionType.MESSAGE_USER)
        output_lines.append((", ".join(harass_ids), "Coordinated Harassment", f"{len(evts)} events ({num_msgs} messages)"))

    # Coordinated like inflation: same target (post author)
    like_ids = [uid for uid in (like_inflation_user_ids or []) if uid in all_user_ids]
    if like_ids:
        targets = [uid for uid in all_user_ids if uid not in set(like_ids)]
        if targets:
            target = rng.choice(targets)
            base = now - timedelta(days=rng.randint(1, 7), hours=rng.randint(0, 23))
            evts, counter = coordinated_like_inflation(like_ids, target, base, counter, rng, config=config)
            all_events.extend(evts)
            num_likes = sum(1 for e in evts if e.interaction_type == InteractionType.LIKE)
            output_lines.append((", ".join(like_ids), "Coordinated Like Inflation", f"{len(evts)} events ({num_likes} likes on {target})"))

    # Profile cloning: impersonate victims
    clone_ids = [uid for uid in (profile_cloning_user_ids or []) if uid in all_user_ids]
    if clone_ids:
        targets = [uid for uid in all_user_ids if uid not in set(clone_ids)]
        if targets:
            victims = rng.sample(targets, min(5, len(targets)))
            base = now - timedelta(days=rng.randint(2, 10), hours=rng.randint(0, 23))
            evts, counter = profile_cloning(clone_ids, victims, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(clone_ids), "Profile Cloning", f"{len(evts)} events"))

    # Endorsement inflation
    endorse_ids = [uid for uid in (endorsement_inflation_user_ids or []) if uid in all_user_ids]
    if endorse_ids:
        targets = [uid for uid in all_user_ids if uid not in set(endorse_ids)]
        if targets:
            victims = rng.sample(targets, min(10, len(targets)))
            base = now - timedelta(days=rng.randint(1, 7), hours=rng.randint(0, 23))
            evts, counter = endorsement_inflation(endorse_ids, victims, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(endorse_ids), "Endorsement Inflation", f"{len(evts)} events"))

    # Recommendation fraud
    recommend_ids = [uid for uid in (recommendation_fraud_user_ids or []) if uid in all_user_ids]
    if recommend_ids:
        targets = [uid for uid in all_user_ids if uid not in set(recommend_ids)]
        if targets:
            victims = rng.sample(targets, min(len(recommend_ids) * 2, len(targets)))
            base = now - timedelta(days=rng.randint(1, 5), hours=rng.randint(0, 23))
            evts, counter = recommendation_fraud(recommend_ids, victims, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(recommend_ids), "Recommendation Fraud", f"{len(evts)} events"))

    # Job posting scam
    job_ids = [uid for uid in (job_scam_user_ids or []) if uid in all_user_ids]
    if job_ids:
        targets = [uid for uid in all_user_ids if uid not in set(job_ids)]
        if targets:
            base = now - timedelta(days=rng.randint(2, 7), hours=rng.randint(0, 23))
            evts, counter = job_posting_scam(job_ids, targets, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(job_ids), "Job Posting Scam", f"{len(evts)} events"))

    # Invitation spam
    invite_ids = [uid for uid in (invitation_spam_user_ids or []) if uid in all_user_ids]
    if invite_ids:
        targets = [uid for uid in all_user_ids if uid not in set(invite_ids)]
        if targets:
            base = now - timedelta(days=rng.randint(1, 5), hours=rng.randint(0, 23))
            evts, counter = invitation_spam(invite_ids, targets, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(invite_ids), "Invitation Spam", f"{len(evts)} events"))

    # Group spam
    grp_ids = [uid for uid in (group_spam_user_ids or []) if uid in all_user_ids]
    if grp_ids:
        groups_map = user_groups_joined or {}
        base = now - timedelta(days=rng.randint(14, 30), hours=rng.randint(0, 23))
        evts, counter = group_spam(grp_ids, groups_map, base, counter, rng, config=config)
        all_events.extend(evts)
        output_lines.append((", ".join(grp_ids), "Group Spam", f"{len(evts)} events"))

    # Ad engagement fraud (use invitation_spam or group_spam as bots to avoid CLOSE_ACCOUNT conflict)
    ad_bot_ids = invite_ids or grp_ids
    if ad_bot_ids:
        available_bots = rng.sample(ad_bot_ids, min(5, len(ad_bot_ids)))
        if available_bots:
            base = now - timedelta(days=rng.randint(2, 10), hours=rng.randint(0, 23))
            bot_ids = rng.sample(available_bots, min(5, len(available_bots)))
            evts, counter = ad_engagement_fraud(available_bots, base, counter, rng, config=config)
            all_events.extend(evts)
            output_lines.append((", ".join(available_bots), "Ad Engagement Fraud", f"{len(evts)} events"))

    # Format and print aligned output
    if output_lines:
        # Truncate attack types if needed and find max widths
        formatted_lines = []
        for user_ids, attack_type, details in output_lines:
            if len(attack_type) > 20:
                attack_type = attack_type[:20] + "..."
            formatted_lines.append((user_ids, attack_type, details))
        
        max_id_width = max(len(line[0]) for line in formatted_lines)
        max_attack_width = max(len(line[1]) for line in formatted_lines)
        
        for user_ids, attack_type, details in formatted_lines:
            print(f"  {user_ids:<{max_id_width}}  {attack_type:<{max_attack_width}}  {details}")

    all_events.sort(key=lambda e: e.timestamp)

    # Assign session IDs to fraud events (prefix "a" to distinguish from legit)
    _assign_fraud_session_ids(all_events)

    enforce_login_first_invariant(all_events)
    enforce_spam_after_login_invariant(all_events)

    victims = set()
    for e in all_events:
        victims.add(e.user_id)
    msg_count = sum(1 for e in all_events if e.interaction_type == InteractionType.MESSAGE_USER)
    close_count = sum(1 for e in all_events if e.interaction_type == InteractionType.CLOSE_ACCOUNT)

    patterns_used = sorted(set(victim_to_pattern.values()))
    print(f"\nSummary:")
    print(f"  Victims:         {len(victims)}")
    print(f"  Total events:    {len(all_events)}")
    print(f"  Spam messages:   {msg_count}")
    print(f"  Accounts closed: {close_count}")
   
    return all_events, victim_to_pattern


__all__ = ["generate_malicious_events"]
