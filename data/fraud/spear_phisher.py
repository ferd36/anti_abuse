"""Spear Phisher: targeted impersonation attack against the victim's connections.

Unlike mass-spam patterns, the attacker:
  - Uses a residential IP to blend in with legitimate traffic.
  - Optionally tweaks the profile/name to enhance the impersonation.
  - Researches each target by viewing their profile first (reconnaissance).
  - Sends a longer, personalised message shortly after each recon view.
  - Targets only 5-15 users (the victim's high-value connections).
  - Keeps the account open to maintain the impersonation.

The 1:1 view-then-message cadence with realistic human-like delays
is the primary behavioral fingerprint.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.enums import InteractionType, IPType

from data.config_utils import get_cfg
from ._common import (
    ALT_USER_AGENTS,
    make_event,
    make_login_with_failures,
    pick_attacker_country,
    pick_residential_ip,
)

# Spear-phish messages are longer and more varied than generic spam.
# Some contain URLs (fake invoices, shared docs), others are pure social
# engineering (urgency, authority, familiarity).
_SPEAR_PHISH_METADATA = [
    {"message_length": 280, "contains_url": True, "is_spam": True,
     "phish_pretext": "shared_document",
     "message_text": "Hi! I've shared a document with you that needs your review. It's time-sensitive. Please access it here: https://docs-share.company.com/view/abc123. Let me know once you've had a chance to look."},
    {"message_length": 195, "contains_url": True, "is_spam": True,
     "phish_pretext": "invoice",
     "message_text": "Your invoice #8847 is ready. We noticed an issue with your payment method. Please update your details here: https://billing-portal.com/secure to avoid service interruption."},
    {"message_length": 310, "contains_url": True, "is_spam": True,
     "phish_pretext": "calendar_invite",
     "message_text": "You're invited to an important meeting with the leadership team. Please confirm your attendance by accepting the calendar invite: https://meet.company.com/join/xyz. The agenda covers Q4 strategy and we need your input. See you there!"},
    {"message_length": 150, "contains_url": False, "is_spam": True,
     "phish_pretext": "urgent_request",
     "message_text": "I need your help urgently. Can you approve this transfer by end of day? My usual contact is out. Please reply ASAP."},
    {"message_length": 230, "contains_url": False, "is_spam": True,
     "phish_pretext": "job_opportunity",
     "message_text": "I came across your profile and think you'd be great for a role we're hiring for. It's a senior position with a top firm. Interested in learning more? I can share details over a quick call this week."},
    {"message_length": 175, "contains_url": True, "is_spam": True,
     "phish_pretext": "password_reset",
     "message_text": "We detected unusual activity on your account. Reset your password immediately: https://security-reset.com/verify. Ignore this and your account may be locked within 24 hours."},
    {"message_length": 260, "contains_url": False, "is_spam": True,
     "phish_pretext": "wire_transfer",
     "message_text": "The wire details have changed for the vendor payment. Please use the new account information I'm sending separately. This is urgent—we need to process by tomorrow. Call me if you have questions."},
    {"message_length": 340, "contains_url": True, "is_spam": True,
     "phish_pretext": "contract_review",
     "message_text": "The revised contract is ready for your signature. I've made the changes we discussed. Please review and sign here: https://sign.contract.io/d/abc. We need to finalize by Friday for the deal to close on schedule. Let me know if anything looks off."},
]


def spear_phisher(
    victim_id: str,
    victim_country: str,
    all_user_ids: list[str],
    base_time: datetime,
    counter: int,
    rng: random.Random,
    *,
    config: dict | None = None,
) -> tuple[list, int]:
    """
    Targeted impersonation: login → optional profile tweak → for each target
    view their page then send a crafted message → leave account open.

    The attacker uses a residential IP and a plausible user agent to look
    like normal account activity.  The distinguishing signals are:
      - Every MESSAGE_USER is preceded by a VIEW_USER_PAGE to the same target.
      - Messages are longer than typical spam.
      - The account shows a sudden burst of view+message pairs after a
        login from a new country.
    """
    events: list = []
    ip = pick_residential_ip(rng)
    attacker_country = pick_attacker_country(victim_country, rng)
    ua = rng.choice(ALT_USER_AGENTS)
    ts = base_time

    # --- Phase 1: login (few or no failures — attacker has good creds) ---
    login_evts, counter, ts = make_login_with_failures(
        victim_id, ts, ip, counter, rng, "spear_phisher",
        extra_metadata={
            "attacker_country": attacker_country,
            "user_agent": ua,
        },
    )
    events.extend(login_evts)

    # --- Phase 2 (optional): tweak profile to enhance impersonation ---
    ts += timedelta(minutes=rng.randint(2, 20))

    if rng.random() < get_cfg(config, "fraud", "spear_phisher", "profile_tweak_pct", default=0.4):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_PROFILE, ts, ip,
            metadata={
                "attack_pattern": "spear_phisher",
                "ip_country": attacker_country,
                "user_agent": ua,
            },
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(1, 5))

    if rng.random() < get_cfg(config, "fraud", "spear_phisher", "change_name_pct", default=0.3):
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.CHANGE_NAME, ts, ip,
            metadata={
                "attack_pattern": "spear_phisher",
                "ip_country": attacker_country,
                "user_agent": ua,
            },
            ip_type=IPType.RESIDENTIAL,
        ))
        ts += timedelta(minutes=rng.randint(1, 5))

    # --- Phase 3: pick targets (small, curated set) ---
    targets = [uid for uid in all_user_ids if uid != victim_id]
    rng.shuffle(targets)
    num_targets = rng.randint(5, 15)
    phish_targets = targets[:num_targets]

    # --- Phase 4: recon-then-message loop ---
    # Each target: view profile → wait 5-30 min → send crafted message →
    # wait 30 min - 3 hours before moving on to the next target.
    for target in phish_targets:
        # Reconnaissance: view the target's profile
        ts += timedelta(minutes=rng.randint(1, 10))
        counter += 1
        events.append(make_event(
            counter, victim_id, InteractionType.VIEW_USER_PAGE, ts, ip,
            target_user_id=target,
            metadata={
                "attack_pattern": "spear_phisher",
                "ip_country": attacker_country,
                "user_agent": ua,
                "recon": True,
            },
            ip_type=IPType.RESIDENTIAL,
        ))

        # Wait, then send a personalised message to the same target
        ts += timedelta(minutes=rng.randint(5, 30))
        counter += 1
        meta = dict(rng.choice(_SPEAR_PHISH_METADATA))
        meta["attack_pattern"] = "spear_phisher"
        meta["ip_country"] = attacker_country
        meta["user_agent"] = ua
        events.append(make_event(
            counter, victim_id, InteractionType.MESSAGE_USER, ts, ip,
            target_user_id=target,
            metadata=meta,
            ip_type=IPType.RESIDENTIAL,
        ))

        # Cool-down before the next target to mimic human pacing
        ts += timedelta(minutes=rng.randint(30, 180))

    return events, counter
