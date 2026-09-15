"""Requirement #2b — lesion detection by classical computer vision.

Deliberately NOT a trained U-Net. Reasons we say out loud:
  - IDRiD gives 54 pixel-annotated training images. A segmentation net trained on that
    is a model of 54 images, not of diabetic retinopathy.
  - Classical morphology is inherently interpretable: every detection traces to an
    explicit geometric criterion a clinician can be shown.
  - It needs zero training time, which we do not have.

Three detectors, each keyed to the actual appearance of the lesion:

  microaneurysms  Small, round, DARK, isolated. Found by morphological closing on the
                  inverted green channel (removes vessels, which are elongated) followed
                  by extended-minima. The classic Walter-Klein approach.
  haemorrhages    Dark like MAs but LARGER and irregular. Same dark-blob pipeline with a
                  larger size band and a relaxed circularity requirement.
  hard exudates   BRIGHT, sharp-edged, irregular, yellow-white. Found by top-hat on the
                  green channel with the optic disc masked out (the disc is bright and
                  round and would otherwise dominate every image).

Every detector returns pixel-space blobs so the API can draw them and assign quadrants.
"""
from __future__ import annotations

import cv2
import numpy as np

from src.segment.structures import quadrant_of

# Vessels occupy roughly 7-15% of a fundus image. These bound what we will accept from
# the adaptive threshold before falling back to targeting the coverage directly.
MIN_VESSEL_COVERAGE = 0.02
MAX_VESSEL_COVERAGE = 0.30
TARGET_VESSEL_COVERAGE = 0.10


def vessel_map(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Vessel segmentation by multiscale Frangi vesselness on the inverted green channel.

    Frangi is the standard tubular-structure filter: it scores each pixel on how
    ridge-like the local Hessian is, across a range of scales, so it responds to long
    thin dark structures (vessels) and not to compact dark blobs (haemorrhages,
    microaneurysms). That distinction is exactly what we need, because a vessel
    cross-section and a haemorrhage are identical to a plain intensity threshold.

    An earlier implementation used max-over-orientations morphological line opening; it
    responded to the smooth background as strongly as to vessels and flagged 99% of the
    retina, which silently deleted every lesion candidate downstream. Frangi is both more
    principled and, unlike that version, actually verified — see tests/test_lesions.py.

    The output is thresholded by Otsu on the in-retina response and then clipped to a
    plausible coverage band: vessels occupy roughly 7-15% of a fundus image, so a mask
    outside [2%, 30%] means the filter has failed and we prefer to suppress nothing
    rather than suppress everything.
    """
    from skimage.filters import frangi

    g = cv2.split(bgr)[1].astype(np.float32) / 255.0
    inv = 1.0 - g
    # Scales start at 2.0, NOT 1.0. At sigma 1 a microaneurysm — a 2-4 px dark dot — is
    # itself a valid ridge, so the filter flags the very objects it exists to distinguish
    # from vessels. Measured: with sigmas from 1.0 the vessel mask deleted every
    # microaneurysm on our synthetic set (18 planted, 0 detected).
    resp = frangi(inv, sigmas=np.arange(2.0, 7.0, 1.0), black_ridges=False)
    resp = np.nan_to_num(resp)
    resp[~mask] = 0.0
    vals = resp[mask]
    if vals.size == 0 or vals.max() <= 0:
        return np.zeros_like(mask, dtype=bool)

    def at(threshold: float) -> np.ndarray:
        return (resp >= threshold) & mask

    # First choice: Otsu on the in-retina response, which adapts to the image.
    norm = (vals / vals.max() * 255).astype(np.uint8)
    otsu_level, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    vessels = at(otsu_level / 255.0 * vals.max())

    # Otsu assumes a clean bimodal response. Dark lesions are also somewhat ridge-like,
    # so on a heavily diseased retina they skew the histogram and Otsu lands far outside
    # any plausible vessel coverage. Measured on our synthetic set, Otsu succeeded on a
    # clean retina (13.8% coverage) and failed on grade-2 and grade-4 images.
    #
    # The first version of this guard returned an EMPTY mask in that case, which meant
    # vessel suppression switched itself off precisely on the images where lesions are
    # present — the only images where it does anything. Falling back to a fixed
    # percentile is strictly better: vessels occupy a fairly stable fraction of a fundus
    # image, so targeting that fraction degrades gracefully instead of vanishing.
    coverage = float(vessels[mask].mean())
    if not (MIN_VESSEL_COVERAGE <= coverage <= MAX_VESSEL_COVERAGE):
        vessels = at(float(np.percentile(vals, 100.0 * (1.0 - TARGET_VESSEL_COVERAGE))))

    # Vessels are connected structures; isolated specks are noise, not vessel.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        vessels.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(vessels)
    min_area = max(int(0.00002 * mask.sum()), 12)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == i] = True
    return keep


def _blobs(binary: np.ndarray, min_area: int, max_area: int,
           min_circularity: float = 0.0) -> list[dict]:
    n, labels, stats, cents = cv2.connectedComponentsWithStats(
        binary.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not (min_area <= area <= max_area):
            continue
        w, h = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
        # circularity via the bounding-box-normalised fill and aspect ratio; cheaper and
        # more stable on tiny blobs than a contour perimeter measure.
        aspect = min(w, h) / max(max(w, h), 1)
        fill = area / max(w * h, 1)
        circ = aspect * fill
        if circ < min_circularity:
            continue
        cx, cy = cents[i]
        out.append({"cx": float(cx), "cy": float(cy), "area": area,
                    "w": w, "h": h, "circularity": round(float(circ), 3)})
    return out


def detect_dark_lesions(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> tuple[list, list]:
    """Returns (microaneurysms, haemorrhages) as blob lists.

    Discrimination is **shape-first**. Both lesion types and the vessels are dark, so an
    intensity threshold alone cannot separate them; what separates them is that lesions
    are compact and vessels are elongated. We therefore threshold for darkness, then
    filter candidates on compactness, and use the Frangi vessel mask only to remove
    detections that sit squarely on a vessel. Relying on the vessel mask as the primary
    filter is what broke the first version of this function.

    Microaneurysms and haemorrhages are the same detection with different size bands:
    an MA is by definition a small round dark dot; a haemorrhage is larger and less
    regular. Size bands are expressed as a fraction of measured optic-disc area, so they
    transfer between cameras with different resolutions and fields of view.
    """
    g = cv2.split(bgr)[1]
    g = cv2.medianBlur(g, 3)
    # Illumination-flatten so a dark corner isn't read as a giant haemorrhage. The
    # background kernel must be much larger than any lesion or it erases them.
    bg = cv2.medianBlur(g, max(int(g.shape[1] / 20) | 1, 21))
    flat = cv2.subtract(bg, g)          # dark objects become bright here
    flat[~mask] = 0

    vals = flat[mask]
    if vals.size == 0:
        return [], []
    thr = float(np.percentile(vals, 98.5))
    cand = (flat >= max(thr, 8)) & mask

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN, k) > 0

    disc_area = np.pi * disc["radius"] ** 2
    # compactness floors: an MA is near-circular; a haemorrhage is irregular but still
    # blob-like, and anything below ~0.18 is a vessel segment.
    ma = _blobs(cand, max(int(disc_area * 0.0004), 3), int(disc_area * 0.02),
                min_circularity=0.42)
    he = _blobs(cand, int(disc_area * 0.02), int(disc_area * 0.9),
                min_circularity=0.22)

    # Suppress only on ELONGATED vessel components. A compact patch of vesselness
    # response is far more likely to be the lesion we are trying to count than a vessel,
    # so deleting candidates under it loses true positives — which is exactly what a
    # whole-mask suppression did here (haemorrhages 7 planted, 2 detected).
    vd = elongated_vessels(vessel_map(bgr, mask))
    if vd.any():
        ma = [b for b in ma if not vd[int(b["cy"]), int(b["cx"])]]
        he = [b for b in he if not vd[int(b["cy"]), int(b["cx"])]]
    return ma, he


def elongated_vessels(vessels: np.ndarray, min_elongation: float = 3.0) -> np.ndarray:
    """Keep only components long and thin enough to be a genuine vessel segment."""
    if not vessels.any():
        return vessels
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        vessels.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(vessels)
    for i in range(1, n):
        w = int(stats[i, cv2.CC_STAT_WIDTH]); h = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area <= 0:
            continue
        # thinness: a vessel fills only a fraction of its bounding box, and the box is
        # far from square. Either signal alone is enough to call it vessel-like.
        elongation = max(w, h) / max(min(w, h), 1)
        fill = area / max(w * h, 1)
        if elongation >= min_elongation or fill < 0.25:
            keep[labels == i] = True
    return keep


def detect_exudates(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> list[dict]:
    """Hard exudates: bright, sharp, irregular. Optic disc excluded."""
    g = cv2.split(bgr)[1]
    # mask out the disc generously - a 1.4x radius disc of exclusion
    dmask = np.ones_like(mask, dtype=bool)
    cv2.circle(dmask.view(np.uint8), (disc["cx"], disc["cy"]),
               int(disc["radius"] * 1.4), 0, -1)
    work = mask & dmask

    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                   (max(int(disc["radius"] / 2) | 1, 7),) * 2)
    tophat = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, se)
    tophat[~work] = 0
    vals = tophat[work]
    if vals.size == 0:
        return []
    thr = float(np.percentile(vals, 99.3))
    cand = (tophat >= max(thr, 12)) & work

    # exudates have strong edges; a soft bright patch (drusen, reflection) does not
    edges = cv2.Canny(cv2.GaussianBlur(g, (0, 0), 1.0), 40, 110)
    ek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    near_edge = cv2.dilate(edges, ek) > 0
    cand = cand & near_edge

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    disc_area = np.pi * disc["radius"] ** 2
    return _blobs(cand, int(disc_area * 0.0008), int(disc_area * 0.5))


# ------------------------------------------------------------------ orchestration
LESION_COLOURS = {                      # BGR
    "microaneurysms": (0, 0, 255),      # red
    "haemorrhages": (255, 0, 0),        # blue
    "hard_exudates": (0, 255, 0),       # green
}


def analyse(bgr: np.ndarray, mask: np.ndarray, disc: dict, fovea: dict) -> dict:
    """Full lesion pass. Returns the `lesions` block plus raw blobs for drawing."""
    ma, he = detect_dark_lesions(bgr, mask, disc)
    ex = detect_exudates(bgr, mask, disc)
    raw = {"microaneurysms": ma, "haemorrhages": he, "hard_exudates": ex}

    out = {}
    for name, blobs in raw.items():
        quads = {"ST": 0, "SN": 0, "IT": 0, "IN": 0}
        for b in blobs:
            quads[quadrant_of(b["cx"], b["cy"], disc, fovea)] += 1
        out[name] = {"count": len(blobs), "by_quadrant": quads}
    out["method"] = "classical-cv"
    return {"summary": out, "raw": raw}


def draw_lesions(bgr: np.ndarray, raw: dict) -> np.ndarray:
    out = bgr.copy()
    for name, blobs in raw.items():
        colour = LESION_COLOURS[name]
        for b in blobs:
            r = max(int(np.sqrt(b["area"] / np.pi)) + 3, 4)
            cv2.circle(out, (int(b["cx"]), int(b["cy"])), r, colour, 2)
    return out
