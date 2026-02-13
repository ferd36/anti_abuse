"""Pytest configuration for anti_abuse tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (run with pytest -m slow or pytest --run-slow)",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (disabled by default)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test (use --run-slow to run)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
