# Cloud Run image for the inference API.
#
# The model is baked into the image rather than fetched at boot: Cloud Run cold-starts
# are already the slowest thing in the demo, and a 90 MB download on first request would
# make the judge's first upload time out. Trade image size for predictable latency.
# --platform is pinned because Cloud Run runs linux/amd64. Building on an Apple Silicon
# laptop otherwise produces an arm64 image that deploys "successfully" and then fails to
# start, which is a 3am problem. It also matters because tensorflow-cpu publishes no
# arm64 Linux wheel at all, so the slim build only resolves on amd64.
ARG TARGETPLATFORM=linux/amd64
FROM --platform=${TARGETPLATFORM} python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=3 \
    OMP_NUM_THREADS=4

# opencv-python-headless still needs libgl/libglib at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-serve.txt .
# --timeout/--retries: the tensorflow-cpu wheel is ~230 MB and this layer is the one that
# fails on a flaky link or under QEMU emulation, where the download crawls and pip's
# 15 s default read timeout trips. A build that dies two thirds of the way through a
# 230 MB download at 3am is the classic hackathon loss, so pay for patience here.
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements-serve.txt

COPY src/ ./src/
COPY artifacts/ ./artifacts/

ENV DR_MODEL_DIR=/app/artifacts/model \
    PORT=8080
EXPOSE 8080

# Single worker on purpose: the TF model is ~90 MB of RAM and Cloud Run's default
# instance is 512 MB-2 GB. Two workers would double that for no throughput gain on a
# screening tool serving a few hundred images a day. Scale with instances, not workers.
# JSON/exec form so uvicorn is PID 1 and receives Cloud Run's SIGTERM directly; the
# sh -c wrapper is only there to expand ${PORT}, which Cloud Run injects at runtime.
CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
