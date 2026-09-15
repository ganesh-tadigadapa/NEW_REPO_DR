"""Metrics, threshold tuning, and the one-shot holdout protocol.

## The protocol, which is the actual deliverable here

    1. Train.                                        (train split)
    2. Tune the referable cut for sensitivity.       (VALIDATION logits only)
    3. Fit the temperature.                          (VALIDATION logits only)
    4. FREEZE. Write thresholds.json + temperature.json.
    5. Run the holdout ONCE.                         (IDRiD, never seen, never tuned on)

Step 5 is run by `scripts/run_holdout.py`, which refuses to run twice against the same
frozen config without an explicit override, because "we opened the test set once" has to
be enforced by something other than good intentions.

## Metrics we report and why

  QWK                 the APTOS competition metric, so our number is comparable to
                      published work. Quadratic weights punish being far off.
  referable sens/spec the operational decision. Reported WITH bootstrap CIs, because on
                      a 103-image holdout a point estimate alone is close to meaningless.
  ECE                 whether the confidence is honest, before and after calibration.
  confusion matrix    where the errors actually are.
"""
from __future__ import annotations

import json
import numpy as np

from src.common.config import REFERABLE_MIN_GRADE
from src.grading.model import (cumulative_to_grade, cumulative_to_per_grade,
                               logits_to_cumulative)


# ------------------------------------------------------------------ metrics
def quadratic_weighted_kappa(y_true, y_pred, n_classes: int = 5) -> float:
    y_true = np.asarray(y_true, int); y_pred = np.asarray(y_pred, int)
    O = np.zeros((n_classes, n_classes))
    for t, p in zip(y_true, y_pred):
        O[t, p] += 1
    w = np.zeros((n_classes, n_classes))
    for i in range(n_classes):
        for j in range(n_classes):
            w[i, j] = (i - j) ** 2 / (n_classes - 1) ** 2
    hist_t = np.bincount(y_true, minlength=n_classes)
    hist_p = np.bincount(y_pred, minlength=n_classes)
    E = np.outer(hist_t, hist_p).astype(float)
    if O.sum() == 0 or E.sum() == 0:
        return 0.0
    E = E / E.sum() * O.sum()
    denom = (w * E).sum()
    if denom == 0:
        return 1.0
    return float(1.0 - (w * O).sum() / denom)


def confusion(y_true, y_pred, n=5) -> list:
    M = np.zeros((n, n), int)
    for t, p in zip(np.asarray(y_true, int), np.asarray(y_pred, int)):
        M[t, p] += 1
    return M.tolist()


def binary_stats(y_true_bin, y_pred_bin) -> dict:
    t = np.asarray(y_true_bin, int); p = np.asarray(y_pred_bin, int)
    tp = int(((p == 1) & (t == 1)).sum()); tn = int(((p == 0) & (t == 0)).sum())
    fp = int(((p == 1) & (t == 0)).sum()); fn = int(((p == 0) & (t == 1)).sum())
    return {
        "sensitivity": round(tp / max(tp + fn, 1), 4),
        "specificity": round(tn / max(tn + fp, 1), 4),
        "ppv": round(tp / max(tp + fp, 1), 4),
        "npv": round(tn / max(tn + fn, 1), 4),
        "accuracy": round((tp + tn) / max(len(t), 1), 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }


def roc_auc(scores, labels) -> float:
    s = np.asarray(scores, float); y = np.asarray(labels, int)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(s)
    ranks = np.empty(len(s), float); ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt)); np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    return float((ranks[y == 1].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def bootstrap_ci(fn, *arrays, n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> dict:
    """Percentile bootstrap CI. On a 103-image holdout this is not optional."""
    rng = np.random.default_rng(seed)
    arrays = [np.asarray(a) for a in arrays]
    n = len(arrays[0])
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            vals.append(fn(*[a[idx] for a in arrays]))
        except Exception:
            continue
    if not vals:
        return {"lo": None, "hi": None, "n_boot": 0}
    lo, hi = np.percentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"lo": round(float(lo), 4), "hi": round(float(hi), 4), "n_boot": len(vals)}


# ------------------------------------------------------ threshold tuning
def tune_referable_cut(cum_val: np.ndarray, grades_val: np.ndarray,
                       target_sensitivity: float = 0.90,
                       min_specificity: float = 0.85) -> dict:
    """Choose the cut on P(grade>=2) that meets the clinical operating point.

    Policy, stated explicitly because it is a clinical choice and not a technical one:
    among all cuts reaching the sensitivity target, take the one with the HIGHEST
    specificity. If none reaches it, take the cut with the highest sensitivity that still
    holds specificity above the floor, and record that the target was missed. We never
    silently report the best-looking operating point.
    """
    y = (np.asarray(grades_val) >= REFERABLE_MIN_GRADE).astype(int)
    p = np.asarray(cum_val)[:, 1]
    cands = np.unique(np.concatenate([[0.0, 1.0], np.quantile(p, np.linspace(0, 1, 501))]))
    rows = []
    for t in cands:
        st = binary_stats(y, (p >= t).astype(int))
        rows.append({"cut": float(t), **st})

    meeting = [r for r in rows if r["sensitivity"] >= target_sensitivity
               and r["specificity"] >= min_specificity]
    if meeting:
        best = max(meeting, key=lambda r: (r["specificity"], r["sensitivity"]))
        status = "target_met"
    else:
        relaxed = [r for r in rows if r["specificity"] >= min_specificity]
        if relaxed:
            best = max(relaxed, key=lambda r: r["sensitivity"])
            status = "sensitivity_target_missed_specificity_floor_held"
        else:
            best = max(rows, key=lambda r: r["sensitivity"] + r["specificity"])
            status = "both_targets_missed"
    return {"chosen": best, "status": status,
            "target_sensitivity": target_sensitivity,
            "min_specificity": min_specificity,
            "auc": round(roc_auc(p, y), 4),
            "curve": rows[::10]}


def tune_all_cuts(cum_val: np.ndarray, grades_val: np.ndarray,
                  referable_cut: float) -> list:
    """Cuts for the other grade boundaries, chosen to maximise QWK.

    The referable cut (index 1) is fixed by the clinical target above and is NOT
    re-optimised here — the referral decision outranks the grade-agreement metric.
    """
    grades_val = np.asarray(grades_val)
    cuts = [0.5, referable_cut, 0.5, 0.5]
    for k in (0, 2, 3):
        best, best_q = cuts[k], -2.0
        for t in np.linspace(0.02, 0.98, 97):
            trial = list(cuts); trial[k] = float(t)
            q = quadratic_weighted_kappa(grades_val, cumulative_to_grade(cum_val, trial))
            if q > best_q:
                best_q, best = q, float(t)
        cuts[k] = best
    # cuts must stay ordered or the grade decoder can produce nonsense
    return cuts


def evaluate_split(logits: np.ndarray, grades: np.ndarray, cuts, label: str,
                   with_ci: bool = True) -> dict:
    cum = logits_to_cumulative(logits)
    pred = cumulative_to_grade(cum, cuts)
    y_ref = (np.asarray(grades) >= REFERABLE_MIN_GRADE).astype(int)
    p_ref = cum[:, 1]
    pred_ref = (p_ref >= cuts[1]).astype(int)

    out = {
        "split": label,
        "n": int(len(grades)),
        "grade_distribution": np.bincount(np.asarray(grades, int), minlength=5).tolist(),
        "qwk": round(quadratic_weighted_kappa(grades, pred), 4),
        "exact_accuracy": round(float((np.asarray(pred) == np.asarray(grades)).mean()), 4),
        "within_one_grade": round(float((np.abs(np.asarray(pred) - np.asarray(grades)) <= 1).mean()), 4),
        "confusion_matrix": confusion(grades, pred),
        "referable": {**binary_stats(y_ref, pred_ref),
                      "auc": round(roc_auc(p_ref, y_ref), 4),
                      "cut": float(cuts[1])},
        "cuts": [float(c) for c in cuts],
    }
    if with_ci:
        out["referable"]["sensitivity_ci95"] = bootstrap_ci(
            lambda a, b: binary_stats(a, b)["sensitivity"], y_ref, pred_ref)
        out["referable"]["specificity_ci95"] = bootstrap_ci(
            lambda a, b: binary_stats(a, b)["specificity"], y_ref, pred_ref)
        out["qwk_ci95"] = bootstrap_ci(
            lambda a, b: quadratic_weighted_kappa(a, b),
            np.asarray(grades, int), np.asarray(pred, int))
    return out
