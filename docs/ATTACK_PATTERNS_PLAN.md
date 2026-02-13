# Plan: Adding New Attack Patterns

This document outlines the plan to add 10 new attack patterns to the anti-abuse system. It covers core model changes, invariants, config, and implementation order.

---

## 1. New Attack Patterns (Summary)

| Pattern | Category | Needs Fishy Accounts | Key Interactions |
|---------|----------|---------------------|------------------|
| profile_cloning | ATO/impersonation | Yes | VIEW, CONNECT, MESSAGE (impersonating victim) |
| endorsement_inflation | Credibility gaming | Yes | ENDORSE_SKILL |
| recommendation_fraud | Credibility gaming | Yes | GIVE_RECOMMENDATION |
| job_posting_scam | Phishing/harvest | Yes (or victim) | CREATE_JOB, APPLY_TO_JOB, VIEW_JOB |
| invitation_spam | Graph harvesting | Yes | SEND_CONNECTION_REQUEST (mass) |
| group_spam | Infiltration | Yes | JOIN_GROUP, POST_IN_GROUP |
| romance_scam | Long-con fraud | Victim-based | MESSAGE_USER (extended DM thread) |
| session_hijacking | Token theft | Victim-based | SESSION_LOGIN (or LOGIN + flag) |
| credential_phishing | Phishing | Victim-based | PHISHING_LOGIN |
| ad_engagement_fraud | Ad fraud | Yes | AD_VIEW, AD_CLICK |

---

## 2. Core Model Changes

### 2.1 InteractionType (core/enums.py)

**New enum values:**

```python
# Credibility / LinkedIn-specific
ENDORSE_SKILL = "endorse_skill"           # Endorse someone's skill (target_user_id, skill_id in metadata)
GIVE_RECOMMENDATION = "give_recommendation"  # Write recommendation for target (target_user_id)
CREATE_JOB_POSTING = "create_job_posting"   # Create job (no target; job_id in metadata)
APPLY_TO_JOB = "apply_to_job"               # Apply to job (job_id in metadata; target_user_id = poster?)
VIEW_JOB = "view_job"                       # View job listing (job_id in metadata)
SEND_CONNECTION_REQUEST = "send_connection_request"  # Same as CONNECT_WITH_USER semantically; or alias
JOIN_GROUP = "join_group"                   # Join group (group_id in metadata)
LEAVE_GROUP = "leave_group"                 # Leave group (group_id in metadata)
POST_IN_GROUP = "post_in_group"             # Post in group (group_id in metadata; optional target for reply)
AD_VIEW = "ad_view"                         # View ad (ad_id in metadata)
AD_CLICK = "ad_click"                       # Click ad (ad_id in metadata)
# Auth anomaly
SESSION_LOGIN = "session_login"              # Login via stolen session token (no password)
PHISHING_LOGIN = "phishing_login"            # Credential capture event (fake login page)
```

**Target rules:**
- `ENDORSE_SKILL`, `GIVE_RECOMMENDATION`: require `target_user_id`
- `CREATE_JOB_POSTING`: no target
- `APPLY_TO_JOB`, `VIEW_JOB`: `target_user_id` = job poster (optional); `job_id` in metadata
- `JOIN_GROUP`, `LEAVE_GROUP`: no target; `group_id` in metadata
- `POST_IN_GROUP`: optional target (reply-to); `group_id` in metadata
- `AD_VIEW`, `AD_CLICK`: no target; `ad_id` in metadata
- `SESSION_LOGIN`, `PHISHING_LOGIN`: no target (like LOGIN)

**Invariant update (UserInteraction):**
- Add `_REQUIRES_TARGET`: ENDORSE_SKILL, GIVE_RECOMMENDATION
- Add `_NO_TARGET`: CREATE_JOB_POSTING, JOIN_GROUP, LEAVE_GROUP, POST_IN_GROUP, AD_VIEW, AD_CLICK, SESSION_LOGIN, PHISHING_LOGIN
- APPLY_TO_JOB, VIEW_JOB: optional target (may need new `_OPTIONAL_TARGET` set and validation logic)

### 2.2 UserProfile (core/models.py)

**New field (optional, for profile cloning):**

```python
cloned_from_user_id: str | None = None  # If set, this profile impersonates that user
```

**Invariants:**
- `cloned_from_user_id` must be None or a non-empty string
- If set, must differ from `user_id` (cannot clone self)
- Validated in `__post_init__`

### 2.3 UserInteraction metadata conventions

Standard metadata keys for new patterns:

| Pattern | Required Keys | Optional Keys |
|---------|---------------|---------------|
| endorsement_inflation | `attack_pattern`, `skill_id`, `ip_country` | |
| recommendation_fraud | `attack_pattern`, `recommendation_text`, `ip_country` | |
| job_posting_scam | `attack_pattern`, `job_id`, `ip_country` | `job_title`, `phishing_url` |
| invitation_spam | `attack_pattern`, `ip_country`, `ip_cluster` | `batch_size` |
| group_spam | `attack_pattern`, `group_id`, `ip_country` | `post_content` |
| romance_scam | `attack_pattern`, `ip_country`, `scam_phase` | `message_count` |
| session_hijacking | `attack_pattern`, `ip_country`, `session_stolen` | `original_session_id` |
| credential_phishing | `attack_pattern`, `ip_country`, `phishing_site` | |
| ad_engagement_fraud | `attack_pattern`, `ad_id`, `ip_country` | `advertiser_id` |

---

## 3. Fishy Account Types (mock_data / config)

**New fishy account counts in `fishy_accounts`:**

```python
"num_profile_cloning": 8,
"num_endorsement_inflation": 12,
"num_recommendation_fraud": 10,
"num_job_scam": 6,
"num_invitation_spam": 15,
"num_group_spam": 8,
```

**Note:** Romance scam, session hijacking, credential phishing, ad fraud are **victim-based** (ATO on existing legit users), not pre-created fishy accounts. They integrate into `generate_malicious_events` as new pattern types.

---

## 4. Temporal Invariants (core/validate.py)

**New invariants:**

1. **ENDORSE_SKILL**: LOGIN before ENDORSE; target must exist
2. **GIVE_RECOMMENDATION**: CONNECT_WITH_USER (or connection exists) before GIVE_RECOMMENDATION; target must be a connection
3. **CREATE_JOB_POSTING**: LOGIN before CREATE_JOB
4. **APPLY_TO_JOB**: VIEW_JOB before APPLY_TO_JOB (optional); LOGIN before both
5. **JOIN_GROUP**: LOGIN before JOIN_GROUP
6. **POST_IN_GROUP**: JOIN_GROUP before POST_IN_GROUP for that group
7. **SEND_CONNECTION_REQUEST**: LOGIN before SEND; rate limits (many per hour = spam)
8. **SESSION_LOGIN**: No preceding LOGIN from same IP in same session (different IP = hijack)
9. **PHISHING_LOGIN**: Distinct from normal LOGIN (different session, no prior success)
10. **AD_VIEW/AD_CLICK**: Minimal (no strict ordering; possible burst = fraud)

**Non-fraud (legit) invariants:**
- Normal users: no SESSION_LOGIN, no PHISHING_LOGIN
- DOWNLOAD_ADDRESS_BOOK: already restricted for normals
- ENDORSE_SKILL, GIVE_RECOMMENDATION: legit users can do these; fraud = bulk/ring behavior

---

## 5. Config (config.py)

### 5.1 fishy_accounts

```python
"num_profile_cloning": 8,
"num_endorsement_inflation": 12,
"num_recommendation_fraud": 10,
"num_job_scam": 6,
"num_invitation_spam": 15,
"num_group_spam": 8,
"profiles": {
    # ... existing ...
    "profile_cloning_has_photo_pct": 0.9,  # Clones copy victim's photo
    "endorsement_inflation_endorsements_max": 50,
    "recommendation_fraud_recommendations_max": 5,
},
```

### 5.2 fraud.pattern_weights (victim-based patterns)

Add to `_FRAUD_PATTERN_ORDER` and weights:

```python
"romance_scam": 0.04,
"session_hijacking": 0.03,
"credential_phishing": 0.04,
"ad_engagement_fraud": 0.02,
```

### 5.3 fraud.<pattern> (pattern-specific)

```python
"profile_cloning": {
    "messages_per_victim_min": 3,
    "messages_per_victim_max": 15,
    "connect_before_message_pct": 0.7,
},
"endorsement_inflation": {
    "endorsements_per_skill_min": 5,
    "endorsements_per_skill_max": 20,
    "cluster_ips_max": 4,
},
"recommendation_fraud": {
    "recommendations_per_pair": 1,
    "cluster_ips_max": 4,
},
"job_posting_scam": {
    "applications_per_job_min": 10,
    "applications_per_job_max": 100,
    "phishing_redirect_pct": 0.4,
},
"invitation_spam": {
    "requests_per_account_min": 50,
    "requests_per_account_max": 200,
    "cluster_ips_max": 4,
},
"group_spam": {
    "posts_per_group_min": 3,
    "posts_per_group_max": 15,
    "groups_per_account_min": 1,
    "groups_per_account_max": 5,
},
"romance_scam": {
    "messages_per_victim_min": 20,
    "messages_per_victim_max": 100,
    "duration_days_min": 7,
    "duration_days_max": 60,
},
"session_hijacking": {
    "actions_after_hijack_min": 5,
    "actions_after_hijack_max": 30,
},
"credential_phishing": {
    "capture_then_login_pct": 0.8,
},
"ad_engagement_fraud": {
    "clicks_per_ad_min": 10,
    "clicks_per_ad_max": 500,
    "cluster_ips_max": 4,
},
```

### 5.4 Config validation

- Add new `num_*` keys to `_validate` int-check
- Ensure `pattern_weights` sum remains reasonable (or keep relative)
- All `*_pct` in [0, 1]

---

## 6. Database Schema (db/repository.py)

### 6.1 user_profiles

```sql
ALTER TABLE user_profiles ADD COLUMN cloned_from_user_id TEXT REFERENCES users(user_id);
```

Migration: nullable, default NULL.

### 6.2 user_interactions

No schema change. New `interaction_type` values stored as strings. `metadata` JSON already flexible.

### 6.3 Indexes (optional)

```sql
CREATE INDEX IF NOT EXISTS idx_interactions_group ON user_interactions(metadata) WHERE interaction_type IN ('join_group','post_in_group','leave_group');
```

(JSON extraction for group_id may require application-level query; index optional.)

---

## 7. ML Features (ml/features.py)

**New features to consider:**

| Feature | Description |
|---------|-------------|
| endorsement_rate_24h | Endorsements given per hour (burst = inflation) |
| recommendation_count | Number of recommendations given |
| job_applications_24h | Applications sent (burst = scam) |
| connection_requests_24h | Connection requests sent (spam) |
| group_joins_24h | Groups joined in 24h |
| group_posts_24h | Posts in groups |
| session_ip_change | Same user, different IP (hijacking signal) |
| ad_click_rate | Clicks per view (fraud) |
| cloned_profile | Boolean: cloned_from_user_id set |

**ACTION_VOCAB / sequence encoder:** Add actions for new InteractionTypes. Ensure order is consistent.

---

## 8. Implementation Order

**Phase 1: Core + Schema (no fraud gen yet)**
1. Add InteractionType enum values
2. Update UserInteractiontarget rules
3. Add UserProfile.cloned_from_user_id
4. DB migration for cloned_from_user_id
5. Update core/validate temporal invariants for new types

**Phase 2: Config**
6. Add fishy_accounts entries
7. Add fraud.pattern_weights and fraud.<pattern> params
8. Update _validate()

**Phase 3: Fishy account generation (mock_data)**
9. Add _generate_profile_cloning_users, etc.
10. Add _generate_profiles logic for cloned_from_user_id
11. Wire into generate_all

**Phase 4: Fraud event generators (data/fraud/)**
12. profile_cloning.py
13. endorsement_inflation.py
14. recommendation_fraud.py
15. job_posting_scam.py
16. invitation_spam.py
17. group_spam.py
18. romance_scam.py
19. session_hijacking.py
20. credential_phishing.py
21. ad_engagement_fraud.py

**Phase 5: Integration**
22. Wire new fishy IDs into generate_malicious_events
23. Add victim-based patterns to _distribute_victims and event generation
24. Update generate.py to pass new user ID lists

**Phase 6: ML**
25. Add new features to FEATURE_NAMES
26. Update _compute_user_features
27. Update ACTION_VOCAB, sequence encoder
28. Retrain model if needed

---

## 9. Test Requirements

- Unit tests for each new fraud pattern (data/fraud/<pattern>.py)
- Temporal invariant tests for new interaction types
- Config validation tests for new keys
- Mock data tests for new fishy account types
- Integration test: generate_all with new config produces valid corpus

---

## 10. Generation Pattern / Label Updates

**Places that reference attack pattern names:**

- `core/models.User.generation_pattern` – any non-empty string allowed
- `data/mock_data.py` – `is_*` lambdas, `excluded_ids` for legit event generation
- `data/fraud/__init__.py` – `_FRAUD_PATTERN_ORDER`, `victim_to_pattern` mapping
- `generate.py` – extraction of user IDs by `generation_pattern`
- `api/static/index.html` – badge display for fraud labels
- `tests/test_mock_data.py` – `fishy_patterns` set for validation

**New pattern names to add everywhere:**

- `profile_cloning`, `endorsement_inflation`, `recommendation_fraud`
- `job_posting_scam`, `invitation_spam`, `group_spam`
- `romance_scam`, `session_hijacking`, `credential_phishing`, `ad_engagement_fraud`

---

## 11. Open Questions

1. **SEND_CONNECTION_REQUEST vs CONNECT_WITH_USER**: Use existing CONNECT_WITH_USER for invitation spam (invitation = CONNECT initiator), or add SEND_CONNECTION_REQUEST for the request event vs acceptance?
2. **APPLY_TO_JOB target**: Is target_user_id the job poster or the applicant? (Applicant = user_id; poster = target?)
3. **Group model**: Do we need a Group entity, or is group_id in metadata sufficient?
4. **Ad model**: Same for ads—ad_id in metadata sufficient?
5. **Session vs LOGIN**: SESSION_LOGIN as distinct type vs LOGIN with metadata `session_stolen=True`?
