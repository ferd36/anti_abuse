"""
SQLite database layer for the anti-abuse ATO system.

Provides:
  - Schema creation (users, user_profiles, user_interactions tables).
  - Repository class with CRUD and query operations.
  - Conversion between domain objects and DB rows.

Pre-conditions are enforced on all public methods.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile


# ===================================================================
# Schema DDL
# ===================================================================
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id                  TEXT PRIMARY KEY,
    email                    TEXT NOT NULL UNIQUE,
    join_date                TEXT NOT NULL,          -- ISO-8601 UTC
    country                  TEXT NOT NULL,
    ip_address               TEXT NOT NULL,
    registration_ip          TEXT NOT NULL,          -- IP at account creation (country-matched for legit)
    registration_country    TEXT NOT NULL,          -- where user signed up; differs from country when moved
    address                  TEXT NOT NULL DEFAULT '', -- current address; for moved users, reflects new location
    ip_type                  TEXT NOT NULL,          -- 'residential' | 'hosting'
    language                 TEXT NOT NULL,
    is_active                INTEGER NOT NULL DEFAULT 1,   -- 0/1 boolean
    generation_pattern       TEXT NOT NULL DEFAULT 'clean',
    email_verified           INTEGER NOT NULL DEFAULT 1,   -- 0/1 boolean
    two_factor_enabled       INTEGER NOT NULL DEFAULT 0,   -- 0/1 boolean
    last_password_change_at  TEXT,                          -- ISO-8601 UTC, nullable
    account_tier             TEXT NOT NULL DEFAULT 'free',  -- free | premium | enterprise
    failed_login_streak      INTEGER NOT NULL DEFAULT 0,
    phone_verified           INTEGER NOT NULL DEFAULT 0,   -- 0/1 boolean
    user_type                TEXT NOT NULL DEFAULT 'regular'  -- regular | recruiter
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id              TEXT PRIMARY KEY REFERENCES users(user_id),
    display_name         TEXT NOT NULL,
    headline             TEXT NOT NULL DEFAULT '',
    summary              TEXT NOT NULL DEFAULT '',
    connections_count    INTEGER NOT NULL DEFAULT 0,
    profile_created_at   TEXT NOT NULL,     -- ISO-8601 UTC
    last_updated_at      TEXT,              -- ISO-8601 UTC, nullable
    has_profile_photo    INTEGER NOT NULL DEFAULT 0,   -- 0/1 boolean
    profile_completeness REAL NOT NULL DEFAULT 0.0,    -- 0.0 to 1.0
    endorsements_count   INTEGER NOT NULL DEFAULT 0,
    profile_views_received INTEGER NOT NULL DEFAULT 0,
    location_text        TEXT NOT NULL DEFAULT '',
    groups_joined        TEXT NOT NULL DEFAULT '[]',  -- JSON array of group_id strings
    cloned_from_user_id  TEXT REFERENCES users(user_id)  -- nullable, for profile cloning
);

CREATE TABLE IF NOT EXISTS user_interactions (
    interaction_id   TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(user_id),
    interaction_type TEXT NOT NULL,
    timestamp        TEXT NOT NULL,        -- ISO-8601 UTC
    ip_address       TEXT NOT NULL,
    ip_type          TEXT NOT NULL,
    target_user_id   TEXT REFERENCES users(user_id),  -- nullable
    metadata         TEXT NOT NULL DEFAULT '{}',  -- JSON string
    session_id       TEXT                  -- nullable
);

CREATE INDEX IF NOT EXISTS idx_interactions_user
    ON user_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type
    ON user_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp
    ON user_interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_target
    ON user_interactions(target_user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_session
    ON user_interactions(session_id);
"""


# ===================================================================
# Helpers
# ===================================================================
def _dt_to_iso(dt: datetime) -> str:
    """Convert a timezone-aware datetime to an ISO-8601 UTC string.

    Always normalizes to UTC so that stored strings sort correctly
    via lexicographic comparison (used by enforce_close_account_invariant).
    """
    # Normalize to UTC to guarantee consistent '+00:00' suffix
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.isoformat()


def _iso_to_dt(s: str) -> datetime:
    """Parse an ISO-8601 string back to a timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


# ===================================================================
# Repository
# ===================================================================
class Repository:
    """
    Data-access layer backed by SQLite.

    Pre-conditions:
      - db_path must be a valid path (or ':memory:' for in-memory).
      - All insert methods require domain objects that already satisfy
        their own invariants.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        # Migration: add registration_ip if missing (existing DBs)
        try:
            self._conn.execute("ALTER TABLE users ADD COLUMN registration_ip TEXT")
            self._conn.execute("UPDATE users SET registration_ip = ip_address WHERE registration_ip IS NULL")
            self._conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        # Migration: add registration_country and address if missing
        for col, default_sql in [
            ("registration_country", "country"),
            ("address", "''"),
        ]:
            try:
                self._conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                self._conn.execute(f"UPDATE users SET {col} = COALESCE({default_sql}, '') WHERE {col} IS NULL")
                self._conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
        # Migration: add groups_joined to user_profiles if missing
        try:
            self._conn.execute("ALTER TABLE user_profiles ADD COLUMN groups_joined TEXT NOT NULL DEFAULT '[]'")
            self._conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        # Migration: add cloned_from_user_id to user_profiles if missing
        try:
            self._conn.execute("ALTER TABLE user_profiles ADD COLUMN cloned_from_user_id TEXT REFERENCES users(user_id)")
            self._conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def insert_user(self, user: User) -> None:
        """Insert a single user. Pre-condition: user is a valid User."""
        assert isinstance(user, User), f"Expected User, got {type(user)}"
        self._conn.execute(
            """INSERT INTO users
               (user_id, email, join_date, country, ip_address, registration_ip,
                registration_country, address, ip_type, language,
                is_active, generation_pattern, email_verified, two_factor_enabled,
                last_password_change_at, account_tier, failed_login_streak, phone_verified,
                user_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._user_to_row(user),
        )
        self._conn.commit()

    def insert_users_batch(self, users: list[User]) -> None:
        """Insert multiple users in a single transaction."""
        assert all(isinstance(u, User) for u in users), "All items must be User"
        rows = [self._user_to_row(u) for u in users]
        self._conn.executemany(
            """INSERT INTO users
               (user_id, email, join_date, country, ip_address, registration_ip,
                registration_country, address, ip_type, language,
                is_active, generation_pattern, email_verified, two_factor_enabled,
                last_password_change_at, account_tier, failed_login_streak, phone_verified,
                user_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    @staticmethod
    def _user_to_row(u: User) -> tuple:
        return (
            u.user_id, u.email, _dt_to_iso(u.join_date), u.country,
            u.ip_address, u.registration_ip, u.registration_country, u.address,
            u.ip_type.value, u.language, 1 if u.is_active else 0,
            u.generation_pattern, 1 if u.email_verified else 0,
            1 if u.two_factor_enabled else 0,
            _dt_to_iso(u.last_password_change_at) if u.last_password_change_at else None,
            u.account_tier, u.failed_login_streak, 1 if u.phone_verified else 0,
            getattr(u, "user_type", "regular"),
        )

    def get_user(self, user_id: str) -> User | None:
        """Fetch a user by ID. Returns None if not found."""
        assert isinstance(user_id, str) and len(user_id) > 0
        row = self._conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def get_user_with_profile(self, user_id: str) -> tuple[User | None, UserProfile | None]:
        """Fetch user and profile in one query. Returns (User, Profile) or (None, None)."""
        assert isinstance(user_id, str) and len(user_id) > 0
        row = self._conn.execute(
            """SELECT u.*, p.display_name, p.headline, p.summary, p.connections_count,
                      p.profile_created_at, p.last_updated_at,
                      p.has_profile_photo, p.profile_completeness,
                      p.endorsements_count, p.profile_views_received, p.location_text,
                      p.groups_joined, p.cloned_from_user_id
               FROM users u
               LEFT JOIN user_profiles p ON u.user_id = p.user_id
               WHERE u.user_id = ?""",
            (user_id,),
        ).fetchone()
        if row is None:
            return None, None
        user = self._row_to_user(row)
        if row["display_name"] is None:
            return user, None
        profile = self._row_to_profile(row)
        return user, profile

    def get_all_users(self) -> list[User]:
        """Return all users."""
        rows = self._conn.execute("SELECT * FROM users").fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_active_user_ids(self) -> list[str]:
        """Return IDs of all active users."""
        rows = self._conn.execute(
            "SELECT user_id FROM users WHERE is_active = 1"
        ).fetchall()
        return [r["user_id"] for r in rows]

    def count_users(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_user_generation_patterns(self) -> dict[str, str]:
        """Return user_id -> generation_pattern for all users."""
        rows = self._conn.execute(
            "SELECT user_id, generation_pattern FROM users"
        ).fetchall()
        return {r["user_id"]: r["generation_pattern"] for r in rows}

    def update_user_generation_pattern(self, user_id: str, generation_pattern: str) -> None:
        """Update the generation_pattern for a user (e.g. when marking as ATO victim)."""
        assert isinstance(user_id, str) and len(user_id) > 0
        assert isinstance(generation_pattern, str) and len(generation_pattern) > 0
        self._conn.execute(
            "UPDATE users SET generation_pattern = ? WHERE user_id = ?",
            (generation_pattern, user_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        keys = row.keys()
        return User(
            user_id=row["user_id"],
            email=row["email"],
            join_date=_iso_to_dt(row["join_date"]),
            country=row["country"],
            ip_address=row["ip_address"],
            registration_ip=row["registration_ip"] if "registration_ip" in keys else row["ip_address"],
            registration_country=row["registration_country"] if "registration_country" in keys else row["country"],
            address=row["address"] if "address" in keys else "",
            ip_type=IPType(row["ip_type"]),
            language=row["language"],
            is_active=bool(row["is_active"]),
            generation_pattern=row["generation_pattern"] if "generation_pattern" in keys else "clean",
            email_verified=bool(row["email_verified"]) if "email_verified" in keys else True,
            two_factor_enabled=bool(row["two_factor_enabled"]) if "two_factor_enabled" in keys else False,
            last_password_change_at=(
                _iso_to_dt(row["last_password_change_at"]) if row["last_password_change_at"] else None
            ) if "last_password_change_at" in keys else None,
            account_tier=row["account_tier"] if "account_tier" in keys else "free",
            failed_login_streak=row["failed_login_streak"] if "failed_login_streak" in keys else 0,
            phone_verified=bool(row["phone_verified"]) if "phone_verified" in keys else False,
            user_type=row["user_type"] if "user_type" in keys else "regular",
        )

    # ------------------------------------------------------------------
    # UserProfiles
    # ------------------------------------------------------------------
    def insert_profile(self, profile: UserProfile) -> None:
        """Insert a single profile. Pre-condition: profile is a valid UserProfile."""
        assert isinstance(profile, UserProfile), f"Expected UserProfile, got {type(profile)}"
        self._conn.execute(
            """INSERT INTO user_profiles
               (user_id, display_name, headline, summary, connections_count,
                profile_created_at, last_updated_at, has_profile_photo,
                profile_completeness, endorsements_count, profile_views_received,
                location_text, groups_joined, cloned_from_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._profile_to_row(profile),
        )
        self._conn.commit()

    def insert_profiles_batch(self, profiles: list[UserProfile]) -> None:
        """Insert multiple profiles in a single transaction."""
        assert all(isinstance(p, UserProfile) for p in profiles)
        rows = [self._profile_to_row(p) for p in profiles]
        self._conn.executemany(
            """INSERT INTO user_profiles
               (user_id, display_name, headline, summary, connections_count,
                profile_created_at, last_updated_at, has_profile_photo,
                profile_completeness, endorsements_count, profile_views_received,
                location_text, groups_joined, cloned_from_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    @staticmethod
    def _profile_to_row(p: UserProfile) -> tuple:
        return (
            p.user_id, p.display_name, p.headline, p.summary,
            p.connections_count, _dt_to_iso(p.profile_created_at),
            _dt_to_iso(p.last_updated_at) if p.last_updated_at else None,
            1 if p.has_profile_photo else 0, p.profile_completeness,
            p.endorsements_count, p.profile_views_received, p.location_text,
            json.dumps(list(p.groups_joined)),
            getattr(p, "cloned_from_user_id", None),
        )

    def get_profile(self, user_id: str) -> UserProfile | None:
        """Fetch a profile by user_id. Returns None if not found."""
        assert isinstance(user_id, str) and len(user_id) > 0
        row = self._conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_profile(row)

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> UserProfile:
        keys = row.keys()
        raw = row["groups_joined"] if "groups_joined" in keys else "[]"
        try:
            groups = tuple(json.loads(raw)) if raw else ()
        except (json.JSONDecodeError, TypeError):
            groups = ()
        cloned_from = row["cloned_from_user_id"] if "cloned_from_user_id" in keys else None
        return UserProfile(
            user_id=row["user_id"],
            display_name=row["display_name"],
            headline=row["headline"],
            summary=row["summary"],
            connections_count=row["connections_count"],
            profile_created_at=_iso_to_dt(row["profile_created_at"]),
            last_updated_at=_iso_to_dt(row["last_updated_at"]) if row["last_updated_at"] else None,
            has_profile_photo=bool(row["has_profile_photo"]) if "has_profile_photo" in keys else False,
            profile_completeness=float(row["profile_completeness"]) if "profile_completeness" in keys else 0.0,
            endorsements_count=row["endorsements_count"] if "endorsements_count" in keys else 0,
            profile_views_received=row["profile_views_received"] if "profile_views_received" in keys else 0,
            location_text=row["location_text"] if "location_text" in keys else "",
            groups_joined=groups,
            cloned_from_user_id=cloned_from if cloned_from else None,
        )

    # ------------------------------------------------------------------
    # UserInteractions
    # ------------------------------------------------------------------
    def insert_interaction(self, interaction: UserInteraction) -> None:
        """Insert a single interaction."""
        assert isinstance(interaction, UserInteraction)
        self._conn.execute(
            """INSERT INTO user_interactions
               (interaction_id, user_id, interaction_type, timestamp,
                ip_address, ip_type, target_user_id, metadata, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._interaction_to_row(interaction),
        )
        self._conn.commit()

    def insert_interactions_batch(self, interactions: list[UserInteraction]) -> None:
        """Insert multiple interactions in a single transaction."""
        assert all(isinstance(i, UserInteraction) for i in interactions)
        rows = [self._interaction_to_row(i) for i in interactions]
        self._conn.executemany(
            """INSERT INTO user_interactions
               (interaction_id, user_id, interaction_type, timestamp,
                ip_address, ip_type, target_user_id, metadata, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    def get_interactions_by_user(
        self, user_id: str, limit: int | None = None
    ) -> list[UserInteraction]:
        """Fetch interactions for a user, ordered by timestamp desc."""
        assert isinstance(user_id, str) and len(user_id) > 0
        sql = "SELECT * FROM user_interactions WHERE user_id = ? ORDER BY timestamp DESC"
        params: list = [user_id]
        if limit is not None:
            assert isinstance(limit, int) and limit > 0
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_interaction(r) for r in rows]

    def get_interactions_by_type(
        self, interaction_type: InteractionType, limit: int | None = None
    ) -> list[UserInteraction]:
        """Fetch interactions of a given type, ordered by timestamp desc."""
        assert isinstance(interaction_type, InteractionType)
        sql = "SELECT * FROM user_interactions WHERE interaction_type = ? ORDER BY timestamp DESC"
        params: list = [interaction_type.value]
        if limit is not None:
            assert isinstance(limit, int) and limit > 0
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_interaction(r) for r in rows]

    def get_interactions_in_range(
        self, start: datetime, end: datetime
    ) -> list[UserInteraction]:
        """Fetch interactions in a time range [start, end]."""
        assert start.tzinfo is not None and end.tzinfo is not None
        assert start <= end
        rows = self._conn.execute(
            """SELECT * FROM user_interactions
               WHERE timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp""",
            (_dt_to_iso(start), _dt_to_iso(end)),
        ).fetchall()
        return [self._row_to_interaction(r) for r in rows]

    def get_connections(self, user_id: str) -> list[dict]:
        """
        Return users connected to the given user (via CONNECT_WITH_USER).
        Looks at both directions: user initiated or was the target.
        Returns list of dicts with user_id, display_name, headline, country.
        """
        assert isinstance(user_id, str) and len(user_id) > 0
        rows = self._conn.execute(
            """SELECT DISTINCT
                   CASE WHEN i.user_id = ? THEN i.target_user_id ELSE i.user_id END AS connected_id
               FROM user_interactions i
               WHERE i.interaction_type = 'connect_with_user'
                 AND (i.user_id = ? OR i.target_user_id = ?)""",
            (user_id, user_id, user_id),
        ).fetchall()
        connected_ids = [r["connected_id"] for r in rows]
        if not connected_ids:
            return []
        placeholders = ",".join("?" for _ in connected_ids)
        profiles = self._conn.execute(
            f"""SELECT u.user_id, u.country, u.is_active,
                       p.display_name, p.headline
                FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                WHERE u.user_id IN ({placeholders})
                ORDER BY p.display_name""",
            connected_ids,
        ).fetchall()
        return [
            {
                "user_id": r["user_id"],
                "display_name": r["display_name"] or r["user_id"],
                "headline": r["headline"] or "",
                "country": r["country"],
                "is_active": bool(r["is_active"]),
            }
            for r in profiles
        ]

    _SORT_COLUMNS = {
        "user_id": "u.user_id",
        "display_name": "p.display_name",
        "headline": "p.headline",
        "country": "u.country",
        "ip_type": "u.ip_type",
        "is_active": "u.is_active",
        "ato_prob": "u.ato_prob",
        "generation_pattern": "u.generation_pattern",
        "connections_count": "p.connections_count",
        "join_date": "u.join_date",
    }

    def search_users(
        self,
        query: str = "",
        page: int = 1,
        per_page: int = 50,
        user_ids_filter: list[str] | None = None,
        sort_by: str = "user_id",
        sort_order: str = "asc",
    ) -> dict:
        """
        Search/paginate users joined with profiles.
        Returns {users: [...], total: int, page: int, per_page: int}.
        When user_ids_filter is provided, only returns users in that set.
        """
        assert page >= 1 and per_page >= 1
        offset = (page - 1) * per_page

        order_col = self._SORT_COLUMNS.get(sort_by, "u.user_id")
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
        order_clause = f"ORDER BY {order_col} {order_dir}, u.user_id ASC"

        base_where = ""
        base_params: tuple = ()
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            base_where = (
                " AND (u.user_id LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\' "
                "OR p.display_name LIKE ? ESCAPE '\\' OR u.country LIKE ? ESCAPE '\\')"
            )
            base_params = (like, like, like, like)

        if user_ids_filter is not None and len(user_ids_filter) == 0:
            return {"users": [], "total": 0, "page": page, "per_page": per_page}

        filter_where = ""
        filter_params: tuple = ()
        if user_ids_filter is not None and len(user_ids_filter) > 0:
            placeholders = ",".join("?" * len(user_ids_filter))
            filter_where = f" AND u.user_id IN ({placeholders})"
            filter_params = tuple(user_ids_filter)

        where_clause = "WHERE 1=1" + base_where + filter_where
        all_params = base_params + filter_params

        count = self._conn.execute(
            f"""SELECT COUNT(*) FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                {where_clause}""",
            all_params,
        ).fetchone()[0]

        rows = self._conn.execute(
            f"""SELECT u.*, p.display_name, p.headline, p.connections_count,
                       p.has_profile_photo, p.profile_completeness,
                       p.endorsements_count, p.profile_views_received, p.location_text
                FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                {where_clause}
                {order_clause}
                LIMIT ? OFFSET ?""",
            all_params + (per_page, offset),
        ).fetchall()
        users = [self._row_to_user_dict(r) for r in rows]
        return {"users": users, "total": count, "page": page, "per_page": per_page}

    def get_user_ids_matching(
        self,
        query: str = "",
        user_ids_filter: list[str] | None = None,
    ) -> list[str]:
        """Return user_ids matching the search filters (for risk sorting)."""
        base_where = ""
        base_params: tuple = ()
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            base_where = (
                " AND (u.user_id LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\' "
                "OR p.display_name LIKE ? ESCAPE '\\' OR u.country LIKE ? ESCAPE '\\')"
            )
            base_params = (like, like, like, like)

        if user_ids_filter is not None and len(user_ids_filter) == 0:
            return []

        filter_where = ""
        filter_params: tuple = ()
        if user_ids_filter is not None and len(user_ids_filter) > 0:
            placeholders = ",".join("?" * len(user_ids_filter))
            filter_where = f" AND u.user_id IN ({placeholders})"
            filter_params = tuple(user_ids_filter)

        where_clause = "WHERE 1=1" + base_where + filter_where
        all_params = base_params + filter_params

        rows = self._conn.execute(
            f"""SELECT u.user_id FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                {where_clause}
                ORDER BY u.user_id""",
            all_params,
        ).fetchall()
        return [r["user_id"] for r in rows]

    def get_users_by_ids_ordered(self, user_ids: list[str]) -> list[dict]:
        """Return users with profiles for the given IDs, in the order of user_ids."""
        if not user_ids:
            return []
        placeholders = ",".join("?" * len(user_ids))
        order_map = {uid: i for i, uid in enumerate(user_ids)}
        rows = self._conn.execute(
            f"""SELECT u.*, p.display_name, p.headline, p.connections_count,
                       p.has_profile_photo, p.profile_completeness,
                       p.endorsements_count, p.profile_views_received, p.location_text
                FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                WHERE u.user_id IN ({placeholders})""",
            user_ids,
        ).fetchall()
        users = [self._row_to_user_dict(r) for r in rows]
        users.sort(key=lambda u: order_map[u["user_id"]])
        return users

    @staticmethod
    def _row_to_user_dict(r: sqlite3.Row) -> dict:
        """Convert a joined user+profile row to a dict for API responses."""
        keys = r.keys()
        return {
            "user_id": r["user_id"],
            "email": r["email"],
            "country": r["country"],
            "ip_type": r["ip_type"],
            "language": r["language"],
            "is_active": bool(r["is_active"]),
            "join_date": r["join_date"],
            "display_name": r["display_name"] or r["user_id"],
            "headline": r["headline"] or "",
            "connections_count": r["connections_count"] or 0,
            "generation_pattern": r["generation_pattern"] if "generation_pattern" in keys else "clean",
            "email_verified": bool(r["email_verified"]) if "email_verified" in keys else True,
            "two_factor_enabled": bool(r["two_factor_enabled"]) if "two_factor_enabled" in keys else False,
            "account_tier": r["account_tier"] if "account_tier" in keys else "free",
            "phone_verified": bool(r["phone_verified"]) if "phone_verified" in keys else False,
            "has_profile_photo": bool(r["has_profile_photo"]) if "has_profile_photo" in keys else False,
            "profile_completeness": float(r["profile_completeness"] or 0),
            "endorsements_count": r["endorsements_count"] if "endorsements_count" in keys else 0,
            "profile_views_received": r["profile_views_received"] if "profile_views_received" in keys else 0,
            "location_text": r["location_text"] if "location_text" in keys else "",
        }

    def count_interactions_by_type_for_user(self, user_id: str) -> dict[str, int]:
        """Return {interaction_type_value: count} for a specific user."""
        assert isinstance(user_id, str) and len(user_id) > 0
        rows = self._conn.execute(
            """SELECT interaction_type, COUNT(*) as cnt
               FROM user_interactions
               WHERE user_id = ?
               GROUP BY interaction_type""",
            (user_id,),
        ).fetchall()
        return {r["interaction_type"]: r["cnt"] for r in rows}

    def count_interactions(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM user_interactions"
        ).fetchone()[0]

    def count_interactions_by_type(self) -> dict[str, int]:
        """Return {interaction_type_value: count}."""
        rows = self._conn.execute(
            """SELECT interaction_type, COUNT(*) as cnt
               FROM user_interactions GROUP BY interaction_type"""
        ).fetchall()
        return {r["interaction_type"]: r["cnt"] for r in rows}

    @staticmethod
    def _interaction_to_row(i: UserInteraction) -> tuple:
        return (
            i.interaction_id,
            i.user_id,
            i.interaction_type.value,
            _dt_to_iso(i.timestamp),
            i.ip_address,
            i.ip_type.value,
            i.target_user_id,
            json.dumps(i.metadata),
            i.session_id,
        )

    @staticmethod
    def _row_to_interaction(row: sqlite3.Row) -> UserInteraction:
        keys = row.keys()
        return UserInteraction(
            interaction_id=row["interaction_id"],
            user_id=row["user_id"],
            interaction_type=InteractionType(row["interaction_type"]),
            timestamp=_iso_to_dt(row["timestamp"]),
            ip_address=row["ip_address"],
            ip_type=IPType(row["ip_type"]),
            target_user_id=row["target_user_id"],
            metadata=json.loads(row["metadata"]),
            session_id=row["session_id"] if "session_id" in keys else None,
        )

    # ------------------------------------------------------------------
    # Invariant enforcement
    # ------------------------------------------------------------------
    def enforce_close_account_invariant(self) -> int:
        """
        Delete any interactions that occur after a CLOSE_ACCOUNT event
        for the same user. Returns the number of rows deleted.

        This handles cross-dataset issues (e.g. legitimate events that
        predate ATO close events, or vice versa).
        """
        deleted = self._conn.execute(
            """DELETE FROM user_interactions
               WHERE rowid IN (
                   SELECT i.rowid
                   FROM user_interactions i
                   INNER JOIN (
                       SELECT user_id, MIN(timestamp) AS close_ts
                       FROM user_interactions
                       WHERE interaction_type = 'close_account'
                       GROUP BY user_id
                   ) c ON i.user_id = c.user_id
                   WHERE i.timestamp > c.close_ts
               )"""
        ).rowcount
        self._conn.commit()
        return deleted

    def deactivate_users_with_close_account(self) -> int:
        """
        Set is_active=False for all users who have a CLOSE_ACCOUNT event.
        Returns the number of users updated.
        """
        updated = self._conn.execute(
            """UPDATE users SET is_active = 0
               WHERE user_id IN (
                   SELECT DISTINCT user_id FROM user_interactions
                   WHERE interaction_type = 'close_account'
               )"""
        ).rowcount
        self._conn.commit()
        return updated

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._conn.close()
