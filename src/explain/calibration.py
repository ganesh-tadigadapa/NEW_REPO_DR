"""Requirement #4c — calibrated confidence.

A raw sigmoid output is not a probability. Modern deep networks are systematically
*overconfident*: a batch of predictions at "90% confident" is typically right rather less
than 90% of the time. Putting an uncalibrated number next to a medical decision is
actively dangerous, because the clinician reads it as a probability and it is not one.

**Temperature scaling** (Guo et al. 2017) is the fix: divide the logits by a single
scalar T fitted on the validation set by minimising negative log-likelihood. One
parameter, so it cannot overfit; it never changes any ranking, so accuracy, QWK, AUC and
the tuned thresholds are all mathematically unchanged. It only makes the numbers honest.

We report **ECE before and after** to prove the correction did something, and we bin by
the referable probability, because that is the number shown to the user.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def coral_nll(logits: np.ndarray, levels: np.ndarray, T: float) -> float:
    """Negative log-likelihood of the cumulative binary targets at temperature T."""
    z = np.asarray(logits, dtype=np.float64) / max(T, 1e-3)
    p = np.clip(_sigmoid(z), 1e-9, 1 - 1e-9)
    y = np.asarray(levels, dtype=np.float64)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum(axis=1).mean())


def fit_temperature(logits: np.ndarray, levels: np.ndarray,
                    bounds=(0.05, 10.0)) -> float:
    """Fit T on VALIDATION logits. Never on training, never on the holdout."""
    res = minimize_scalar(lambda t: coral_nll(logits, levels, t),
                          bounds=bounds, method="bounded")
    return float(res.x)


def apply_temperature(logits: np.ndarray, T: float) -> np.ndarray:
    return np.asarray(logits, dtype=np.float64) / max(T, 1e-3)


# ------------------------------------------------------------------ ECE
def expected_calibration_error(probs: np.ndarray, labels: np.ndarray,
                               n_bins: int = 10) -> dict:
    """Standard equal-width-bin ECE for a binary probability (we use P(referable)).

    ECE = sum over bins of (bin_size/N) * |accuracy_in_bin - mean_confidence_in_bin|.
    """
    probs = np.asarray(probs, dtype=np.float64).ravel()
    labels = np.asarray(labels).ravel().astype(int)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece, mce, bins = 0.0, 0.0, []
    n = len(probs)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (probs > lo) & (probs <= hi) if i else (probs >= lo) & (probs <= hi)
        cnt = int(sel.sum())
        if cnt == 0:
            bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": 0,
                         "confidence": None, "accuracy": None})
            continue
        conf = float(probs[sel].mean())
        acc = float(labels[sel].mean())
        gap = abs(acc - conf)
        ece += cnt / n * gap
        mce = max(mce, gap)
        bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": cnt,
                     "confidence": round(conf, 4), "accuracy": round(acc, 4)})
    return {"ece": round(float(ece), 5), "mce": round(float(mce), 5),
            "n_bins": n_bins, "n": n, "bins": bins}


def brier_score(probs: np.ndarray, labels: np.ndarray) -> float:
    p = np.asarray(probs, dtype=np.float64).ravel()
    y = np.asarray(labels, dtype=np.float64).ravel()
    return float(np.mean((p - y) ** 2))


# ------------------------------------------------------------------ persistence
def save_temperature(path: Path, T: float, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"temperature": T, **report}, indent=2))


def load_temperature(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        return float(json.loads(path.read_text())["temperature"])
    except Exception:
        return None


def confidence_from_cumulative(cum_row: np.ndarray, grade: int) -> float:
    """The number shown as "confidence" in the UI: P(the grade we reported).

    Deliberately NOT max(per_grade_probability) — reporting the confidence of a grade you
    did not output is a subtle lie, and on an ordinal chain the argmax grade and the
    threshold grade can differ.
    """
    from src.grading.model import cumulative_to_per_grade
    probs = cumulative_to_per_grade(np.asarray(cum_row).reshape(1, -1))[0]
    return float(probs[int(np.clip(grade, 0, len(probs) - 1))])
