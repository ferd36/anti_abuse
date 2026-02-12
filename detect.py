#!/usr/bin/env python3
"""
Run ML detection on all users and save results for the UI.

Writes ml/output/flagged_users.json. The UI reads this file
to show risk badges and filter flagged users.

Usage:
    python detect.py [--db PATH] [--threshold FLOAT]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ml.features import extract_features, extract_sequences, MAX_SEQ_LEN
from ml.model import ATOClassifier, ATOCombinedClassifier


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ATO detection on all users")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().parent / "anti_abuse.db",
        help="Path to anti_abuse.db",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "ml" / "output",
        help="Directory with model.pt and scaler",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: model-dir/flagged_users.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Probability threshold for flagging",
    )
    args = parser.parse_args()

    output_path = args.output or args.model_dir / "flagged_users.json"

    print("Loading model...")
    with open(args.model_dir / "config.json") as f:
        config = json.load(f)

    model_type = config.get("model_type", "mlp")
    scaler_mean = np.load(args.model_dir / "scaler_mean.npy")
    scaler_scale = np.load(args.model_dir / "scaler_scale.npy")

    print(f"Model type: {model_type}")

    print("Extracting hand-crafted features...")
    X_df, y_series = extract_features(args.db)
    user_ids = y_series.index.tolist()

    X_scaled = (X_df.astype(np.float32) - scaler_mean) / scaler_scale
    X_t = torch.from_numpy(X_scaled.values).float()

    if model_type == "combined":
        model = ATOCombinedClassifier(
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

        print("Running combined model detection...")
        with torch.no_grad():
            logits = model(X_t, cat_tokens, time_deltas, mask)
            probs = torch.sigmoid(logits).numpy().flatten()
    else:
        model = ATOClassifier(
            n_features=config["n_features"],
            hidden_dims=tuple(config["hidden_dims"]),
            dropout=config["dropout"],
        )
        model.load_state_dict(torch.load(args.model_dir / "model.pt", weights_only=True))
        model.eval()

        print("Running MLP model detection...")
        with torch.no_grad():
            logits = model(X_t)
            probs = torch.sigmoid(logits).numpy().flatten()

    flagged = (probs >= args.threshold).astype(bool)

    results = {
        uid: {"prob": float(p), "flagged": bool(f)}
        for uid, p, f in zip(user_ids, probs, flagged)
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "model_type": model_type,
                "threshold": args.threshold,
                "total_users": len(results),
                "flagged_count": sum(1 for r in results.values() if r["flagged"]),
                "users": results,
            },
            f,
            indent=2,
        )

    n_flagged = sum(1 for r in results.values() if r["flagged"])
    print(f"Detection complete: {len(results)} users, {n_flagged} flagged")
    print(f"Results saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
