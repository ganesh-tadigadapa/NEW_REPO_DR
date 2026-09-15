"""Requirement #3 — the ICDR 0-4 severity model.

## Why an ordinal head and not a 5-way softmax

The ICDR grades are *ordered*. Softmax cross-entropy treats "predicted 0, truth 4" and
"predicted 3, truth 4" as equally wrong. Clinically the first could blind someone and the
second is a rounding error. Softmax throws away the single most important structural fact
about the label space.

We use **CORAL** (Consistent Rank Logits, Cao et al. 2020): instead of 5 class scores, the
head emits K-1 = 4 cumulative binary probabilities

    p_k = P(grade > k)   for k = 0,1,2,3

from a *single shared* feature projection plus 4 independent bias terms. Sharing the
weights and letting only the biases differ is what guarantees monotonicity:
p_0 >= p_1 >= p_2 >= p_3 always holds, so the model can never output the incoherent
"probably worse than grade 2 but probably not worse than grade 1".

Three things fall out of this for free, and each is worth saying to a judge:

1. **Referable DR is a direct output.** Referable = grade >= 2 = `p_1`. We do not derive
   it by cutting a regression score or by summing softmax bins — it is one number the
   network was explicitly trained to produce, and it has its own tunable threshold. That
   is what lets us hit ">90% sensitivity" as a *decision*, not a hope.
2. **The predicted grade is just the count of exceeded thresholds**, which is naturally
   ordinal and cannot skip a grade.
3. **Per-grade probabilities** come from differencing the cumulative chain.

Backbone is EfficientNetV2-S: strong accuracy per FLOP, which matters because inference
runs on a CPU Cloud Run instance, and it has a clean final conv block for Grad-CAM.
"""
from __future__ import annotations

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

NUM_GRADES = 5
NUM_CUTS = NUM_GRADES - 1
LAST_CONV_LAYER = "top_conv"       # EfficientNetV2-S final conv; the Grad-CAM target


class CoralHead(layers.Layer):
    """Shared-weight ordinal head. Emits NUM_CUTS logits for P(grade > k).

    Weights are created in `build()` rather than `__init__` so that Keras can restore
    them correctly when the model is deserialised. Creating them in `__init__` leaves the
    layer marked built-but-not-actually-built on load, which is the kind of bug that
    surfaces as quietly wrong predictions rather than an exception.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.proj = layers.Dense(1, use_bias=False, name="coral_proj")

    def build(self, input_shape):
        self.proj.build(input_shape)
        # Biases must start in DECREASING order so the cumulative chain begins monotone
        # and roughly matches the prior prevalence of each severity level.
        self.cut_bias = self.add_weight(
            name="coral_cut_bias", shape=(NUM_CUTS,),
            initializer=keras.initializers.Constant([2.0, 0.5, -1.0, -2.5]),
            trainable=True)
        super().build(input_shape)

    def call(self, x):
        return self.proj(x) + self.cut_bias      # (batch, NUM_CUTS)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], NUM_CUTS)

    def get_config(self):
        return super().get_config()


def coral_loss(label_levels, logits):
    """Sum of NUM_CUTS binary cross-entropies against the cumulative label encoding.

    Grade g is encoded as [1]*g + [0]*(NUM_CUTS-g); e.g. grade 2 -> [1,1,0,0], read as
    "grade > 0: yes, grade > 1: yes, grade > 2: no, grade > 3: no".
    """
    label_levels = tf.cast(label_levels, logits.dtype)
    per_cut = tf.nn.sigmoid_cross_entropy_with_logits(labels=label_levels, logits=logits)
    return tf.reduce_mean(tf.reduce_sum(per_cut, axis=-1))


def grade_to_levels(y: np.ndarray) -> np.ndarray:
    """(N,) grades -> (N, NUM_CUTS) cumulative binary encoding."""
    y = np.asarray(y).reshape(-1, 1)
    return (y > np.arange(NUM_CUTS)[None, :]).astype("float32")


def build_model(image_size: int = 512, backbone: str = "efficientnetv2s",
                dropout: float = 0.3, weights: str | None = "imagenet") -> keras.Model:
    inputs = keras.Input(shape=(image_size, image_size, 3), name="image")
    # EfficientNetV2 expects [0,255] and rescales internally.
    if backbone == "efficientnetv2s":
        base = keras.applications.EfficientNetV2S(
            include_top=False, weights=weights, input_tensor=inputs)
    elif backbone == "efficientnetv2b0":       # smaller, for CPU smoke tests
        base = keras.applications.EfficientNetV2B0(
            include_top=False, weights=weights, input_tensor=inputs)
    else:
        raise ValueError(f"unknown backbone {backbone}")
    base.trainable = True

    x = layers.GlobalAveragePooling2D(name="gap")(base.output)
    x = layers.Dropout(dropout, name="head_dropout")(x)
    logits = CoralHead(name="coral")(x)
    model = keras.Model(inputs, logits, name=f"dr_{backbone}_coral")
    model.last_conv_layer = _find_last_conv(base)
    return model


def _find_last_conv(base: keras.Model) -> str:
    for layer in reversed(base.layers):
        if isinstance(layer, layers.Conv2D) or "top_conv" in layer.name:
            return layer.name
    raise RuntimeError("no conv layer found for Grad-CAM")


# ----------------------------------------------------------------- decoding
def logits_to_cumulative(logits: np.ndarray) -> np.ndarray:
    """(N, NUM_CUTS) logits -> monotone cumulative probabilities P(grade > k)."""
    p = 1.0 / (1.0 + np.exp(-np.asarray(logits, dtype=np.float64)))
    # CORAL's shared weights make this monotone by construction, but float error and any
    # future head change could break it, so we enforce it rather than assume it.
    return np.minimum.accumulate(p, axis=-1)


def cumulative_to_per_grade(cum: np.ndarray) -> np.ndarray:
    """P(grade > k) chain -> P(grade == g) for g in 0..4. Rows sum to 1."""
    cum = np.asarray(cum, dtype=np.float64)
    n = cum.shape[0]
    ones = np.ones((n, 1))
    zeros = np.zeros((n, 1))
    upper = np.concatenate([ones, cum], axis=1)        # P(grade > k-1), k=0..4
    lower = np.concatenate([cum, zeros], axis=1)       # P(grade > k)
    probs = np.clip(upper - lower, 0.0, 1.0)
    s = probs.sum(axis=1, keepdims=True)
    return probs / np.maximum(s, 1e-12)


def cumulative_to_grade(cum: np.ndarray, cuts: np.ndarray | list | None = None) -> np.ndarray:
    """Predicted grade = number of cumulative probabilities above their cut point.

    `cuts` defaults to 0.5 each, and is tuned on validation data — this is the knob that
    trades sensitivity against specificity per grade boundary.
    """
    cum = np.asarray(cum)
    if cuts is None:
        cuts = np.full(cum.shape[-1], 0.5)
    cuts = np.asarray(cuts, dtype=np.float64).reshape(1, -1)
    return (cum > cuts).sum(axis=-1).astype(int)


def referable_probability(cum: np.ndarray) -> np.ndarray:
    """P(grade >= 2) — read straight off the second cumulative output."""
    return np.asarray(cum)[:, 1]
