#!/usr/bin/env bash
# Deploy the API to Cloud Run. Run this on hour 1 with no model, not on hour 30.
#
#   ./scripts/deploy_cloudrun.sh
#
# Requires: an OPEN billing account on the project (see docs/BLOCKERS.md).
set -euo pipefail

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${SERVICE_NAME:-dr-api}"
REPO="${AR_REPO:-dr}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}"

echo "project=${PROJECT} region=${REGION} service=${SERVICE}"
echo "COST: Cloud Run scales to zero. With --min-instances=0 the idle cost is \$0."
echo "      Set --min-instances=1 ONLY for the demo window, then put it back."

gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
    cloudbuild.googleapis.com --project "${PROJECT}"

gcloud artifacts repositories describe "${REPO}" --location "${REGION}" \
    --project "${PROJECT}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPO}" --repository-format=docker \
    --location "${REGION}" --project "${PROJECT}" \
    --description "DR screening images"

# Cloud Build runs on amd64, which is what Cloud Run needs. Building locally on an
# Apple Silicon machine and pushing would produce an arm64 image that cannot start.
gcloud builds submit --tag "${IMAGE}" --project "${PROJECT}"

gcloud run deploy "${SERVICE}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --project "${PROJECT}" \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 120 \
    --concurrency 4 \
    --min-instances 0 \
    --max-instances 4 \
    --set-env-vars "CORS_ORIGINS=*"

URL=$(gcloud run services describe "${SERVICE}" --region "${REGION}" \
        --project "${PROJECT}" --format 'value(status.url)')
echo
echo "LIVE: ${URL}"
echo "      ${URL}/health"
echo
echo "Set NEXT_PUBLIC_API_BASE=${URL} in Vercel, then redeploy the frontend."
