#!/bin/bash
# Cloud Run 배포 스크립트
# 로컬에서 Docker 이미지를 빌드하고 Cloud Run에 배포합니다.

set -e

PROJECT_ID="gpx-hub-478923"
SERVICE_NAME="ghostx-fastapi"
REGION="asia-northeast3"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🔨 Building Docker image..."
docker build -t ${IMAGE_NAME} .

echo "📤 Pushing image to Google Container Registry..."
docker push ${IMAGE_NAME}

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10

echo "✅ Deployment complete!"

