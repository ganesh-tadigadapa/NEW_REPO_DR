"""Trainer. Runs unmodified as a Vertex AI custom job, a Kaggle notebook, or locally.

    python -m src.grading.train \
        --aptos-csv data/raw/aptos/train.csv \
        --aptos-images data/raw/aptos/train_images \
        --epochs 12 --batch 16 --image-size 512 --run-id run-20260911-a1

Cloud-agnostic by construction: it reads local paths, and `--gcs-out` (if given) copies
the artefacts up at the end. Nothing in here imports a Google library, which is precisely
why the Kaggle fallback cost us no code changes when the GCP billing account turned out
to be closed.

Everything a reported number depends on is written next to the weights:
`run.json` (the full config + git commit), `history.json`, `thresholds.json`,
`temperature.json`. A metric whose run cannot be reproduced is not a metric.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aptos-csv", required=True)
    ap.add_argument("--aptos-images", required=True)
    ap.add_argument("--image-ext", default=".png")
    ap.add_argument("--out", default="artifacts/model")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--image-size", type=int, default=512)
    ap.add_argument("--backbone", default="efficientnetv2s")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--head-only-epochs", type=int, default=1,
                    help="warm up the head with the backbone frozen")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--no-enhance", action="store_true",
                    help="ABLATION: train on raw crops without Ben-Graham/CLAHE")
    ap.add_argument("--no-class-weights", action="store_true",
                    help="ABLATION: disable per-cut positive weighting")
    ap.add_argument("--limit", type=int, default=0, help="debug: cap dataset size")
    ap.add_argument("--gcs-out", default="", help="optional gs:// prefix to copy to")
    args = ap.parse_args()

    import tensorflow as tf
    from src.grading.data import (build_dataset, class_weights_from_levels,
                                  read_aptos, stratified_split, write_split)
    from src.grading.model import build_model, coral_loss

    run_id = args.run_id or f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    print(f"[{run_id}] GPUs visible: {tf.config.list_physical_devices('GPU')}")

    paths, labels = read_aptos(Path(args.aptos_csv), Path(args.aptos_images),
                               ext=args.image_ext)
    if args.limit:
        paths, labels = paths[:args.limit], labels[:args.limit]
    tr_p, tr_y, va_p, va_y = stratified_split(paths, labels, args.val_frac, args.seed)
    write_split(out / "split.csv", tr_p, tr_y, va_p, va_y)
    print(f"[{run_id}] train={len(tr_p)} val={len(va_p)} "
          f"train_dist={np.bincount(tr_y, minlength=5).tolist()}")

    enhance = not args.no_enhance
    train_ds = build_dataset(tr_p, tr_y, args.image_size, args.batch, True, enhance)
    val_ds = build_dataset(va_p, va_y, args.image_size, args.batch, False, enhance)

    pos_w = (np.ones(4, "float32") if args.no_class_weights
             else class_weights_from_levels(tr_y))
    print(f"[{run_id}] per-cut positive weights: {pos_w.round(3).tolist()}")
    pos_w_t = tf.constant(pos_w)

    def weighted_coral(y_true, y_pred):
        y_true = tf.cast(y_true, y_pred.dtype)
        per_cut = tf.nn.weighted_cross_entropy_with_logits(
            labels=y_true, logits=y_pred, pos_weight=tf.cast(pos_w_t, y_pred.dtype))
        return tf.reduce_mean(tf.reduce_sum(per_cut, axis=-1))

    loss_fn = coral_loss if args.no_class_weights else weighted_coral

    model = build_model(args.image_size, args.backbone)
    last_conv = model.last_conv_layer

    # ---- stage 1: warm up the head so random head gradients don't wreck the backbone
    history = {}
    if args.head_only_epochs > 0:
        for layer in model.layers:
            if layer.name not in ("coral", "head_dropout", "gap"):
                layer.trainable = False
        model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss=loss_fn)
        h = model.fit(train_ds, validation_data=val_ds,
                      epochs=args.head_only_epochs, verbose=2)
        history["warmup"] = {k: [float(x) for x in v] for k, v in h.history.items()}

    # ---- stage 2: fine-tune everything
    for layer in model.layers:
        layer.trainable = True
    model.compile(optimizer=tf.keras.optimizers.Adam(args.lr), loss=loss_fn)

    ckpt = out / "model.keras"
    cbs = [
        tf.keras.callbacks.ModelCheckpoint(str(ckpt), monitor="val_loss",
                                           save_best_only=True, verbose=1),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.3,
                                             patience=2, min_lr=1e-6, verbose=1),
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=4,
                                         restore_best_weights=True, verbose=1),
        tf.keras.callbacks.CSVLogger(str(out / "training_log.csv")),
    ]
    t0 = time.time()
    h = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs,
                  callbacks=cbs, verbose=2)
    train_seconds = time.time() - t0
    history["finetune"] = {k: [float(x) for x in v] for k, v in h.history.items()}

    if not ckpt.exists():
        model.save(str(ckpt))

    # ---- dump validation logits: everything downstream (threshold tuning, temperature
    # scaling, calibration curves) is fitted from THIS file, never from the holdout.
    print(f"[{run_id}] writing validation logits")
    val_logits, val_levels = [], []
    for xb, yb in val_ds:
        val_logits.append(model.predict(xb, verbose=0))
        val_levels.append(yb.numpy())
    val_logits = np.concatenate(val_logits); val_levels = np.concatenate(val_levels)
    np.savez(out / "val_logits.npz", logits=val_logits, levels=val_levels,
             grades=val_levels.sum(axis=1).astype(int), paths=np.array(va_p))

    cfg = {
        "run_id": run_id,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "train_seconds": round(train_seconds, 1),
        "image_size": args.image_size,
        "backbone": args.backbone,
        "last_conv_layer": last_conv,
        "epochs_requested": args.epochs,
        "batch": args.batch,
        "lr": args.lr,
        "enhance": enhance,
        "class_weights": (None if args.no_class_weights else pos_w.tolist()),
        "n_train": len(tr_p), "n_val": len(va_p),
        "train_grade_dist": np.bincount(tr_y, minlength=5).tolist(),
        "val_grade_dist": np.bincount(va_y, minlength=5).tolist(),
        "seed": args.seed,
        "tensorflow": tf.__version__,
        "argv": vars(args),
    }
    (out / "run.json").write_text(json.dumps(cfg, indent=2))
    (out / "history.json").write_text(json.dumps(history, indent=2))
    print(f"[{run_id}] done in {train_seconds/60:.1f} min -> {out}")

    if args.gcs_out:
        subprocess.run(["gsutil", "-m", "cp", "-r", str(out),
                        args.gcs_out.rstrip("/") + f"/{run_id}"], check=False)


if __name__ == "__main__":
    main()
