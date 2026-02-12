# Fraud Types (Account Takeover Patterns)

This document describes the 13 types of fraud (attack patterns) simulated in the anti-abuse ATO system. Each pattern mimics realistic attacker behaviour — the tactics, timing, and signals that appear when a criminal takes over or exploits a user account.

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

## Summary

| Pattern            | Speed     | Volume    | Key signal                                      |
|--------------------|-----------|-----------|-------------------------------------------------|
| Smash & Grab       | Very fast | High      | Burst of spam + close in under 24h               |
| Low & Slow         | Slow      | Moderate  | Activity spread over days                       |
| Country Hopper     | Medium    | Moderate  | Multiple IP countries in a week                 |
| Data Thief         | Fast      | None      | Download only, no spam                          |
| Credential Stuffer | Fast      | High      | Same IP hits many accounts                      |
| Login Storm        | Fast      | Low       | Many failed logins before success               |
| Stealth Takeover   | Slow      | Moderate  | Multi-country, multi-device progression        |
| Fake Account       | Slow      | Variable  | Dormant then sudden US hosting + password change|
| Scraper Cluster    | Medium    | High      | Mass profile views, machine-like patterns      |
| Spear Phisher      | Slow      | Low       | Residential IP, personalised messages          |
| Credential Tester  | Very fast | Low       | Quick login-only sweeps across many accounts    |
| Connection Harvester| Medium    | High      | Sudden spike in connection requests            |
| Sleeper Agent      | Very slow | Moderate  | Login-only for weeks, then spam burst           |
| Profile Defacement | Fast      | None      | Burst of profile/name changes, no spam          |
