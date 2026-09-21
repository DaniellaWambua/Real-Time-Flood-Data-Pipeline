"""Shared scoring helpers: reconstruction error and threshold selection.

Used by train.py, evaluate_consensus.py, and diagnose_overfitting.py, so
the anomaly score is defined in exactly one place.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score

from src.config import THRESHOLD_SEARCH_MAX, THRESHOLD_SEARCH_MIN, THRESHOLD_SEARCH_STEP


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def reconstruction_error(model, X):
    """Reconstruction error on the final day of each window.

    The flood label belongs to the last day only, so scoring the whole
    window average dilutes that day's signal against the other thirteen,
    ordinary ones sitting next to it. Scoring just the last day isolates it.
    """
    X_pred = model.predict(X, verbose=0)
    return np.mean(np.square(X[:, -1, :] - X_pred[:, -1, :]), axis=1)


def choose_threshold(errors_val, y_val):
    """Percentile of normal error with the best F1 on validation.

    Many percentiles often tie on the same F1 when there are only a
    handful of flood windows in validation, so among ties the highest
    threshold (best precision) is kept, rather than the first one found.
    """
    normal_errors = errors_val[y_val == 0]
    candidates = []
    for percentile in np.arange(THRESHOLD_SEARCH_MIN, THRESHOLD_SEARCH_MAX, THRESHOLD_SEARCH_STEP):
        threshold = np.percentile(normal_errors, percentile)
        y_pred = (errors_val > threshold).astype(int)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        candidates.append((f1, threshold))
    best_f1 = max(f1 for f1, _ in candidates)
    return max(threshold for f1, threshold in candidates if f1 == best_f1)
