"""
ML pipeline for fraud detection.

Orchestrates data generation (optional), feature extraction, and training
on a configurable fraction of the user base.

Usage:
    python -m ml.pipeline [--generate] [--train-fraction F]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fraud detection ML pipeline")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run generate.py to (re)generate the database before training",
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.2,
        help="Fraction of user base for training (default: 0.2 = 20%%)",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument(
        "--model",
        type=str,
        choices=["mlp", "combined"],
        default="combined",
        help="Model type: 'mlp' or 'combined' (transformer + features)",
    )
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = args.db or project_root / "anti_abuse.db"

    if args.generate:
        print("=" * 50)
        print("Step 1: Generating database")
        print("=" * 50)
        rc = subprocess.run(
            [sys.executable, "-m", "generate"],
            cwd=project_root,
            capture_output=False,
        )
        if rc.returncode != 0:
            return rc.returncode

    print("\n" + "=" * 50, flush=True)
    print("Step 2: Training model", flush=True)
    print("=" * 50, flush=True)
    cmd = [
        sys.executable, "-m", "ml.train",
        "--db", str(db_path),
        "--train-fraction", str(args.train_fraction),
        "--epochs", str(args.epochs),
        "--model", args.model,
    ]
    rc = subprocess.run(cmd, cwd=project_root, capture_output=False)
    return rc.returncode


if __name__ == "__main__":
    sys.exit(main())
