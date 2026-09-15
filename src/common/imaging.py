"""Fundus image preprocessing.

Three operations, in this order, and the order matters:

1. `crop_to_retina`  — fundus photos are a bright circle on a black rectangle, and the
   black border varies hugely between cameras. Cropping to the circle is what makes a
   cheap portable camera's output look dimensionally like a hospital camera's.
2. `ben_graham`      — subtract a heavily blurred copy of the image from itself. This
   cancels the camera's own illumination gradient. Highest-value single trick on fundus
   images; it is what won the 2015 Kaggle DR competition.
3. `clahe_green`     — contrast-limited adaptive histogram equalisation on the green
   channel, which carries the most lesion detail (haemoglobin absorbs green).

Everything here is pure numpy/OpenCV — no model, no GPU. It runs identically in the
trainer, in the API, and in the tests.
"""
from __future__ import annotations

import cv2
import numpy as np


# --------------------------------------------------------------------------- crop
def retina_mask(bgr: np.ndarray, thresh: int = 10) -> np.ndarray:
    """Boolean mask of the illuminated circular retina region."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # A fixed low threshold is enough: the surround is genuinely near-black, and using
    # Otsu here fails on very dark (underexposed) fundus images by eating the retina.
    mask = gray > thresh
    if mask.mean() < 0.02:  # pathologically dark image - fall back to Otsu
        _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask = m > 0
    # close small holes so vessels/dark lesions inside the disc don't punch the mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, k) > 0
    return mask


def crop_to_retina(bgr: np.ndarray, pad: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Crop away the black surround. Returns (cropped_bgr, cropped_mask)."""
    mask = retina_mask(bgr)
    if not mask.any():
        return bgr, np.ones(bgr.shape[:2], dtype=bool)
    ys, xs = np.where(mask)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, bgr.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, bgr.shape[1])
    return bgr[y0:y1, x0:x1], mask[y0:y1, x0:x1]


def square_pad(bgr: np.ndarray, mask: np.ndarray | None = None):
    """Pad to a square with black so the resize doesn't distort the retina's aspect."""
    h, w = bgr.shape[:2]
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    out = np.zeros((s, s, bgr.shape[2]), dtype=bgr.dtype)
    out[top:top + h, left:left + w] = bgr
    if mask is None:
        return out, None
    om = np.zeros((s, s), dtype=bool)
    om[top:top + h, left:left + w] = mask
    return out, om


# ---------------------------------------------------------------- enhancement
def ben_graham(bgr: np.ndarray, sigma_frac: float = 1 / 30, alpha: float = 4.0,
               beta: float = -4.0, gamma: float = 128.0) -> np.ndarray:
    """out = alpha*img + beta*blur(img) + gamma. Cancels the illumination gradient."""
    sigma = max(int(bgr.shape[1] * sigma_frac), 1)
    blur = cv2.GaussianBlur(bgr, (0, 0), sigma)
    return cv2.addWeighted(bgr, alpha, blur, beta, gamma)


def clahe_green(bgr: np.ndarray, clip: float = 2.5, tiles: int = 8) -> np.ndarray:
    """CLAHE on the green channel only; red and blue pass through."""
    b, g, r = cv2.split(bgr)
    cl = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tiles, tiles))
    return cv2.merge([b, cl.apply(g), r])


def apply_circular_mask(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Re-blacken outside the retina. Ben-Graham lifts the surround to grey otherwise,
    and that grey ring is a bright artefact the CNN will happily learn from."""
    out = bgr.copy()
    out[~mask] = 0
    return out


# ---------------------------------------------------------------- pipelines
def preprocess_for_model(bgr: np.ndarray, size: int, enhance: bool = True) -> np.ndarray:
    """The exact transform used at train AND at inference. Returns uint8 BGR size×size.

    If these two ever diverge the model silently degrades, so there is one function.
    """
    cropped, mask = crop_to_retina(bgr)
    cropped, mask = square_pad(cropped, mask)
    cropped = cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask.astype(np.uint8), (size, size),
                      interpolation=cv2.INTER_NEAREST).astype(bool)
    if enhance:
        cropped = ben_graham(cropped)
        cropped = clahe_green(cropped)
    # erode the mask slightly: the very edge of the retina is a bright rim artefact
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.erode(mask.astype(np.uint8), k).astype(bool)
    return apply_circular_mask(cropped, mask)


def preprocess_for_lesions(bgr: np.ndarray, size: int):
    """Higher-resolution, *un*-Ben-Grahamed image for classical lesion CV.

    Ben-Graham destroys absolute intensity, and the exudate detector keys on absolute
    brightness — so lesion CV gets its own, gentler pipeline. Returns (bgr, mask).
    """
    cropped, mask = crop_to_retina(bgr)
    cropped, mask = square_pad(cropped, mask)
    cropped = cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask.astype(np.uint8), (size, size),
                      interpolation=cv2.INTER_NEAREST).astype(bool)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.erode(mask.astype(np.uint8), k).astype(bool)
    return cropped, mask


def decode_image(data: bytes) -> np.ndarray:
    """bytes -> BGR uint8. Raises ValueError on anything OpenCV can't read."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    return img


def to_png_bytes(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("png encode failed")
    return buf.tobytes()
