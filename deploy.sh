#!/bin/bash
# Deploy FaqSmartBuddy ADK Agent to Google Cloud Run
set -e

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/FaqAssistant/.env"

# ── Load environment variables ────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo "❌  .env not found at $ENV_FILE"
  echo "    Make sure FaqAssistant/.env exists with required variables."
  exit 1
fi

# Read environment variables from .env
eval "$(grep -E '^(GOOGLE_API_KEY|GOOGLE_PROJECT_ID|GOOGLE_GENAI_USE_VERTEXAI)=' "$ENV_FILE" | grep -v '^#')"

# Cloud Run deployment config
PROJECT_ID="${GOOGLE_PROJECT_ID:?GOOGLE_PROJECT_ID not set in .env}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-faqsmartbuddy-agent}"
GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-0}"

# ── Validate required vars ────────────────────────────────────────────────────
missing=()
[[ -z "$GOOGLE_API_KEY" ]] && missing+=("GOOGLE_API_KEY")
[[ -z "$GOOGLE_PROJECT_ID" ]] && missing+=("GOOGLE_PROJECT_ID")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "❌  Required vars missing: ${missing[*]}"
  echo "    Make sure they are set in $ENV_FILE"
  exit 1
fi

# ── Build environment variables string ────────────────────────────────────────
ENV_VARS="GOOGLE_API_KEY=$GOOGLE_API_KEY,GOOGLE_PROJECT_ID=$GOOGLE_PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=$GENAI_USE_VERTEXAI"

# ── Confirm deployment ────────────────────────────────────────────────────────
echo ""
echo "🚀 Ready to deploy FaqSmartBuddy to Google Cloud Run"
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Service: $SERVICE_NAME"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Deployment cancelled."
  exit 0
fi

# ── Deploy ────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Deploying to Cloud Run…"
echo "   (Cloud Build will build the Docker image — no local Docker needed)"
echo ""

gcloud run deploy "$SERVICE_NAME" \
  --source "$SCRIPT_DIR" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --set-env-vars "$ENV_VARS" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 3 \
  --allow-unauthenticated

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Your service is available at:"
gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format 'value(status.url)'
echo ""

