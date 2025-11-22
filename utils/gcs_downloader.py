"""
Google Cloud Storage에서 ML 모델 파일을 다운로드하는 유틸리티
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage not installed. GCS download will be disabled.")


def download_models_from_gcs(
    bucket_name: Optional[str] = None,
    local_dir: Path = Path("/app/ml_models"),
    force_download: bool = False
) -> bool:
    """
    Cloud Storage에서 ML 모델 파일들을 다운로드합니다.
    
    Args:
        bucket_name: GCS 버킷 이름 (환경 변수 GCS_MODEL_BUCKET에서 가져옴)
        local_dir: 로컬 저장 디렉토리
        force_download: 이미 파일이 있어도 다시 다운로드할지 여부
    
    Returns:
        성공 여부
    """
    if not GCS_AVAILABLE:
        logger.warning("GCS not available, skipping model download")
        return False
    
    bucket_name = bucket_name or os.getenv("GCS_MODEL_BUCKET")
    if not bucket_name:
        logger.warning("⚠️ GCS_MODEL_BUCKET not set, skipping GCS download")
        return False
    
    logger.info(f"📥 Starting GCS download from bucket: {bucket_name}")
    
    try:
        logger.info(f"🔗 Connecting to GCS...")
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # 버킷 존재 확인
        if not bucket.exists():
            logger.error(f"❌ Bucket does not exist: {bucket_name}")
            return False
        
        logger.info(f"✅ Bucket found: {bucket_name}")
        
        # 다운로드할 파일 목록 (pre, post 모드의 모든 .pkl 파일)
        prefixes = ["pre/", "post/"]
        downloaded = 0
        total_found = 0
        
        for prefix in prefixes:
            local_prefix_dir = local_dir / prefix.rstrip("/")
            local_prefix_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"🔍 Searching for files with prefix: {prefix}")
            # 버킷에서 파일 목록 가져오기
            blobs = list(bucket.list_blobs(prefix=prefix))
            logger.info(f"📋 Found {len(blobs)} blobs with prefix {prefix}")
            
            for blob in blobs:
                # .pkl 파일만 다운로드
                if not blob.name.endswith(".pkl"):
                    continue
                
                total_found += 1
                local_path = local_dir / blob.name
                
                # 이미 파일이 있고 force_download가 False면 스킵
                if local_path.exists() and not force_download:
                    logger.debug(f"⏭️  File already exists: {blob.name}, skipping")
                    continue
                
                # 디렉토리 생성
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 다운로드
                file_size_mb = blob.size / 1024 / 1024
                logger.info(f"📥 Downloading {blob.name} ({file_size_mb:.2f} MB) from GCS...")
                blob.download_to_filename(str(local_path))
                downloaded += 1
                logger.info(f"✅ Downloaded: {blob.name}")
        
        logger.info(f"📊 Summary: {total_found} .pkl files found, {downloaded} downloaded")
        
        if downloaded > 0:
            logger.info(f"✅ Successfully downloaded {downloaded} model files from GCS")
            return True
        elif total_found > 0:
            logger.info(f"ℹ️  All {total_found} files already exist locally, no download needed")
            return True
        else:
            logger.warning(f"⚠️  No .pkl files found in GCS bucket {bucket_name}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Failed to download models from GCS: {e}", exc_info=True)
        return False

