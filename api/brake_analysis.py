from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import pandas as pd

from utils.supabase_client import supabase
from services.save_brake_analysis import save_brake_analysis
from services.brake_feedback import generate_braking_feedback
from services.track_corners import get_corner_segments_for_track

# ✅ 새로 추가
from services.braking_dynamics import analyze_braking_dynamics
from services.preprocessing import preprocess_csv_data

router = APIRouter()

@router.post("/brake-analysis")
async def analyze_brake(
    file: UploadFile = File(...),
    lap_id: str = Form(...),
    driver_id: str = Form(...),
    track: str = Form(...)
):
    try:
        # 1) CSV → 전처리 (단위 판독/변환 + 소문자 컬럼 + 숫자화 + 보정)
        contents = await file.read()
        lines = contents.decode("utf-8", errors="ignore").splitlines()
        df = preprocess_csv_data(lines)  # ✅ 여기서 m/s→km/h 등 처리 완료

        # 2) 트랙 세그먼트 로드 (가드)
        try:
            segments = get_corner_segments_for_track(supabase, (track or "").lower())
        except Exception:
            segments = None

        # 3) 브레이크 동역학 분석 (휠별 슬립/ABS/G/서스/타이어/브템 포함)
        results = analyze_braking_dynamics(df, segments=segments)
        segments_out = results.get("segments", [])
        summary_out = results.get("summary", {})

        # 4) DB 저장 (세그먼트 리스트만 저장)
        save_brake_analysis(
            lap_id=lap_id,
            track=(track or "").lower(),
            driver_id=driver_id,
            analysis_results=segments_out
        )

        # 5) 피드백 생성
        feedbacks = generate_braking_feedback(lap_id, (track or "").lower())

        # 6) 응답
        return {
            "lap_id": lap_id,
            "track": (track or "").lower(),
            "analysis": segments_out,   # ✅ 세그먼트 배열
            "summary": summary_out,     # ✅ 요약 추가
            "feedback": feedbacks
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"브레이크 분석 실패: {repr(e)}")
