"""
Transformer-based sequence encoder for user interaction histories.

Encodes each user's ordered interaction sequence into a fixed-size
embedding vector. Each interaction is tokenized as:
  - action_type (7 types)
  - ip_type (2 types)
  - login_success (3 states: True/False/N/A)
  - ip_country_changed (binary)
  - time_delta (minutes since previous action, continuous)

The transformer output is mean-pooled over the sequence to produce
a fixed-size user embedding.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn


# Vocabulary sizes for categorical token fields
NUM_ACTION_TYPES = 12   # 11 types + 1 padding
NUM_IP_TYPES = 3        # residential, hosting, padding
NUM_LOGIN_SUCCESS = 4   # True, False, N/A, padding

# Token field indices in the integer tensor
ACTION_IDX = 0
IP_TYPE_IDX = 1
LOGIN_SUCCESS_IDX = 2
IP_COUNTRY_CHANGED_IDX = 3  # 0 or 1

# Mapping from string values to token IDs (0 = padding)
ACTION_VOCAB = {
    "<pad>": 0,
    "account_creation": 1,
    "login": 2,
    "change_password": 3,
    "change_profile": 4,
    "change_name": 5,
    "message_user": 6,
    "view_user_page": 7,
    "upload_address_book": 8,
    "download_address_book": 9,
    "close_account": 10,
    "connect_with_user": 11,
}

IP_TYPE_VOCAB = {
    "<pad>": 0,
    "residential": 1,
    "hosting": 2,
}

LOGIN_SUCCESS_VOCAB = {
    "<pad>": 0,
    "true": 1,
    "false": 2,
    "na": 3,
}


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding."""

    def __init__(self, d_model: int, max_len: int = 256) -> None:
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        if d_model > 1:
            pe[:, 1::2] = torch.cos(position * div_term[: d_model // 2])
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model)"""
        return x + self.pe[:, : x.size(1)]


class ActionSequenceEncoder(nn.Module):
    """
    Transformer encoder for user interaction sequences.

    Input:
        cat_tokens: (batch, seq_len, 4)  — action_type, ip_type, login_success, ip_country_changed
        time_deltas: (batch, seq_len)    — minutes since previous action
        mask: (batch, seq_len)           — True for padding positions

    Output:
        (batch, embed_dim) — fixed-size user embedding
    """

    def __init__(
        self,
        embed_dim: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        dropout: float = 0.1,
        max_seq_len: int = 256,
    ) -> None:
        super().__init__()
        self.embed_dim = embed_dim

        # Categorical embeddings
        self.action_emb = nn.Embedding(NUM_ACTION_TYPES, embed_dim, padding_idx=0)
        self.ip_type_emb = nn.Embedding(NUM_IP_TYPES, embed_dim, padding_idx=0)
        self.login_success_emb = nn.Embedding(NUM_LOGIN_SUCCESS, embed_dim, padding_idx=0)
        self.ip_country_emb = nn.Embedding(2, embed_dim)  # 0/1

        # Continuous: time delta projection
        self.time_proj = nn.Linear(1, embed_dim)

        # Combine: project sum of embeddings
        self.input_proj = nn.Linear(embed_dim, embed_dim)
        self.pos_enc = PositionalEncoding(embed_dim, max_seq_len)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=n_heads,
            dim_feedforward=embed_dim * 2,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.layer_norm = nn.LayerNorm(embed_dim)

    def forward(
        self,
        cat_tokens: torch.Tensor,
        time_deltas: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            cat_tokens:  (batch, seq_len, 4) int tensor
            time_deltas: (batch, seq_len) float tensor
            mask:        (batch, seq_len) bool tensor (True = padding)

        Returns:
            (batch, embed_dim) user embedding
        """
        action_ids = cat_tokens[:, :, ACTION_IDX]
        ip_type_ids = cat_tokens[:, :, IP_TYPE_IDX]
        login_ids = cat_tokens[:, :, LOGIN_SUCCESS_IDX]
        ip_country_ids = cat_tokens[:, :, IP_COUNTRY_CHANGED_IDX]

        # Sum categorical embeddings + time projection
        tok_emb = (
            self.action_emb(action_ids)
            + self.ip_type_emb(ip_type_ids)
            + self.login_success_emb(login_ids)
            + self.ip_country_emb(ip_country_ids)
            + self.time_proj(time_deltas.unsqueeze(-1))
        )

        tok_emb = self.input_proj(tok_emb)
        tok_emb = self.pos_enc(tok_emb)

        # Transformer with padding mask
        out = self.transformer(tok_emb, src_key_padding_mask=mask)
        out = self.layer_norm(out)

        # Mean pool over non-padding positions
        mask_expanded = (~mask).unsqueeze(-1).float()  # (batch, seq, 1)
        pooled = (out * mask_expanded).sum(dim=1) / mask_expanded.sum(dim=1).clamp(min=1)

        return pooled
