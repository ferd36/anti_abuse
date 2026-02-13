"""
Run fraud prediction on the database.

Usage:
    python -m ml.predict [--db PATH] [--model-dir PATH] [--threshold FLOAT]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ml.features import extract_features, extract_sequences, MAX_SEQ_LEN
from ml.model import FraudClassifier, FraudCombinedClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict fraud victims")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "anti_abuse.db",
        help="Path to anti_abuse.db",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Directory with saved model.pt and scaler",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--top-k", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Loading model...")
    with open(args.model_dir / "config.json") as f:
        config = json.load(f)

    model_type = config.get("model_type", "mlp")
    scaler_mean = np.load(args.model_dir / "scaler_mean.npy")
    scaler_scale = np.load(args.model_dir / "scaler_scale.npy")

    print(f"Model type: {model_type}")

    print("Extracting features...")
    X, y_true = extract_features(args.db)
    user_ids = y_true.index.tolist()

    X_scaled = (X.astype(np.float32) - scaler_mean) / scaler_scale
    X_t = torch.from_numpy(X_scaled.values).float()

    if model_type == "combined":
        model = FraudCombinedClassifier(
            n_features=config["n_features"],
            seq_embed_dim=config["seq_embed_dim"],
            seq_n_heads=config["seq_n_heads"],
            seq_n_layers=config["seq_n_layers"],
            seq_dropout=config["seq_dropout"],
            hidden_dims=tuple(config["hidden_dims"]),
            dropout=config["dropout"],
            max_seq_len=config.get("max_seq_len", MAX_SEQ_LEN),
        )
        model.load_state_dict(torch.load(args.model_dir / "model.pt", weights_only=True))
        model.eval()

        print("Extracting interaction sequences for transformer...")
        cat_tokens, time_deltas, mask, _ = extract_sequences(
            args.db, max_seq_len=config.get("max_seq_len", MAX_SEQ_LEN),
        )

        with torch.no_grad():
            logits = model(X_t, cat_tokens, time_deltas, mask)
            probs = torch.sigmoid(logits).numpy().flatten()
    else:
        model = FraudClassifier(
            n_features=config["n_features"],
            hidden_dims=tuple(config["hidden_dims"]),
            dropout=config["dropout"],
        )
        model.load_state_dict(torch.load(args.model_dir / "model.pt", weights_only=True))
        model.eval()

        with torch.no_grad():
            logits = model(X_t)
            probs = torch.sigmoid(logits).numpy().flatten()

    preds = (probs >= args.threshold).astype(int)
    results = list(zip(user_ids, probs, preds, y_true.values))

    # Top-K by probability
    sorted_results = sorted(results, key=lambda r: r[1], reverse=True)
    print(f"\nTop-{args.top_k} predicted fraud victims (by probability):")
    print("-" * 50)
    for i, (uid, prob, pred, actual) in enumerate(sorted_results[: args.top_k], 1):
        label = "fraud" if actual == 1 else "legit"
        match = "✓" if pred == actual else "✗"
        print(f"  {i:2d}. {uid}  p={prob:.3f}  pred={pred}  actual={label}  {match}")

    n_pred_fraud = sum(preds)
    n_actual_fraud = int(y_true.sum())
    print(f"\nSummary: {n_pred_fraud} predicted fraud | {n_actual_fraud} actual fraud victims")


if __name__ == "__main__":
    main()
