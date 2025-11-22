"""
iRacing SDK 수집 서비스 API

FastAPI 엔드포인트로 SDK 수집 서비스를 제어할 수 있습니다.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import os
from services.iracing_sdk_collector import IRacingSDKCollector

router = APIRouter()

# 전역 수집기 인스턴스 (실제로는 더 안전한 방식으로 관리 필요)
_collector: Optional[IRacingSDKCollector] = None


@router.post("/iracing-sdk/start")
async def start_sdk_collection(
    api_url: Optional[str] = None,
    user_token: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """
    SDK 수집 시작
    
    - api_url: Next.js API URL (기본값: 환경변수 또는 localhost:3000)
    - user_token: Supabase 인증 토큰
    """
    global _collector
    
    if _collector and _collector.is_running:
        raise HTTPException(status_code=400, detail="이미 수집 중입니다.")
    
    api_url = api_url or os.getenv('NEXTJS_API_URL', 'http://localhost:3000')
    user_token = user_token or os.getenv('USER_TOKEN')
    
    _collector = IRacingSDKCollector(api_url=api_url, user_token=user_token)
    
    if _collector.start():
        return {
            "status": "started",
            "message": "SDK 수집이 시작되었습니다."
        }
    else:
        raise HTTPException(status_code=500, detail="SDK 수집 시작 실패")


@router.post("/iracing-sdk/stop")
async def stop_sdk_collection():
    """SDK 수집 중지"""
    global _collector
    
    if not _collector or not _collector.is_running:
        raise HTTPException(status_code=400, detail="수집 중이 아닙니다.")
    
    _collector.stop()
    return {
        "status": "stopped",
        "message": "SDK 수집이 중지되었습니다."
    }


@router.get("/iracing-sdk/status")
async def get_sdk_status():
    """SDK 수집 상태 조회"""
    global _collector
    
    if not _collector:
        return {
            "status": "not_initialized",
            "is_running": False,
            "is_connected": False
        }
    
    is_connected = _collector.ir and _collector.ir.is_connected() if _collector.ir else False
    
    return {
        "status": "running" if _collector.is_running else "stopped",
        "is_running": _collector.is_running,
        "is_connected": is_connected,
        "sample_count": len(_collector.samples),
        "session_start_time": _collector.session_start_time.isoformat() if _collector.session_start_time else None
    }

