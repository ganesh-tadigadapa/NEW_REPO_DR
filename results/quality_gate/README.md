# Quality-gate thresholds

`thresholds.json` is **deliberately absent**. Until the 200-image human labelling session
happens, the gate runs on the documented defaults in `src/common/config.py` and reports
`thresholds_fitted: false` in every API response and on every report page.

`thresholds.SYNTHETIC-DO-NOT-USE.json` is a fit against 13 synthetic images. It is kept
only as proof the fitting pipeline runs end to end. It must never be promoted to
`thresholds.json`: 13 images with almost no spread produce a decision boundary a
rounding error wide, which is why the first fit rejected a 768px render of an image it
had accepted at 1024px.

## To fit them for real

1. Export ~200 images spanning good and bad quality.
2. Have a clinician (or the lead) label each `1` = would grade this, `0` = would ask for a retake.
3. Save as CSV with columns `path,gradeable`.
4. Run:

```bash
python scripts/compare_focus_metrics.py --labels data/raw/quality_labels.csv
python scripts/fit_quality_thresholds.py  --labels data/raw/quality_labels.csv \
    --provenance "labelled by <name>, <date>, <how>"
```

That writes `thresholds.json`, and the gate picks it up automatically on the next API
start. The combined-gate agreement in that file is a reportable number.
