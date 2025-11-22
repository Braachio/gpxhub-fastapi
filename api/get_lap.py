import pandas as pd

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from utils.supabase_client import supabase
from utils.sanitize import sanitize_for_json
from utils.analysis.corner_exit_analysis import analyze_corner_exit_and_feedback
from utils.analysis.corner_entry_analysis import analyze_corner_entry_and_feedback

from services.lap_data import fetch_lap_meta_and_data
from services.fixed_sector import get_sector_summary_by_lap_id

router = APIRouter()

@router.get("/lap/{lap_id}")
def get_lap_data(lap_id: str):
    lap = fetch_lap_meta_and_data(lap_id)
    if not lap:
        return JSONResponse(status_code=404, content={"error": "랩 정보를 찾을 수 없습니다."})

    controls = lap["controls"]  # list[dict]
    vehicle = lap["vehicle"]    # list[dict]
    meta = lap["meta"]

    # ✅ DataFrame 준비(소문자 컬럼 보장)
    df_controls = pd.DataFrame(controls)
    df_vehicle = pd.DataFrame(vehicle)
    df_controls.columns = [c.strip().lower() for c in df_controls.columns]
    df_vehicle.columns  = [c.strip().lower() for c in df_vehicle.columns]

    # ✅ 섹터 요약 분석
    try:
        sector_results = get_sector_summary_by_lap_id(supabase, lap_id, df_controls)
    except Exception as e:
        print(f"❌ 섹터 요약 분석 실패: {repr(e)}")
        sector_results = []

    # ✅ 코너 이탈/진입 피드백
    try:
        # 기존 분석 함수는 DF 인자를 기대함
        corner_feedback = analyze_corner_exit_and_feedback(df_controls, df_vehicle)
    except Exception as e:
        print(f"❌ 코너 피드백 분석 실패: {repr(e)}")
        corner_feedback = []

    try:
        entry_segments = analyze_corner_entry_and_feedback(df_controls)
    except Exception as e:
        print(f"❌ 트레일 브레이킹 분석 실패: {repr(e)}")
        entry_segments = []

    # ✅ 트랙 코너 맵
    try:
        track_key = (meta.get("track") or "").lower()
        corner_map_response = supabase.table("corner_segments") \
            .select("*") \
            .eq("track", track_key) \
            .order("start") \
            .execute()
        track_corner_map = corner_map_response.data or []
    except Exception as e:
        print(f"❌ track_corner_map 조회 실패: {repr(e)}")
        track_corner_map = []

    # ✅ 그래프용 데이터(controls + vehicle 병합)
    try:
        df = pd.merge(df_controls, df_vehicle, on="time", how="inner")
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
            # 범프스톱(휠별)
            "bumpstopup_ride_lf","bumpstopup_ride_rf","bumpstopup_ride_lr","bumpstopup_ride_rr",
            "bumpstopdn_ride_lf","bumpstopdn_ride_rf","bumpstopdn_ride_lr","bumpstopdn_ride_rr",
            "bumpstop_force_lf","bumpstop_force_rf","bumpstop_force_lr","bumpstop_force_rr",
        ]
        data_for_graph = df[[k for k in graph_keys if k in df.columns]].to_dict(orient="records")
    except Exception as e:
        print(f"❌ 그래프 데이터 생성 실패: {repr(e)}")
        data_for_graph = controls  # 최소한 기존과 동일한 필드 보장

    # ✅ 브레이크 분석 결과 조회(+ metrics 평탄화)
    try:
        ba_resp = supabase.table("brake_analysis") \
            .select("*") \
            .eq("lap_id", lap_id) \
            .order("start_time") \
            .execute()

        brake_rows = ba_resp.data or []

        def flatten_metrics(row: dict) -> dict:
            m = row.get("metrics") or {}
            # metrics를 상위로 머지(기존 키와 충돌 없도록 metrics_ 접두사로도 보유 가능)
            flat = {**row}
            flat.pop("metrics", None)
            # 필요 시 아래 한 줄로 접두사 유지 병행 가능:
            # flat.update({f"metrics_{k}": v for k, v in m.items()})
            flat.update(m)
            return flat

        brake_analysis = [flatten_metrics(r) for r in brake_rows]

        # 간단 요약(있으면 평균치 계산)
        if brake_analysis:
            df_ba = pd.DataFrame(brake_analysis)
            def avg(col):
                return float(df_ba[col].dropna().mean()) if col in df_ba.columns else None
            brake_summary = {
                "num_segments": int(len(brake_analysis)),
                "avg_decel": avg("decel_avg"),
                "avg_brake_peak": avg("brake_peak"),
                "avg_trail_ratio": avg("trail_braking_ratio"),
                "avg_abs_on_ratio": avg("abs_on_ratio"),
                # 확장 지표(있을 때만)
                "avg_slip_lock_front": avg("slip_lock_ratio_front"),
                "avg_slip_lock_rear":  avg("slip_lock_ratio_rear"),
                "avg_brake_temp_rise_front": avg("brake_temp_rise_front"),
                "avg_brake_temp_rise_rear":  avg("brake_temp_rise_rear"),
            }
        else:
            brake_summary = {}
    except Exception as e:
        print(f"❌ brake_analysis 조회 실패: {repr(e)}")
        brake_analysis = []
        brake_summary = {}

    return sanitize_for_json({
        "track": meta.get("track"),
        "lap_id": lap_id,
        "car": meta.get("car"),
        # ✅ 통합 그래프 데이터 반환
        "data_for_graph": data_for_graph,
        # 기존 필드 유지(하위 호환 필요 시)
        "data": controls,
        "sector_results": sector_results,
        "corner_exit_analysis": corner_feedback or [],
        "corner_entry_analysis": entry_segments or [],
        "track_corner_map": track_corner_map,
        # ✅ 브레이크 분석 결과/요약 추가
        "brake_analysis": brake_analysis,
        "brake_summary": brake_summary,
    })
