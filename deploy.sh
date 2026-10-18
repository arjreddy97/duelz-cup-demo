#!/usr/bin/env bash
# Deploy to Cloud Run (builds from source with Cloud Build).
#
# The Gemini key is read from Secret Manager (preferred). Create it once with:
#   printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
#       --data-file=- --project duelz-play
# and grant the Cloud Run runtime service account roles/secretmanager.secretAccessor.
#
# Fallback without Secret Manager (less safe: the key becomes a plain env var
# visible in the service config): USE_ENV_KEY=1 GEMINI_API_KEY=... ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

PROJECT=duelz-play
REGION=us-central1
SERVICE=duelz-cup-demo
SECRET=${GEMINI_SECRET_NAME:-gemini-api-key}

# max-instances=1 keeps the in-memory rate limits global; concurrency covers the
# streaming connections. Live runs are also capped per hour and per day in-app.
COMMON=(--source . --region "$REGION" --project "$PROJECT"
        --allow-unauthenticated --max-instances 1 --concurrency 40
        --memory 2Gi --cpu 2 --timeout 300)

if [ "${USE_ENV_KEY:-0}" = "1" ]; then
  : "${GEMINI_API_KEY:?set GEMINI_API_KEY in your shell first}"
  gcloud run deploy "$SERVICE" "${COMMON[@]}" \
    --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY}"
else
  gcloud run deploy "$SERVICE" "${COMMON[@]}" \
    --set-secrets "GEMINI_API_KEY=${SECRET}:latest"
fi
