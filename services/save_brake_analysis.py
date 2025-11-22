# services/save_brake_analysis.py
from __future__ import annotations
from typing import List, Dict, Any
from utils.supabase_client import supabase

# Supabase insert payload 제한 대비
CHUNK_SIZE = 500

# 테이블 칼럼(스키마 기준) - 고정 저장 필드
_BASE_COLUMNS = {
    "lap_id",
    "driver_id",
    "track",
    "corner_index",
    "segment_name",
    "start_time",
    "end_time",
    "brake_start_dist",   # ← start_dist 매핑
    "end_dist",
    "brake_start_speed",  # ← speed_start 매핑
    "speed_end",
    "brake_duration",     # ← duration 매핑
    "brake_distance",     # ← end_dist - start_dist
    "brake_slope",        # ← brake_slope_initial 매핑
    "decel_avg",
    "brake_peak",
    "brake_auc",
    "trail_braking_ratio",
    "abs_on_ratio",
    "metrics",            # JSONB
}

# 세그먼트(dict)의 키 중, 위 고정 칼럼으로 매핑하는 규칙
def _map_segment_to_row(seg: Dict[str, Any], lap_id: str, track: str, driver_id: str | None) -> Dict[str, Any]:
    # 필수/권장 키 안전하게 꺼내기
    start_dist = seg.get("start_dist")
    end_dist   = seg.get("end_dist")

    # ⬇️ 추가: corner_index 최후 방어(-1로 대체)
    corner_idx = seg.get("corner_index")
    if corner_idx in (None, "", "null"):
        corner_idx = -1

    row = {
        # PK는 DB default, 여기선 생략
        "lap_id": lap_id,
        "driver_id": driver_id,
        "track": track,

        # 코너/세그먼트
        "corner_index": corner_idx,                 # ← not-null 보장
        "segment_name": seg.get("segment_name"),

        # 시간/거리/속도
        "start_time": seg.get("start_time"),
        "end_time": seg.get("end_time"),
        "brake_start_dist": start_dist,                           # start_dist → brake_start_dist
        "end_dist": end_dist,
        "brake_start_speed": seg.get("speed_start"),              # speed_start → brake_start_speed
        "speed_end": seg.get("speed_end"),

        # 기간/거리/기울기
        "brake_duration": seg.get("duration"),                    # duration → brake_duration
        "brake_distance": (end_dist - start_dist) if (isinstance(start_dist, (int, float)) and isinstance(end_dist, (int, float))) else None,
        "brake_slope": seg.get("brake_slope_initial"),            # brake_slope_initial → brake_slope

        # 요약 지표(칼럼화)
        "decel_avg": seg.get("decel_avg"),
        "brake_peak": seg.get("brake_peak"),
        "brake_auc": seg.get("brake_auc"),
        "trail_braking_ratio": seg.get("trail_braking_ratio"),
        "abs_on_ratio": seg.get("abs_on_ratio"),
    }

    # metrics JSONB: 위에 칼럼으로 올린 것/테이블에 없는 것들을 모두 담음
    # 1) 고정 매핑에 이미 쓴 키
    used_keys = {
        "corner_index", "segment_name",
        "start_time", "end_time",
        "start_dist", "end_dist", "speed_start", "speed_end",
        "duration", "brake_slope_initial",
        "decel_avg", "brake_peak", "brake_auc",
        "trail_braking_ratio", "abs_on_ratio",
    }
    # 2) 테이블 고정 칼럼 키
    used_keys |= _BASE_COLUMNS

    metrics = {k: v for k, v in seg.items() if k not in used_keys}

    # 예: 슬립/서스/범프/타이어/브템/타이밍 추가 지표들이 metrics로 들어감
    # ("slip_peak_lf", "slip_lock_ratio_front", "sus_pk_lf", "bump_force_pk_lf", "tyre_press_mean_lf",
    #  "brake_temp_rise_front", "delta_t_brake_to_g_lon", ...)

    row["metrics"] = metrics
    return row


def _chunked_insert(table: str, rows: List[Dict[str, Any]], chunk_size: int = CHUNK_SIZE):
    """Supabase insert를 청크로 나누어 실행"""
    for i in range(0, len(rows), chunk_size):
        batch = rows[i:i + chunk_size]
        supabase.table(table).insert(batch).execute()


def save_brake_analysis(
    lap_id: str,
    track: str,
    driver_id: str | None,
    analysis_results: List[Dict[str, Any]],
    replace: bool = True,
) -> int:
    """
    세그먼트 배열(analysis_results)을 brake_analysis 테이블에 저장.
    - replace=True: 동일 lap_id 레코드 삭제 후 재삽입
    - 반환값: 저장된 행 수
    """
    if not analysis_results:
        return 0

    # 옵션: 기존 같은 랩 결과 제거(덮어쓰기 용이)
    if replace:
        supabase.table("brake_analysis").delete().eq("lap_id", lap_id).execute()

    rows: List[Dict[str, Any]] = []
    # lap_id/track/driver_id는 상위에서 보장된 값 사용
    tkey = (track or "").lower()

    for seg in analysis_results:
        row = _map_segment_to_row(seg, lap_id=lap_id, track=tkey, driver_id=driver_id)
        rows.append(row)

    if not rows:
        return 0

    _chunked_insert("brake_analysis", rows)
    return len(rows)
