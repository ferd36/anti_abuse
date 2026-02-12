"""Executive Hunter: coordinated hosting IP cluster targeting CEOs & Founders.

A sophisticated attack targeting high-value executive accounts:
  - Uses a cluster of hosting IPs (similar to scraper cluster).
  - Targets only users with CEO, Founder, or C-level titles in their headline.
  - Each compromised account sends targeted spear-phishing messages.
  - Messages are crafted for executive audiences (wire transfers, urgent approvals,
    board meetings, acquisitions).
  - Low volume per account to evade rate limits, but coordinated across cluster.

Behavioral fingerprints:
  - Hosting IPs from related subnets.
  - View-then-message pattern (reconnaissance before sending).
  - Executive-focused message content with urgency and authority.
  - Multiple accounts from the same IP cluster targeting the same exec victims.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import (
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_hosting_ip,
)

# Executive-targeted phishing messages with urgency and authority
_EXEC_PHISH_METADATA = [
    {"message_length": 320, "contains_url": True, "is_spam": True,
     "phish_pretext": "wire_transfer_approval",
     "message_text": "Urgent: The $2.3M wire transfer for the Acme acquisition needs your approval by EOD. Our CFO is traveling and unreachable. Please authorize here: https://wire-approve.secure.bank/tx/8847 or we'll miss the closing deadline."},
    {"message_length": 285, "contains_url": True, "is_spam": True,
     "phish_pretext": "board_meeting",
     "message_text": "The emergency board meeting has been moved to 9 AM tomorrow. We need your vote on the merger proposal. Review the materials here: https://boardroom.company.io/meeting/urgent and confirm attendance. This is time-sensitive."},
    {"message_length": 240, "contains_url": False, "is_spam": True,
     "phish_pretext": "ceo_impersonation",
     "message_text": "This is sensitive. I'm in meetings all day and need you to handle a vendor payment. Can you process $450K to the account I'll send separately? Our usual CFO approval process is too slow for this deadline."},
    {"message_length": 310, "contains_url": True, "is_spam": True,
     "phish_pretext": "legal_document",
     "message_text": "The NDA for the confidential partnership needs your signature immediately. Legal cleared it this morning. Sign here: https://legal-docs.company.net/sign/nda-2847. We can't proceed with discussions until this is executed. Please prioritize."},
    {"message_length": 270, "contains_url": True, "is_spam": True,
     "phish_pretext": "investor_update",
     "message_text": "Confidential investor update: the Series C term sheet is ready. Review and approve before the board call: https://investor-portal.company.io/terms. This stays between us until the formal announcement. Time is critical here."},
    {"message_length": 195, "contains_url": False, "is_spam": True,
     "phish_pretext": "urgent_credentials",
     "message_text": "IT flagged your account for suspicious activity. For security, please verify your credentials with me directly. Don't use the normal channels—this is a targeted attack investigation."},
    {"message_length": 340, "contains_url": True, "is_spam": True,
     "phish_pretext": "acquisition_bid",
     "message_text": "Strictly confidential: we've received an unsolicited acquisition bid from a strategic buyer. The offer is compelling but time-limited. Review the term sheet here: https://ma-deals.advisors.com/bid/xyz before our call at 3 PM. Don't share this with anyone until we discuss strategy."},
    {"message_length": 220, "contains_url": False, "is_spam": True,
     "phish_pretext": "payroll_emergency",
     "message_text": "Payroll system is down and we need to process today's run manually. Can you approve the batch transfer for $1.8M? I'll send the account details. HR is panicking—employees need to be paid on time."},
]


def executive_hunter(
    attacker_ids: list[str],
    attacker_countries: list[str],
    all_user_ids: list[str],
    user_headlines: dict[str, str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Coordinated executive targeting campaign: multiple compromised accounts
    from hosting IPs target CEOs and Founders with spear-phishing messages.

    Args:
        attacker_ids:       User IDs of compromised accounts (the senders).
        attacker_countries: Home countries of the attacker accounts.
        all_user_ids:       Full user population.
        user_headlines:     {user_id: headline} to identify executives.
        base_time:          Campaign start time.
        counter:            Global event counter.
        rng:                Seeded random generator.

    Returns:
        (events, counter) — the attack events and updated counter.
    """
    cfg = config or {}
    cluster_max = get_cfg(cfg, "fraud", "executive_hunter", "cluster_ips_max", default=4)
    num_targets_min = get_cfg(cfg, "fraud", "executive_hunter", "num_targets_min", default=15)
    num_targets_max = get_cfg(cfg, "fraud", "executive_hunter", "num_targets_max", default=40)
    fallback_max = get_cfg(cfg, "fraud", "executive_hunter", "fallback_targets_max", default=30)

    events: list = []
    attacker_country = pick_attacker_country(attacker_countries[0], rng)

    # Cluster of related hosting IPs (coordinated attack infrastructure)
    cluster_ips = [pick_hosting_ip(rng) for _ in range(min(len(attacker_ids) + 1, cluster_max))]

    # Find executive targets: CEO, Founder, C-level titles
    exec_keywords = ["CEO", "Founder", "Chief Executive", "Co-Founder", "Managing Partner"]
    exec_targets = []
    attacker_set = set(attacker_ids)
    
    for uid in all_user_ids:
        if uid in attacker_set:
            continue
        headline = user_headlines.get(uid, "")
        if any(keyword.lower() in headline.lower() for keyword in exec_keywords):
            exec_targets.append(uid)
    
    # If no execs found, fall back to random high-value targets
    if not exec_targets:
        exec_targets = [uid for uid in all_user_ids if uid not in attacker_set]
        rng.shuffle(exec_targets)
        exec_targets = exec_targets[:fallback_max]
    
    # Shuffle and limit targets
    rng.shuffle(exec_targets)
    num_targets_total = min(len(exec_targets), rng.randint(num_targets_min, num_targets_max))
    exec_targets = exec_targets[:num_targets_total]

    ts = base_time

    # --- Phase 1: Each attacker account logs in from hosting IP ---
    latest_login_ts = ts
    for idx, aid in enumerate(attacker_ids):
        ip = cluster_ips[idx % len(cluster_ips)]
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # Stagger logins slightly
        login_ts = ts + timedelta(minutes=rng.randint(0, 20))
        login_evts, counter, login_ts = make_login_with_failures(
            aid, login_ts, ip, counter, rng, "executive_hunter",
            extra_metadata={
                "attacker_country": attacker_country,
                "user_agent": ua,
                "ip_cluster_id": f"cluster_{cluster_ips[0][:10]}",
            },
        )
        events.extend(login_evts)
        latest_login_ts = max(latest_login_ts, login_ts)

    ts = latest_login_ts + timedelta(minutes=rng.randint(10, 30))

    # --- Phase 2: Distribute executive targets across attacker accounts ---
    # Each attacker gets a subset of targets to avoid concentration
    targets_per_attacker = max(1, len(exec_targets) // len(attacker_ids))
    
    for idx, aid in enumerate(attacker_ids):
        ip = cluster_ips[idx % len(cluster_ips)]
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # Get this attacker's subset of targets
        start_idx = idx * targets_per_attacker
        end_idx = start_idx + targets_per_attacker
        if idx == len(attacker_ids) - 1:  # Last attacker gets remainder
            end_idx = len(exec_targets)
        
        attacker_targets = exec_targets[start_idx:end_idx]
        
        # For each target: view profile → send targeted message
        for target_uid in attacker_targets:
            # Reconnaissance: view the executive's profile
            ts += timedelta(minutes=rng.randint(5, 20))
            counter += 1
            events.append(make_event(
                counter, aid, InteractionType.VIEW_USER_PAGE, ts, ip,
                target_user_id=target_uid,
                metadata={
                    "attack_pattern": "executive_hunter",
                    "ip_country": attacker_country,
                    "user_agent": ua,
                    "ip_cluster_id": f"cluster_{cluster_ips[0][:10]}",
                    "target_type": "executive",
                    "recon": True,
                },
                ip_type=IPType.HOSTING,
            ))
            
            # Send targeted executive phishing message
            ts += timedelta(minutes=rng.randint(10, 45))
            counter += 1
            meta = dict(rng.choice(_EXEC_PHISH_METADATA))
            meta["attack_pattern"] = "executive_hunter"
            meta["ip_country"] = attacker_country
            meta["user_agent"] = ua
            meta["ip_cluster_id"] = f"cluster_{cluster_ips[0][:10]}"
            meta["target_type"] = "executive"
            
            events.append(make_event(
                counter, aid, InteractionType.MESSAGE_USER, ts, ip,
                target_user_id=target_uid,
                metadata=meta,
                ip_type=IPType.HOSTING,
            ))
            
            # Add some variance to mimic human pacing
            ts += timedelta(minutes=rng.randint(15, 60))

    return events, counter
