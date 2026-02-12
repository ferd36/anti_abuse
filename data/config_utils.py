"""Config helpers for dataset generation."""

from __future__ import annotations


def get_cfg(cfg: dict | None, *path: str, default=None):
    """Get nested config value. get_cfg(cfg, 'users', 'inactive_pct', default=0.05)."""
    if hasattr(cfg, "to_dict"):
        cfg = cfg.to_dict()
    d = cfg or {}
    for k in path:
        d = (d or {}).get(k, {})
    if d is None or (isinstance(d, dict) and len(d) == 0):
        return default
    return d
