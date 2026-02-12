"""Dataset configuration for mock data generation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


def _default_config() -> dict:
    return {
        "users": {
            "inactive_pct": 0.05,
            "hosting_ip_pct": 0.10,
            "recruiter_pct": 0.06,
            "unrelated_email_pct": 0.05,
            "email_verified_pct": 0.95,
            "two_factor_pct": 0.25,
            "phone_verified_pct": 0.60,
            "password_changed_pct": 0.40,
            "account_tier_free": 0.70,
            "account_tier_premium": 0.25,
            "failed_login_streak_pct": 0.05,
        },
        "connections": {
            "zero_connections_pct": 0.08,
        },
        "profiles": {
            "profile_photo_pct": 0.75,
            "profile_updated_pct": 0.70,
        },
        "user_agents": {
            "non_browser_ua_pct": 0.12,
        },
        "email": {
            "first_last": 0.70,
            "firstlast": 0.85,
            "last_first": 0.92,
            "suffix_pct": 0.35,
        },
        "usage_patterns": {
            "returning_user_pct": 0.05,
            "career_update_pct": 0.03,
            "exec_delegation_pct": 0.02,
            "dormant_account_pct": 0.06,
            "pattern_weights": {
                "casual_browser": 0.26,
                "active_job_seeker": 0.11,
                "regular_networker": 0.26,
                "weekly_check_in": 0.16,
                "content_consumer": 0.21,
                "recruiter": 0.0,
                "new_user_onboarding": 0.0,
                "returning_user": 0.0,
                "career_update": 0.0,
                "exec_delegation": 0.0,
                "dormant_account": 0.0,
            },
            "dormant_account": {"login_once_pct": 0.70},
            "new_user_onboarding": {
                "profile_update_pct": 0.50,
                "upload_address_book_pct": 0.40,
                "message_on_connect_pct": 0.20,
            },
            "career_update": {
                "update_type_headline": 0.55,
                "update_type_summary": 0.85,
                "second_update_in_session_pct": 0.30,
            },
            "returning_user": {"second_session_pct": 0.40},
            "content_consumer": {
                "connect_after_view_pct": 0.05,
                "message_after_view_pct": 0.15,
            },
            "casual_browser": {
                "message_after_view_pct": 0.30,
                "like_react_after_view_pct": 0.40,
            },
            "recruiter": {"message_on_connect_pct": 0.20},
            "exec_delegation": {"message_on_connect_pct": 0.15},
            "active_job_seeker": {"headline_update_pct": 0.20},
        },
        "common": {
            "login_failure_before_success_pct": 0.03,
        },
        "fraud": {
            "pattern_weights": {
                "smash_grab": 0.073,
                "low_slow": 0.073,
                "country_hopper": 0.073,
                "data_thief": 0.073,
                "credential_stuffer": 0.171,
                "login_storm": 0.049,
                "stealth_takeover": 0.049,
                "scraper_cluster": 0.098,
                "spear_phisher": 0.073,
                "credential_tester": 0.122,
                "connection_harvester": 0.049,
                "sleeper_agent": 0.049,
                "profile_defacement": 0.049,
            },
            "fake_account": {"change_profile_pct": 0.70, "change_name_pct": 0.60},
            "connection_harvester": {"download_address_book_pct": 0.50},
            "country_hopper": {"view_during_hop_pct": 0.60},
            "credential_stuffer": {"close_account_pct": 0.50},
            "credential_tester": {
                "failed_login_first_pct": 0.30,
                "page_view_after_login_pct": 0.40,
            },
            "spear_phisher": {"profile_tweak_pct": 0.40, "change_name_pct": 0.30},
            "profile_defacement": {
                "change_profile_pct": 0.85,
                "change_password_pct": 0.40,
            },
        },
    }


@dataclass
class DatasetConfig:
    """Hierarchical dataset config: section -> generator -> parameter."""

    users: dict = field(default_factory=dict)
    connections: dict = field(default_factory=dict)
    profiles: dict = field(default_factory=dict)
    user_agents: dict = field(default_factory=dict)
    email: dict = field(default_factory=dict)
    usage_patterns: dict = field(default_factory=dict)
    common: dict = field(default_factory=dict)
    fraud: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        default = _default_config()
        for key in default:
            d = getattr(self, key, None)
            if not d:
                setattr(self, key, deepcopy(default[key]))
        self._validate()

    def __getitem__(self, key: str):
        """Support dict-like access: config['users']."""
        return getattr(self, key, None)

    def to_dict(self) -> dict:
        """Return nested dict for get_cfg() and downstream consumers."""
        return {
            "users": self.users,
            "connections": self.connections,
            "profiles": self.profiles,
            "user_agents": self.user_agents,
            "email": self.email,
            "usage_patterns": self.usage_patterns,
            "common": self.common,
            "fraud": self.fraud,
        }

    def _collect_pct_values(self, d: dict, prefix: str = "") -> list[tuple[str, float]]:
        """Recursively collect (path, value) for keys ending in _pct or known probability keys."""
        out: list[tuple[str, float]] = []
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(self._collect_pct_values(v, path))
            elif isinstance(v, (int, float)):
                if k.endswith("_pct") or k in (
                    "first_last", "firstlast", "last_first",
                    "account_tier_free", "account_tier_premium",
                ):
                    out.append((path, float(v)))
        return out

    def _validate(self) -> None:
        """Raise AssertionError if any invariant is violated."""
        errs: list[str] = []

        def check_pct(path: str, val: float) -> None:
            if not 0 <= val <= 1:
                errs.append(f"{path}={val}: must be in [0, 1]")

        for path, val in self._collect_pct_values(self.to_dict()):
            check_pct(path, val)

        free = self.users.get("account_tier_free", 0)
        prem = self.users.get("account_tier_premium", 0)
        if free + prem > 1:
            errs.append(f"users.account_tier_free + account_tier_premium = {free + prem} > 1")

        for pattern, weights in [
            ("usage_patterns.pattern_weights", self.usage_patterns.get("pattern_weights", {})),
            ("fraud.pattern_weights", self.fraud.get("pattern_weights", {})),
        ]:
            for k, w in weights.items():
                if not isinstance(w, (int, float)) or w < 0:
                    errs.append(f"{pattern}.{k}={w}: must be >= 0")

        if errs:
            raise AssertionError("Config invariants violated:\n  " + "\n  ".join(errs))


DATASET_CONFIG = DatasetConfig()
