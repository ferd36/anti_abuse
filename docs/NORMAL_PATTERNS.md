# Normal Usage Patterns

This document describes typical, legitimate user behaviour on the platform. These patterns represent the baseline that fraud detection tries to distinguish from malicious account takeover and abuse.

---

## 1. Casual Browser

**What it is:** A light user who logs in occasionally (about 1–2 times per week), views a few profiles, and sometimes sends a message. Low activity overall.

**Typical behaviour:**
- 1–2 logins per week
- 2–10 profile views per session
- Occasional messages, rarely more than a few per week
- Same country and IP type (usually residential) over time

**How it differs from fraud:** No address book download, no burst of messages, no rapid country changes.

---

## 2. Active Job Seeker

**What it is:** Someone actively looking for work. Frequent logins, many profile views, connection requests, and messages. Activity is spread over days or weeks, not compressed into hours.

**Typical behaviour:**
- Multiple logins per week
- Many profile views (often targeting recruiters or relevant roles)
- Connection requests to people in target companies
- Messages that are personalised, not templated spam
- No address book download

**How it differs from fraud:** High volume but spread over time; no download-then-spam sequence; no hosting IPs or country hopping.

---

## 3. Recruiter

**What it is:** A recruiter or hiring manager (distinct user type) who regularly sources candidates. Uses candidate search, then views profiles and sends connection requests. High volume but steady over time.

**Typical behaviour:**
- Frequent logins (e.g. 3–10 sessions per week)
- Candidate search (SEARCH_CANDIDATES) with filters (role, skills, location) before viewing
- Many profile views and connection requests per session
- Messages that are work-related and often personalised
- Activity follows a consistent schedule (e.g. weekday mornings 9–11)
- Same country; may use corporate IPs

**How it differs from fraud:** Volume is sustained, not a sudden burst; no address book download; no rapid IP or country changes; search-then-view pattern is recruiter-specific.

---

## 4. Regular Networker

**What it is:** An engaged user who logs in regularly (e.g. 2–3 times per week), sends connection requests, views profiles, and occasionally messages. Moderate, steady activity.

**Typical behaviour:**
- Regular logins, roughly same cadence
- Mix of profile views, connection requests, and messages
- Activity spread across the week
- Consistent location and device

**How it differs from fraud:** No rapid spike; no download-then-spam; no suspicious geo or IP patterns.

---

## 5. Returning User

**What it is:** A user who was inactive for weeks or months, then logs in again. They browse, may update their profile, and gradually resume activity.

**Typical behaviour:**
- Long gap since last login
- Login followed by profile views and possibly profile updates
- Low to moderate activity in the first sessions back
- No sudden burst of messages or connections

**How it differs from fraud:** No address book download; no mass messaging; activity builds gradually, not in a single burst.

---

## 5a. Career Update

**What it is:** A user who logs in primarily to update their profile — job headline, summary, or last name (e.g. marriage). Minimal activity: 1–2 sessions of LOGIN → UPDATE_HEADLINE / UPDATE_SUMMARY / CHANGE_LAST_NAME. No browsing or messaging.

**Typical behaviour:**
- 1–2 logins spread over days
- Updates headline (job change), summary (profile refresh), or last name (marriage)
- No profile views, connections, or messages

**How it differs from fraud:** No address book download; no messaging; isolated profile updates from user's own country and IP.

---

## 5b. Dormant Account

**What it is:** A user who created an account but never actively used it. Signed up, maybe logged in once to verify, then never returned. No profile views, connections, or messages.

**Typical behaviour:**
- ACCOUNT_CREATION only, or plus 1 LOGIN within the first 1–2 days
- No browsing, no connections, no messages
- ~30% never log in again after signup; ~70% log in once

**How it differs from fraud:** No activity at all; no download, no spam; just abandonment.

---

## 6. New User Onboarding

**What it is:** A recently joined user who is setting up their profile and building their network. Activity is concentrated in the first few days, then tapers.

**Typical behaviour:**
- High activity in first 1–3 days
- Profile creation and updates
- Connection requests (often to people they know)
- May upload address book once to find contacts (legitimate use)
- Activity drops after initial setup

**How it differs from fraud:** Single address book upload for discovery, not exfiltration; no spam; residential IP; activity pattern matches onboarding, not exploitation.

---

## 7. Weekly Check-in

**What it is:** A user who logs in roughly once a week for a quick browse. Minimal activity per session.

**Typical behaviour:**
- ~1 login per week
- 1–5 profile views
- Rarely sends messages or connection requests
- Very regular timing (e.g. same day each week)

**How it differs from fraud:** Very low volume; no download or spam; consistent, predictable pattern.

---

## 8. Content Consumer

**What it is:** A user who mostly views profiles and activity feeds. Rarely sends messages or connection requests.

**Typical behaviour:**
- Many profile views
- Few or no messages
- Few connection requests
- Read-heavy, low outbound engagement

**How it differs from fraud:** No messaging bursts; no address book download; no mass connection requests.

---

## 9. Exec Delegation

**What it is:** A CEO or executive creates the account, but a remote secretary in the Philippines accesses it repeatedly on their behalf. This looks like account takeover (country mismatch, repeated logins from abroad) but is a false positive — legitimate delegated access.

**Typical behaviour:**
- Account creation from exec's country (US, GB, CA, AU)
- Secretary logs in from Philippines 2–4 times per week
- Secretary does VIEW, CONNECT, MESSAGE as part of exec-assistant work
- Activity spread over weeks; no DOWNLOAD_ADDRESS_BOOK; no mass spam
- Metadata includes `delegated_access: true` for analysis

**How it differs from fraud:** No address book download; no burst of spam; no rapid takeover and close. The country mismatch and repeated "foreign" logins mimic ATO but reflect normal exec-assistant workflows (common in BPO-heavy regions like the Philippines).

---

## Summary

| Pattern             | Login frequency | Volume   | Main characteristic                         |
|---------------------|-----------------|----------|---------------------------------------------|
| Casual Browser      | 1–2/week        | Low      | Occasional, light engagement                |
| Active Job Seeker   | Several/week    | High     | Sustained activity, spread over time        |
| Recruiter           | Frequent        | High     | Steady view/connect volume, work-focused    |
| Regular Networker   | 2–3/week        | Moderate | Consistent mix of actions                   |
| Returning User      | After long gap  | Low–Mod  | Gradual return, no burst                    |
| Career Update       | 1–2 total       | Very low | Profile updates only, no browsing            |
| Dormant Account    | 0–1 total       | None     | Signup only, no activity                    |
| New User Onboarding| High at first   | High     | Concentrated in first few days              |
| Weekly Check-in     | ~1/week         | Very low | Minimal, regular sessions                   |
| Content Consumer    | Variable        | Low out  | Many views, few messages or connections     |
| Exec Delegation     | 2–4/week (PH)   | Moderate | Secretary abroad; country mismatch, false positive |

---

## Normal Sessions and Temporal Succession

A **session** is a bounded period of activity, typically starting with a login and ending when the user stops (or after a long idle gap, e.g. 30+ minutes). The order in which actions occur is constrained by how the platform works — some actions are impossible without others.

### Temporal Invariants (What Must Come Before What)

1. **Account creation is always first.** A user cannot do anything before `ACCOUNT_CREATION`. This is a one-time event at the start of the account lifecycle.

2. **Login precedes all other activity in a session.** You cannot view profiles, send messages, connect with users, download or upload address books, or change settings without first logging in. So:
   - **Invalid:** `VIEW_USER_PAGE` → `LOGIN` (viewing before login is not feasible)
   - **Valid:** `LOGIN` → `VIEW_USER_PAGE` → `MESSAGE_USER`

3. **Messaging and connecting typically follow browsing.** Legitimate users usually view a profile before messaging or connecting with that person:
   - **Typical:** `LOGIN` → `VIEW_USER_PAGE` (target A) → `MESSAGE_USER` (target A) or `CONNECT_WITH_USER` (target A)
   - **Rare but possible:** `LOGIN` → `CONNECT_WITH_USER` without prior view (e.g. bulk invites from a list)

4. **Address book download is rare for normal users.** When it happens, it is usually:
   - **New users:** `LOGIN` → `UPLOAD_ADDRESS_BOOK` (to find existing contacts) — early in onboarding
   - **Legitimate use of download:** Almost never; normal users do not download their full address book. A `DOWNLOAD_ADDRESS_BOOK` followed quickly by mass messaging is a strong fraud signal.

5. **Close account is terminal.** `CLOSE_ACCOUNT` must be the last event for that user. No activity occurs after it.

### Typical Session Structures

| Session type | Typical sequence | Duration |
|--------------|------------------|----------|
| **Quick browse** | `LOGIN` → `VIEW_USER_PAGE` × 2–5 | 2–10 min |
| **Engaged session** | `LOGIN` → `VIEW_USER_PAGE` × several → `CONNECT_WITH_USER` × 1–3 → `MESSAGE_USER` × 0–2 | 10–30 min |
| **Job search** | `LOGIN` → `VIEW_USER_PAGE` × many → `CONNECT_WITH_USER` × 5–15 → `MESSAGE_USER` × 1–5 | 20–60 min |
| **Recruiter sweep** | `LOGIN` → `SEARCH_CANDIDATES` × 1–4 → `VIEW_USER_PAGE` × many → `CONNECT_WITH_USER` × many | 15–45 min |
| **Onboarding** | `LOGIN` (or first session) → `UPDATE_HEADLINE` / `UPDATE_SUMMARY` → `UPLOAD_ADDRESS_BOOK` (optional) → `CONNECT_WITH_USER` × several | 10–40 min |
| **Return visit** | `LOGIN` → `VIEW_USER_PAGE` × few → maybe `UPDATE_HEADLINE` / `UPDATE_SUMMARY` / `CHANGE_LAST_NAME` | 5–15 min |
| **Career update** | `LOGIN` → `UPDATE_HEADLINE` (job change) / `UPDATE_SUMMARY` (profile refresh) / `CHANGE_LAST_NAME` (marriage) | 2–5 min |

### What Normal Sessions Do *Not* Look Like

- **Login immediately followed by download:** `LOGIN` → `DOWNLOAD_ADDRESS_BOOK` within minutes, with no prior browsing, is suspicious.
- **Download then mass message burst:** `LOGIN` → `DOWNLOAD_ADDRESS_BOOK` → `MESSAGE_USER` × 50+ in a short window is a fraud pattern.
- **Activity before login:** Any `VIEW_USER_PAGE`, `MESSAGE_USER`, or `CONNECT_WITH_USER` before a `LOGIN` in the same session is invalid.
- **Messaging without prior context:** Sending many messages to different users without any preceding `VIEW_USER_PAGE` in that session is unusual for normal users (they typically look before they reach out).
