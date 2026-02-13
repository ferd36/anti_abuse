"""
Tests for the Flask server API endpoints.

Covers:
  - GET / (index)
  - GET /api/users (list, search, pagination, bad params)
  - GET /api/users/<user_id> (found, not found, with/without profile)
  - GET /api/users/<user_id>/connections (found, not found, with data)
  - GET /api/users/<user_id>/interactions (found, not found, limit, bad limit)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("flask")
from flask.testing import FlaskClient

from db.repository import Repository
from core.enums import InteractionType, IPType
from core.models import User, UserInteraction, UserProfile


# ===================================================================
# Fixtures
# ===================================================================
@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.fixture
def repo_with_data(now: datetime) -> Repository:
    """In-memory repository pre-populated with test data."""
    repo = Repository(":memory:")

    users = [
        User(
            user_id="u-0001", email="alice@example.com",
            join_date=now - timedelta(days=30), country="US",
            ip_address="203.0.113.1", registration_ip="203.0.113.1",
            registration_country="US", address="123 Main St",
            ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
        ),
        User(
            user_id="u-0002", email="bob@example.com",
            join_date=now - timedelta(days=20), country="GB",
            ip_address="198.51.100.1", registration_ip="198.51.100.1",
            registration_country="GB", address="1 High St",
            ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
        ),
        User(
            user_id="u-0003", email="charlie@example.com",
            join_date=now - timedelta(days=10), country="DE",
            ip_address="198.51.100.2", registration_ip="198.51.100.2",
            registration_country="DE", address="",
            ip_type=IPType.HOSTING, language="de", is_active=False,
        ),
    ]
    repo.insert_users_batch(users)

    profiles = [
        UserProfile(
            user_id="u-0001", display_name="Alice Smith",
            headline="Engineer", summary="Loves code.",
            connections_count=10, profile_created_at=now - timedelta(days=29),
        ),
        UserProfile(
            user_id="u-0002", display_name="Bob Johnson",
            headline="Manager", summary="Team lead.",
            connections_count=5, profile_created_at=now - timedelta(days=19),
        ),
    ]
    repo.insert_profiles_batch(profiles)

    interactions = [
        UserInteraction(
            interaction_id="evt-0001", user_id="u-0001",
            interaction_type=InteractionType.LOGIN, timestamp=now - timedelta(hours=2),
            ip_address="203.0.113.1", ip_type=IPType.RESIDENTIAL,
            metadata={"user_agent": "Chrome/120"},
        ),
        UserInteraction(
            interaction_id="evt-0002", user_id="u-0001",
            interaction_type=InteractionType.MESSAGE_USER, timestamp=now - timedelta(hours=1),
            ip_address="203.0.113.1", ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
            metadata={"message_length": 100},
        ),
        UserInteraction(
            interaction_id="evt-0003", user_id="u-0001",
            interaction_type=InteractionType.CONNECT_WITH_USER, timestamp=now,
            ip_address="203.0.113.1", ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0002",
        ),
        UserInteraction(
            interaction_id="evt-0003a", user_id="u-0002",
            interaction_type=InteractionType.ACCEPT_CONNECTION_REQUEST,
            timestamp=now + timedelta(seconds=60),
            ip_address="198.51.100.1", ip_type=IPType.RESIDENTIAL,
            target_user_id="u-0001",
        ),
        UserInteraction(
            interaction_id="evt-0004", user_id="u-0002",
            interaction_type=InteractionType.LOGIN, timestamp=now,
            ip_address="198.51.100.1", ip_type=IPType.RESIDENTIAL,
        ),
    ]
    repo.insert_interactions_batch(interactions)

    return repo


@pytest.fixture
def client(repo_with_data: Repository, monkeypatch) -> FlaskClient:
    """Flask test client with monkeypatched repo."""
    import api.server as server_module

    monkeypatch.setattr(server_module, "get_repo", lambda: repo_with_data)

    server_module.app.config["TESTING"] = True
    with server_module.app.test_client() as client:
        with server_module.app.app_context():
            yield client

    repo_with_data.close()


@pytest.fixture
def client_with_real_repo(tmp_path, now: datetime, monkeypatch) -> FlaskClient:
    """Flask test client using the real get_repo/close_repo path with a temp DB."""
    import api.server as server_module

    db_path = tmp_path / "test.db"

    # Pre-populate the temp DB
    repo = Repository(db_path)
    repo.insert_user(User(
        user_id="u-0001", email="test@example.com",
        join_date=now - timedelta(days=5), country="US",
        ip_address="203.0.113.1", registration_ip="203.0.113.1",
        registration_country="US", address="",
        ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
    ))
    repo.close()

    # Point the server at our temp DB
    monkeypatch.setattr(server_module, "_DB_PATH", db_path)

    server_module.app.config["TESTING"] = True
    with server_module.app.test_client() as client:
        yield client


# ===================================================================
# Index
# ===================================================================
class TestRealRepoLifecycle:
    """Tests that exercise the real get_repo + close_repo teardown path."""

    def test_real_get_repo_and_teardown(self, client_with_real_repo: FlaskClient) -> None:
        resp = client_with_real_repo.get("/api/users/u-0001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["user_id"] == "u-0001"

    def test_real_repo_user_not_found(self, client_with_real_repo: FlaskClient) -> None:
        resp = client_with_real_repo.get("/api/users/u-9999")
        assert resp.status_code == 404


class TestIndex:
    def test_index_returns_html(self, client: FlaskClient) -> None:
        resp = client.get("/")
        # May return 200 if index.html exists, or 404 if not
        assert resp.status_code in (200, 404)


# ===================================================================
# GET /api/users
# ===================================================================
class TestListUsers:
    def test_list_users_default(self, client: FlaskClient) -> None:
        resp = client.get("/api/users")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["users"]) == 3
        assert data["page"] == 1
        assert data["per_page"] == 50

    def test_list_users_with_search(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?q=alice")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] >= 1
        user_ids = [u["user_id"] for u in data["users"]]
        assert "u-0001" in user_ids

    def test_list_users_search_by_country(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?q=DE")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] >= 1

    def test_list_users_pagination(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?per_page=1&page=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["users"]) == 1
        assert data["page"] == 2
        assert data["per_page"] == 1
        assert data["total"] == 3

    def test_list_users_bad_page(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?page=abc")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_list_users_bad_per_page(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?per_page=0")
        assert resp.status_code == 400

    def test_list_users_per_page_too_large(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?per_page=999")
        assert resp.status_code == 400

    def test_list_users_empty_search(self, client: FlaskClient) -> None:
        resp = client.get("/api/users?q=nonexistentxyz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert len(data["users"]) == 0


# ===================================================================
# GET /api/users/<user_id>
# ===================================================================
class TestGetUser:
    def test_get_user_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["user_id"] == "u-0001"
        assert data["user"]["email"] == "alice@example.com"
        assert data["profile"]["display_name"] == "Alice Smith"
        assert data["connections_count"] >= 0
        assert "interaction_counts" in data
        assert "recent_interactions" in data

    def test_get_user_not_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-9999")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_get_user_without_profile(self, client: FlaskClient) -> None:
        # u-0003 has no profile
        resp = client.get("/api/users/u-0003")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["user_id"] == "u-0003"
        assert data["profile"] is None

    def test_get_user_interaction_counts(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001")
        data = resp.get_json()
        counts = data["interaction_counts"]
        assert counts.get("login", 0) >= 1
        assert counts.get("message_user", 0) >= 1

    def test_get_user_recent_interactions(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001")
        data = resp.get_json()
        interactions = data["recent_interactions"]
        assert len(interactions) >= 1
        # Check interaction structure
        first = interactions[0]
        assert "interaction_id" in first
        assert "interaction_type" in first
        assert "timestamp" in first
        assert "ip_address" in first
        assert "metadata" in first


# ===================================================================
# GET /api/users/<user_id>/connections
# ===================================================================
class TestGetConnections:
    def test_get_connections_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/connections")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "u-0001"
        assert isinstance(data["connections"], list)

    def test_get_connections_not_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-9999/connections")
        assert resp.status_code == 404

    def test_get_connections_has_connected_user(self, client: FlaskClient) -> None:
        # u-0001 connected with u-0002
        resp = client.get("/api/users/u-0001/connections")
        data = resp.get_json()
        connected_ids = [c["user_id"] for c in data["connections"]]
        assert "u-0002" in connected_ids

    def test_get_connections_reverse_direction(self, client: FlaskClient) -> None:
        # u-0002 should also see u-0001 as connected (reverse lookup)
        resp = client.get("/api/users/u-0002/connections")
        data = resp.get_json()
        connected_ids = [c["user_id"] for c in data["connections"]]
        assert "u-0001" in connected_ids


# ===================================================================
# GET /api/users/<user_id>/interactions
# ===================================================================
class TestGetInteractions:
    def test_get_interactions_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "u-0001"
        assert len(data["interactions"]) >= 1

    def test_get_interactions_not_found(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-9999/interactions")
        assert resp.status_code == 404

    def test_get_interactions_with_limit(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions?limit=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["interactions"]) == 1

    def test_get_interactions_bad_limit(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions?limit=abc")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_get_interactions_limit_too_large(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions?limit=9999")
        assert resp.status_code == 400

    def test_get_interactions_limit_zero(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions?limit=0")
        assert resp.status_code == 400

    def test_interaction_structure(self, client: FlaskClient) -> None:
        resp = client.get("/api/users/u-0001/interactions?limit=1")
        data = resp.get_json()
        interaction = data["interactions"][0]
        assert "interaction_id" in interaction
        assert "interaction_type" in interaction
        assert "timestamp" in interaction
        assert "ip_address" in interaction
        assert "ip_type" in interaction
        assert "target_user_id" in interaction
        assert "metadata" in interaction


# ===================================================================
# Model & detection endpoints
# ===================================================================
class TestModelEndpoints:
    def test_model_status_no_model(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/model-status when no model exists."""
        import api.server as server_module
        monkeypatch.setattr(server_module, "_MODEL_PATH", tmp_path / "nonexistent.pt")
        resp = client.get("/api/model-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trained"] is False
        assert data["mtime"] is None

    def test_model_status_with_model(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/model-status when model exists."""
        import api.server as server_module
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake")
        monkeypatch.setattr(server_module, "_MODEL_PATH", model_path)
        resp = client.get("/api/model-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trained"] is True
        assert data["mtime"] is not None

    def test_clear_model_nothing_to_clear(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """POST /api/clear-model when no model exists."""
        import api.server as server_module
        monkeypatch.setattr(server_module, "_MODEL_PATH", tmp_path / "nonexistent.pt")
        monkeypatch.setattr(server_module, "_FLAGGED_PATH", tmp_path / "nonexistent.json")
        resp = client.post("/api/clear-model")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "No model" in data["message"]

    def test_clear_model_removes_files(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """POST /api/clear-model removes model and flagged files."""
        import api.server as server_module
        model_path = tmp_path / "model.pt"
        flagged_path = tmp_path / "flagged.json"
        model_path.write_text("fake")
        flagged_path.write_text("{}")
        monkeypatch.setattr(server_module, "_MODEL_PATH", model_path)
        monkeypatch.setattr(server_module, "_FLAGGED_PATH", flagged_path)
        resp = client.post("/api/clear-model")
        assert resp.status_code == 200
        assert not model_path.exists()
        assert not flagged_path.exists()

    def test_get_flagged_unavailable(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/flagged when no detection results."""
        import api.server as server_module
        monkeypatch.setattr(server_module, "_FLAGGED_PATH", tmp_path / "nonexistent.json")
        resp = client.get("/api/flagged")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is False

    def test_get_flagged_available(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/flagged when detection results exist."""
        import json
        import api.server as server_module
        flagged_path = tmp_path / "flagged.json"
        flagged_path.write_text('{"threshold": 0.5, "total_users": 10, "flagged_count": 2, "users": {"u-1": {"prob": 0.9, "flagged": true}}}')
        monkeypatch.setattr(server_module, "_load_flagged_data", lambda: json.loads(flagged_path.read_text()))
        resp = client.get("/api/flagged")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is True
        assert data["threshold"] == 0.5
        assert data["total_users"] == 10
        assert data["flagged_count"] == 2
        assert "u-1" in data["users"]

    def test_detection_metrics_unavailable(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/detection-metrics when no flagged data."""
        import api.server as server_module
        monkeypatch.setattr(server_module, "_FLAGGED_PATH", tmp_path / "nonexistent.json")
        resp = client.get("/api/detection-metrics")
        assert resp.status_code == 200
        assert resp.get_json()["available"] is False

    def test_detection_metrics_available(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/detection-metrics with flagged data and repo labels."""
        import json
        import api.server as server_module
        flagged_path = tmp_path / "flagged.json"
        flagged_path.write_text(
            '{"users": {"u-0001": {"prob": 0.9, "flagged": true}, "u-0002": {"prob": 0.1, "flagged": false}}}'
        )
        monkeypatch.setattr(
            server_module, "_load_flagged_data",
            lambda: json.loads(flagged_path.read_text()),
        )
        resp = client.get("/api/detection-metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is True
        assert "precision" in data
        assert "recall" in data
        assert "f1" in data
        assert "tp" in data

    def test_list_users_fraud_prob_sort_no_data(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/users?sort_by=fraud_prob falls back when no flagged data."""
        import api.server as server_module
        monkeypatch.setattr(server_module, "_FLAGGED_PATH", tmp_path / "nonexistent.json")
        resp = client.get("/api/users?sort_by=fraud_prob")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["users"]) >= 1

    def test_list_users_fraud_prob_sort_with_data(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/users?sort_by=fraud_prob uses flagged data when available."""
        import json
        import api.server as server_module
        flagged_path = tmp_path / "flagged.json"
        flagged_path.write_text(
            '{"users": {"u-0001": {"prob": 0.9, "flagged": true}, "u-0002": {"prob": 0.3, "flagged": false}, "u-0003": {"prob": 0.7, "flagged": true}}}'
        )
        monkeypatch.setattr(
            server_module, "_load_flagged_data",
            lambda: json.loads(flagged_path.read_text()),
        )
        resp = client.get("/api/users?sort_by=fraud_prob&sort_order=desc")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["users"]) >= 1
        probs = [u.get("fraud_prob") for u in data["users"] if u.get("fraud_prob") is not None]
        if len(probs) >= 2:
            assert probs == sorted(probs, reverse=True)

    def test_list_users_flagged_only(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """GET /api/users?flagged_only=1 filters to flagged users."""
        import json
        import api.server as server_module
        flagged_path = tmp_path / "flagged.json"
        flagged_path.write_text(
            '{"users": {"u-0001": {"prob": 0.9, "flagged": true}, "u-0002": {"prob": 0.1, "flagged": false}}}'
        )
        monkeypatch.setattr(
            server_module, "_load_flagged_data",
            lambda: json.loads(flagged_path.read_text()),
        )
        resp = client.get("/api/users?flagged_only=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["users"][0]["user_id"] == "u-0001"

    def test_run_train_streams(self, client: FlaskClient, monkeypatch) -> None:
        """POST /api/run-train streams SSE events."""
        from unittest.mock import MagicMock, patch
        import api.server as server_module

        def fake_stream():
            yield "data: {\"epoch\":1,\"loss\":0.5}\n\n"
            yield "data: {\"done\":true}\n\n"

        with patch.object(server_module, "_stream_train_loss", side_effect=fake_stream):
            resp = client.post("/api/run-train")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        assert b"epoch" in resp.data or b"done" in resp.data

    def test_run_train_real_stream(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        """POST /api/run-train with real _stream_train_loss (mocked subprocess)."""
        from unittest.mock import MagicMock, patch
        import api.server as server_module

        mock_proc = MagicMock()
        mock_proc.stdout = iter(['{"epoch":1,"loss":0.5}\n', '{"done":true}\n'])
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            resp = client.post("/api/run-train")
        assert resp.status_code == 200
        assert b"epoch" in resp.data or b"done" in resp.data

    def test_run_detection_success(self, client: FlaskClient, monkeypatch) -> None:
        """POST /api/run-detection returns success when detect succeeds."""
        from unittest.mock import patch
        import api.server as server_module

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "Done", "stderr": ""})()
            resp = client.post("/api/run-detection")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_run_detection_failure(self, client: FlaskClient, monkeypatch) -> None:
        """POST /api/run-detection returns 500 when detect fails."""
        from unittest.mock import patch
        import api.server as server_module

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 1, "stdout": "", "stderr": "Error"})()
            resp = client.post("/api/run-detection")
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False
