#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 모델 파일을 Google Cloud Storage에 업로드하는 스크립트

사용법:
    python scripts/upload_models_to_gcs.py --bucket-name gpx-hub-ml-models
"""
import argparse
import os
import sys
from pathlib import Path
from google.cloud import storage

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def upload_models_to_gcs(
    bucket_name: str,
    local_dir: Path = Path("ml_models"),
    project_id: str = "gpx-hub-478923"
):
    """
    로컬의 ML 모델 파일들을 GCS 버킷에 업로드합니다.
    
    Args:
        bucket_name: GCS 버킷 이름
        local_dir: 로컬 모델 디렉토리 경로
        project_id: GCP 프로젝트 ID
    """
    if not local_dir.exists():
        print(f"❌ 모델 디렉토리를 찾을 수 없습니다: {local_dir}")
        return
    
    # GCS 클라이언트 생성
    client = storage.Client(project=project_id)
    
    # 버킷 가져오기 또는 생성
    try:
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            print(f"📦 버킷이 없습니다. 생성 중: {bucket_name}")
            bucket = client.create_bucket(bucket_name, location="asia-northeast3")
        else:
            print(f"✅ 버킷 찾음: {bucket_name}")
    except Exception as e:
        print(f"❌ 버킷 접근 실패: {e}")
        return
    
    # .pkl 파일만 업로드
    uploaded = 0
    skipped = 0
    
    for pkl_file in local_dir.rglob("*.pkl"):
        # 상대 경로 계산
        relative_path = pkl_file.relative_to(local_dir)
        blob_name = str(relative_path).replace("\\", "/")  # Windows 경로 변환
        
        blob = bucket.blob(blob_name)
        
        # 이미 존재하는지 확인
        if blob.exists():
            print(f"⏭️  이미 존재: {blob_name}")
            skipped += 1
            continue
        
        # 업로드
        print(f"📤 업로드 중: {blob_name} ({pkl_file.stat().st_size / 1024 / 1024:.2f} MB)")
        blob.upload_from_filename(str(pkl_file))
        uploaded += 1
        print(f"✅ 업로드 완료: {blob_name}")
    
    print(f"\n✅ 완료! 업로드: {uploaded}개, 스킵: {skipped}개")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload ML models to GCS")
    parser.add_argument(
        "--bucket-name",
        required=True,
        help="GCS bucket name (e.g., gpx-hub-ml-models)"
    )
    parser.add_argument(
        "--local-dir",
        default="ml_models",
        help="Local model directory path (default: ml_models)"
    )
    parser.add_argument(
        "--project-id",
        default="gpx-hub-478923",
        help="GCP project ID"
    )
    
    args = parser.parse_args()
    
    upload_models_to_gcs(
        bucket_name=args.bucket_name,
        local_dir=Path(args.local_dir),
        project_id=args.project_id
    )

