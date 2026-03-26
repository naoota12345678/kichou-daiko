#!/bin/bash
# Cloud Run デプロイスクリプト
# 使い方: bash deploy.sh

PROJECT_ID="dentyo-80203"
SERVICE_NAME="scraper-api"
REGION="asia-northeast1"

echo "=== Building & deploying to Cloud Run ==="

gcloud run deploy $SERVICE_NAME \
  --project $PROJECT_ID \
  --region $REGION \
  --source . \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --concurrency 3 \
  --min-instances 0 \
  --max-instances 10 \
  --session-affinity \
  --set-env-vars "ALLOWED_ORIGINS=https://dentyo.romu.ai" \
  --set-env-vars "API_BASE_URL=https://scraper-api-274739552175.asia-northeast1.run.app"

echo ""
echo "=== Deploy complete ==="
gcloud run services describe $SERVICE_NAME \
  --project $PROJECT_ID \
  --region $REGION \
  --format "value(status.url)"
