# Deployment

## Why not Render free tier

**Measured, not assumed:** the API holds **1021 MB RSS** after one inference
(TensorFlow runtime + the 234 MB EfficientNetV2-S model). Render's free tier is
**512 MB**. It would OOM on the judge's first upload.

| Option | RAM | Cost | Verdict |
|---|---|---|---|
| Render free | 512 MB | $0 | ❌ OOM |
| Render Standard | 2 GB | $25/mo | ✅ works, costs money |
| Fly.io free | 256 MB shared | $0 | ❌ OOM |
| **Hugging Face Spaces (CPU basic)** | **16 GB** | **$0** | ✅ **recommended** |

Hugging Face Spaces needs no credit card, supports Docker, and is designed for
public model demos. The app must listen on **port 7860**.

## Backend → Hugging Face Spaces

1. Create the Space: <https://huggingface.co/new-space> → SDK **Docker** → Blank →
   visibility **Public**.
2. Install the CLI and log in (needs a WRITE token from
   <https://huggingface.co/settings/tokens>):

   ```bash
   pip install -U "huggingface_hub[cli]"
   hf auth login
   ```

3. Push. The model is 234 MB, so it goes through git-lfs:

   ```bash
   cd /Users/ganesh/Downloads/SIH_PROJECT
   git clone https://huggingface.co/spaces/<your-username>/<space-name> /tmp/dr-space
   cd /tmp/dr-space
   git lfs install
   git lfs track "*.keras"

   mkdir -p src artifacts/model results/quality_gate results/active
   cp -r /Users/ganesh/Downloads/SIH_PROJECT/src/* src/
   cp -r /Users/ganesh/Downloads/SIH_PROJECT/artifacts/model/* artifacts/model/
   cp /Users/ganesh/Downloads/SIH_PROJECT/results/quality_gate/thresholds.json results/quality_gate/
   cp /Users/ganesh/Downloads/SIH_PROJECT/results/active/metrics.json results/active/
   cp /Users/ganesh/Downloads/SIH_PROJECT/requirements-serve.txt .
   cp /Users/ganesh/Downloads/SIH_PROJECT/deploy/Dockerfile.hf Dockerfile

   git add -A && git commit -m "DR screening API" && git push
   ```

4. Watch the build in the Space's **Logs** tab. First build takes ~5–10 min
   (TensorFlow is a large wheel). When it is live:

   ```bash
   curl https://<your-username>-<space-name>.hf.space/health
   ```

   Expect `"model_id":"aptos-kaggle-run1"` and `"synthetic_demo_model":false`.

## Frontend → Vercel

1. Push this repo to GitHub (the frontend needs a git source; the backend did not).
2. <https://vercel.com/new> → import the repo → **Root Directory: `web`**.
3. Environment variable:

   ```
   NEXT_PUBLIC_API_BASE = https://<your-username>-<space-name>.hf.space
   ```

   `web/lib/api.ts` reads it and falls back to `http://localhost:8080`, so this is the
   only setting that matters.
4. Deploy. Open the URL and run the seven bundled samples.

## Cold starts

A free Space sleeps after ~48 h idle and takes ~30 s to wake. **Open the URL a few
minutes before demoing.** Do not let a judge be the one who wakes it.
