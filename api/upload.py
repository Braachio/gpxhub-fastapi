# 📦 필수 모듈 import
from fastapi import UploadFile, Form, File, APIRouter
from fastapi.responses import JSONResponse
import pandas as pd

# 📦 프로젝트 내부 유틸 import
from utils.supabase_client import supabase
from utils.analysis.corner_exit_analysis import analyze_corner_exit_and_feedback
from utils.analysis.corner_entry_analysis import analyze_corner_entry_and_feedback
from services.insert import extract_value, chunked_insert, chunked_insert_lap_raw
from services.upload_lap_data import generate_lap_hash
from services.fixed_sector import get_sector_summary_by_lap_id
from services.braking_dynamics import analyze_braking_dynamics
from services.save_brake_analysis import save_brake_analysis
from services.track_corners import get_corner_segments_for_track
from services.preprocessing import preprocess_csv_data

router = APIRouter()

def normalize_uuid(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "null", "undefined"):
        return None
    return s


# ✅ 중복 컬럼 제거 유틸 함수
def deduplicate_columns(columns):
    seen = {}
    result = []
    for col in columns:
        col_lower = col.strip().lower()
        if col_lower in seen:
            seen[col_lower] += 1
            col_lower = f"{col_lower}_{seen[col_lower]}"
        else:
            seen[col_lower] = 0
        result.append(col_lower)
    return result


@router.post("/analyze-motec-csv")
async def analyze_motec_csv(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    save: bool = Form(False),
    weather: str = Form(None),
    air_temp: float = Form(None),
    track_temp: float = Form(None)
):
    try:
        # 1️⃣ 업로드된 CSV 파일 읽기 및 줄 단위 분리
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        lines = text.splitlines()

        # 2️⃣ 헤더 메타데이터에서 기본 정보 추출
        lap_time = extract_value(lines, "Duration")
        try:
            lap_time_value = float(lap_time.strip().split()[0])
        except Exception:
            lap_time_value = None

        track_name = extract_value(lines, "Venue")
        car_name = extract_value(lines, "Vehicle")


        # ✅ 전처리 함수 호출
        try:
            df = preprocess_csv_data(lines)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        
        df.columns = [c.strip().lower() for c in df.columns]

        lap_id = None  # 이후 메타 생성/재사용로 채워짐

        # 9️⃣ 데이터프레임 이상 확인
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"remove_straight_sections() 결과 오류: {df}")

        # 🔢 제어/차량 상태 컬럼 분리
        control_cols = ["time", "throttle", "brake", "steerangle", "speed", "rpms", "gear", "distance"]
        control_cols = [col for col in control_cols if col in df.columns]
        control_df = df[control_cols].copy()

        vehicle_cols = ["time"] + [col for col in df.columns if col not in control_cols and col != "time"]
        vehicle_df = df[vehicle_cols].copy()

        # 🧬 랩 고유 해시 생성 (중복 방지)
        lap_hash = generate_lap_hash(df)

        # 🧠 코너 진입/이탈 분석
        entry_segments = analyze_corner_entry_and_feedback(control_df)
        exit_segments = analyze_corner_exit_and_feedback(control_df, vehicle_df)

        # 📊 프론트엔드용 그래프 데이터 변환
        graph_keys = [
            # 기본
            "time","distance","speed","throttle","brake","steerangle","gear",
            # G/ABS
            "g_lon","g_lat","abs",
            # 휠 스피드(휠별)
            "wheel_speed_lf","wheel_speed_rf","wheel_speed_lr","wheel_speed_rr",
            # 서스피션(휠별)
            "sus_travel_lf","sus_travel_rf","sus_travel_lr","sus_travel_rr",
            # 브레이크 온도(휠별)
            "brake_temp_lf","brake_temp_rf","brake_temp_lr","brake_temp_rr",
            # 타이어 압력/표면온도(휠별)
            "tyre_press_lf","tyre_press_rf","tyre_press_lr","tyre_press_rr",
            "tyre_tair_lf","tyre_tair_rf","tyre_tair_lr","tyre_tair_rr",
            # 범프스톱(휠별, 필요 시 그래프에서 선택)
            "bumpstopup_ride_lf","bumpstopup_ride_rf","bumpstopup_ride_lr","bumpstopup_ride_rr",
            "bumpstopdn_ride_lf","bumpstopdn_ride_rf","bumpstopdn_ride_lr","bumpstopdn_ride_rr",
            "bumpstop_force_lf","bumpstop_force_rf","bumpstop_force_lr","bumpstop_force_rr",
        ]
        graph_data = df[[k for k in graph_keys if k in df.columns]].to_dict(orient="records")


        # 🧩 해당 트랙 코너 세그먼트 정의 가져오기
        try:
            segments = get_corner_segments_for_track(supabase, (track_name or "").lower())
        except Exception:
            segments = None

        # 🛑 브레이킹 동역학 분석 (휠별 슬립/ABS/G/서스/범프/타이어/브템 포함)
        brake_results = analyze_braking_dynamics(df, segments)
        print(f"🔧 braking_dynamics 분석 결과: {brake_results}")

        # ⬇️ 추가: corner_index 보정
        segments_out = brake_results.get("segments", [])
        for i, seg in enumerate(segments_out, start=1):
            if seg.get("corner_index") is None:
                seg["corner_index"] = -1
                seg["segment_name"] = seg.get("segment_name") or f"brake_seg_{i}"

        # 🔐 사용자 ID 정규화 및 검증 (메타 작성 시 필요)
        norm_user_id = normalize_uuid(user_id)
        if not norm_user_id:
            return JSONResponse(status_code=400, content={"error": "user_id는 필수입니다.(UUID)"})

        # 🧱 이미 업로드된 랩인지 체크 (hash 기준)
        existing = supabase.table("lap_meta").select("id").eq("hash", lap_hash).execute()
        if existing.data:
            lap_id = existing.data[0]["id"]
        else:
            # 1) 메타데이터 생성
            meta_resp = supabase.table("lap_meta").insert({
                "user_id": norm_user_id,
                "track": (track_name or "").lower(),
                "car": car_name,
                "weather": weather,
                "air_temp": air_temp,
                "track_temp": track_temp,
                "hash": lap_hash,
                "lap_time": lap_time_value
            }).execute()
            lap_id = meta_resp.data[0]["id"]

        # 2) 브레이크 분석 결과는 항상 저장/갱신
        print(f"📝 brake_analysis 저장 시도 → lap_id={lap_id}, track={(track_name or '').lower()}, driver_id={user_id}")
        save_brake_analysis(
            lap_id=lap_id,
            track=(track_name or "").lower(),
            driver_id=user_id,
            analysis_results=brake_results.get("segments", [])
        )

        sector_results = None

        # 3) save=True일 때만 원시 주행 데이터 저장 및 섹터 요약 계산
        if save:
            df["lap_id"] = lap_id
            chunked_insert("lap_controls", df[control_cols + ["lap_id"]].to_dict(orient="records"))
            vehicle_cols = [col for col in df.columns if col not in control_cols + ["lap_id", "time"]]
            chunked_insert("lap_vehicle_status", df[["time"] + vehicle_cols + ["lap_id"]].to_dict(orient="records"))
            chunked_insert_lap_raw(lap_id, df)

            sector_results = get_sector_summary_by_lap_id(supabase, lap_id, df)

        # ✅ 공통 응답
        return {
            "status": "✅ 분석 및 저장 완료" if save else "✅ 분석 완료 (결과 저장)",
            "lap_id": lap_id,
            "track": track_name,
            "car": car_name,
            "lap_time": lap_time_value,
            "data": graph_data,
            "sector_results": sector_results,
            "corner_exit_analysis": exit_segments or [],
            "corner_entry_analysis": entry_segments or [],
            "brake_analysis": brake_results.get("segments", []),
            "brake_summary": brake_results.get("summary", {})
        }

    # ❌ 예외 발생 처리
    except Exception as e:
        print(f"❌ 예외 발생: {repr(e)}")
        return JSONResponse(status_code=500, content={"error": f"분석 실패: {repr(e)}"})
