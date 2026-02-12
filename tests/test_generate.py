"""Tests for generate.py main entry point."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile
from generate import main


def _minimal_corpus():
    """Minimal corpus for fast testing."""
    now = datetime.now(timezone.utc)
    users = [
        User(
            user_id="u-1", email="a@b.com",
            join_date=now - timedelta(days=1), country="US",
            ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
            language="en", is_active=True,
        ),
    ]
    profiles = [
        UserProfile(
            user_id="u-1", display_name="A", headline="", summary="",
            connections_count=0, profile_created_at=now,
        ),
    ]
    interactions = [
        UserInteraction(
            interaction_id="evt-1", user_id="u-1",
            interaction_type=InteractionType.LOGIN, timestamp=now,
            ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
        ),
    ]
    return users, profiles, interactions


def test_generate_main_with_memory(capsys: pytest.CaptureFixture[str]) -> None:
    """generate.main() with --memory runs without error."""
    original_argv = sys.argv
    try:
        sys.argv = ["generate.py", "--memory"]
        with patch("generate.generate_all", return_value=_minimal_corpus()):
            with patch("generate.generate_malicious_events", return_value=([], {})):
                main()
    finally:
        sys.argv = original_argv

    out = capsys.readouterr().out
    assert "Using in-memory database" in out
    assert "users" in out.lower()


def test_generate_main_with_fraud_pct(capsys: pytest.CaptureFixture[str]) -> None:
    """generate.main() with --fraud-pct runs without error."""
    original_argv = sys.argv
    try:
        sys.argv = ["generate.py", "--memory", "--fraud-pct", "1.0"]
        with patch("generate.generate_all", return_value=_minimal_corpus()):
            with patch("generate.generate_malicious_events", return_value=([], {})):
                main()
    finally:
        sys.argv = original_argv

    out = capsys.readouterr().out
    assert "Using in-memory database" in out


def test_generate_main_with_users(capsys: pytest.CaptureFixture[str]) -> None:
    """generate.main() with --users passes num_users and config to generate_all."""
    original_argv = sys.argv
    try:
        sys.argv = ["generate.py", "--memory", "--users", "100"]
        with patch("generate.generate_all", return_value=_minimal_corpus()) as mock_gen:
            with patch("generate.generate_malicious_events", return_value=([], {})):
                main()
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["seed"] == 42
        assert call_kwargs["num_users"] == 100
        assert "config" in call_kwargs
        assert call_kwargs["config"]["users"]["inactive_pct"] == 0.05
    finally:
        sys.argv = original_argv


def test_generate_main_invalid_fraud_pct() -> None:
    """generate.main() with invalid --fraud-pct raises."""
    original_argv = sys.argv
    try:
        sys.argv = ["generate.py", "--memory", "--fraud-pct", "0"]
        with pytest.raises(AssertionError, match="fraud-pct"):
            main()
    finally:
        sys.argv = original_argv
