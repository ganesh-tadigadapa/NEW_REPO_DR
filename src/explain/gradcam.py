"""Requirement #4a — Grad-CAM, and the measurement that makes it defensible.

## What we explain

With a CORAL head there is no "class logit" to differentiate — there are four cumulative
logits. We explain **the referable decision**, i.e. the logit for P(grade >= 2), because
that is the output the clinic actually acts on. Explaining a softmax class score would
tell a health worker why the model said "grade 3 rather than grade 2", which is not the
question anyone is asking. This is a deliberate choice and a good answer to give.

## Why this can't run on a managed prediction endpoint

Grad-CAM needs the gradient of an output with respect to an intermediate activation. A
managed endpoint returns the output tensor and nothing else. This is the concrete reason
the model is loaded in-process inside Cloud Run rather than behind Vertex Prediction —
the explainability requirement makes the fashionable architecture impossible. It also
happens to be cheaper.

## Why we also measure it

Grad-CAM is well known to be unreliable, and "here is a pretty heatmap" is not evidence.
`attribution_mass_in_masks` computes what fraction of the heatmap's total attention falls
inside ground-truth lesion annotations, against a random-attribution control. That turns
explainability from a screenshot into a number with a baseline — see
`scripts/eval_explainability.py`.
"""
from __future__ import annotations

import cv2
import numpy as np
import tensorflow as tf

REFERABLE_CUT_INDEX = 1        # logit for P(grade > 1) == P(grade >= 2) == referable


def _grad_model(model: tf.keras.Model, last_conv_layer: str):
    conv = model.get_layer(last_conv_layer)
    return tf.keras.Model(model.inputs, [conv.output, model.output])


def gradcam(model: tf.keras.Model, image_batch: np.ndarray, last_conv_layer: str,
            cut_index: int = REFERABLE_CUT_INDEX) -> np.ndarray:
    """Returns a (H, W) heatmap in [0,1] at the conv layer's resolution.

    Standard Grad-CAM: weight each feature map by the mean gradient of the target logit
    w.r.t. that map, sum, ReLU (we only want evidence *for* the decision, not against),
    normalise.
    """
    gm = _grad_model(model, last_conv_layer)
    x = tf.convert_to_tensor(image_batch, dtype=tf.float32)
    with tf.GradientTape() as tape:
        conv_out, logits = gm(x, training=False)
        tape.watch(conv_out)
        target = logits[:, cut_index]
    grads = tape.gradient(target, conv_out)
    if grads is None:
        raise RuntimeError("no gradient reached the conv layer — wrong layer name?")
    weights = tf.reduce_mean(grads, axis=(1, 2), keepdims=True)      # (B,1,1,C)
    cam = tf.reduce_sum(conv_out * weights, axis=-1)                  # (B,H,W)
    cam = tf.nn.relu(cam).numpy()[0]
    if cam.max() > cam.min():
        cam = (cam - cam.min()) / (cam.max() - cam.min())
    else:
        cam = np.zeros_like(cam)
    return cam


def gradcam_plus_plus(model: tf.keras.Model, image_batch: np.ndarray,
                      last_conv_layer: str, cut_index: int = REFERABLE_CUT_INDEX) -> np.ndarray:
    """Grad-CAM++: pixel-wise positive weights. Localises *multiple* small lesions better
    than Grad-CAM, which tends to blob onto one region — and DR is a multi-lesion disease,
    so this is a substantive difference here, not a nicety.
    """
    gm = _grad_model(model, last_conv_layer)
    x = tf.convert_to_tensor(image_batch, dtype=tf.float32)
    with tf.GradientTape() as t3:
        with tf.GradientTape() as t2:
            with tf.GradientTape() as t1:
                conv_out, logits = gm(x, training=False)
                for t in (t1, t2, t3):
                    t.watch(conv_out)
                score = tf.exp(logits[:, cut_index])
            g1 = t1.gradient(score, conv_out)
        g2 = t2.gradient(g1, conv_out)
    g3 = t3.gradient(g2, conv_out)

    global_sum = tf.reduce_sum(conv_out, axis=(1, 2), keepdims=True)
    denom = 2.0 * g2 + global_sum * g3
    denom = tf.where(tf.abs(denom) > 1e-8, denom, tf.ones_like(denom))
    alpha = g2 / denom
    weights = tf.reduce_sum(alpha * tf.nn.relu(g1), axis=(1, 2), keepdims=True)
    cam = tf.reduce_sum(conv_out * weights, axis=-1)
    cam = tf.nn.relu(cam).numpy()[0]
    if cam.max() > cam.min():
        cam = (cam - cam.min()) / (cam.max() - cam.min())
    else:
        cam = np.zeros_like(cam)
    return cam


# ------------------------------------------------------------------ rendering
def upsample(cam: np.ndarray, size: int) -> np.ndarray:
    return cv2.resize(cam, (size, size), interpolation=cv2.INTER_CUBIC).clip(0, 1)


def colourise(cam: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)


def overlay(bgr: np.ndarray, cam: np.ndarray, alpha: float = 0.40,
            mask: np.ndarray | None = None) -> np.ndarray:
    """Heatmap over the fundus image. `mask` blacks out the non-retina surround so the
    heatmap can't appear to 'light up' the border."""
    cam_up = upsample(cam, bgr.shape[0])
    if mask is not None:
        cam_up = cam_up * mask.astype(np.float32)
    heat = colourise(cam_up)
    out = cv2.addWeighted(heat, alpha, bgr, 1 - alpha, 0)
    if mask is not None:
        out[~mask] = 0
    return out


# ------------------------------------------------------------------ measurement
def attribution_mass_in_masks(cam: np.ndarray, lesion_mask: np.ndarray) -> float:
    """Fraction of total attention that lands inside annotated lesions.

    This is Table 3 in docs/BENCHMARKS.md. Interpretation needs the control below: on a
    typical fundus image lesions cover a tiny fraction of the retina, so a *random*
    heatmap scores well above zero. The number only means something as a ratio to that.
    """
    cam_up = upsample(cam, lesion_mask.shape[0])
    total = float(cam_up.sum())
    if total <= 0:
        return 0.0
    return float(cam_up[lesion_mask > 0].sum() / total)


def random_attribution_control(lesion_mask: np.ndarray, retina_mask: np.ndarray,
                               seed: int = 0) -> float:
    """The honest baseline: what a *uniform* heatmap over the retina would score.

    Equivalently, the fraction of retina area that is lesion. If Grad-CAM does not beat
    this by a wide margin, the heatmap is decorative and we should say so.
    """
    r = retina_mask > 0
    if r.sum() == 0:
        return 0.0
    return float(((lesion_mask > 0) & r).sum() / r.sum())


def attention_summary(cam: np.ndarray, lesion_raw: dict, disc: dict, fovea: dict,
                      size: int) -> str:
    """One plain-English sentence for the UI and the PDF. No numbers we can't back."""
    from src.segment.structures import quadrant_of
    cam_up = upsample(cam, size)
    if cam_up.max() <= 0:
        return "The model produced no localised attention for this image."
    ys, xs = np.where(cam_up >= max(0.7 * cam_up.max(), 1e-6))
    if len(ys) == 0:
        return "Attention was diffuse rather than focused on a specific region."
    cy, cx = float(ys.mean()), float(xs.mean())
    quad = quadrant_of(cx, cy, disc, fovea)
    names = {"ST": "superotemporal", "SN": "superonasal",
             "IT": "inferotemporal", "IN": "inferonasal"}
    # how many detected lesions sit under the hot region
    hot = cam_up >= max(0.7 * cam_up.max(), 1e-6)
    n = 0
    for blobs in lesion_raw.values():
        for b in blobs:
            y, x = int(b["cy"]), int(b["cx"])
            if 0 <= y < size and 0 <= x < size and hot[y, x]:
                n += 1
    where = f"Attention is concentrated in the {names[quad]} quadrant"
    if n:
        return f"{where}, co-located with {n} detected lesion{'s' if n != 1 else ''}."
    return (f"{where}, but no classically-detected lesion lies under it — "
            "treat this explanation with caution and review the image.")
