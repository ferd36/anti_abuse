"""Tests for serve.py main entry point."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

pytest.importorskip("flask")
from serve import main


def test_serve_main_parses_args() -> None:
    """serve.main() parses --port and calls app.run."""
    original_argv = sys.argv
    try:
        sys.argv = ["serve.py", "--port", "5999"]
        with patch("serve.app") as mock_app:
            main()
            mock_app.run.assert_called_once_with(debug=True, port=5999)
    finally:
        sys.argv = original_argv


def test_serve_main_default_port() -> None:
    """serve.main() uses default port 5001 when --port not given."""
    original_argv = sys.argv
    try:
        sys.argv = ["serve.py"]
        with patch("serve.app") as mock_app:
            main()
            mock_app.run.assert_called_once_with(debug=True, port=5001)
    finally:
        sys.argv = original_argv
