"""
Flask server for the anti-abuse UI.

Endpoints:
  GET /                              -> Serves the frontend
  GET /api/users?q=&page=&per_page=&flagged_only=  -> Paginated user list
  GET /api/users/<user_id>           -> Full user + profile + interaction stats
  GET /api/users/<user_id>/connections  -> Users connected to this user
  GET /api/users/<user_id>/interactions?limit=  -> Recent interactions
  GET /api/flagged                   -> Detection results (for UI)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory

from db.repository import Repository

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "anti_abuse.db"
_STATIC_DIR = _PROJECT_ROOT / "api" / "static"
_FLAGGED_PATH = _PROJECT_ROOT / "ml" / "output" / "flagged_users.json"
_MODEL_PATH = _PROJECT_ROOT / "ml" / "output" / "model.pt"

app = Flask(__name__, static_folder=str(_STATIC_DIR))

# Cache for flagged data (invalidated when file mtime changes)
_flagged_cache: tuple[float, dict] | None = None


@app.after_request
def add_cache_headers(response):
    """Prevent browser caching of API responses."""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


def _load_flagged_data() -> dict | None:
    """Load fraud detection results from JSON. Cached until file changes."""
    global _flagged_cache
    if not _FLAGGED_PATH.exists():
        _flagged_cache = None
        return None
    mtime = _FLAGGED_PATH.stat().st_mtime
    if _flagged_cache is not None and _flagged_cache[0] == mtime:
        return _flagged_cache[1]
    try:
        with open(_FLAGGED_PATH) as f:
            data = json.load(f)
        _flagged_cache = (mtime, data)
        return data
    except (json.JSONDecodeError, OSError):
        _flagged_cache = None
        return None


def get_repo() -> Repository:
    """Return request-scoped repository instance."""
    if "repo" not in g:
        g.repo = Repository(_DB_PATH)
    return g.repo


@app.teardown_appcontext
def close_repo(exception: BaseException | None) -> None:
    """Close request-scoped repository connection."""
    repo = g.pop("repo", None)
    if repo is not None:
        repo.close()


def _parse_int_arg(
    name: str,
    default: int,
    min_value: int = 1,
    max_value: int | None = None,
) -> tuple[int | None, str | None]:
    """Strict integer parsing for query args."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, f"{name} must be an integer"
    if value < min_value:
        return None, f"{name} must be >= {min_value}"
    if max_value is not None and value > max_value:
        return None, f"{name} must be <= {max_value}"
    return value, None


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(str(_STATIC_DIR), "index.html")


# ---------------------------------------------------------------------------
# API: Users
# ---------------------------------------------------------------------------
@app.route("/api/users")
def list_users():
    repo = get_repo()
    query = request.args.get("q", "")
    page, page_err = _parse_int_arg("page", default=1, min_value=1)
    per_page, per_page_err = _parse_int_arg("per_page", default=50, min_value=1, max_value=200)
    if page_err or per_page_err:
        return jsonify({
            "error": "Invalid pagination values",
            "details": page_err or per_page_err,
        }), 400

    sort_by = request.args.get("sort_by", "user_id")
    sort_order = request.args.get("sort_order", "asc")

    flagged_user_ids = None
    flagged_data = _load_flagged_data()
    if request.args.get("flagged_only") in ("1", "true", "yes"):
        if flagged_data:
            flagged_user_ids = [
                uid for uid, d in flagged_data.get("users", {}).items()
                if d.get("flagged")
            ]
        else:
            flagged_user_ids = []

    # Special path for risk (fraud_prob) sorting: requires flagged data
    if sort_by == "fraud_prob" and flagged_data:
        user_ids = repo.get_user_ids_matching(
            query=query,
            user_ids_filter=flagged_user_ids if flagged_user_ids is not None else None,
        )
        users_map = flagged_data.get("users", {})
        with_probs = [
            (uid, users_map.get(uid, {}).get("prob", 0.0))
            for uid in user_ids
        ]
        with_probs.sort(key=lambda x: x[1], reverse=(sort_order.lower() == "desc"))
        total = len(with_probs)
        offset = (page - 1) * per_page
        page_ids = [uid for uid, _ in with_probs[offset : offset + per_page]]
        users = repo.get_users_by_ids_ordered(page_ids)
        result = {"users": users, "total": total, "page": page, "per_page": per_page}
    else:
        if sort_by == "fraud_prob":
            sort_by = "user_id"  # Fallback when no detection data
        result = repo.search_users(
            query=query,
            page=page,
            per_page=per_page,
            user_ids_filter=flagged_user_ids if flagged_user_ids is not None else None,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    if flagged_data:
        users_map = flagged_data.get("users", {})
        for u in result["users"]:
            d = users_map.get(u["user_id"], {})
            u["fraud_prob"] = d.get("prob")
            u["fraud_flagged"] = d.get("flagged", False)
    else:
        for u in result["users"]:
            u["fraud_prob"] = None
            u["fraud_flagged"] = False

    result["flagged_count"] = (
        flagged_data.get("flagged_count") if flagged_data else None
    )
    return jsonify(result)


def _stream_train_loss():
    """Generator that runs training and yields SSE events with loss data."""
    proc = subprocess.Popen(
        ["python", "-m", "ml.train", "--train-fraction", "0.2", "--stream"],
        cwd=str(_PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    recent_lines: list[str] = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if "epoch" in data and "loss" in data:
                yield f"data: {json.dumps(data)}\n\n"
            elif data.get("done"):
                yield f"data: {json.dumps({'done': True})}\n\n"
        except json.JSONDecodeError:
            recent_lines.append(line)
            if len(recent_lines) > 20:
                recent_lines.pop(0)
    proc.wait(timeout=300)
    if proc.returncode != 0:
        err = "\n".join(recent_lines[-10:]) or f"Exit code {proc.returncode}"
        yield f"data: {json.dumps({'error': err})}\n\n"


@app.route("/api/run-train", methods=["POST"])
def run_train():
    """Train the model on a small fraction of users. Streams loss via SSE."""
    return Response(
        _stream_train_loss(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/model-status")
def model_status():
    """Check whether a trained model exists."""
    trained = _MODEL_PATH.exists()
    mtime = _MODEL_PATH.stat().st_mtime if trained else None
    return jsonify({"trained": trained, "mtime": mtime})


@app.route("/api/clear-model", methods=["POST"])
def clear_model():
    """Delete the trained model and risk scores."""
    global _flagged_cache
    try:
        cleared = False
        if _MODEL_PATH.exists():
            _MODEL_PATH.unlink()
            cleared = True
        if _FLAGGED_PATH.exists():
            _FLAGGED_PATH.unlink()
            cleared = True
        # Clear the cache immediately
        _flagged_cache = None
        if cleared:
            return jsonify({"success": True, "message": "Model and risk scores cleared"})
        return jsonify({"success": True, "message": "No model to clear"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/run-detection", methods=["POST"])
def run_detection():
    """Run detect.py (uses trained model on all users) and return success/failure."""
    detect_script = _PROJECT_ROOT / "detect.py"
    result = subprocess.run(
        ["python", str(detect_script)],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        return jsonify({
            "success": False,
            "error": result.stderr or result.stdout or "Detection failed",
        }), 500
    return jsonify({
        "success": True,
        "message": result.stdout or "Detection complete",
    })


@app.route("/api/flagged")
def get_flagged():
    """Return fraud detection results for the UI."""
    data = _load_flagged_data()
    if data is None:
        return jsonify({
            "available": False,
            "message": "Run python detect.py to generate detection results",
        })
    return jsonify({
        "available": True,
        "threshold": data.get("threshold"),
        "total_users": data.get("total_users"),
        "flagged_count": data.get("flagged_count"),
        "users": data.get("users", {}),
    })


@app.route("/api/detection-metrics")
def detection_metrics():
    """Compare detection flags against ground-truth generation_pattern labels.

    Returns precision, recall, F1, and a confusion breakdown.
    """
    flagged_data = _load_flagged_data()
    if flagged_data is None:
        return jsonify({"available": False})

    repo = get_repo()
    users_map = flagged_data.get("users", {})
    labels = repo.get_user_generation_patterns()

    tp = fp = fn = tn = 0
    for uid, det in users_map.items():
        predicted_fraud = det.get("flagged", False)
        actual_fraud = labels.get(uid, "clean") != "clean"
        if predicted_fraud and actual_fraud:
            tp += 1
        elif predicted_fraud and not actual_fraud:
            fp += 1
        elif not predicted_fraud and actual_fraud:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return jsonify({
        "available": True,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": tp + fp + fn + tn,
    })


@app.route("/api/users/<user_id>")
def get_user(user_id: str):
    repo = get_repo()
    user, profile = repo.get_user_with_profile(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    connections = repo.get_connections(user_id)
    interactions = repo.get_interactions_by_user(user_id, limit=50)
    interaction_counts = repo.count_interactions_by_type_for_user(user_id)

    fraud_prob = None
    fraud_flagged = False
    flagged_data = _load_flagged_data()
    if flagged_data:
        u = flagged_data.get("users", {}).get(user_id, {})
        fraud_prob = u.get("prob")
        fraud_flagged = u.get("flagged", False)

    return jsonify({
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "join_date": user.join_date.isoformat(),
            "country": user.country,
            "ip_address": user.ip_address,
            "registration_ip": user.registration_ip,
            "registration_country": user.registration_country,
            "address": user.address,
            "ip_type": user.ip_type.value,
            "language": user.language,
            "is_active": user.is_active,
            "generation_pattern": user.generation_pattern,
            "normal_pattern": getattr(user, "normal_pattern", "") or "",
            "user_type": getattr(user, "user_type", "regular"),
            "email_verified": user.email_verified,
            "two_factor_enabled": user.two_factor_enabled,
            "phone_verified": user.phone_verified,
            "account_tier": user.account_tier,
            "failed_login_streak": user.failed_login_streak,
            "last_password_change_at": user.last_password_change_at.isoformat() if user.last_password_change_at else None,
        },
        "profile": {
            "display_name": profile.display_name,
            "headline": profile.headline,
            "summary": profile.summary,
            "connections_count": profile.connections_count,
            "profile_created_at": profile.profile_created_at.isoformat(),
            "last_updated_at": profile.last_updated_at.isoformat() if profile.last_updated_at else None,
            "groups_joined": list(profile.groups_joined),
            "cloned_from_user_id": profile.cloned_from_user_id,
        } if profile else None,
        "connections_count": len(connections),
        "connections": [
            {
                "user_id": c["user_id"],
                "display_name": c["display_name"],
                "headline": c["headline"],
                "country": c["country"],
                "is_active": c["is_active"],
            }
            for c in connections
        ],
        "interaction_counts": interaction_counts,
        "recent_interactions": [
            {
                "interaction_id": i.interaction_id,
                "interaction_type": i.interaction_type.value,
                "timestamp": i.timestamp.isoformat(),
                "ip_address": i.ip_address,
                "ip_type": i.ip_type.value,
                "ip_country": i.metadata.get("ip_country") or i.metadata.get("attacker_country"),
                "user_agent": i.metadata.get("user_agent"),
                "target_user_id": i.target_user_id,
                "metadata": i.metadata,
            }
            for i in interactions
        ],
        "fraud_prob": fraud_prob,
        "fraud_flagged": fraud_flagged,
    })


@app.route("/api/users/<user_id>/connections")
def get_connections(user_id: str):
    repo = get_repo()
    user = repo.get_user(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    connections = repo.get_connections(user_id)
    return jsonify({"user_id": user_id, "connections": connections})


@app.route("/api/users/<user_id>/interactions")
def get_interactions(user_id: str):
    repo = get_repo()
    user = repo.get_user(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    limit, limit_err = _parse_int_arg("limit", default=100, min_value=1, max_value=1000)
    if limit_err:
        return jsonify({
            "error": "Invalid limit",
            "details": limit_err,
        }), 400
    interactions = repo.get_interactions_by_user(user_id, limit=limit)
    return jsonify({
        "user_id": user_id,
        "interactions": [
            {
                "interaction_id": i.interaction_id,
                "interaction_type": i.interaction_type.value,
                "timestamp": i.timestamp.isoformat(),
                "ip_address": i.ip_address,
                "ip_type": i.ip_type.value,
                "ip_country": i.metadata.get("ip_country") or i.metadata.get("attacker_country"),
                "user_agent": i.metadata.get("user_agent"),
                "target_user_id": i.target_user_id,
                "metadata": i.metadata,
            }
            for i in interactions
        ],
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Database: {_DB_PATH}")
    print(f"Static:   {_STATIC_DIR}")
    app.run(debug=True, port=5001)
