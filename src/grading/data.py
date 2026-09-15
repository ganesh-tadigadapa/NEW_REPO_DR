"""Dataset construction for APTOS / IDRiD.

## The split rule, which matters more than the architecture

Splits are **stratified by grade** and made once, with a fixed seed, and written to disk
as a CSV. Two consequences we say out loud:

  - APTOS is heavily imbalanced (roughly half the images are grade 0 and grade 3 is under
    6%). An unstratified random split can leave a validation set with a handful of grade-3
    cases, and every metric computed on it is then noise.
  - **IDRiD is never split.** It is the external holdout, opened exactly once, after
    everything is frozen. It does not appear in training or validation under any
    circumstance, and no threshold is ever tuned on it.

APTOS gives one image per patient, so there is no patient-level leakage to guard against
here. If a dataset with multiple images per patient is ever added, the split must move to
grouping by patient — a note, not a claim that we did it.

## Augmentation

Only transforms that produce a *plausible fundus photograph*: flips (a mirrored retina is
just the other eye), rotation (the camera has no canonical orientation), and mild
brightness/contrast jitter (cameras and operators vary). We deliberately do NOT use
aggressive colour jitter or cutout: lesion colour is diagnostic information, and cutout
can delete the only lesion in a mild case and turn a grade-1 label into a lie.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import tensorflow as tf

from src.common.imaging import preprocess_for_model
from src.grading.model import grade_to_levels

AUTOTUNE = tf.data.AUTOTUNE


# ------------------------------------------------------------------ splitting
def stratified_split(paths: list[str], labels: list[int], val_frac: float = 0.15,
                     seed: int = 1337) -> tuple[list, list, list, list]:
    rng = np.random.default_rng(seed)
    paths, labels = np.array(paths), np.array(labels)
    tr_idx, va_idx = [], []
    for g in np.unique(labels):
        idx = np.where(labels == g)[0]
        rng.shuffle(idx)
        n_val = max(int(round(len(idx) * val_frac)), 1)
        va_idx.extend(idx[:n_val].tolist())
        tr_idx.extend(idx[n_val:].tolist())
    rng.shuffle(tr_idx); rng.shuffle(va_idx)
    return (paths[tr_idx].tolist(), labels[tr_idx].tolist(),
            paths[va_idx].tolist(), labels[va_idx].tolist())


def write_split(out: Path, train, train_y, val, val_y) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["path", "grade", "split"])
        for p, g in zip(train, train_y):
            w.writerow([p, g, "train"])
        for p, g in zip(val, val_y):
            w.writerow([p, g, "val"])


def read_aptos(csv_path: Path, image_dir: Path,
               ext: str = ".png") -> tuple[list[str], list[int]]:
    """APTOS train.csv has columns id_code,diagnosis."""
    paths, labels = [], []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            p = image_dir / f"{row['id_code']}{ext}"
            if p.exists():
                paths.append(str(p)); labels.append(int(row["diagnosis"]))
    if not paths:
        raise FileNotFoundError(
            f"no APTOS images found under {image_dir} matching {csv_path}")
    return paths, labels


def read_idrid(csv_path: Path, image_dir: Path,
               ext: str = ".jpg") -> tuple[list[str], list[int]]:
    """IDRiD grading CSV: 'Image name','Retinopathy grade',..."""
    paths, labels = [], []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            name = (row.get("Image name") or row.get("image_name") or "").strip()
            grade = row.get("Retinopathy grade") or row.get("retinopathy_grade")
            if not name or grade is None or grade == "":
                continue
            p = image_dir / f"{name}{ext}"
            if p.exists():
                paths.append(str(p)); labels.append(int(float(grade)))
    if not paths:
        raise FileNotFoundError(f"no IDRiD images found under {image_dir}")
    return paths, labels


# ------------------------------------------------------------------ pipeline
def _load_and_preprocess(path: str, size: int, enhance: bool) -> np.ndarray:
    import cv2
    img = cv2.imread(path.decode() if isinstance(path, bytes) else path)
    if img is None:
        return np.zeros((size, size, 3), np.uint8)
    return preprocess_for_model(img, size, enhance=enhance)


def _augment(x: tf.Tensor, seed: int = 0) -> tf.Tensor:
    x = tf.image.random_flip_left_right(x)
    x = tf.image.random_flip_up_down(x)
    k = tf.random.uniform([], 0, 4, dtype=tf.int32)
    x = tf.image.rot90(x, k)
    x = tf.image.random_brightness(x, 18.0)
    x = tf.image.random_contrast(x, 0.88, 1.12)
    return tf.clip_by_value(x, 0.0, 255.0)


def build_dataset(paths: list[str], labels: list[int], size: int, batch: int,
                  training: bool, enhance: bool = True,
                  shuffle_buffer: int = 512) -> tf.data.Dataset:
    levels = grade_to_levels(np.array(labels))
    ds = tf.data.Dataset.from_tensor_slices((paths, levels))
    if training:
        ds = ds.shuffle(min(shuffle_buffer, len(paths)), reshuffle_each_iteration=True)

    def _map(path, lvl):
        img = tf.numpy_function(
            lambda p: _load_and_preprocess(p, size, enhance).astype("float32"),
            [path], tf.float32)
        img.set_shape((size, size, 3))
        if training:
            img = _augment(img)
        lvl.set_shape((levels.shape[1],))
        return img, lvl

    ds = ds.map(_map, num_parallel_calls=AUTOTUNE)
    return ds.batch(batch).prefetch(AUTOTUNE)


def class_weights_from_levels(labels: list[int]) -> np.ndarray:
    """Per-CUT positive weights for the CORAL loss.

    Each cut k is its own binary problem "is the grade above k?", and each has its own
    imbalance — cut 3 (grade 4 vs the rest) is far rarer than cut 0. A single global class
    weight would be wrong for all four. We return one positive-class weight per cut,
    computed as neg/pos, which is the standard correction.
    """
    lv = grade_to_levels(np.array(labels))
    pos = lv.sum(axis=0)
    neg = len(lv) - pos
    return np.where(pos > 0, neg / np.maximum(pos, 1), 1.0).astype("float32")
