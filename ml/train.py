"""
Train fraud detection model.

Supports two modes:
  --model mlp         Traditional MLP on hand-crafted features only
  --model combined    Transformer sequence encoder + MLP (end-to-end)

Usage:
    python -m ml.train [--db PATH] [--train-fraction F] [--epochs N] [--model combined]
    # From project root (anti_abuse/)
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)
from torch.utils.data import DataLoader, TensorDataset

from ml.features import FEATURE_NAMES, extract_features, extract_sequences, MAX_SEQ_LEN
from ml.model import FraudClassifier, FraudCombinedClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train fraud detection model")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "anti_abuse.db",
        help="Path to anti_abuse.db",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["mlp", "combined"],
        default="combined",
        help="Model type: 'mlp' (features only) or 'combined' (transformer + features)",
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=1.0,
        help="Fraction of user base to use for training (0.0-1.0). "
             "Stratified sample. Validation uses held-out 20%%.",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=str, default="128,64,32")
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--patience", type=int, default=15,
                        help="Early stopping patience (epochs without improvement)")
    parser.add_argument("--seq-embed-dim", type=int, default=64)
    parser.add_argument("--seq-n-heads", type=int, default=4)
    parser.add_argument("--seq-n-layers", type=int, default=2)
    parser.add_argument("--seq-dropout", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--stream", action="store_true", help="Emit JSON loss per epoch for streaming UI")
    return parser.parse_args()


# ---- MLP-only training (unchanged) ----


def train_mlp(args: argparse.Namespace) -> None:
    """Train the hand-crafted-features-only MLP model."""
    print("Loading data and extracting features...")
    X, y = extract_features(args.db)
    n_features = X.shape[1]
    n_positive = int(y.sum())
    n_total = len(y)
    print(f"  Users: {n_total}, fraud victims: {n_positive} ({100 * n_positive / n_total:.1f}%)")

    X_pool, X_val, y_pool, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=args.seed
    )

    train_fraction = max(0.01, min(1.0, args.train_fraction))
    if train_fraction < 1.0:
        X_train, _, y_train, _ = train_test_split(
            X_pool, y_pool,
            train_size=train_fraction,
            stratify=y_pool,
            random_state=args.seed,
        )
        print(f"  Train fraction: {train_fraction:.1%} -> {len(X_train)} users ({int(y_train.sum())} fraud)")
    else:
        X_train, y_train = X_pool, y_pool

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train.astype(np.float32))
    X_val_scaled = scaler.transform(X_val.astype(np.float32))

    X_train_t = torch.from_numpy(X_train_scaled).float()
    y_train_t = torch.from_numpy(y_train.values.astype(np.float32)).float()
    X_val_t = torch.from_numpy(X_val_scaled).float()

    train_ds = TensorDataset(X_train_t, y_train_t)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)

    hidden_dims = tuple(int(x) for x in args.hidden.split(","))
    model = FraudClassifier(n_features=n_features, hidden_dims=hidden_dims, dropout=args.dropout)
    pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))

    # Compile model for faster training (PyTorch 2.0+)
    compiled_model = torch.compile(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=5,
    )

    print("\nTraining MLP model (compiled)...")
    best_val_auc = 0.0
    best_model_state = None
    best_epoch = -1
    epochs_without_improvement = 0

    for epoch in range(args.epochs):
        compiled_model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            logits = compiled_model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        compiled_model.eval()
        with torch.no_grad():
            logits_val = compiled_model(X_val_t)
            probs = torch.sigmoid(logits_val).numpy()
            preds = (probs >= 0.5).astype(float)
        val_auc = roc_auc_score(y_val, probs)
        val_f1 = f1_score(y_val, preds, zero_division=0)
        scheduler.step(val_auc)

        # Best model checkpointing
        if val_auc > best_val_auc:
            best_val_auc = val_auc
            best_epoch = epoch + 1
            best_model_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        epoch_loss = total_loss / len(train_loader)
        if args.stream:
            print(f'{{"epoch":{epoch + 1},"loss":{epoch_loss:.4f}}}', flush=True)
        if (epoch + 1) % 10 == 0 or epoch == 0:
            current_lr = optimizer.param_groups[0]["lr"]
            print(f"  Epoch {epoch + 1:3d}  loss={epoch_loss:.4f}  "
                  f"val_auc={val_auc:.3f}  val_f1={val_f1:.3f}  lr={current_lr:.1e}")

        # Early stopping
        if epochs_without_improvement >= args.patience:
            print(f"  Early stopping at epoch {epoch + 1} (no improvement for {args.patience} epochs)")
            break

    # Restore best model for final evaluation and saving
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        compiled_model = torch.compile(model)
        compiled_model.eval()
        with torch.no_grad():
            logits_val = compiled_model(X_val_t)
            probs = torch.sigmoid(logits_val).numpy()
            preds = (probs >= 0.5).astype(float)
        print(f"  Restored best model from epoch {best_epoch} (val_auc={best_val_auc:.3f})")

    _print_final_metrics(y_val, probs, preds)

    if args.stream:
        print('{"done":true}', flush=True)

    # Save (use original model, not compiled wrapper)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.out_dir / "model.pt")
    np.save(args.out_dir / "scaler_mean.npy", scaler.mean_)
    np.save(args.out_dir / "scaler_scale.npy", scaler.scale_)
    with open(args.out_dir / "config.json", "w") as f:
        json.dump({
            "model_type": "mlp",
            "n_features": n_features,
            "feature_names": FEATURE_NAMES,
            "hidden_dims": list(hidden_dims),
            "dropout": args.dropout,
        }, f, indent=2)
    print(f"\nModel saved to {args.out_dir}")


# ---- Combined (Transformer + MLP) training ----


def train_combined(args: argparse.Namespace) -> None:
    """Train the combined transformer + MLP model end-to-end."""
    print("Loading data and extracting hand-crafted features...")
    X, y = extract_features(args.db)
    n_features = X.shape[1]
    n_positive = int(y.sum())
    n_total = len(y)
    print(f"  Users: {n_total}, fraud victims: {n_positive} ({100 * n_positive / n_total:.1f}%)")

    print("Extracting interaction sequences for transformer...")
    cat_tokens, time_deltas, mask, y_seq = extract_sequences(args.db, max_seq_len=MAX_SEQ_LEN)
    print(f"  Sequences: {cat_tokens.shape[0]} users, max_len={cat_tokens.shape[1]}")

    # Verify user ordering matches (both use same users_df ordering)
    assert len(y) == len(y_seq), "Feature and sequence extraction user counts differ"
    assert (y.values == y_seq.values).all(), "Label mismatch between features and sequences"

    # Create index arrays for splitting
    indices = np.arange(n_total)
    idx_pool, idx_val = train_test_split(
        indices, test_size=0.2, stratify=y.values, random_state=args.seed,
    )

    train_fraction = max(0.01, min(1.0, args.train_fraction))
    if train_fraction < 1.0:
        idx_train, _ = train_test_split(
            idx_pool,
            train_size=train_fraction,
            stratify=y.values[idx_pool],
            random_state=args.seed,
        )
        n_fraud_train = int(y.values[idx_train].sum())
        print(f"  Train fraction: {train_fraction:.1%} -> {len(idx_train)} users ({n_fraud_train} fraud)")
    else:
        idx_train = idx_pool

    # Scale hand-crafted features
    scaler = StandardScaler()
    X_np = X.values.astype(np.float32)
    X_train_scaled = scaler.fit_transform(X_np[idx_train])
    X_val_scaled = scaler.transform(X_np[idx_val])

    # Tensors — features
    X_train_t = torch.from_numpy(X_train_scaled).float()
    X_val_t = torch.from_numpy(X_val_scaled).float()
    y_train_vals = y.values[idx_train].astype(np.float32)
    y_val_vals = y.values[idx_val].astype(np.float32)
    y_train_t = torch.from_numpy(y_train_vals).float()

    # Tensors — sequences
    cat_train = cat_tokens[idx_train]
    cat_val = cat_tokens[idx_val]
    td_train = time_deltas[idx_train]
    td_val = time_deltas[idx_val]
    mask_train = mask[idx_train]
    mask_val = mask[idx_val]

    # DataLoader (pack all inputs into single TensorDataset)
    train_ds = TensorDataset(X_train_t, cat_train, td_train, mask_train, y_train_t)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)

    # Model
    hidden_dims = tuple(int(x) for x in args.hidden.split(","))
    model = FraudCombinedClassifier(
        n_features=n_features,
        seq_embed_dim=args.seq_embed_dim,
        seq_n_heads=args.seq_n_heads,
        seq_n_layers=args.seq_n_layers,
        seq_dropout=args.seq_dropout,
        hidden_dims=hidden_dims,
        dropout=args.dropout,
        max_seq_len=MAX_SEQ_LEN,
    )

    pos_weight = (y_train_vals == 0).sum() / max(1, (y_train_vals == 1).sum())
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))

    # Compile model for faster training (PyTorch 2.0+)
    compiled_model = torch.compile(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=5,
    )

    print(f"\nTraining combined model (compiled, transformer embed_dim={args.seq_embed_dim}, "
          f"layers={args.seq_n_layers}, heads={args.seq_n_heads})...")
    best_val_auc = 0.0
    best_model_state = None
    best_epoch = -1
    epochs_without_improvement = 0

    for epoch in range(args.epochs):
        compiled_model.train()
        total_loss = 0.0
        for xb, cat_b, td_b, mask_b, yb in train_loader:
            optimizer.zero_grad()
            logits = compiled_model(xb, cat_b, td_b, mask_b)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        # Validation
        compiled_model.eval()
        with torch.no_grad():
            logits_val = compiled_model(X_val_t, cat_val, td_val, mask_val)
            probs = torch.sigmoid(logits_val).numpy()
            preds = (probs >= 0.5).astype(float)
        val_auc = roc_auc_score(y_val_vals, probs)
        val_f1 = f1_score(y_val_vals, preds, zero_division=0)
        scheduler.step(val_auc)

        # Best model checkpointing
        if val_auc > best_val_auc:
            best_val_auc = val_auc
            best_epoch = epoch + 1
            best_model_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        epoch_loss = total_loss / len(train_loader)
        if args.stream:
            print(f'{{"epoch":{epoch + 1},"loss":{epoch_loss:.4f}}}', flush=True)
        if (epoch + 1) % 10 == 0 or epoch == 0:
            current_lr = optimizer.param_groups[0]["lr"]
            print(f"  Epoch {epoch + 1:3d}  loss={epoch_loss:.4f}  "
                  f"val_auc={val_auc:.3f}  val_f1={val_f1:.3f}  lr={current_lr:.1e}")

        # Early stopping
        if epochs_without_improvement >= args.patience:
            print(f"  Early stopping at epoch {epoch + 1} (no improvement for {args.patience} epochs)")
            break

    # Restore best model for final evaluation and saving
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        compiled_model = torch.compile(model)
        compiled_model.eval()
        with torch.no_grad():
            logits_val = compiled_model(X_val_t, cat_val, td_val, mask_val)
            probs = torch.sigmoid(logits_val).numpy()
            preds = (probs >= 0.5).astype(float)
        print(f"  Restored best model from epoch {best_epoch} (val_auc={best_val_auc:.3f})")

    _print_final_metrics(y_val_vals, probs, preds)

    if args.stream:
        print('{"done":true}', flush=True)

    # Save (use original model, not compiled wrapper)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.out_dir / "model.pt")
    np.save(args.out_dir / "scaler_mean.npy", scaler.mean_)
    np.save(args.out_dir / "scaler_scale.npy", scaler.scale_)
    with open(args.out_dir / "config.json", "w") as f:
        json.dump({
            "model_type": "combined",
            "n_features": n_features,
            "feature_names": FEATURE_NAMES,
            "hidden_dims": list(hidden_dims),
            "dropout": args.dropout,
            "seq_embed_dim": args.seq_embed_dim,
            "seq_n_heads": args.seq_n_heads,
            "seq_n_layers": args.seq_n_layers,
            "seq_dropout": args.seq_dropout,
            "max_seq_len": MAX_SEQ_LEN,
        }, f, indent=2)
    print(f"\nModel saved to {args.out_dir}")


# ---- Shared helpers ----


def _print_final_metrics(y_true, probs, preds) -> None:
    print("\nValidation metrics:")
    print(f"  Accuracy:  {accuracy_score(y_true, preds):.3f}")
    print(f"  Precision: {precision_score(y_true, preds, zero_division=0):.3f}")
    print(f"  Recall:    {recall_score(y_true, preds, zero_division=0):.3f}")
    print(f"  F1:        {f1_score(y_true, preds, zero_division=0):.3f}")
    print(f"  ROC AUC:   {roc_auc_score(y_true, probs):.3f}")
    print(f"  Confusion matrix:\n{confusion_matrix(y_true, preds)}")


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    if args.model == "mlp":
        train_mlp(args)
    else:
        train_combined(args)


if __name__ == "__main__":
    main()
