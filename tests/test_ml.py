"""Tests for ml/ modules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("torch")
import torch

from ml.model import ATOClassifier, ATOCombinedClassifier, predict_proba
from ml.sequence_encoder import ActionSequenceEncoder


class TestATOClassifier:
    def test_forward_output_shape(self) -> None:
        model = ATOClassifier(n_features=31, hidden_dims=(16, 8), dropout=0.1)
        x = torch.randn(4, 31)
        out = model(x)
        assert out.shape == (4,)

    def test_predict_proba(self) -> None:
        model = ATOClassifier(n_features=31, hidden_dims=(16,), dropout=0.0)
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


class TestATOCombinedClassifier:
    def test_forward_output_shape(self) -> None:
        model = ATOCombinedClassifier(
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
    from pathlib import Path
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
