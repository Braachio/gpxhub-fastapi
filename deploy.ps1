# Cloud Run 배포 스크립트 (PowerShell)
# 로컬에서 Docker 이미지를 빌드하고 Cloud Run에 배포합니다.

$PROJECT_ID = "gpx-hub-478923"
$SERVICE_NAME = "ghostx-fastapi"
$REGION = "asia-northeast3"
$IMAGE_NAME = "gcr.io/$PROJECT_ID/$SERVICE_NAME"

Write-Host "🔨 Building Docker image..." -ForegroundColor Cyan
docker build -t $IMAGE_NAME .

Write-Host "📤 Pushing image to Google Container Registry..." -ForegroundColor Cyan
docker push $IMAGE_NAME

Write-Host "🚀 Deploying to Cloud Run..." -ForegroundColor Cyan
gcloud run deploy $SERVICE_NAME `
  --image $IMAGE_NAME `
  --platform managed `
  --region $REGION `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 2 `
  --timeout 300 `
  --max-instances 10

Write-Host "✅ Deployment complete!" -ForegroundColor Green

