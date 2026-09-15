# Cloud spend log

**This build is free-tier only. Target spend: $0.00.**

Training runs on **Kaggle GPU** (free P100/T4, no billing). Hosting is free-tier
(Render/Vercel or equivalent). GCP/Vertex is not part of the current architecture.

| Time | Resource | Rate | Duration | Cost | Running total |
|---|---|---|---|---|---|
| build hour 0 | (none — free tier only) | — | — | $0.00 | $0.00 |

## Standing cost guards

- **No paid cloud resource is provisioned for this build.** Kaggle GPU and free hosting only.
- No hosted **prediction endpoint** is ever created. Inference runs in-process.
  (Also the reason Grad-CAM is possible at all — an endpoint returns logits, not gradients.)
- If a paid resource is ever proposed, state $/hr *before* provisioning and log it here.

## HISTORICAL / ALTERNATIVE ARCHITECTURE — GCP rates

Retained for reference only; not part of the current build. Were we to train on Vertex AI:
`n1-standard-8` + 1× **T4** ≈ **$0.73/hr** in `us-central1` (T4 $0.35 + VM $0.38). A 2-hour
run ≈ **$1.50**. Cap was $60 with a budget alert. Cloud Run `--min-instances=0` except during
a demo window.
