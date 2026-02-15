# Anti-Abuse Application Bug Report

## 1. Zero Division Error in Training Script
**File**: `ml/train.py`
**Severity**: High (Crash)

The training script calculates the fraction of fraud victims without checking if the dataset is empty. This causes a `ZeroDivisionError` if the database is initialized but has no users (e.g., after a failed generation run).

```python
# ml/train.py:87-88
n_total = len(y)
print(f"  Users: {n_total}, fraud victims: {n_positive} ({100 * n_positive / n_total:.1f}%)")
```

**Recommendation**: Add a check for `n_total > 0` before performing the division or printing the percentage.

## 2. Unhandled Database Lock / Resource Cleanup
**File**: `generate.py`
**Severity**: Medium (Operational)

The `Repository` is opened and closed at the end of the script. If `generate.py` crashes or is interrupted (SIGINT) during the potentially long data validation/insertion phase, `repo.close()` is never called. This leaves the SQLite database in a locked state (WAL file present), preventing subsequent access by other tools (e.g., `sqlite3`, `train.py`) until the lock is cleared or the environment restarted.

**Recommendation**: Use a `try...finally` block or a context manager for the `Repository` to ensure connection closure.

```python
repo = Repository(db_path)
try:
    # ... operations ...
finally:
    repo.close()
```

## 3. Potential Infinite Loop / Hang in Data Generation
**File**: `generate.py` / `data/mock_data.py`
**Severity**: Medium (Performance)

The data generation process for 1,000 users appeared to hang indefinitely in the test environment. While O(N) logic is generally present, the large number of interactions combined with Python-side filtering (e.g., `_enforce_close_account_invariant` using list comprehensions over potentially large lists) can cause significant slowdowns or apparent hangs.

**Recommendation**: Add progress logging to long-running steps in `generate.py` (like `add_accept_events_for_connects` and invariant enforcers) to verify progress. Optimizing these filters to use indices or sets instead of list iteration would improve performance.

## 4. Feature Extraction Edge Case (Login Failures)
**File**: `ml/features.py`
**Severity**: Low (Data Quality)

The feature `login_failures_before_success` counts *all* login failures if the user has never successfully logged in.

```python
# ml/features.py:207
login_failures_before_success = float((login_evts["login_success"] == False).sum())
```

While technically correct (all failures are "before" a success that hasn't happened yet), this might conflate legitimate users who can't log in with malicious actors. It's worth validating if this distinction matters for the model.

## 5. Hardcoded Prediction Threshold
**File**: `ml/predict.py`
**Severity**: Low (Flexibility)

The prediction threshold is hardcoded to `0.5` by default, though configurable via arguments. For fraud detection, where recall is often prioritized over precision (or vice-versa depending on policy), a calibrated threshold based on validation set performance (e.g., maximizing F1 or Recall at fixed Precision) would be better than a static default.
