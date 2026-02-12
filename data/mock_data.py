"""
Mock data generator for the anti-abuse ATO system.

Generates:
  - 100,000 users with realistic distributions.
  - UserProfiles with Zipf-distributed connection counts.
  - Up to 2 months of interactions with varied frequency per user.

Design notes on realism:
  - ~10% of users use hosting IPs (potential bot/VPN).
  - ~5% of users are inactive (closed accounts).
  - Interaction frequency follows a power-law distribution:
    most users have few interactions, some are very active.
  - Connections follow a Zipf distribution (many low, few high).
  - Account creation is the first event in every user's history.
  - No interactions occur after a CLOSE_ACCOUNT event.
  - Some users switch IPs between interactions (VPN/proxy).
  - User agents vary: ~12% of users use non-browser UAs
    (API clients, bots, mobile apps, scripts).
  - Not all users have 2 full months of interactions — users
    who joined recently have proportionally shorter histories.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from core.constants import (
    GENERATION_PATTERN_CLEAN,
    INTERACTION_WINDOW_DAYS,
    NUM_FAKE_ACCOUNTS,
    NUM_USERS,
)
from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile
from data.config_utils import get_cfg
from data.non_fraud import generate_legitimate_events

# ---------------------------------------------------------------------------
# Mock-data-specific constants (not in core.constants)
# ---------------------------------------------------------------------------
# IPs used by fake account creation rings (same country, shared across accounts)
_FAKE_ACCOUNT_IP_POOL_RU = [
    "91.185.32.12", "91.185.32.45", "91.185.32.78", "91.185.33.10", "91.185.33.55",
    "91.185.34.22", "91.185.35.67", "91.186.12.88", "91.186.13.101", "91.186.14.203",
    "95.165.28.45", "95.165.29.112", "95.165.30.78", "185.71.45.33", "185.71.46.90",
    "188.170.22.156", "188.170.23.77", "193.104.88.12", "194.58.12.34", "195.24.156.89",
]

# Country weights (rough population / internet-user distribution)
_COUNTRY_WEIGHTS = {
    "US": 20, "IN": 15, "BR": 8, "GB": 7, "DE": 6, "FR": 5, "JP": 5,
    "CA": 4, "AU": 3, "KR": 3, "MX": 3, "ID": 3, "PH": 3, "TR": 2,
    "RU": 2, "NG": 2, "PL": 2, "NL": 2, "SE": 1, "IT": 2,
    "ES": 2, "ZA": 1, "EG": 1, "CN": 3, "VN": 2, "PK": 2,
    "UA": 1, "RO": 1, "BD": 1, "TH": 1,
}
_COUNTRIES = list(_COUNTRY_WEIGHTS.keys())
_COUNTRY_W = list(_COUNTRY_WEIGHTS.values())

# Languages per country (tuples for multi-language countries)
_COUNTRY_LANG: dict[str, tuple[str, ...]] = {
    "US": ("en", "es"),
    "GB": ("en",),
    "CA": ("en", "fr"),
    "AU": ("en",),
    "IN": ("hi", "en"),
    "BR": ("pt",),
    "DE": ("de",),
    "FR": ("fr",),
    "JP": ("ja",),
    "KR": ("ko",),
    "MX": ("es",),
    "NG": ("en",),
    "RU": ("ru",),
    "CN": ("zh",),
    "ID": ("id",),
    "PH": ("tl", "en"),
    "TR": ("tr",),
    "EG": ("ar",),
    "PK": ("hi", "en"),
    "BD": ("bn",),
    "VN": ("vi",),
    "IT": ("it",),
    "ES": ("es", "ca"),
    "NL": ("nl",),
    "SE": ("sv",),
    "PL": ("pl",),
    "UA": ("uk",),
    "RO": ("ro",),
    "ZA": ("en", "af"),
    "TH": ("th",),
}

# First-name pools (simplified)
_FIRST_NAMES = [
    "James", "Mary", "Amit", "Priya", "Carlos", "Maria", "Hans", "Sophie",
    "Yuki", "Hana", "Wei", "Lin", "Ahmed", "Fatima", "Olga", "Ivan",
    "Kofi", "Ama", "Luis", "Ana", "Kim", "Ji-yeon", "Thiago", "Fernanda",
    "Raj", "Sita", "Mohammed", "Aisha", "Pierre", "Claire", "Luca", "Giulia",
    "Sven", "Ingrid", "Jan", "Eva", "Oleg", "Natasha", "Chen", "Mei",
    "Kenji", "Sakura", "David", "Sarah", "Michael", "Emma", "Daniel", "Laura",
]

_LAST_NAMES = [
    "Smith", "Kumar", "Silva", "Müller", "Tanaka", "Wang", "Ali", "Kim",
    "Garcia", "Johansson", "Nowak", "Petrov", "Brown", "Johnson", "Williams",
    "Okafor", "Santos", "Nguyen", "Lee", "Chen", "Andersen", "Dubois",
    "Rossi", "Fernandez", "Martinez", "Lopez", "Gonzalez", "Wilson", "Taylor",
    "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson",
]

# Email domains (weights approximate real-world distribution)
_EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "protonmail.com", "mail.com", "aol.com", "zoho.com", "yandex.com",
    "gmx.com", "live.com", "msn.com", "qq.com", "163.com", "btinternet.com",
]
_EMAIL_DOMAIN_WEIGHTS = [25, 15, 12, 8, 6, 4, 3, 3, 2, 2, 2, 2, 1, 2, 1, 3]

_HEADLINES = [
    "Software Engineer", "Product Manager", "Data Scientist",
    "Marketing Director", "UX Designer", "Sales Executive",
    "Full Stack Developer", "Business Analyst", "HR Manager",
    "DevOps Engineer", "CEO & Founder", "Consultant",
    "Student", "Freelance Writer", "Graphic Designer",
    "Research Scientist", "Account Manager", "Operations Lead",
    "Cloud Architect", "Machine Learning Engineer",
    "Senior Developer", "Technical Lead", "Scrum Master",
    "Project Manager", "Finance Analyst", "Legal Counsel",
    "Teacher", "Nurse", "Architect", "Designer",
    "Entrepreneur", "Investor", "Recruiter", "Copywriter",
    "Data Analyst", "Frontend Developer", "Backend Engineer",
    "Security Engineer", "QA Engineer", "Support Specialist",
]

_SUMMARIES = [
    "Passionate about building great products.",
    "Experienced professional with 10+ years in the industry.",
    "Looking for new opportunities and connections.",
    "Love collaborating across teams to solve hard problems.",
    "Focused on driving growth and innovation.",
    "Dedicated to continuous learning and improvement.",
    "Enthusiastic about technology and its impact on society.",
    "Previously at FAANG. Now building something new.",
    "Helping teams ship faster and smarter.",
    "Always curious. Always learning.",
    "Connecting people and ideas.",
    "Building the future, one commit at a time.",
    "Expert in distributed systems and scaling.",
    "Passionate about user experience and accessibility.",
    "Former startup founder. Now advising and investing.",
    "Love mentoring and growing technical teams.",
    "Open source contributor. Python and Go enthusiast.",
    "15 years in fintech. Now exploring AI/ML.",
    "Making complex things simple.",
    "Believe in work-life balance and sustainable pace.",
    "",  # Some users leave summary empty
]

_LOCATIONS = [
    "San Francisco, CA", "New York, NY", "London, UK", "Berlin, Germany",
    "Tokyo, Japan", "Mumbai, India", "São Paulo, Brazil", "Sydney, Australia",
    "Toronto, Canada", "Seoul, South Korea", "Paris, France", "Amsterdam, Netherlands",
    "Stockholm, Sweden", "Warsaw, Poland", "Mexico City, Mexico",
    "Lagos, Nigeria", "Moscow, Russia", "Shanghai, China", "Ho Chi Minh City, Vietnam",
    "Manila, Philippines", "Istanbul, Turkey", "Cairo, Egypt", "Karachi, Pakistan",
    "Dhaka, Bangladesh", "Bangkok, Thailand", "Rome, Italy", "Madrid, Spain",
    "Cape Town, South Africa", "Kyiv, Ukraine", "Bucharest, Romania",
    "Seattle, WA", "Chicago, IL", "Austin, TX", "Boston, MA", "Denver, CO",
    "Vancouver, BC", "Melbourne, Australia", "Singapore", "Hong Kong",
    "Dublin, Ireland", "Zurich, Switzerland", "Barcelona, Spain",
    "",  # Some users don't set location
    "",
]


# ---------------------------------------------------------------------------
# User agents
# ---------------------------------------------------------------------------
_BROWSER_USER_AGENTS = [
    # Current (2024)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/17.2",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile",
    # Older Chrome / Chromium
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/100.0.4896.127",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/90.0.4430.212",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 Chrome/95.0.4638.69",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/88.0.4324.182",
    # Older Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:95.0) Gecko/20100101 Firefox/95.0",
    # Older Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/605.1.15 Safari/605.1.1",
    # Older Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/90.0.818.66",
    # Legacy IE / Edge legacy
    "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
    # Older mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 Chrome/91.0.4472.120 Mobile",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 Chrome/88.0.4324.181 Mobile",
]

_NON_BROWSER_USER_AGENTS = [
    "python-requests/2.31.0",
    "curl/8.4.0",
    "LinkedInApp/9.1.590 (iPhone; iOS 17.2)",
    "LinkedInApp/4.1.940 (Android 14; Pixel 8)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "PostmanRuntime/7.35.0",
    "httpie/3.2.2",
    "wget/1.21.4",
    "Go-http-client/2.0",
    "Java/17.0.9",
    "okhttp/4.12.0",
    "node-fetch/3.3.2",
    "axios/1.6.2",
    "Scrapy/2.11.0",
    "Apache-HttpClient/5.3",
]

# ---------------------------------------------------------------------------
# IP generation (first-octet ranges by region, from RIR allocations)
# ---------------------------------------------------------------------------
# ARIN (North America)
_IP_ARIN = [12, 13, 24, 38, 50, 52, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 96, 97, 98, 99, 104, 107, 108]
# RIPE (Europe, Russia, Turkey)
_IP_RIPE = [2, 5, 31, 37, 46, 51, 62, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 109, 141, 144, 146, 176, 178, 185, 188, 193, 194, 195, 212, 213, 217]
# APNIC (Asia-Pacific)
_IP_APNIC = [1, 14, 27, 36, 39, 42, 43, 49, 58, 59, 60, 61, 101, 103, 106, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 133, 139, 140, 150, 153, 157, 163, 171, 175, 180, 182, 183, 202, 203, 210, 211, 218, 219, 220, 221, 222, 223]
# LACNIC (Latin America)
_IP_LACNIC = [138, 143, 168, 170, 177, 179, 181, 186, 187, 189, 191, 200, 201]
# AfriNIC (Africa)
_IP_AFRINIC = [41, 102, 105, 154, 156, 196, 197]

_COUNTRY_IP_FIRST_OCTETS: dict[str, list[int]] = {
    "US": _IP_ARIN,
    "CA": _IP_ARIN,
    "GB": _IP_RIPE,
    "DE": _IP_RIPE,
    "FR": _IP_RIPE,
    "IT": _IP_RIPE,
    "ES": _IP_RIPE,
    "NL": _IP_RIPE,
    "SE": _IP_RIPE,
    "PL": _IP_RIPE,
    "UA": _IP_RIPE,
    "RO": _IP_RIPE,
    "RU": _IP_RIPE,
    "TR": _IP_RIPE,
    "IN": _IP_APNIC,
    "JP": _IP_APNIC,
    "KR": _IP_APNIC,
    "CN": _IP_APNIC,
    "AU": _IP_APNIC,
    "PH": _IP_APNIC,
    "ID": _IP_APNIC,
    "VN": _IP_APNIC,
    "TH": _IP_APNIC,
    "PK": _IP_APNIC,
    "BD": _IP_APNIC,
    "BR": _IP_LACNIC,
    "MX": _IP_LACNIC,
    "NG": _IP_AFRINIC,
    "ZA": _IP_AFRINIC,
    "EG": _IP_AFRINIC,
}


def _random_ip_for_country(country: str, rng: random.Random) -> str:
    """Generate a plausible IP from allocations for the given country."""
    first_octets = _COUNTRY_IP_FIRST_OCTETS.get(country, _IP_ARIN)
    first = rng.choice(first_octets)
    return f"{first}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


# ---------------------------------------------------------------------------
# Zipf distribution for connections
# ---------------------------------------------------------------------------
def _zipf_connections(rng: random.Random, config: dict) -> int:
    """
    Sample connections count from a Zipf distribution.

    Most users have few connections; a small number are highly connected.
    zero_connections_pct have zero; the rest use Pareto(alpha=1.2) * 20, capped at 30,000.
    """
    if rng.random() < get_cfg(config, "connections", "zero_connections_pct", default=0.08):
        return 0
    raw = rng.paretovariate(1.2)
    return min(int(raw * 20), 30_000)


# ---------------------------------------------------------------------------
# Email generation (name-based, varied formats and domains)
# ---------------------------------------------------------------------------
def _ascii_local(s: str) -> str:
    """Normalize name for email local part (replace accented chars)."""
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "o"}
    out = s.lower()
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def _make_random_email(rng: random.Random, used_emails: set[str]) -> str:
    """Generate unique email unrelated to display name (e.g. work, old, or generic)."""
    domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
    prefixes = ("user", "contact", "hello", "info", "mail", "box", "id", "acc")
    local = f"{rng.choice(prefixes)}{rng.randint(1000, 999999)}"
    email = f"{local}@{domain}"
    while email in used_emails:
        local = f"{rng.choice(prefixes)}{rng.randint(10000, 99999999)}"
        email = f"{local}@{domain}"
    used_emails.add(email)
    return email


def _make_email(
    first: str,
    last: str,
    rng: random.Random,
    used_emails: set[str],
    config: dict,
) -> str:
    """Generate unique email from name; mostly first.last with some variations."""
    f, l = _ascii_local(first), _ascii_local(last)
    domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
    suffix = (
        str(rng.randint(1, 9999))
        if rng.random() < get_cfg(config, "email", "suffix_pct", default=0.35)
        else ""
    )

    roll = rng.random()
    t1 = get_cfg(config, "email", "first_last", default=0.70)
    t2 = get_cfg(config, "email", "firstlast", default=0.85)
    t3 = get_cfg(config, "email", "last_first", default=0.92)
    if roll < t1:
        local = f"{f}.{l}{suffix}"
    elif roll < t2:
        local = f"{f}{l}{suffix}" if suffix else f"{f}.{l}"
    elif roll < t3:
        local = f"{l}.{f}{suffix}"
    else:
        local = f"{f}_{l}{suffix}"

    email = f"{local}@{domain}"
    while email in used_emails:
        suffix = str(rng.randint(1, 99999))
        local = f"{f}.{l}{suffix}"
        email = f"{local}@{domain}"
    used_emails.add(email)
    return email


# ---------------------------------------------------------------------------
# User generation
# ---------------------------------------------------------------------------
def _generate_users(
    rng: random.Random,
    now: datetime,
    num_users: int = NUM_USERS,
    config: dict | None = None,
) -> tuple[list[User], set[str], dict[str, tuple[str, str]]]:
    """Generate num_users users with realistic distributions."""
    cfg = config or {}
    users: list[User] = []
    used_emails: set[str] = set()
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(num_users):
        user_id = f"u-{i:06d}"
        country = rng.choices(_COUNTRIES, weights=_COUNTRY_W, k=1)[0]
        languages = _COUNTRY_LANG.get(country, ("en",))
        language = rng.choice(languages)

        is_hosting = rng.random() < get_cfg(cfg, "users", "hosting_ip_pct", default=0.10)
        ip_type = IPType.HOSTING if is_hosting else IPType.RESIDENTIAL
        ip_address = _random_ip_for_country(country, rng)

        days_ago = rng.randint(1, 730)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        email = (
            _make_random_email(rng, used_emails)
            if rng.random() < get_cfg(cfg, "users", "unrelated_email_pct", default=0.05)
            else _make_email(first, last, rng, used_emails, cfg)
        )

        inactive_pct = get_cfg(cfg, "users", "inactive_pct", default=0.05)
        is_active = rng.random() >= inactive_pct

        email_verified = rng.random() < get_cfg(cfg, "users", "email_verified_pct", default=0.95)
        two_factor_enabled = rng.random() < get_cfg(cfg, "users", "two_factor_pct", default=0.25)
        phone_verified = rng.random() < get_cfg(cfg, "users", "phone_verified_pct", default=0.60)

        last_password_change_at = None
        if rng.random() < get_cfg(cfg, "users", "password_changed_pct", default=0.40):
            delta_max = (now - join_date).total_seconds()
            delta_sec = rng.randint(0, max(0, int(delta_max)))
            last_password_change_at = join_date + timedelta(seconds=delta_sec)

        tier_roll = rng.random()
        free_pct = get_cfg(cfg, "users", "account_tier_free", default=0.70)
        prem_pct = get_cfg(cfg, "users", "account_tier_premium", default=0.25)
        if tier_roll < free_pct:
            account_tier = "free"
        elif tier_roll < free_pct + prem_pct:
            account_tier = "premium"
        else:
            account_tier = "enterprise"

        user_type = "recruiter" if rng.random() < get_cfg(cfg, "users", "recruiter_pct", default=0.06) else "regular"

        failed_login_streak = 0
        if rng.random() < get_cfg(cfg, "users", "failed_login_streak_pct", default=0.05):
            failed_login_streak = rng.randint(1, 3)

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            ip_type=ip_type,
            language=language,
            is_active=is_active,
            generation_pattern=GENERATION_PATTERN_CLEAN,
            email_verified=email_verified,
            two_factor_enabled=two_factor_enabled,
            last_password_change_at=last_password_change_at,
            account_tier=account_tier,
            failed_login_streak=failed_login_streak,
            phone_verified=phone_verified,
            user_type=user_type,
        ))

    return users, used_emails, name_map


# Export for generate.py / fraud
FAKE_ACCOUNT_USER_IDS: list[str] = [
    f"u-{NUM_USERS + i:06d}" for i in range(NUM_FAKE_ACCOUNTS)
]


# ---------------------------------------------------------------------------
# Fake account users (for fake_account attack pattern)
# ---------------------------------------------------------------------------
def _generate_fake_account_users(
    rng: random.Random,
    now: datetime,
    used_emails: set[str],
    base_idx: int = NUM_USERS,
) -> tuple[list[User], dict[str, tuple[str, str]]]:
    """
    Generate fake account users. These are created by IP rings (shared IPs
    from one country). They get only ACCOUNT_CREATION in mock_data; the
    rest of the attack flow is added by fraud.
    """
    users: list[User] = []
    name_map: dict[str, tuple[str, str]] = {}

    for i in range(NUM_FAKE_ACCOUNTS):
        user_id = f"u-{base_idx + i:06d}"
        country = "RU"  # Fake accounts appear to originate from RU
        language = "ru"

        # Join date: 50-55 days ago (dormant for a while)
        days_ago = rng.randint(50, 55)
        join_date = now - timedelta(days=days_ago, seconds=rng.randint(0, 86400))

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        name_map[user_id] = (first, last)
        f, l = _ascii_local(first), _ascii_local(last)
        local = f"fake{base_idx}.{f}.{l}{rng.randint(1, 9999)}"
        domain = rng.choices(_EMAIL_DOMAINS, weights=_EMAIL_DOMAIN_WEIGHTS, k=1)[0]
        email = f"{local}@{domain}"
        while email in used_emails:
            local = f"fake{base_idx}.{f}.{l}{rng.randint(1, 99999)}"
            email = f"{local}@{domain}"
        used_emails.add(email)

        # Fake accounts are "active" until malicious flow closes them
        ip_address = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        ip_type = IPType.RESIDENTIAL

        users.append(User(
            user_id=user_id,
            email=email,
            join_date=join_date,
            country=country,
            ip_address=ip_address,
            ip_type=ip_type,
            language=language,
            is_active=True,
            generation_pattern="fake_account",
            email_verified=False,       # Fake accounts skip verification
            two_factor_enabled=False,
            last_password_change_at=None,
            account_tier="free",
            failed_login_streak=0,
            phone_verified=False,       # Fake accounts never verify phone
        ))

    return users, name_map


# ---------------------------------------------------------------------------
# Profile generation
# ---------------------------------------------------------------------------
def _generate_profiles(
    users: list[User],
    name_map: dict[str, tuple[str, str]],
    rng: random.Random,
    now: datetime,
    config: dict | None = None,
) -> list[UserProfile]:
    """Generate a UserProfile for every user with Zipf-distributed connections."""
    cfg = config or {}
    profiles: list[UserProfile] = []
    fake_ids = {u.user_id for u in users[-NUM_FAKE_ACCOUNTS:]}

    for user in users:
        is_fake = user.user_id in fake_ids
        first, last = name_map.get(user.user_id, (rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)))
        display_name = f"{first} {last}"

        headline = rng.choice(_HEADLINES)
        summary = rng.choice(_SUMMARIES)

        connections_count = _zipf_connections(rng, cfg)

        # Profile created shortly after join
        profile_offset = timedelta(seconds=rng.randint(60, 3600))
        profile_created_at = user.join_date + profile_offset
        if profile_created_at > now:
            profile_created_at = now - timedelta(seconds=1)

        last_updated_at = None
        if rng.random() < get_cfg(cfg, "profiles", "profile_updated_pct", default=0.70):
            update_offset = timedelta(
                days=rng.randint(1, max(1, (now - profile_created_at).days or 1))
            )
            last_updated_at = profile_created_at + update_offset
            if last_updated_at > now:
                last_updated_at = now - timedelta(seconds=1)

        # --- New profile fields ---
        if is_fake:
            # Fake accounts: minimal profiles
            has_profile_photo = False
            location_text = ""
            endorsements_count = 0
            profile_views_received = rng.randint(0, 5)
        else:
            has_profile_photo = rng.random() < get_cfg(cfg, "profiles", "profile_photo_pct", default=0.75)
            location_text = rng.choice(_LOCATIONS)
            # Endorsements: Zipf-like, loosely correlated with connections
            endorsements_count = min(int(rng.paretovariate(1.5) * 3), connections_count)
            # Profile views: Zipf-like
            profile_views_received = min(int(rng.paretovariate(1.1) * 10), 50_000)

        # Profile completeness: fraction of key fields that are filled
        filled = sum([
            bool(display_name),
            bool(headline),
            bool(summary),
            has_profile_photo,
            bool(location_text),
        ])
        profile_completeness = round(filled / 5.0, 2)

        profiles.append(UserProfile(
            user_id=user.user_id,
            display_name=display_name,
            headline=headline,
            summary=summary,
            connections_count=connections_count,
            profile_created_at=profile_created_at,
            last_updated_at=last_updated_at,
            has_profile_photo=has_profile_photo,
            profile_completeness=profile_completeness,
            endorsements_count=endorsements_count,
            profile_views_received=profile_views_received,
            location_text=location_text,
        ))

    return profiles


# ---------------------------------------------------------------------------
# Interaction generation
# ---------------------------------------------------------------------------


def _generate_interactions(
    users: list[User],
    rng: random.Random,
    now: datetime,
    config: dict | None = None,
) -> list[UserInteraction]:
    """
    Generate up to 2 months of interactions for all users.

    - Fake accounts: ACCOUNT_CREATION only (from shared IP pool).
    - Legitimate users: pattern-based generation via non_fraud module.
      Respects temporal invariants: ACCOUNT_CREATION first, LOGIN before
      other activity, VIEW before MESSAGE/CONNECT when reaching out.
    - Inactive users get a CLOSE_ACCOUNT event (terminal).
    """
    cfg = config or {}
    interactions: list[UserInteraction] = []
    all_user_ids = [u.user_id for u in users]
    window_start = now - timedelta(days=INTERACTION_WINDOW_DAYS)

    interaction_counter = 0

    user_primary_ua: dict[str, str] = {}
    for user in users:
        if rng.random() < get_cfg(cfg, "user_agents", "non_browser_ua_pct", default=0.12):
            user_primary_ua[user.user_id] = rng.choice(_NON_BROWSER_USER_AGENTS)
        else:
            user_primary_ua[user.user_id] = rng.choice(_BROWSER_USER_AGENTS)

    fake_ids = {u.user_id for u in users[-NUM_FAKE_ACCOUNTS:]}

    for user in users:
        if user.user_id not in fake_ids:
            continue
        primary_ua = user_primary_ua.get(user.user_id, rng.choice(_BROWSER_USER_AGENTS))
        interaction_counter += 1
        create_ts = user.join_date
        if create_ts < window_start:
            create_ts = window_start
        ip = rng.choice(_FAKE_ACCOUNT_IP_POOL_RU)
        interactions.append(UserInteraction(
            interaction_id=f"evt-{interaction_counter:08d}",
            user_id=user.user_id,
            interaction_type=InteractionType.ACCOUNT_CREATION,
            timestamp=create_ts,
            ip_address=ip,
            ip_type=IPType.RESIDENTIAL,
            metadata={"user_agent": primary_ua, "ip_country": "RU"},
        ))

    _last_pct = [-1]

    def _progress(processed: int, total: int, events_count: int) -> None:
        if total <= 0:
            return
        pct = 100 * processed / total
        if processed == 1 or processed == total or pct >= _last_pct[0] + 5:
            _last_pct[0] = int(pct // 5) * 5
            print(f"\r  Users: {processed:,}/{total:,} ({pct:.1f}%) | Events: {events_count:,}", end="", flush=True)

    legit_events, interaction_counter = generate_legitimate_events(
        users, all_user_ids, window_start, now,
        interaction_counter, rng, user_primary_ua, fake_ids,
        config=cfg,
        progress_callback=_progress,
    )
    if len(users) > len(fake_ids):
        print()
    interactions.extend(legit_events)

    # Sort by timestamp for realism
    interactions.sort(key=lambda i: i.timestamp)

    # Enforce invariant: account creation must be first per user,
    # and no events after CLOSE_ACCOUNT.
    interactions = _enforce_account_creation_first(interactions)
    interactions = _enforce_close_account_invariant(interactions)

    # Assign session IDs based on temporal gaps and login events
    _assign_session_ids(interactions, prefix="s")

    return interactions


def _assign_session_ids(
    interactions: list[UserInteraction],
    prefix: str = "s",
) -> None:
    """
    Assign session_id to interactions IN PLACE (mutates frozen instances).

    A new session starts when:
      - It's the first event for a user.
      - The event is a LOGIN or ACCOUNT_CREATION.
      - There's a 30+ minute gap since the previous event for that user.

    Must be called after sorting by timestamp.
    Uses object.__setattr__ to bypass frozen dataclass restriction.
    """
    user_session_counter: dict[str, int] = {}
    user_last_ts: dict[str, datetime] = {}
    session_gap = timedelta(minutes=30)

    for interaction in interactions:
        uid = interaction.user_id
        ts = interaction.timestamp
        itype = interaction.interaction_type

        new_session = False
        if uid not in user_session_counter:
            new_session = True
        elif itype in (InteractionType.LOGIN, InteractionType.ACCOUNT_CREATION):
            new_session = True
        elif (ts - user_last_ts[uid]) > session_gap:
            new_session = True

        if new_session:
            user_session_counter[uid] = user_session_counter.get(uid, 0) + 1

        user_last_ts[uid] = ts
        session_id = f"{uid}-{prefix}{user_session_counter[uid]:04d}"
        object.__setattr__(interaction, "session_id", session_id)


def _enforce_account_creation_first(
    interactions: list[UserInteraction],
) -> list[UserInteraction]:
    """
    Ensure ACCOUNT_CREATION is the first event per user.
    Move any events timestamped before account creation to after it.
    Input must be sorted by timestamp.
    """
    creation_ts: dict[str, datetime] = {}

    # First pass: find creation timestamps
    for i in interactions:
        if i.interaction_type == InteractionType.ACCOUNT_CREATION:
            if i.user_id not in creation_ts:
                creation_ts[i.user_id] = i.timestamp

    # Second pass: filter out events before account creation
    cleaned: list[UserInteraction] = []
    dropped_users: set[str] = set()
    for i in interactions:
        if i.interaction_type == InteractionType.ACCOUNT_CREATION:
            cleaned.append(i)
        elif i.user_id in creation_ts and i.timestamp >= creation_ts[i.user_id]:
            cleaned.append(i)
        else:
            # Track users whose events are dropped (no ACCOUNT_CREATION or before it)
            if i.user_id not in creation_ts:
                dropped_users.add(i.user_id)

    if dropped_users:
        logging.warning(
            f"{len(dropped_users)} user(s) had interactions but no "
            f"ACCOUNT_CREATION event — all their events were dropped: "
            f"{sorted(dropped_users)[:10]}{'...' if len(dropped_users) > 10 else ''}"
        )

    return cleaned


def _enforce_close_account_invariant(
    interactions: list[UserInteraction],
) -> list[UserInteraction]:
    """
    Remove any interactions that occur after a CLOSE_ACCOUNT for the same user.
    Input must be sorted by timestamp.
    """
    closed_at: dict[str, datetime] = {}
    cleaned: list[UserInteraction] = []

    for i in interactions:
        if i.user_id in closed_at:
            # Skip any event after the user's account was closed
            continue
        cleaned.append(i)
        if i.interaction_type == InteractionType.CLOSE_ACCOUNT:
            closed_at[i.user_id] = i.timestamp

    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_all(
    seed: int = 42,
    num_users: int = NUM_USERS,
    config: dict | None = None,
) -> tuple[list[User], list[UserProfile], list[UserInteraction]]:
    """
    Generate the complete mock dataset.

    Args:
        seed: Random seed for reproducibility.
        num_users: Number of regular (non-fake) users to generate.
        config: Dataset composition percentages (see generate.DATASET_CONFIG).

    Returns:
      (users, profiles, interactions) - all validated domain objects.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc) - timedelta(minutes=15)  # buffer so events stay in past during long run

    print(f"Generating {num_users} users...")
    users, used_emails, name_map = _generate_users(rng, now, num_users, config)
    print(f"  Created {len(users)} users ({sum(1 for u in users if not u.is_active)} inactive)")

    print(f"Generating {NUM_FAKE_ACCOUNTS} fake account users...")
    fake_users, fake_name_map = _generate_fake_account_users(rng, now, used_emails, base_idx=num_users)
    users = users + fake_users
    name_map.update(fake_name_map)
    print(f"  Total users: {len(users)}")

    print("Generating profiles (Zipf connections)...")
    profiles = _generate_profiles(users, name_map, rng, now, config)
    conns = [p.connections_count for p in profiles]
    conns.sort()
    median_conn = conns[len(conns) // 2]
    max_conn = conns[-1]
    print(f"  Created {len(profiles)} profiles (connections: median={median_conn}, max={max_conn})")

    print(f"Generating interactions ({INTERACTION_WINDOW_DAYS}-day window)...")
    interactions = _generate_interactions(users, rng, now, config)
    print(f"  Created {len(interactions)} interactions")

    return users, profiles, interactions
