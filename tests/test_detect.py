"""Tests for detect.py CLI."""

from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("torch")


def _make_minimal_db(tmp_path, repo_factory):
    """Create minimal DB with users and interactions for feature extraction."""
    from datetime import datetime, timezone

    from core.enums import InteractionType, IPType
    from core.models import User, UserInteraction, UserProfile

    db_path = tmp_path / "detect_test.db"
    now = datetime.now(timezone.utc)
    repo = repo_factory(db_path)
    for i in range(5):
        uid = f"u-{i:04d}"
        repo.insert_user(User(
            user_id=uid, email=f"u{i}@test.com",
            join_date=now, country="US",
            ip_address="1.2.3.4", registration_ip="1.2.3.4",
            registration_country="US", address="",
            ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
        ))
        repo.insert_profiles_batch([UserProfile(
            user_id=uid, display_name=f"User{i}", headline="", summary="",
            connections_count=0, profile_created_at=now,
        )])
        repo.insert_interactions_batch([UserInteraction(
            interaction_id=f"evt-{i}", user_id=uid,
            interaction_type=InteractionType.LOGIN, timestamp=now,
            ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
        )])
    repo.close()
    return db_path


def test_detect_main_mlp(tmp_path, monkeypatch) -> None:
    """detect.main() runs with MLP model and writes flagged_users.json."""
    pytest.importorskip("pandas")
    from db.repository import Repository

    db_path = _make_minimal_db(tmp_path, Repository)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    import numpy as np
    import torch

    from ml.features import FEATURE_NAMES
    from ml.model import FraudClassifier
    n_features = len(FEATURE_NAMES)
    model = FraudClassifier(n_features=n_features, hidden_dims=(16,), dropout=0.1)
    torch.save(model.state_dict(), model_dir / "model.pt")
    np.save(model_dir / "scaler_mean.npy", np.zeros(n_features))
    np.save(model_dir / "scaler_scale.npy", np.ones(n_features))
    with open(model_dir / "config.json", "w") as f:
        json.dump({
            "model_type": "mlp",
            "n_features": n_features,
            "hidden_dims": [16],
            "dropout": 0.1,
        }, f, indent=2)

    from detect import main

    output_path = tmp_path / "flagged.json"
    old_argv = sys.argv
    try:
        sys.argv = ["detect.py", "--db", str(db_path), "--model-dir", str(model_dir), "--output", str(output_path)]
        rc = main()
    finally:
        sys.argv = old_argv

    assert rc == 0
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "users" in data
    assert data["total_users"] == 5
    assert "threshold" in data


def test_detect_main_combined(tmp_path, monkeypatch) -> None:
    """detect.main() runs with combined model and writes flagged_users.json."""
    pytest.importorskip("pandas")
    from db.repository import Repository

    db_path = _make_minimal_db(tmp_path, Repository)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    import json
    import sys

    import numpy as np
    import torch

    from ml.features import FEATURE_NAMES
    from ml.model import FraudCombinedClassifier

    n_features = len(FEATURE_NAMES)
    max_seq_len = 32
    model = FraudCombinedClassifier(
        n_features=n_features,
        seq_embed_dim=16,
        seq_n_heads=2,
        seq_n_layers=1,
        hidden_dims=(16,),
        dropout=0.1,
        max_seq_len=max_seq_len,
    )
    torch.save(model.state_dict(), model_dir / "model.pt")
    np.save(model_dir / "scaler_mean.npy", np.zeros(n_features))
    np.save(model_dir / "scaler_scale.npy", np.ones(n_features))
    with open(model_dir / "config.json", "w") as f:
        json.dump({
            "model_type": "combined",
            "n_features": n_features,
            "seq_embed_dim": 16,
            "seq_n_heads": 2,
            "seq_n_layers": 1,
            "seq_dropout": 0.1,
            "hidden_dims": [16],
            "dropout": 0.1,
            "max_seq_len": max_seq_len,
        }, f, indent=2)

    output_path = tmp_path / "flagged_combined.json"
    old_argv = sys.argv
    try:
        sys.argv = ["detect.py", "--db", str(db_path), "--model-dir", str(model_dir), "--output", str(output_path)]
        from detect import main
        rc = main()
    finally:
        sys.argv = old_argv

    assert rc == 0
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert data["model_type"] == "combined"

