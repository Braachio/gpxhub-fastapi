# PowerShell 스크립트: ML 모델 파일을 GCS에 업로드
# 사용법: .\scripts\upload_models_to_gcs.ps1 -BucketName "gpx-hub-ml-models"

param(
    [Parameter(Mandatory=$true)]
    [string]$BucketName,
    
    [string]$LocalDir = "ml_models",
    [string]$ProjectId = "gpx-hub-478923"
)

Write-Host "📤 ML 모델 파일을 GCS에 업로드합니다..." -ForegroundColor Cyan
Write-Host "버킷: $BucketName" -ForegroundColor Yellow
Write-Host "로컬 디렉토리: $LocalDir" -ForegroundColor Yellow

python scripts/upload_models_to_gcs.py --bucket-name $BucketName --local-dir $LocalDir --project-id $ProjectId

