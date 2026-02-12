"""Tests for config.py."""

from __future__ import annotations

import pytest

from config import DatasetConfig, DATASET_CONFIG


def test_default_config_validates() -> None:
    """Default DATASET_CONFIG passes _validate() on init."""
    assert DATASET_CONFIG["users"]["inactive_pct"] == 0.05


def test_empty_config_populates_all_sections() -> None:
    """DatasetConfig() with no args populates all sections from defaults."""
    cfg = DatasetConfig()
    assert cfg.users
    assert cfg.connections
    assert cfg.profiles
    assert cfg.user_agents
    assert cfg.email
    assert cfg.usage_patterns
    assert cfg.common
    assert cfg.fraud


def test_partial_override_keeps_provided_section() -> None:
    """DatasetConfig(users={...}) keeps override; other sections use defaults."""
    cfg = DatasetConfig(users={"inactive_pct": 0.01})
    assert cfg.users["inactive_pct"] == 0.01
    assert cfg.connections["zero_connections_pct"] == 0.08


def test_config_to_dict_has_nested_structure() -> None:
    """to_dict() returns nested dict used by get_cfg()."""
    d = DATASET_CONFIG.to_dict()
    assert d["users"]["inactive_pct"] == 0.05
    assert d["fraud"]["pattern_weights"]["credential_stuffer"] == 0.171


def test_to_dict_returns_all_sections() -> None:
    """to_dict() includes all 8 top-level sections."""
    d = DATASET_CONFIG.to_dict()
    assert set(d) == {"users", "connections", "profiles", "user_agents", "email", "usage_patterns", "common", "fraud"}


def test_config_getitem() -> None:
    """DatasetConfig supports dict-like access."""
    assert DATASET_CONFIG["users"]["inactive_pct"] == 0.05


def test_config_getitem_unknown_key_returns_none() -> None:
    """__getitem__ for unknown key returns None."""
    assert DATASET_CONFIG["nonexistent"] is None


def test_validate_accepts_boundary_values() -> None:
    """_validate() accepts 0 and 1 as valid percentages."""
    DatasetConfig(users={"inactive_pct": 0})
    DatasetConfig(users={"inactive_pct": 1})


def test_validate_raises_on_invalid_pct() -> None:
    """_validate() raises when a percentage is outside [0, 1]."""
    with pytest.raises(AssertionError, match="inactive_pct=1.5"):
        DatasetConfig(users={"inactive_pct": 1.5})


def test_validate_raises_on_negative_pct() -> None:
    """_validate() raises when a percentage is negative."""
    with pytest.raises(AssertionError, match="-0.1"):
        DatasetConfig(users={"inactive_pct": -0.1})


def test_validate_raises_on_nested_invalid_pct() -> None:
    """_validate() raises for invalid pct in nested section."""
    with pytest.raises(AssertionError, match="login_once_pct"):
        DatasetConfig(usage_patterns={"dormant_account": {"login_once_pct": 2.0}})


def test_validate_raises_on_account_tier_sum() -> None:
    """_validate() raises when account_tier_free + premium > 1."""
    with pytest.raises(AssertionError, match="account_tier"):
        DatasetConfig(users={"account_tier_free": 0.8, "account_tier_premium": 0.3})


def test_validate_accepts_account_tier_sum_equal_one() -> None:
    """_validate() accepts account_tier_free + premium == 1."""
    DatasetConfig(users={"account_tier_free": 0.7, "account_tier_premium": 0.3})


def test_validate_raises_on_negative_pattern_weight() -> None:
    """_validate() raises when fraud pattern weight is negative."""
    with pytest.raises(AssertionError, match="must be >= 0"):
        DatasetConfig(fraud={"pattern_weights": {"smash_grab": -0.1}})


def test_validate_raises_on_negative_usage_pattern_weight() -> None:
    """_validate() raises when usage_patterns weight is negative."""
    with pytest.raises(AssertionError, match="must be >= 0"):
        DatasetConfig(usage_patterns={"pattern_weights": {"casual_browser": -0.1}})


def test_validate_raises_on_non_numeric_pattern_weight() -> None:
    """_validate() raises when pattern weight is not numeric."""
    with pytest.raises(AssertionError, match="must be >= 0"):
        DatasetConfig(fraud={"pattern_weights": {"smash_grab": "bad"}})


def test_validate_reports_multiple_errors() -> None:
    """_validate() collects and reports all invariant violations."""
    with pytest.raises(AssertionError) as exc_info:
        DatasetConfig(
            users={"inactive_pct": 1.5, "account_tier_free": 0.9, "account_tier_premium": 0.2},
            fraud={"pattern_weights": {"smash_grab": -0.1}},
        )
    msg = str(exc_info.value)
    assert "inactive_pct=1.5" in msg
    assert "account_tier" in msg
    assert "smash_grab=-0.1" in msg
