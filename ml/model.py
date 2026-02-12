"""
PyTorch neural networks for ATO detection.

- ATOClassifier: MLP-only model (hand-crafted features).
- ATOCombinedClassifier: Transformer sequence encoder + MLP (hand-crafted
  features concatenated with transformer embedding). Trained end-to-end.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from ml.sequence_encoder import ActionSequenceEncoder


class ATOClassifier(nn.Module):
    """
    Multi-layer perceptron for ATO victim classification.

    Input: normalized feature vector of shape (batch_size, n_features)
    Output: logits of shape (batch_size,) for binary classification
    """

    def __init__(
        self,
        n_features: int,
        hidden_dims: tuple[int, ...] = (128, 64, 32),
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.n_features = n_features

        layers = []
        prev_dim = n_features
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h_dim),
                nn.BatchNorm1d(h_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
            ])
            prev_dim = h_dim
        self.backbone = nn.Sequential(*layers)
        self.head = nn.Linear(prev_dim, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch_size, n_features)

        Returns:
            (batch_size,) logits
        """
        h = self.backbone(x)
        return self.head(h).squeeze(-1)


class ATOCombinedClassifier(nn.Module):
    """
    Combined transformer + MLP model.

    The transformer encodes the user's interaction sequence into a
    fixed-size embedding. This is concatenated with the hand-crafted
    feature vector and fed through an MLP head.

    Trained end-to-end: gradients flow through both the transformer
    and the MLP.
    """

    def __init__(
        self,
        n_features: int,
        seq_embed_dim: int = 64,
        seq_n_heads: int = 4,
        seq_n_layers: int = 2,
        seq_dropout: float = 0.1,
        hidden_dims: tuple[int, ...] = (128, 64, 32),
        dropout: float = 0.3,
        max_seq_len: int = 128,
    ) -> None:
        super().__init__()
        self.n_features = n_features
        self.seq_embed_dim = seq_embed_dim

        self.seq_encoder = ActionSequenceEncoder(
            embed_dim=seq_embed_dim,
            n_heads=seq_n_heads,
            n_layers=seq_n_layers,
            dropout=seq_dropout,
            max_seq_len=max_seq_len,
        )

        # MLP takes hand-crafted features + transformer embedding
        combined_dim = n_features + seq_embed_dim
        layers = []
        prev_dim = combined_dim
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h_dim),
                nn.BatchNorm1d(h_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
            ])
            prev_dim = h_dim
        self.backbone = nn.Sequential(*layers)
        self.head = nn.Linear(prev_dim, 1)

    def forward(
        self,
        x_features: torch.Tensor,
        cat_tokens: torch.Tensor,
        time_deltas: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            x_features:  (batch, n_features) — scaled hand-crafted features
            cat_tokens:  (batch, seq_len, 4) — int token IDs
            time_deltas: (batch, seq_len)    — minutes since prev action
            mask:        (batch, seq_len)    — True for padding

        Returns:
            (batch,) logits
        """
        seq_emb = self.seq_encoder(cat_tokens, time_deltas, mask)
        combined = torch.cat([x_features, seq_emb], dim=-1)
        h = self.backbone(combined)
        return self.head(h).squeeze(-1)


def predict_proba(model: nn.Module, x: torch.Tensor, **kwargs) -> torch.Tensor:
    """Return probability of class 1 (ATO victim)."""
    model.eval()
    with torch.no_grad():
        logits = model(x, **kwargs)
        return torch.sigmoid(logits)
