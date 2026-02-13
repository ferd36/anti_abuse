# Anti-Abuse Fraud Detection

Account takeover and fraud detection system with mock data generation, ML models, and a web UI for exploring users and risk scores.

## Setup

```bash
cd anti_abuse
pip install -r requirements.txt
```

## Quick Start

```bash
python generate.py              # Create database with 100k users
python -m ml.train --train-fraction 0.2   # Train model (20% of users)
python detect.py                # Run detection on all users
python serve.py                 # Start UI at http://127.0.0.1:5001
```

## Commands

### Generate Data

```bash
python generate.py [--users N] [--fraud-pct P] [--memory]
```

- `--users` Number of users (default: 100,000)
- `--fraud-pct` Target fraud-victim percentage (default: 0.5)
- `--memory` Use in-memory DB for testing

### Train

```bash
python -m ml.train [--db PATH] [--train-fraction F] [--epochs N] [--model mlp|combined]
```

- `--db` Path to anti_abuse.db
- `--train-fraction` Fraction of users for training (default: 1.0)
- `--epochs` Training epochs (default: 100)
- `--model` `mlp` (features only) or `combined` (transformer + MLP)
- `--stream` Emit loss JSON for streaming UI

### Detect

```bash
python detect.py [--db PATH] [--threshold FLOAT]
```

Runs the trained model on all users and writes `ml/output/flagged_users.json` for the UI.

### Serve

```bash
python serve.py [--port PORT]
```

Starts the Flask UI (default port 5001).

## ML Features

| Category | Features |
|----------|----------|
| **Behavioral tempo** | login_to_download_minutes, download_to_first_spam_minutes, interactions_per_hour (1h, 24h), first_login_to_close_hours |
| **Geo/IP** | ip_country_mismatch, ip_country_changes_last_7d, ratio_hosting_ips, num_distinct_ips_last_24h |
| **Pattern** | login_failures_before_success, spam_count_last_24h, unique_targets_messaged_last_24h, download_address_book_count |
| **Session** | same_ip_shared_with_others (credential stuffing signal) |
| **Derived** | hour_of_day (sin/cos), days_since_last_activity, script_user_agent |

## Project Structure

```
anti_abuse/
├── api/          # Flask server and static UI
├── core/         # Models, enums, validation
├── data/         # Mock data, fraud/non-fraud generators
├── db/           # SQLite repository
├── ml/           # Train, predict, features, model definitions
├── generate.py   # Data generation
├── detect.py     # Run detection
└── serve.py      # Start UI server
```
