"""
Feature extraction for fraud detection.

Extracts behavioral, geographic, and pattern features per user
from the anti_abuse database.

Optimized for large datasets using pandas groupby instead of
per-user filtering.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ml.sequence_encoder import (
    ACTION_VOCAB,
    IP_TYPE_VOCAB,
    LOGIN_SUCCESS_VOCAB,
)


# ---------------------------------------------------------------------------
# Feature names (must match order/structure for model)
# ---------------------------------------------------------------------------
FEATURE_NAMES = [
    # --- behavioral tempo ---
    "login_to_download_minutes",
    "download_to_first_spam_minutes",
    "interactions_per_hour_1h",
    "interactions_per_hour_24h",
    "first_login_to_close_hours",
    # --- geo/IP ---
    "ip_country_mismatch",
    "ip_country_changes_last_7d",
    "ratio_hosting_ips",
    "num_distinct_ips_last_24h",
    # --- pattern ---
    "login_failures_before_success",
    "spam_count_last_24h",
    "unique_targets_messaged_last_24h",
    "download_address_book_count",
    # --- session/campaign ---
    "same_ip_shared_with_others",
    "sessions_last_7d",
    # --- profile ---
    "connections_count",
    "has_profile_photo",
    "profile_completeness",
    "endorsements_count",
    "profile_views_received",
    # --- account trust signals ---
    "email_verified",
    "two_factor_enabled",
    "phone_verified",
    "account_tier_premium",
    "account_tier_enterprise",
    "failed_login_streak",
    "account_age_days",
    # --- derived ---
    "hour_of_day_sin",
    "hour_of_day_cos",
    "days_since_last_activity",
    "script_user_agent",
]

_DEFAULT_ROW = {f: 0.0 for f in FEATURE_NAMES}
_DEFAULT_ROW["days_since_last_activity"] = 999.0


def _parse_metadata(meta_json: str) -> dict:
    """Parse metadata JSON, return empty dict on error."""
    if not meta_json:
        return {}
    try:
        return json.loads(meta_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_ip_country(meta: dict) -> str | None:
    """Extract country from metadata (ip_country or attacker_country)."""
    return meta.get("ip_country") or meta.get("attacker_country")


_NON_BROWSER_UA_HINTS = (
    "python", "requests", "curl", "wget", "httpie", "postman",
    "scrapy", "go-http", "java/", "okhttp", "node-fetch", "axios",
    "apache-http", "slackbot", "bot",
)


def _is_script_user_agent(meta: dict) -> bool:
    """Check if user agent suggests automation / non-browser client."""
    ua = meta.get("user_agent", "") or ""
    ua_lower = ua.lower()
    return any(hint in ua_lower for hint in _NON_BROWSER_UA_HINTS)


def _compute_user_features(
    user_ints: pd.DataFrame,
    user_country_val: str,
    user_connections_val: float,
    now: pd.Timestamp,
    shared_ips: set[str],
    user_attrs: dict | None = None,
) -> dict:
    """Compute feature dict for a single user given their interactions.

    Args:
        user_attrs: Optional dict with user/profile fields:
            has_profile_photo, profile_completeness, endorsements_count,
            profile_views_received, email_verified, two_factor_enabled,
            phone_verified, account_tier, failed_login_streak, account_age_days.
    """
    ua = user_attrs or {}
    if len(user_ints) == 0:
        row = dict(_DEFAULT_ROW)
        row["connections_count"] = user_connections_val
        row.update(_user_attr_features(ua))
        return row

    ts_col = user_ints["timestamp"]
    last_ts = ts_col.max()
    window_24h = last_ts - timedelta(hours=24)
    window_7d = last_ts - timedelta(days=7)
    window_1h = last_ts - timedelta(hours=1)

    mask_24h = ts_col >= window_24h
    mask_7d = ts_col >= window_7d
    mask_1h = ts_col >= window_1h

    recent_24h = user_ints[mask_24h]

    itype = user_ints["interaction_type"]

    # --- Behavioral tempo ---
    login_mask = itype == "login"
    download_mask = itype == "download_address_book"
    message_mask = itype == "message_user"
    close_mask = itype == "close_account"

    login_ts_vals = ts_col[login_mask]
    download_ts_vals = ts_col[download_mask]
    message_ts_vals = ts_col[message_mask]
    close_ts_vals = ts_col[close_mask]

    login_to_download_minutes = 0.0
    if len(login_ts_vals) > 0 and len(download_ts_vals) > 0:
        first_login = login_ts_vals.min()
        first_dl = download_ts_vals.min()
        if first_dl >= first_login:
            login_to_download_minutes = (first_dl - first_login).total_seconds() / 60

    download_to_first_spam_minutes = 0.0
    if len(download_ts_vals) > 0 and len(message_ts_vals) > 0:
        first_dl = download_ts_vals.min()
        first_msg = message_ts_vals.min()
        if first_msg >= first_dl:
            download_to_first_spam_minutes = (first_msg - first_dl).total_seconds() / 60

    ints_1h = mask_1h.sum()
    ints_24h = mask_24h.sum()
    interactions_per_hour_1h = float(ints_1h)
    ts_24h_min = recent_24h["timestamp"].min() if ints_24h > 0 else last_ts
    span_24h = (last_ts - ts_24h_min).total_seconds() / 3600
    hours_span_24h = max(1.0 / 24, min(24.0, span_24h))
    interactions_per_hour_24h = ints_24h / hours_span_24h

    first_login_to_close_hours = 0.0
    if len(login_ts_vals) > 0 and len(close_ts_vals) > 0:
        first_login = login_ts_vals.min()
        first_close = close_ts_vals.min()
        if first_close >= first_login:
            first_login_to_close_hours = (first_close - first_login).total_seconds() / 3600

    # --- Geo/IP ---
    ip_countries = user_ints["ip_country"].dropna()
    ip_country_mismatch = 1.0 if (ip_countries != user_country_val).any() else 0.0

    ip_countries_7d = user_ints.loc[mask_7d, "ip_country"].dropna()
    # shift() produces NaN for the first element; NaN != value is True,
    # so we subtract 1 to avoid counting the spurious first-element mismatch.
    ip_country_changes_7d = float(max(0, (ip_countries_7d != ip_countries_7d.shift()).sum() - 1)) if len(ip_countries_7d) > 1 else 0.0

    hosting_count = (user_ints["ip_type"] == "hosting").sum()
    ratio_hosting_ips = hosting_count / len(user_ints)

    distinct_ips_24h = float(recent_24h["ip_address"].nunique())

    # --- Pattern: count only failures that precede the first successful login ---
    login_evts = user_ints[login_mask]
    login_failures_before_success = 0.0
    first_success_ts = login_evts.loc[login_evts["login_success"] == True, "timestamp"].min()  # noqa: E712
    if pd.notna(first_success_ts):
        login_failures_before_success = float(
            ((login_evts["login_success"] == False) & (login_evts["timestamp"] < first_success_ts)).sum()  # noqa: E712
        )
    else:
        login_failures_before_success = float((login_evts["login_success"] == False).sum())  # noqa: E712

    recent_24h_itype = recent_24h["interaction_type"]
    spam_count_24h = float((recent_24h_itype == "message_user").sum())
    msg_24h = recent_24h[recent_24h_itype == "message_user"]
    unique_targets = float(msg_24h["target_user_id"].nunique()) if len(msg_24h) > 0 else 0.0
    download_count = float(download_mask.sum())

    # --- Session: same IP shared with others ---
    user_ips_24h = set(recent_24h["ip_address"].unique())
    same_ip_shared = 1.0 if user_ips_24h & shared_ips else 0.0

    # --- Session count (distinct sessions in last 7 days) ---
    if "session_id" in user_ints.columns:
        sessions_7d = user_ints.loc[mask_7d, "session_id"].dropna().nunique()
    else:
        sessions_7d = 0.0
    sessions_last_7d = float(sessions_7d)

    # --- Derived ---
    hour = last_ts.hour + last_ts.minute / 60
    hour_rad = hour * 2 * math.pi / 24
    hour_of_day_sin = float(math.sin(hour_rad))
    hour_of_day_cos = float(math.cos(hour_rad))
    days_since_last_activity = float((now - last_ts).total_seconds() / 86400)
    script_user_agent = 1.0 if user_ints["script_ua"].any() else 0.0

    result = {
        "login_to_download_minutes": login_to_download_minutes,
        "download_to_first_spam_minutes": download_to_first_spam_minutes,
        "interactions_per_hour_1h": interactions_per_hour_1h,
        "interactions_per_hour_24h": interactions_per_hour_24h,
        "first_login_to_close_hours": first_login_to_close_hours,
        "ip_country_mismatch": ip_country_mismatch,
        "ip_country_changes_last_7d": ip_country_changes_7d,
        "ratio_hosting_ips": ratio_hosting_ips,
        "num_distinct_ips_last_24h": distinct_ips_24h,
        "login_failures_before_success": login_failures_before_success,
        "spam_count_last_24h": spam_count_24h,
        "unique_targets_messaged_last_24h": unique_targets,
        "download_address_book_count": download_count,
        "same_ip_shared_with_others": same_ip_shared,
        "sessions_last_7d": sessions_last_7d,
        "connections_count": user_connections_val,
        "hour_of_day_sin": hour_of_day_sin,
        "hour_of_day_cos": hour_of_day_cos,
        "days_since_last_activity": days_since_last_activity,
        "script_user_agent": script_user_agent,
    }
    result.update(_user_attr_features(ua))
    return result


def _user_attr_features(ua: dict) -> dict:
    """Extract ML features from user/profile attribute dict."""
    tier = ua.get("account_tier", "free")
    return {
        "has_profile_photo": 1.0 if ua.get("has_profile_photo") else 0.0,
        "profile_completeness": float(ua.get("profile_completeness", 0.0)),
        "endorsements_count": float(ua.get("endorsements_count", 0)),
        "profile_views_received": float(ua.get("profile_views_received", 0)),
        "email_verified": 1.0 if ua.get("email_verified") else 0.0,
        "two_factor_enabled": 1.0 if ua.get("two_factor_enabled") else 0.0,
        "phone_verified": 1.0 if ua.get("phone_verified") else 0.0,
        "account_tier_premium": 1.0 if tier == "premium" else 0.0,
        "account_tier_enterprise": 1.0 if tier == "enterprise" else 0.0,
        "failed_login_streak": float(ua.get("failed_login_streak", 0)),
        "account_age_days": float(ua.get("account_age_days", 0)),
    }


def extract_features(db_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """
    Extract fraud detection features for all users.

    Args:
        db_path: Path to anti_abuse.db

    Returns:
        (X: features DataFrame, y: labels Series)
        y = 1 for fraud victims, 0 for legitimate users.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load users and profiles (connections_count + new fields).
    # ORDER BY user_id ensures consistent order with extract_sequences for combined model.
    users_df = pd.read_sql_query(
        """SELECT u.user_id, u.country, u.join_date, u.email_verified,
                  u.two_factor_enabled, u.account_tier, u.failed_login_streak,
                  u.phone_verified,
                  COALESCE(p.connections_count, 0) as connections_count,
                  COALESCE(p.has_profile_photo, 0) as has_profile_photo,
                  COALESCE(p.profile_completeness, 0.0) as profile_completeness,
                  COALESCE(p.endorsements_count, 0) as endorsements_count,
                  COALESCE(p.profile_views_received, 0) as profile_views_received
           FROM users u
           LEFT JOIN user_profiles p ON u.user_id = p.user_id
           ORDER BY u.user_id""",
        conn,
    )
    user_country = dict(zip(users_df["user_id"], users_df["country"]))
    user_connections = dict(zip(users_df["user_id"], users_df["connections_count"]))

    # Pre-compute per-user attribute dicts for the new features
    _now_dt = datetime.now(timezone.utc)
    user_attr_map: dict[str, dict] = {}
    for _, row in users_df.iterrows():
        uid = row["user_id"]
        join_dt = pd.to_datetime(row["join_date"], utc=True)
        user_attr_map[uid] = {
            "has_profile_photo": bool(row["has_profile_photo"]),
            "profile_completeness": float(row["profile_completeness"]),
            "endorsements_count": int(row["endorsements_count"]),
            "profile_views_received": int(row["profile_views_received"]),
            "email_verified": bool(row["email_verified"]),
            "two_factor_enabled": bool(row["two_factor_enabled"]),
            "phone_verified": bool(row["phone_verified"]),
            "account_tier": row["account_tier"],
            "failed_login_streak": int(row["failed_login_streak"]),
            "account_age_days": (_now_dt - join_dt.to_pydatetime()).days if pd.notna(join_dt) else 0,
        }

    # Load all interactions
    interactions = pd.read_sql_query(
        """SELECT user_id, interaction_type, timestamp, ip_address, ip_type,
                  target_user_id, metadata, session_id
           FROM user_interactions
           ORDER BY user_id, timestamp""",
        conn,
    )
    conn.close()

    interactions["timestamp"] = pd.to_datetime(interactions["timestamp"], utc=True)
    interactions["metadata"] = interactions["metadata"].apply(_parse_metadata)
    interactions["ip_country"] = interactions["metadata"].apply(_get_ip_country)
    interactions["script_ua"] = interactions["metadata"].apply(_is_script_user_agent)
    interactions["login_success"] = interactions["metadata"].apply(
        lambda m: m.get("login_success") if isinstance(m.get("login_success"), bool) else None
    )

    # Fraud label: user has any interaction with attack_pattern or attacker_country
    fraud_flags = interactions["metadata"].apply(
        lambda m: bool(m.get("attack_pattern") or m.get("attacker_country"))
    )
    fraud_user_ids = set(interactions.loc[fraud_flags, "user_id"].unique())
    labels = users_df["user_id"].isin(fraud_user_ids).astype(int)

    now = interactions["timestamp"].max()
    if pd.isna(now):
        now = pd.Timestamp(datetime.now(timezone.utc))

    # Pre-compute shared IPs: IPs used by 2+ users in their last 24h windows.
    # Build {user_id: last_ts} map, then filter interactions to each user's 24h,
    # count users per IP, collect IPs with 2+ users.
    user_last_ts = interactions.groupby("user_id")["timestamp"].max()
    interactions["_user_last_ts"] = interactions["user_id"].map(user_last_ts)
    interactions["_in_24h"] = interactions["timestamp"] >= (interactions["_user_last_ts"] - timedelta(hours=24))
    recent_all = interactions[interactions["_in_24h"]]
    ip_user_counts = recent_all.groupby("ip_address")["user_id"].nunique()
    shared_ips = set(ip_user_counts[ip_user_counts >= 2].index)
    interactions.drop(columns=["_user_last_ts", "_in_24h"], inplace=True)

    # Group interactions by user and compute features
    grouped = dict(list(interactions.groupby("user_id")))

    feature_rows = []
    for user_id in users_df["user_id"]:
        ua = user_attr_map.get(user_id, {})
        user_ints = grouped.get(user_id)
        if user_ints is None or len(user_ints) == 0:
            row = dict(_DEFAULT_ROW)
            row["connections_count"] = float(user_connections.get(user_id, 0))
            row.update(_user_attr_features(ua))
            feature_rows.append(row)
        else:
            feature_rows.append(_compute_user_features(
                user_ints,
                user_country.get(user_id, "US"),
                float(user_connections.get(user_id, 0)),
                now,
                shared_ips,
                user_attrs=ua,
            ))

    X = pd.DataFrame(feature_rows, columns=FEATURE_NAMES)
    y = pd.Series(labels.values, index=users_df["user_id"])
    return X, y


# ---------------------------------------------------------------------------
# Sequence extraction for transformer encoder
# ---------------------------------------------------------------------------
MAX_SEQ_LEN = 128

def extract_sequences(
    db_path: str | Path,
    max_seq_len: int = MAX_SEQ_LEN,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, pd.Series]:
    """
    Extract transformer-ready sequence data for all users.

    Optimized: uses vectorized pandas/numpy operations instead of per-row
    iteration, completing in ~30s for 100k users / 1.8M interactions.

    Returns:
        cat_tokens:  (n_users, max_seq_len, 4)  int tensor
        time_deltas: (n_users, max_seq_len)      float tensor
        mask:        (n_users, max_seq_len)      bool tensor (True = padding)
        y:           Series with user_id index    labels
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    users_df = pd.read_sql_query(
        "SELECT user_id, country FROM users ORDER BY user_id", conn,
    )
    user_country = dict(zip(users_df["user_id"], users_df["country"]))
    user_id_to_idx = {uid: i for i, uid in enumerate(users_df["user_id"])}

    interactions = pd.read_sql_query(
        """SELECT user_id, interaction_type, timestamp, ip_address, ip_type, metadata
           FROM user_interactions
           ORDER BY user_id, timestamp""",
        conn,
    )
    conn.close()

    print("  Parsing sequence metadata...")
    interactions["timestamp"] = pd.to_datetime(interactions["timestamp"], utc=True)
    interactions["metadata"] = interactions["metadata"].apply(_parse_metadata)
    interactions["ip_country"] = interactions["metadata"].apply(_get_ip_country)
    interactions["login_success"] = interactions["metadata"].apply(
        lambda m: m.get("login_success") if isinstance(m.get("login_success"), bool) else None
    )

    # Fraud labels
    fraud_flags = interactions["metadata"].apply(
        lambda m: bool(m.get("attack_pattern") or m.get("attacker_country"))
    )
    fraud_user_ids = set(interactions.loc[fraud_flags, "user_id"].unique())
    labels = users_df["user_id"].isin(fraud_user_ids).astype(int)

    # Vectorized tokenization: map string columns to integer codes
    print("  Tokenizing sequences (vectorized)...")
    action_codes = interactions["interaction_type"].map(ACTION_VOCAB).fillna(0).astype(np.int64)
    ip_type_codes = interactions["ip_type"].map(IP_TYPE_VOCAB).fillna(0).astype(np.int64)

    # Login success: True->1, False->2, else->3
    ls = interactions["login_success"]
    login_codes = np.full(len(interactions), LOGIN_SUCCESS_VOCAB["na"], dtype=np.int64)
    login_codes[ls == True] = LOGIN_SUCCESS_VOCAB["true"]  # noqa: E712
    login_codes[ls == False] = LOGIN_SUCCESS_VOCAB["false"]  # noqa: E712

    # IP country changed: compare each row's ip_country to user's country
    user_country_series = interactions["user_id"].map(user_country)
    ip_country_changed = (
        interactions["ip_country"].notna()
        & (interactions["ip_country"] != user_country_series)
    ).astype(np.int64).values

    # Time deltas (seconds between consecutive events, same user)
    ts_seconds = interactions["timestamp"].astype(np.int64) // 10**9
    ts_diff = ts_seconds.diff().fillna(0).values.astype(np.float64)
    # Zero out cross-user boundaries
    user_boundary = interactions["user_id"].values[1:] != interactions["user_id"].values[:-1]
    ts_diff[0] = 0.0
    ts_diff[1:][user_boundary] = 0.0
    ts_diff_minutes = np.clip(ts_diff / 60.0, 0, 10080.0).astype(np.float32)

    # Map user_ids to indices
    user_idx = interactions["user_id"].map(user_id_to_idx).values

    # Build per-user sequence position: within-user row counter
    group_sizes = interactions.groupby("user_id").cumcount().values

    # Allocate output arrays
    n_users = len(users_df)
    all_cat = np.zeros((n_users, max_seq_len, 4), dtype=np.int64)
    all_deltas = np.zeros((n_users, max_seq_len), dtype=np.float32)
    all_mask = np.ones((n_users, max_seq_len), dtype=bool)

    # Count interactions per user to determine which to keep (last max_seq_len)
    user_counts = interactions.groupby("user_id").size()

    # Process in bulk: for each row, compute its target position in the output
    print("  Filling sequence arrays...")
    user_total = interactions["user_id"].map(user_counts).values
    # Position from end: if user has N interactions and this is the k-th (0-indexed),
    # its position in the output is: max_seq_len - (N - k)  if N <= max_seq_len
    # Or: k - (N - max_seq_len) if N > max_seq_len (skip first N - max_seq_len)
    offset = np.maximum(user_total - max_seq_len, 0)
    seq_pos = group_sizes - offset
    # Only keep rows where seq_pos >= 0 and seq_pos < max_seq_len
    keep = (seq_pos >= 0) & (seq_pos < max_seq_len)

    kept_user_idx = user_idx[keep]
    kept_seq_pos = seq_pos[keep]
    kept_action = action_codes.values[keep]
    kept_ip_type = ip_type_codes.values[keep]
    kept_login = login_codes[keep]
    kept_country_changed = ip_country_changed[keep]
    kept_deltas = ts_diff_minutes[keep]

    all_cat[kept_user_idx, kept_seq_pos, 0] = kept_action
    all_cat[kept_user_idx, kept_seq_pos, 1] = kept_ip_type
    all_cat[kept_user_idx, kept_seq_pos, 2] = kept_login
    all_cat[kept_user_idx, kept_seq_pos, 3] = kept_country_changed
    all_deltas[kept_user_idx, kept_seq_pos] = kept_deltas
    all_mask[kept_user_idx, kept_seq_pos] = False

    y = pd.Series(labels.values, index=users_df["user_id"])

    return (
        torch.from_numpy(all_cat),
        torch.from_numpy(all_deltas),
        torch.from_numpy(all_mask),
        y,
    )
