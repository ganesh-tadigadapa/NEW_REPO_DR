"""Generate synthetic fundus images for pipeline testing.

These are NOT training data and no metric may ever be computed on them. They exist so
the quality gate, lesion CV, Grad-CAM, PDF and API can be exercised and demoed before
the real datasets land, and so the blur-rejection path has a guaranteed-blurry input.

Any output of this script is written to data/interim/synthetic/ and is git-ignored.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

RNG = np.random.default_rng(7)


def _base(size: int, rng) -> tuple[np.ndarray, np.ndarray]:
    img = np.zeros((size, size, 3), np.uint8)
    c, r = size // 2, int(size * 0.47)
    mask = np.zeros((size, size), np.uint8)
    cv2.circle(mask, (c, c), r, 255, -1)
    m = mask > 0
    # fundus is orange-red: high red, mid green, low blue
    base = np.array([40, 75, 190], np.float32)
    tint = rng.uniform(-14, 14, 3)
    field = np.zeros((size, size, 3), np.float32)
    field[m] = base + tint
    # radial falloff - real fundus photos are brighter centrally
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((yy - c) ** 2 + (xx - c) ** 2) / r
    fall = np.clip(1.15 - 0.45 * d ** 2, 0, 1.3)[..., None]
    field *= fall
    img = np.clip(field, 0, 255).astype(np.uint8)
    img[~m] = 0
    return img, m


def _vessels(img, mask, size, rng, n=11):
    c = size // 2
    # disc sits nasally, off-centre
    dx, dy = int(size * 0.28) * rng.choice([-1, 1]), int(rng.uniform(-0.05, 0.05) * size)
    disc = (c + dx, c + dy)
    for _ in range(n):
        ang = rng.uniform(0, 2 * np.pi)
        pt = np.array(disc, float)
        th = rng.uniform(4.5, 7.5)
        v = np.array([np.cos(ang), np.sin(ang)])
        for _ in range(rng.integers(28, 46)):
            nxt = pt + v * rng.uniform(7, 13)
            colour = (28, 34, 105) if rng.random() < .6 else (34, 46, 130)
            cv2.line(img, tuple(pt.astype(int)), tuple(nxt.astype(int)),
                     colour, max(int(th), 1), cv2.LINE_AA)
            pt = nxt
            v = v + rng.normal(0, .22, 2); v /= np.linalg.norm(v)
            th *= 0.955
            if np.linalg.norm(pt - np.array([c, c])) > size * 0.45:
                break
    img[~mask] = 0
    return disc


def _disc(img, disc, size):
    r = int(size * 0.055)
    cv2.circle(img, disc, r, (205, 232, 245), -1, cv2.LINE_AA)
    cv2.circle(img, disc, int(r * 0.55), (175, 215, 235), -1, cv2.LINE_AA)
    cv2.GaussianBlur(img, (0, 0), 1.2, dst=img)


def _fovea(img, disc, size, mask):
    c = size // 2
    direction = -1 if disc[0] > c else 1
    fx = int(np.clip(disc[0] + direction * size * 0.27, 0, size - 1))
    fy = disc[1]
    overlay = img.copy()
    cv2.circle(overlay, (fx, fy), int(size * 0.06), (18, 34, 96), -1)
    cv2.addWeighted(overlay, .55, img, .45, 0, dst=img)
    cv2.GaussianBlur(img, (0, 0), size * 0.012, dst=img)
    img[~mask] = 0
    return (fx, fy)


def _lesions(img, mask, size, grade, rng):
    """Plant lesions in numbers loosely consistent with the ICDR grade."""
    counts = {0: (0, 0, 0), 1: (6, 0, 0), 2: (18, 7, 5), 3: (45, 25, 14), 4: (60, 35, 20)}
    n_ma, n_he, n_ex = counts[grade]
    ys, xs = np.where(mask)

    def rand_pt():
        i = rng.integers(len(ys))
        return int(xs[i]), int(ys[i])

    for _ in range(n_ma):                       # microaneurysms: tiny dark dots
        cv2.circle(img, rand_pt(), int(rng.integers(2, 4)), (20, 26, 92), -1, cv2.LINE_AA)
    for _ in range(n_he):                       # haemorrhages: larger dark blots
        p = rand_pt()
        ax = (int(rng.integers(7, 16)), int(rng.integers(6, 14)))
        cv2.ellipse(img, p, ax, float(rng.uniform(0, 180)), 0, 360, (16, 22, 78), -1, cv2.LINE_AA)
    for _ in range(n_ex):                       # hard exudates: bright yellow-white
        p = rand_pt()
        ax = (int(rng.integers(4, 10)), int(rng.integers(4, 9)))
        cv2.ellipse(img, p, ax, float(rng.uniform(0, 180)), 0, 360, (150, 240, 250), -1, cv2.LINE_AA)
    img[~mask] = 0


def synth(size=1024, grade=2, seed=None, defect=None) -> np.ndarray:
    rng = np.random.default_rng(seed) if seed is not None else RNG
    img, mask = _base(size, rng)
    disc = _vessels(img, mask, size, rng)
    _disc(img, disc, size)
    _fovea(img, disc, size, mask)
    _lesions(img, mask, size, grade, rng)
    img = cv2.GaussianBlur(img, (0, 0), 0.7)
    img[~mask] = 0

    if defect == "blur":
        img = cv2.GaussianBlur(img, (0, 0), size * 0.011)
        img[~mask] = 0
    elif defect == "uneven":                     # half the retina in shadow
        yy, xx = np.mgrid[0:size, 0:size]
        ramp = np.clip(0.20 + 1.5 * (xx / size), 0, 1.35)[..., None]
        img = np.clip(img.astype(np.float32) * ramp, 0, 255).astype(np.uint8)
        img[~mask] = 0
    elif defect == "clipped":                    # retina half out of frame
        img = np.roll(img, -int(size * 0.34), axis=1)
        img[:, -int(size * 0.34):] = 0
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/interim/synthetic")
    ap.add_argument("--size", type=int, default=1024)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    made = []
    for g in range(5):
        for k in range(2):
            p = out / f"grade{g}_{k}.png"
            cv2.imwrite(str(p), synth(args.size, g, seed=100 * g + k))
            made.append(p)
    for defect in ("blur", "uneven", "clipped"):
        p = out / f"bad_{defect}.png"
        cv2.imwrite(str(p), synth(args.size, 2, seed=42, defect=defect))
        made.append(p)
    print(f"wrote {len(made)} synthetic images to {out}")
    for p in made:
        print("  ", p)


if __name__ == "__main__":
    main()
