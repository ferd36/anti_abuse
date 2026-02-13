"""Config helpers for dataset generation."""

from __future__ import annotations


def get_cfg(cfg: dict | None, *path: str, default=None):
    """Get nested config value. get_cfg(cfg, 'users', 'inactive_pct', default=0.05)."""
    if hasattr(cfg, "to_dict"):
        cfg = cfg.to_dict()
    d = cfg or {}
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d
