"""Requirement #2a — anatomical landmarks: optic disc and fovea.

We need these for two reasons that are not "because the PS asked":

1. The optic disc is the brightest round object in a fundus photo and it looks exactly
   like a giant hard exudate. Without masking it out, the exudate detector fires on it
   every single time. Disc localisation is a *prerequisite* for lesion counting, not a
   decoration.
2. The ICDR 4-2-1 rule is defined *by quadrant*, and quadrants are defined relative to
   the disc-fovea axis. You cannot compute the clinical rule without knowing where the
   disc is.

Both are classical CV. No training data needed, and the failure modes are inspectable.
"""
from __future__ import annotations

import cv2
import numpy as np


def find_optic_disc(bgr: np.ndarray, mask: np.ndarray) -> dict:
    """Locate the optic disc. Returns {'cx','cy','radius','confidence'} in pixels.

    Method: the disc is the brightest sustained region in the red+green channels. We
    blur hard (killing exudates, which are small) and take the max of the smoothed
    intensity, then fit a radius from the local bright blob.
    """
    h, w = bgr.shape[:2]
    b, g, r = cv2.split(bgr)
    # red saturates in bright fundus images; green alone is noisier. Their mean is the
    # standard compromise for disc detection.
    bright = ((r.astype(np.float32) + g.astype(np.float32)) / 2)
    bright[~mask] = 0

    # A disc is ~1/7 of the retina width. Blurring at that scale makes the disc the
    # global maximum while erasing exudates (which are an order of magnitude smaller).
    sigma = max(int(w / 28), 3)
    sm = cv2.GaussianBlur(bright, (0, 0), sigma)
    sm[~mask] = 0
    _, maxval, _, maxloc = cv2.minMaxLoc(sm)
    cx, cy = maxloc

    # radius: grow from the peak while intensity stays above 60% of peak
    est_r = max(int(w / 14), 5)
    ring = sm[max(cy - est_r * 2, 0):cy + est_r * 2, max(cx - est_r * 2, 0):cx + est_r * 2]
    thr = 0.85 * maxval
    area = float((ring > thr).sum())
    radius = float(np.sqrt(max(area, 1.0) / np.pi))
    radius = float(np.clip(radius, w / 30, w / 8))

    # confidence: how much brighter the peak is than the retina's median. A real disc is
    # markedly brighter; if it isn't, the image is washed out and we say so.
    med = float(np.median(bright[mask])) if mask.any() else 0.0
    conf = float(np.clip((maxval - med) / max(med, 1e-6), 0, 1))
    return {"cx": int(cx), "cy": int(cy), "radius": radius, "confidence": round(conf, 3)}


def find_fovea(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> dict:
    """Locate the fovea geometrically, then refine to the darkest local region.

    Anatomy gives us a strong prior: the fovea sits ~2.5 disc diameters temporal to the
    disc, on roughly the same horizontal line. We use the prior to define a search box,
    then take the darkest blob inside it. Pure intensity search over the whole image
    would find a haemorrhage instead.
    """
    h, w = bgr.shape[:2]
    dd = disc["radius"] * 2.0
    # temporal direction = away from the image centre horizontally. (Left vs right eye is
    # unknown, and this is the standard way to infer it without metadata.)
    direction = -1 if disc["cx"] > w / 2 else 1
    px = int(np.clip(disc["cx"] + direction * 2.5 * dd, 0, w - 1))
    py = int(np.clip(disc["cy"], 0, h - 1))

    box = int(dd)
    x0, x1 = max(px - box, 0), min(px + box, w)
    y0, y1 = max(py - box, 0), min(py + box, h)
    if x1 - x0 < 5 or y1 - y0 < 5:
        return {"cx": px, "cy": py, "confidence": 0.0, "method": "geometric-prior-only"}

    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g[~mask] = 255
    sub = cv2.GaussianBlur(g[y0:y1, x0:x1], (0, 0), max(int(dd / 6), 2))
    minval, _, minloc, _ = cv2.minMaxLoc(sub)
    fx, fy = x0 + minloc[0], y0 + minloc[1]
    med = float(np.median(g[mask])) if mask.any() else 1.0
    conf = float(np.clip((med - minval) / max(med, 1e-6), 0, 1))
    return {"cx": int(fx), "cy": int(fy), "confidence": round(conf, 3),
            "method": "prior+darkest-blob"}


def quadrant_of(x: float, y: float, disc: dict, fovea: dict) -> str:
    """Assign a point to one of the four retinal quadrants: ST/SN/IT/IN.

    The axis is the disc->fovea line (that is what "temporal" means clinically), and the
    perpendicular through the disc splits superior from inferior. Returned codes are
    Superior/Inferior x Temporal/Nasal.
    """
    ax = fovea["cx"] - disc["cx"]
    ay = fovea["cy"] - disc["cy"]
    n = np.hypot(ax, ay)
    if n < 1e-6:
        ax, ay, n = 1.0, 0.0, 1.0
    ax, ay = ax / n, ay / n           # unit vector pointing temporally
    px, py = x - disc["cx"], y - disc["cy"]
    temporal = (px * ax + py * ay) > 0
    # perpendicular (rotate the temporal axis by 90 deg); image y grows downward, so a
    # positive cross product is *inferior* on screen.
    inferior = (px * (-ay) + py * ax) > 0
    return ("I" if inferior else "S") + ("T" if temporal else "N")


def draw_landmarks(bgr: np.ndarray, disc: dict, fovea: dict) -> np.ndarray:
    out = bgr.copy()
    cv2.circle(out, (disc["cx"], disc["cy"]), int(disc["radius"]), (0, 255, 255), 2)
    cv2.putText(out, "disc", (disc["cx"] - 18, disc["cy"] - int(disc["radius"]) - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.drawMarker(out, (fovea["cx"], fovea["cy"]), (255, 0, 255),
                   cv2.MARKER_CROSS, 22, 2)
    cv2.putText(out, "fovea", (fovea["cx"] - 22, fovea["cy"] - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1, cv2.LINE_AA)
    return out
