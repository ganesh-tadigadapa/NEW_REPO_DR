"""SELF-CONTAINED Kaggle trainer for the SIH26038 DR grading model.

NO GITHUB REQUIRED. This file carries the project's trainer source inside it as a
base64 tarball, so you can paste it into one Kaggle cell and run. That removes the
"push the repo somewhere Kaggle can reach" step entirely.

HOW TO USE (about 3 minutes of clicking, then ~2 hours unattended)
------------------------------------------------------------------
  1. kaggle.com -> Create -> New Notebook
  2. Session options (right-hand panel):
       Accelerator -> GPU P100      <- REQUIRED, CPU will take over a day
       Internet    -> ON
  3. Add Input -> Competitions -> search "APTOS 2019 Blindness Detection" -> Add
     (If it asks you to accept the competition rules, accept them.)
  4. Paste this ENTIRE file into one cell.
  5. Run All. Then LEAVE IT. Do not sit and watch the logs.
  6. When it finishes, open the Output tab and download `artifacts_model.zip`.
  7. Locally: unzip it over `artifacts/model/`, restart the API, and the real model
     is live.

WHAT IT PRODUCES
----------------
  artifacts/model/model.keras          the trained weights
  artifacts/model/split.csv            the exact train/val split (stratified, seeded)
  artifacts/model/run.json             config + provenance of this run
  artifacts/model/history.json         per-epoch loss curves
  artifacts/model/val_logits.npz       validation logits, for calibration later
  artifacts_model.zip                  all of the above, zipped for download

WHAT IT DOES *NOT* DO
---------------------
  It does not calibrate, tune thresholds, or touch any external holdout. Those run
  locally afterwards, in that order, per docs/STATE.md. Keeping them out of here is
  deliberate: thresholds tuned inside the training run would be tuned on data the
  model saw.

EXPECTED RESULT
---------------
  Roughly QWK 0.85-0.90 and referable sensitivity around 0.90 on the validation split.
  If you see QWK 1.0, something is wrong -- that is what the synthetic demo model
  scored, and it means the run did not read the real data.
"""

import base64, io, os, subprocess, sys, tarfile, zipfile
from pathlib import Path

SRC_TARBALL_B64 = """
H4sIADijpmoC/+19/XLbRrbn/M2n6GIqG1BDwiQlOTazyr2KrDiqkS2PpCQ1V6uCQRIkEYEAAoCSGK+39iG2ah9o32SfZM/vnG6g
wQ/HnkmyWxuyEosE+vP06dPnu90n7pN/f+M/fhf44yD7y+/y6cpn299ud/+g+o7nvW6/1/+LevzLH/BZ5IWfUfd/+XN++s/UvAjn
wVHvy2fPe/vPnva77pfdPi3JYeMvu8//9588Gz3xvDAOC89z0+Xvtv+fHsge//Lpoez1fn3P9w77h71ub7//Jb3v7ff2D/+iun/k
/p/6cZDPPgCowp9M/v9bf3dH/3f0f53+H/YOn+7o/5+E/o+S+TyJf79j4NPp/8FBf0f//0T0f3+d/vd29P8Pof9f1uj/8/6zA7f3
rN9/tiP/fzb6P0riSTj9HYSAX6H/h1/2+4b+Hxziee+gd9jb0f8/4tNsNq/CeBoFKk8W2ShQyUQV2aKYqUmSKUIJmndc5Cqf+Vkw
Vv4oS/JczZPxIgpyt9E4jpfFjBpQvvppMZ4Gah5OZ4Xy8zvVfJgFWaDG4VgVM79Q8WI+DNDmPFCTLJn/W1P5w2RRqCi8D3LFhR9C
6tlvACODuFC5v0Tbs+RBhYV68HM1miV5ELvqepbRciXROFeTsChoaGhSjf3CVzRSFSV0nsnDxlsquoiK/MnbtoqDexoDTWY8SlDg
f//3/6HyIFBvf174UVgsvaJs2Gm9dRsEnwa37HmTRbHIAs9T4TxNMppjHCeFX4QEo0ZDP/spT2LzPckb5ZhGkZ/nNEn9qnzUJkiN
w1EhJVO/mEXh0JR6Qz8bjcvTNxfe5cXFtTriJw6NJIxoHC2XRppE94HTclOaMy3TTf+Wyl99f3595b04u6QaVe0nqqnh0Gy8OL4+
3lQA42o2jq+uTjc3gEmgfuPF2dXJ+fHZq1MUaV6NsiCIsVJFFvqEBH44dtXrhGBEy+9P4yQvwpEaB/fhKHCp+meq8y9+1NnJi0uV
j/woaOCrd378zen5FY3mXUPRpztQzdeJenHZbPPvHv1+FUZj9fpN+ayPZ4QFmV8E9vN9en4FPKk9PaCnb7IkCieoQCgrjb+nyVwG
eDaM8IhGMM0I91Rf0QZ6SLI8ALaGtPY57QPaYCnXT2I/IoiMwpy+ygaZ+4TIGe2qy9NvTy+Pvzk/9V6dvfZeXh6/OKVm+78J3MI5
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
"""

WORK = Path("/kaggle/working")
REPO = WORK / "repo"


def unpack_source():
    REPO.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode("".join(SRC_TARBALL_B64.split()))
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        tf.extractall(REPO)
    sys.path.insert(0, str(REPO))
    print(f"unpacked trainer source into {REPO}")
    for p in sorted(REPO.rglob("*.py")):
        print("   ", p.relative_to(REPO))


def find_aptos():
    """Locate the APTOS competition data wherever Kaggle mounted it.

    Kaggle does not always mount competition data at the obvious path. Depending on how
    the kernel was created it can land at /kaggle/input/<slug>/ OR nested under
    /kaggle/input/competitions/<slug>/. Measured: a kernel pushed via the API with
    competition_sources mounts it at /kaggle/input/competitions/. So search for the
    train.csv + train_images pair instead of guessing a path.
    """
    base = Path("/kaggle/input")
    candidates = [
        base / "aptos2019-blindness-detection",
        base / "competitions" / "aptos2019-blindness-detection",
        *sorted(base.glob("*aptos*")),
        *sorted(base.glob("competitions/*aptos*")),
    ]
    for r in candidates:
        csv, imgs = r / "train.csv", r / "train_images"
        if csv.exists() and imgs.is_dir():
            print(f"found APTOS at {r}")
            return csv, imgs
    for csv in base.rglob("train.csv"):
        imgs = csv.parent / "train_images"
        if imgs.is_dir():
            print(f"found APTOS by search at {csv.parent}")
            return csv, imgs
    listing = "\n".join(f"  {q}" for q in sorted(base.rglob("*"))[:40])
    raise SystemExit(
        "APTOS data not found under /kaggle/input.\n"
        "Add it with: Add Input -> Competitions -> 'APTOS 2019 Blindness Detection'.\n"
        f"What IS mounted right now:\n{listing or '  (nothing)'}")

def main():
    unpack_source()
    csv, imgs = find_aptos()
    n = sum(1 for _ in open(csv)) - 1
    print(f"\nAPTOS: {csv}  ({n} labelled rows)")
    print(f"images: {imgs}")

    out = WORK / "artifacts" / "model"
    out.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "src.grading.train",
           "--aptos-csv", str(csv),
           "--aptos-images", str(imgs),
           "--image-ext", ".png",
           "--out", str(out),
           "--run-id", "aptos-kaggle-run1",
           "--epochs", "12",
           "--batch", "16",
           "--image-size", "512",
           "--backbone", "efficientnetv2s"]
    print("\n" + " ".join(cmd) + "\n", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode != 0:
        raise SystemExit(f"training failed with exit code {r.returncode}")

    zpath = WORK / "artifacts_model.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out.parent))
    mb = zpath.stat().st_size / 1e6
    print(f"\nDONE. Download {zpath.name} ({mb:.1f} MB) from the Output tab.")
    print("Then unzip it over artifacts/model/ locally and restart the API.")


main()
