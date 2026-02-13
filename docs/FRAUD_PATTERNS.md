# Fraud Types (Account Takeover Patterns)

This document describes the 28 types of fraud (attack patterns) simulated in the anti-abuse system. Each pattern mimics realistic attacker behaviour — the tactics, timing, and signals that appear when a criminal takes over or exploits a user account.

---

## 1. Smash & Grab

**What it is:** A fast, aggressive takeover. The attacker logs in, downloads the victim’s address book, sends spam to 80–200 contacts in 1–3 hours, then closes the account. Everything happens within 24 hours.

**Why it matters:** High volume, short duration. Often used when the attacker expects the account to be locked soon.

**Typical signals:** Login → download → burst of messages → close account, all from hosting IPs in a short window.

---

## 2. Low & Slow

**What it is:** Patient, low-profile abuse. The attacker logs in, waits 2–5 days with occasional page views, then downloads the address book and sends spam to 15–40 users over 2–3 days. The account is left open.

**Why it matters:** Harder to detect because activity is spread out and looks more like normal use.

**Typical signals:** Long gaps between actions, moderate spam volume, account remains active.

---

## 3. Country Hopper

**What it is:** Login from 3–4 different countries over about a week. The attacker downloads the address book and sends spam from yet another country. Sometimes closes the account.

**Why it matters:** Frequent country changes suggest VPN or proxy use and are a strong indicator of compromise.

**Typical signals:** Multiple IP countries in a short period, often from hosting/VPN ranges.

---

## 4. Data Thief

**What it is:** Pure data harvesting. The attacker logs in, downloads the address book, and closes the account. No spam or other visible abuse.

**Why it matters:** Indicates credential theft and data exfiltration for later use (e.g. selling lists or launching other attacks).

**Typical signals:** Login → download → close, no messaging activity.

---

## 5. Credential Stuffer

**What it is:** One attacker IP is used to log into 3–7 victim accounts in quick succession. Each victim gets their address book downloaded and moderate spam. Some accounts are closed.

**Why it matters:** One IP hitting many accounts suggests automated credential stuffing from a leaked password list.

**Typical signals:** Same IP used for multiple accounts in a short time; repeated login → download → spam pattern across victims.

---

## 6. Login Storm

**What it is:** 5–15 failed login attempts, then a successful login. The attacker then downloads the address book and closes the account.

**Why it matters:** Many failures before success suggest brute-force or credential guessing.

**Typical signals:** Long sequence of failed logins followed by one success, then immediate download and close.

---

## 7. Stealth Takeover

**What it is:** Multiple failed logins from hosting IPs, then a successful login. A few days later, another login from a different country with a different user agent. The attacker downloads the address book and closes the account from yet another country using a residential IP.

**Why it matters:** Shows deliberate evasion: different IPs, countries, and devices to avoid detection.

**Typical signals:** Failures before success, multi-country logins, device/IP changes between actions.

---

## 8. Fake Account

**What it is:** Accounts created by IP rings (shared IPs, often from one country). They stay dormant for a while, then someone logs in from US hosting, changes the password, logs in from another country, uploads a large address book, and sends spam.

**Why it matters:** Accounts built specifically for abuse, not real takeovers.

**Typical signals:** Shared IPs at creation, long dormancy, then sudden US hosting login and password change before spam.

---

## 9. Scraper Cluster

**What it is:** Several related hosting IPs take over 3–4 accounts and use them to scrape user profile pages. Scraping can be ordered by name, timed at regular intervals, or coordinated across accounts to hide individual volume.

**Why it matters:** Harvesting data for later targeting or selling; patterns look like automated scraping.

**Typical signals:** Many profile views from a small set of accounts, very regular viewing patterns.

---

## 10. Spear Phisher

**What it is:** Targeted impersonation. The attacker uses a residential IP and may tweak the victim’s profile or name. For each target, they view the profile first, then send a longer, personalised message. Low volume (5–15 targets), account left open.

**Why it matters:** Social engineering with high trust and low volume, harder to detect by volume alone.

**Typical signals:** Residential IP, view-then-message pattern, fewer but longer, personalised messages.

---

## 11. Credential Tester

**What it is:** Validates stolen credentials without exploiting the accounts. One hosting IP tests 5–8 accounts in quick succession. Each account gets a single login (maybe one failed attempt first) and sometimes one page view. No spam or other abuse. Sessions last under 60 seconds.

**Why it matters:** Attacker is building a verified credential list to sell, not using the accounts yet.

**Typical signals:** Same IP, many accounts, minimal activity per account (login + optional view only).

---

## 12. Connection Harvester

**What it is:** After takeover, the attacker sends 50–200 connection requests to inflate the account’s network. They may download the address book first. The account is left open for future campaigns.

**Why it matters:** Building a larger network to appear more trusted for later fraud or spam.

**Typical signals:** Sudden spike in connection requests from a foreign hosting IP, often from an account with low prior connection activity.

---

## 13. Sleeper Agent

**What it is:** The account is compromised early (password changed from a foreign hosting IP). Over 2–4 weeks, the attacker logs in periodically (every few days) with no other activity. Eventually they activate: login, download address book, and run a spam campaign.

**Why it matters:** Long dormancy hides the compromise until the attacker decides to act.

**Typical signals:** Password change from hosting IP, then a long series of login-only sessions at regular intervals, followed by sudden spam activity.

---

## 14. Profile Defacement

**What it is:** The attacker logs in and defaces the victim's visible identity — changes display name, headline, and/or summary. May optionally change the password to lock out the victim. Account is left open so the defaced profile is visible to connections. No spam or messaging.

**Why it matters:** Used for scam pages, brand impersonation, or revenge. The abuse is the profile itself, not messaging.

**Typical signals:** Login from hosting IP in a different country, burst of CHANGE_NAME and CHANGE_PROFILE shortly after login, no MESSAGE_USER activity.

---

## 15. Account Farming

**What it is:** Clusters of hosting IPs create many empty accounts that are sold to buyers. Buyers log in from residential IPs (different from creators), change password, and fill profiles with bogus content (name, headline, summary). No spam or messaging — the abuse is account creation and resale.

**Why it matters:** Indicates credential marketplace activity; accounts are built for later abuse or resale.

**Typical signals:** Accounts created from hosting IPs; buyer takeover from residential IP with password change and profile updates; no download or spam.

---

## 16. Coordinated Harassment

**What it is:** Multiple fake accounts from a hosting IP cluster log in and send harassing messages to the same target users. Coordinated attack — all harassers target the same victims.

**Why it matters:** Indicates organised harassment or doxxing campaigns; the coordination and shared targets are distinctive.

**Typical signals:** Several accounts from related hosting IPs sending MESSAGE_USER to the same targets in a short window.

---

## 17. Coordinated Like Inflation

**What it is:** Clusters of fake accounts from hosting IPs log in and all send LIKE to the same target (post author). Artificial boosting of engagement metrics.

**Why it matters:** Inflates visibility and perceived authority; used for influencer fraud or content manipulation.

**Typical signals:** Multiple accounts from a hosting cluster; all LIKE the same target within a tight time window.

---

## 18. Credential Phishing

**What it is:** Victim submits credentials to a fake login page (PHISHING_LOGIN). The attacker captures credentials and may later log in from a hosting IP to exploit the account.

**Why it matters:** Credential theft via phishing; no brute-force or takeover — the victim hands over access.

**Typical signals:** PHISHING_LOGIN event; optionally followed by LOGIN from hosting IP in a different country hours or days later.

---

## 19. Endorsement Inflation

**What it is:** Clusters of fake accounts log in from hosting IPs and endorse targets' skills in bulk (ENDORSE_SKILL). Inflates credibility for the target profiles.

**Why it matters:** Makes fraudulent profiles look legitimate; used to build trust for later scams.

**Typical signals:** Multiple accounts from hosting cluster; bulk ENDORSE_SKILL to the same targets across multiple skills.

---

## 20. Executive Hunter

**What it is:** Coordinated hosting IP cluster targets CEOs and Founders. Each compromised account views executive profiles, then sends targeted spear-phishing messages (wire transfers, board meetings, urgent approvals). Low volume per account but coordinated across cluster.

**Why it matters:** High-value targeting; messages tailored for executive audiences with urgency and authority.

**Typical signals:** Hosting IP cluster; view-then-message pattern; executive-focused titles in targets; phishing metadata (wire_transfer_approval, board_meeting, etc.).

---

## 21. Profile Cloning

**What it is:** Attackers log in, view victim profiles, optionally connect, then send messages. Impersonates the victim using a cloned profile to gain trust from the victim's connections.

**Why it matters:** Social engineering and impersonation; uses view-then-connect-then-message pattern.

**Typical signals:** Hosting IPs; VIEW_USER_PAGE → CONNECT_WITH_USER (optional) → MESSAGE_USER per victim; multiple victims per cloner.

---

## 22. Recommendation Fraud

**What it is:** Fake accounts from hosting IP clusters log in and give GIVE_RECOMMENDATION to targets. Inflates credibility and perceived trustworthiness.

**Why it matters:** Makes fraudulent profiles look legitimate; recommendations are a strong trust signal.

**Typical signals:** Multiple recommenders from hosting cluster; bulk GIVE_RECOMMENDATION to targets.

---

## 23. Job Posting Scam

**What it is:** Scammers create fake job postings (CREATE_JOB_POSTING). Victims view the job and apply (VIEW_JOB, APPLY_TO_JOB). Some applications redirect to phishing URLs that harvest credentials or personal data.

**Why it matters:** Exploits job seekers; fake jobs lure victims into phishing flows.

**Typical signals:** CREATE_JOB_POSTING from hosting IP; many victims VIEW_JOB and APPLY_TO_JOB; some with phishing_url metadata.

---

## 24. Invitation Spam

**What it is:** Fake accounts from hosting IP clusters send mass SEND_CONNECTION_REQUEST to harvest the graph and inflate network size. 50–200 requests per account.

**Why it matters:** Builds larger networks for later fraud or spam; graph harvesting for targeting.

**Typical signals:** Sudden spike in connection requests from hosting cluster; many SEND_CONNECTION_REQUEST from a small set of accounts.

---

## 25. Group Spam

**What it is:** Spammers log in from hosting IPs, JOIN_GROUP (if not already), then POST_IN_GROUP with spam content. Uses groups the user has joined to post in.

**Why it matters:** Spreads spam to group members; exploits group trust and visibility.

**Typical signals:** Hosting IP; JOIN_GROUP then burst of POST_IN_GROUP; spam content in posts.

---

## 26. Ad Engagement Fraud

**What it is:** Bot accounts log in from hosting IP clusters and generate fake AD_VIEW and AD_CLICK events. Inflates ad performance metrics to defraud advertisers.

**Why it matters:** Ad fraud; advertisers pay for fake engagement.

**Typical signals:** Hosting IP cluster; many AD_VIEW and AD_CLICK from a small set of accounts; machine-like patterns.

---

## 27. Romance Scam

**What it is:** Scammer sends an extended message thread (20–100 messages) to the victim over days or weeks. Victim-based: the victim is the target. Messages progress through phases (initial, middle, ask) to build trust before the financial ask.

**Why it matters:** Social engineering over time; low volume per victim but high trust; residential IPs.

**Typical signals:** Extended MESSAGE_USER thread from scammer to victim; scam_phase metadata; spread over 7–60 days.

---

## 28. Session Hijacking

**What it is:** Attacker steals the victim's session token and uses SESSION_LOGIN (no password). Then performs actions (e.g. 5–30 profile views) from a hosting IP in a different country.

**Why it matters:** Token theft, not credential theft; victim may not notice until they are locked out.

**Typical signals:** SESSION_LOGIN from hosting IP; session_stolen metadata; VIEW_USER_PAGE burst from victim's account in foreign country.

---

## Summary

| Pattern             | Speed     | Volume    | Key signal                                      |
|---------------------|-----------|-----------|-------------------------------------------------|
| Smash & Grab        | Very fast | High      | Burst of spam + close in under 24h               |
| Low & Slow          | Slow      | Moderate  | Activity spread over days                       |
| Country Hopper      | Medium    | Moderate  | Multiple IP countries in a week                 |
| Data Thief          | Fast      | None      | Download only, no spam                          |
| Credential Stuffer  | Fast      | High      | Same IP hits many accounts                      |
| Login Storm         | Fast      | Low       | Many failed logins before success               |
| Stealth Takeover    | Slow      | Moderate  | Multi-country, multi-device progression         |
| Fake Account        | Slow      | Variable  | Dormant then sudden US hosting + password change|
| Scraper Cluster     | Medium    | High      | Mass profile views, machine-like patterns       |
| Spear Phisher       | Slow      | Low       | Residential IP, personalised messages          |
| Credential Tester   | Very fast | Low       | Quick login-only sweeps across many accounts    |
| Connection Harvester| Medium    | High      | Sudden spike in connection requests             |
| Sleeper Agent       | Very slow | Moderate  | Login-only for weeks, then spam burst           |
| Profile Defacement  | Fast      | None      | Burst of profile/name changes, no spam          |
| Account Farming     | Medium    | Low       | Hosting-created accounts, buyer takeover + profile fill |
| Coordinated Harassment | Medium | High      | Cluster targets same users with messages        |
| Coordinated Like Inflation | Medium | Low    | Cluster LIKEs same target                       |
| Credential Phishing | Medium    | None      | PHISHING_LOGIN, then optional LOGIN            |
| Endorsement Inflation | Medium  | High      | Bulk ENDORSE_SKILL from cluster                |
| Executive Hunter    | Slow      | Moderate  | Cluster targets CEOs, view-then-message         |
| Profile Cloning     | Medium    | Moderate  | View, connect, message; impersonation          |
| Recommendation Fraud| Medium    | Moderate  | Bulk GIVE_RECOMMENDATION from cluster           |
| Job Posting Scam    | Medium    | High      | Fake jobs, phishing redirects on apply         |
| Invitation Spam     | Medium    | High      | Mass SEND_CONNECTION_REQUEST from cluster      |
| Group Spam          | Medium    | Moderate  | JOIN_GROUP, POST_IN_GROUP spam                  |
| Ad Engagement Fraud | Medium    | High      | Fake AD_VIEW, AD_CLICK from bots               |
| Romance Scam        | Very slow | Low       | Extended message thread over days/weeks         |
| Session Hijacking   | Fast      | Moderate  | SESSION_LOGIN, then view burst                  |
