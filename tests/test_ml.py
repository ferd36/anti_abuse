"""Tests for ml/ modules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("torch")
import torch

from ml.model import FraudClassifier, FraudCombinedClassifier, predict_proba
from ml.sequence_encoder import ActionSequenceEncoder


class TestFraudClassifier:
    def test_forward_output_shape(self) -> None:
        model = FraudClassifier(n_features=31, hidden_dims=(16, 8), dropout=0.1)
        x = torch.randn(4, 31)
        out = model(x)
        assert out.shape == (4,)

    def test_predict_proba(self) -> None:
        model = FraudClassifier(n_features=31, hidden_dims=(16,), dropout=0.0)
        x = torch.randn(2, 31)
        probs = predict_proba(model, x)
        assert probs.shape == (2,)
        assert (probs >= 0).all() and (probs <= 1).all()


def _make_cat_tokens(batch: int, seq_len: int) -> torch.Tensor:
    """Tensor with valid vocab indices: action 0-11, ip_type 0-2, login 0-3, ip_country 0-1."""
    return torch.stack([
        torch.randint(0, 12, (batch, seq_len)),  # action
        torch.randint(0, 3, (batch, seq_len)),   # ip_type
        torch.randint(0, 4, (batch, seq_len)),   # login_success
        torch.randint(0, 2, (batch, seq_len)),   # ip_country_changed
    ], dim=-1)


class TestFraudCombinedClassifier:
    def test_forward_output_shape(self) -> None:
        model = FraudCombinedClassifier(
            n_features=31,
            seq_embed_dim=16,
            seq_n_heads=2,
            seq_n_layers=1,
            hidden_dims=(16,),
            dropout=0.1,
            max_seq_len=32,
        )
        batch = 4
        x_features = torch.randn(batch, 31)
        cat_tokens = _make_cat_tokens(batch, 32)
        time_deltas = torch.randn(batch, 32)
        mask = torch.ones(batch, 32, dtype=torch.bool)
        out = model(x_features, cat_tokens, time_deltas, mask)
        assert out.shape == (batch,)


class TestActionSequenceEncoder:
    def test_forward_output_shape(self) -> None:
        encoder = ActionSequenceEncoder(
            embed_dim=32, n_heads=2, n_layers=1, dropout=0.0, max_seq_len=64
        )
        batch, seq_len = 2, 64
        cat_tokens = _make_cat_tokens(batch, seq_len)
        time_deltas = torch.randn(batch, seq_len)
        mask = torch.ones(batch, seq_len, dtype=torch.bool)
        out = encoder(cat_tokens, time_deltas, mask)
        assert out.shape == (batch, 32)


def _make_test_db(tmp_path):
    """Create minimal test DB with users, profiles, interactions."""
    from db.repository import Repository
    from core.enums import InteractionType, IPType
    from core.models import User, UserInteraction, UserProfile

    db_path = tmp_path / "test.db"
    now = datetime.now(timezone.utc)
    repo = Repository(db_path)
    repo.insert_user(User(
        user_id="u-1", email="a@b.com",
        join_date=now, country="US",
        ip_address="1.2.3.4", registration_ip="1.2.3.4",
        registration_country="US", address="",
        ip_type=IPType.RESIDENTIAL, language="en", is_active=True,
    ))
    repo.insert_profiles_batch([UserProfile(
        user_id="u-1", display_name="A", headline="", summary="",
        connections_count=0, profile_created_at=now,
    )])
    repo.insert_interactions_batch([UserInteraction(
        interaction_id="evt-1", user_id="u-1",
        interaction_type=InteractionType.LOGIN, timestamp=now,
        ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
    )])
    repo.close()
    return db_path


def _make_trainable_db(tmp_path):
    """Create DB with multiple users (including one fraud) for training."""
    from db.repository import Repository
    from core.enums import InteractionType, IPType
    from core.models import User, UserInteraction, UserProfile

    db_path = tmp_path / "train.db"
    now = datetime.now(timezone.utc)
    repo = Repository(db_path)
    for i in range(10):
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
        is_fraud = i < 2
        evts = [
            UserInteraction(
                interaction_id=f"evt-{i}-1", user_id=uid,
                interaction_type=InteractionType.LOGIN, timestamp=now,
                ip_address="1.2.3.4", ip_type=IPType.RESIDENTIAL,
                metadata={"attack_pattern": "test", "login_success": True} if is_fraud else {"login_success": True},
            ),
        ]
        repo.insert_interactions_batch(evts)
    repo.close()
    return db_path


class TestExtractFeatures:
    def test_extract_features_with_db(self, tmp_path) -> None:
        """extract_features runs on a DB with schema and data from generate."""
        pytest.importorskip("pandas")
        from ml.features import extract_features

        db_path = _make_test_db(tmp_path)
        X_df, y_series = extract_features(db_path)
        assert len(X_df) == len(y_series)
        assert len(X_df.columns) > 0

    def test_extract_sequences_with_db(self, tmp_path) -> None:
        """extract_sequences runs on a DB and returns tensors."""
        pytest.importorskip("pandas")
        from ml.features import extract_sequences

        db_path = _make_test_db(tmp_path)
        cat_tokens, time_deltas, mask, y = extract_sequences(db_path, max_seq_len=32)
        assert cat_tokens.dim() == 3
        assert cat_tokens.shape[0] == len(y)
        assert time_deltas.shape == (len(y), 32)
        assert mask.shape == (len(y), 32)


class TestFeatureHelpers:
    """Unit tests for feature extraction helpers."""

    def test_parse_metadata_empty(self) -> None:
        from ml.features import _parse_metadata
        assert _parse_metadata("") == {}
        assert _parse_metadata(None) == {}

    def test_parse_metadata_invalid_json(self) -> None:
        from ml.features import _parse_metadata
        assert _parse_metadata("not json") == {}
        assert _parse_metadata("{invalid") == {}

    def test_get_ip_country(self) -> None:
        from ml.features import _get_ip_country
        assert _get_ip_country({"ip_country": "US"}) == "US"
        assert _get_ip_country({"attacker_country": "RU"}) == "RU"
        assert _get_ip_country({"ip_country": "DE", "attacker_country": "RU"}) == "DE"
        assert _get_ip_country({}) is None

    def test_is_script_user_agent(self) -> None:
        from ml.features import _is_script_user_agent
        assert _is_script_user_agent({"user_agent": "python-requests/2.31"}) is True
        assert _is_script_user_agent({"user_agent": "Mozilla/5.0 Chrome"}) is False
        assert _is_script_user_agent({"user_agent": "Go-http-client/2.0"}) is True


class TestTrain:
    """Tests for ml.train module."""

    @pytest.mark.slow
    def test_train_mlp_single_epoch(self, tmp_path, capsys) -> None:
        """ml.train runs with MLP model for 1 epoch and saves model."""
        pytest.importorskip("pandas")
        import sys

        db_path = _make_trainable_db(tmp_path)
        out_dir = tmp_path / "output"
        out_dir.mkdir()

        old_argv = sys.argv
        try:
            sys.argv = [
                "ml.train", "--db", str(db_path), "--model", "mlp",
                "--epochs", "1", "--out-dir", str(out_dir),
            ]
            from ml import train as train_module
            train_module.train_mlp(train_module.parse_args())
        finally:
            sys.argv = old_argv

        assert (out_dir / "model.pt").exists()
        assert (out_dir / "config.json").exists()
        assert (out_dir / "scaler_mean.npy").exists()

    def test_train_parse_args(self) -> None:
        """parse_args returns namespace with defaults."""
        import sys

        old_argv = sys.argv
        try:
            sys.argv = ["ml.train", "--epochs", "2"]
            from ml.train import parse_args
            args = parse_args()
            assert args.epochs == 2
            assert args.model in ("mlp", "combined")
        finally:
            sys.argv = old_argv

    @pytest.mark.slow
    def test_train_combined_single_epoch(self, tmp_path, capsys) -> None:
        """ml.train runs with combined model for 1 epoch and saves."""
        pytest.importorskip("pandas")
        import sys

        db_path = _make_trainable_db(tmp_path)
        out_dir = tmp_path / "output"
        out_dir.mkdir()

        old_argv = sys.argv
        try:
            sys.argv = [
                "ml.train", "--db", str(db_path), "--model", "combined",
                "--epochs", "1", "--out-dir", str(out_dir),
                "--seq-embed-dim", "16", "--seq-n-heads", "2", "--seq-n-layers", "1",
            ]
            from ml import train as train_module
            train_module.train_combined(train_module.parse_args())
        finally:
            sys.argv = old_argv

        assert (out_dir / "model.pt").exists()
        assert (out_dir / "config.json").exists()
        config = __import__("json").loads((out_dir / "config.json").read_text())
        assert config["model_type"] == "combined"

    def test_train_main_invokes_mlp(self, tmp_path) -> None:
        """ml.train __main__ invokes train_mlp when --model mlp."""
        pytest.importorskip("pandas")
        import sys
        from unittest.mock import patch

        db_path = _make_trainable_db(tmp_path)
        old_argv = sys.argv
        try:
            sys.argv = ["ml.train", "--db", str(db_path), "--model", "mlp", "--epochs", "1"]
            with patch("ml.train.train_mlp") as mock_mlp:
                with patch("ml.train.train_combined"):
                    from ml.train import main
                    main()
                mock_mlp.assert_called_once()
        finally:
            sys.argv = old_argv

    def test_train_main_invokes_combined(self, tmp_path) -> None:
        """ml.train __main__ invokes train_combined when --model combined."""
        pytest.importorskip("pandas")
        import sys
        from unittest.mock import patch

        db_path = _make_trainable_db(tmp_path)
        old_argv = sys.argv
        try:
            sys.argv = ["ml.train", "--db", str(db_path), "--model", "combined", "--epochs", "1"]
            with patch("ml.train.train_mlp"):
                with patch("ml.train.train_combined") as mock_combined:
                    from ml.train import main
                    main()
                mock_combined.assert_called_once()
        finally:
            sys.argv = old_argv


class TestPredict:
    """Tests for ml.predict module."""

    def test_predict_main_mlp(self, tmp_path, capsys) -> None:
        """ml.predict.main() runs with MLP model and prints results."""
        pytest.importorskip("pandas")
        import json
        import sys

        import numpy as np

        from ml.features import FEATURE_NAMES
        from ml.model import FraudClassifier

        db_path = _make_trainable_db(tmp_path)
        model_dir = tmp_path / "model"
        model_dir.mkdir()

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

        old_argv = sys.argv
        try:
            sys.argv = ["ml.predict", "--db", str(db_path), "--model-dir", str(model_dir), "--top-k", "3"]
            from ml.predict import main
            main()
        finally:
            sys.argv = old_argv

        out = capsys.readouterr().out
        assert "predicted fraud" in out.lower() or "fraud" in out.lower()
        assert "Summary" in out or "summary" in out.lower()

    def test_predict_main_combined(self, tmp_path, capsys) -> None:
        """ml.predict.main() runs with combined model and prints results."""
        pytest.importorskip("pandas")
        import json
        import sys

        import numpy as np

        from ml.features import FEATURE_NAMES
        from ml.model import FraudCombinedClassifier

        db_path = _make_trainable_db(tmp_path)
        model_dir = tmp_path / "model"
        model_dir.mkdir()

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

        old_argv = sys.argv
        try:
            sys.argv = ["ml.predict", "--db", str(db_path), "--model-dir", str(model_dir), "--top-k", "3"]
            from ml.predict import main
            main()
        finally:
            sys.argv = old_argv

        out = capsys.readouterr().out
        assert "combined" in out.lower() or "predicted fraud" in out.lower() or "fraud" in out.lower()
        assert "Summary" in out or "summary" in out.lower()


class TestPipeline:
    """Tests for ml.pipeline module."""

    def test_pipeline_main_no_generate(self, tmp_path, monkeypatch) -> None:
        """ml.pipeline.main() runs training without --generate."""
        pytest.importorskip("pandas")
        import sys
        from unittest.mock import patch

        db_path = _make_trainable_db(tmp_path)
        monkeypatch.chdir(tmp_path)

        old_argv = sys.argv
        try:
            sys.argv = [
                "ml.pipeline", "--db", str(db_path),
                "--train-fraction", "0.5", "--epochs", "1",
            ]
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type("R", (), {"returncode": 0})()
                from ml.pipeline import main
                rc = main()
            assert rc == 0
            assert mock_run.call_count == 1
            call_args = mock_run.call_args[0][0]
            assert "ml.train" in call_args
        finally:
            sys.argv = old_argv

    def test_pipeline_main_with_generate(self, tmp_path, monkeypatch) -> None:
        """ml.pipeline.main() with --generate runs generate then train."""
        pytest.importorskip("pandas")
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)

        old_argv = sys.argv
        try:
            sys.argv = ["ml.pipeline", "--generate", "--epochs", "1"]
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type("R", (), {"returncode": 0})()
                from ml.pipeline import main
                rc = main()
            assert rc == 0
            assert mock_run.call_count == 2
        finally:
            sys.argv = old_argv
