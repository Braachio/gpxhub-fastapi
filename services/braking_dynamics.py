# services/braking_dynamics.py
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Dict, Optional

# ====== 튜닝 가능한 임계값 ======
BRAKE_ON = 3.0            # % 이상이면 제동 시작 후보 (더 민감하게)
BRAKE_OFF = 1.0           # % 미만이면 제동 종료 (더 민감하게)
MIN_BRAKE_DURATION = 0.1  # s (더 짧은 구간도 허용)
STEER_ON = 2.0            # deg
SLIP_LOCKUP = 0.20        # 슬립율 20% 이상 → 락업 위험
ABS_ON_VALUE = 0.5        # abs 컬럼이 [0/1] 또는 [0~1] 범위일 때 개입 판단
ROLL_WINDOW = 5           # 이동평균 윈도(샘플)
INIT_SLOPE_WINDOW = 0.3   # s, 초기 제동 기울기 계산 구간

# 필수 공통 컬럼
BASE_REQUIRED = [
    "time", "distance", "speed", "brake", "steerangle",
    "abs", "g_lon", "g_lat"
]

# 바퀴별/코너별 컬럼(소문자 기준)
WHEEL_COLS = {
    # 서스피션
    "sus_travel_lf", "sus_travel_rf", "sus_travel_lr", "sus_travel_rr",
    # 브레이크 온도
    "brake_temp_lf", "brake_temp_rf", "brake_temp_lr", "brake_temp_rr",
    # 타이어 압력/표면온도
    "tyre_press_lf", "tyre_press_rf", "tyre_press_lr", "tyre_press_rr",
    "tyre_tair_lf",  "tyre_tair_rf",  "tyre_tair_lr",  "tyre_tair_rr",
    # 휠 스피드
    "wheel_speed_lf","wheel_speed_rf","wheel_speed_lr","wheel_speed_rr",
    # 범프스톱 위/아래/힘
    "bumpstopup_ride_lf","bumpstopup_ride_rf","bumpstopup_ride_lr","bumpstopup_ride_rr",
    "bumpstopdn_ride_lf","bumpstopdn_ride_rf","bumpstopdn_ride_lr","bumpstopdn_ride_rr",
    "bumpstop_force_lf","bumpstop_force_rf","bumpstop_force_lr","bumpstop_force_rr",
}

REQUIRED_COLS = BASE_REQUIRED + sorted(list(WHEEL_COLS))

# ────────────────────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────────────────────
def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """대문자/혼합 컬럼명을 소문자로 치환."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def _validate_columns(df: pd.DataFrame):
    # 기본 필수 컬럼만 체크 (더 유연하게)
    base_required = ["time", "speed", "brake"]  # distance 제외
    missing = [c for c in base_required if c not in df.columns]
    if missing:
        print(f"❌ 필수 컬럼 누락: {missing}")
        print(f"📊 실제 컬럼들: {list(df.columns)}")
        raise ValueError(f"필수 컬럼 누락: {missing}")
    
    # distance 컬럼이 없으면 time 기반으로 생성
    if "distance" not in df.columns:
        print("⚠️ distance 컬럼이 없어서 time 기반으로 생성합니다.")
        if "time" in df.columns:
            # 시간 차이를 기반으로 거리 계산 (대략적)
            df["distance"] = df["time"].diff().fillna(0).cumsum() * 50  # 50m/s 가정
        else:
            df["distance"] = range(len(df))  # 인덱스 기반 거리
    
    # 선택적 컬럼들에 대해 기본값 설정
    optional_cols = ["steerangle", "abs", "g_lon", "g_lat"]
    for col in optional_cols:
        if col not in df.columns:
            if col == "abs":
                df[col] = 0.0
            elif col in ["g_lon", "g_lat"]:
                df[col] = 0.0
            elif col == "steerangle":
                df[col] = 0.0
            print(f"⚠️ {col} 컬럼이 없어서 기본값 0.0으로 설정했습니다.")

def _smooth(x: pd.Series, window: int = ROLL_WINDOW) -> pd.Series:
    if window <= 1:
        return x
    return x.rolling(window=window, min_periods=1, center=True).mean()

def _to_np(a: pd.Series) -> np.ndarray:
    return a.to_numpy(dtype=float, copy=False)

def _safe_speed(arr: np.ndarray, eps: float = 0.1) -> np.ndarray:
    return np.maximum(arr, eps)

# ────────────────────────────────────────────────────────────────────────────────
# 제동 구간 검출
# ────────────────────────────────────────────────────────────────────────────────
def _find_brake_segments(df: pd.DataFrame) -> List[Dict]:
    """브레이크 on/off 임계값(Hysteresis) 적용하여 제동 구간(start_idx, end_idx) 검출"""
    brake = _to_np(df["brake"])
    time = _to_np(df["time"])
    on = brake >= BRAKE_ON

    segments = []
    i = 0
    n = len(df)
    while i < n:
        if on[i]:
            start = i
            j = i + 1
            while j < n and brake[j] >= BRAKE_OFF:
                j += 1
            end = j - 1
            if time[end] - time[start] >= MIN_BRAKE_DURATION:
                segments.append({"start_idx": start, "end_idx": end})
            i = j
        else:
            i += 1
    return segments

def _initial_brake_slope(df: pd.DataFrame, start_idx: int) -> Optional[float]:
    """제동 시작 직후 INIT_SLOPE_WINDOW 동안 brake의 1차 기울기(%) / s"""
    t0 = df.at[start_idx, "time"]
    mask = (df["time"] >= t0) & (df["time"] <= t0 + INIT_SLOPE_WINDOW)
    sub = df.loc[mask, ["time", "brake"]]
    if len(sub) < 2:
        return None
    x = sub["time"].to_numpy()
    y = sub["brake"].to_numpy()
    A = np.vstack([x - x[0], np.ones_like(x)]).T
    slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(slope)

# ────────────────────────────────────────────────────────────────────────────────
# 휠별/축별 파생 지표
# ────────────────────────────────────────────────────────────────────────────────
def _compute_wheel_slip(sub: pd.DataFrame) -> pd.DataFrame:
    """
    바퀴별 슬립율 계산:
      slip_ratio_X = (vehicle_speed - wheel_speed_X) / vehicle_speed
    """
    out = sub.copy()
    vs = _safe_speed(out["speed_s"].to_numpy())  # 차량 속도(스무딩 후)
    for w in ["lf", "rf", "lr", "rr"]:
        ws = out[f"wheel_speed_{w}_s"].to_numpy()
        slip = np.clip((vs - ws) / vs, -1.0, 1.0)
        out[f"slip_ratio_{w}"] = slip
    # 축별 평균/좌우차/전후차
    out["slip_front_avg"] = (out["slip_ratio_lf"] + out["slip_ratio_rf"]) / 2.0
    out["slip_rear_avg"]  = (out["slip_ratio_lr"] + out["slip_ratio_rr"]) / 2.0
    out["slip_lr_diff_front"] = (out["slip_ratio_lf"] - out["slip_ratio_rf"]).abs()
    out["slip_lr_diff_rear"]  = (out["slip_ratio_lr"] - out["slip_ratio_rr"]).abs()
    out["slip_fb_diff"] = (out["slip_front_avg"] - out["slip_rear_avg"]).abs()
    return out

def _segment_stats(df: pd.DataFrame, seg: Dict) -> Dict:
    s, e = seg["start_idx"], seg["end_idx"]
    sub = df.iloc[s:e+1].copy()

    # 스무딩
    for k in ["brake", "speed", "abs", "g_lon", "g_lat",
              "wheel_speed_lf","wheel_speed_rf","wheel_speed_lr","wheel_speed_rr"]:
        sub[f"{k}_s"] = _smooth(sub[k])

    # 바퀴별 슬립 계산
    sub = _compute_wheel_slip(sub)

    # 기본 시간/거리/속도/제동량
    t0, t1 = float(sub["time"].iloc[0]), float(sub["time"].iloc[-1])
    d0, d1 = float(sub["distance"].iloc[0]), float(sub["distance"].iloc[-1])
    dur = t1 - t0

    v0, v1 = float(sub["speed_s"].iloc[0]), float(sub["speed_s"].iloc[-1])
    dv = v0 - v1
    decel_avg = dv / dur if dur > 1e-6 else None

    brake_peak = float(sub["brake_s"].max())
    brake_auc = float(np.trapz(sub["brake_s"], sub["time"]))  # 누적 제동량
    slope_init = _initial_brake_slope(sub, sub.index[0])

    # 트레일 브레이킹 비율
    trail_mask = (sub["brake_s"] >= BRAKE_OFF) & (sub["steerangle"].abs() >= STEER_ON)
    trail_ratio = float(trail_mask.mean())

    # ABS/슬립 지표
    abs_on_ratio = float((_smooth(sub["abs"]) >= ABS_ON_VALUE).mean())
    slip_pk_lf = float(sub["slip_ratio_lf"].max())
    slip_pk_rf = float(sub["slip_ratio_rf"].max())
    slip_pk_lr = float(sub["slip_ratio_lr"].max())
    slip_pk_rr = float(sub["slip_ratio_rr"].max())
    slip_lock_ratio_front = float(((sub["slip_ratio_lf"] >= SLIP_LOCKUP) | (sub["slip_ratio_rf"] >= SLIP_LOCKUP)).mean())
    slip_lock_ratio_rear  = float(((sub["slip_ratio_lr"] >= SLIP_LOCKUP) | (sub["slip_ratio_rr"] >= SLIP_LOCKUP)).mean())

    # G 지표
    g_lon_min = float(_smooth(sub["g_lon"]).min())   # 제동 시 보통 음수 최대
    g_lon_mean = float(_smooth(sub["g_lon"]).mean())
    g_lat_peak_abs = float(_smooth(sub["g_lat"]).abs().max())

    # 서스피션 (피크 + 좌우/전후 밸런스)
    sus_pk_lf = float(sub["sus_travel_lf"].max())
    sus_pk_rf = float(sub["sus_travel_rf"].max())
    sus_pk_lr = float(sub["sus_travel_lr"].max())
    sus_pk_rr = float(sub["sus_travel_rr"].max())
    sus_front_avg = (sus_pk_lf + sus_pk_rf) / 2.0
    sus_rear_avg  = (sus_pk_lr + sus_pk_rr) / 2.0
    sus_lr_diff_front = abs(sus_pk_lf - sus_pk_rf)
    sus_lr_diff_rear  = abs(sus_pk_lr - sus_pk_rr)
    sus_fb_diff       = abs(sus_front_avg - sus_rear_avg)

    # 범프스톱 접촉/힘
    bump_contact_cnt_front = int(((sub["bumpstopup_ride_lf"] > 0) | (sub["bumpstopdn_ride_lf"] > 0) |
                                  (sub["bumpstopup_ride_rf"] > 0) | (sub["bumpstopdn_ride_rf"] > 0)).sum())
    bump_contact_cnt_rear  = int(((sub["bumpstopup_ride_lr"] > 0) | (sub["bumpstopdn_ride_lr"] > 0) |
                                  (sub["bumpstopup_ride_rr"] > 0) | (sub["bumpstopdn_ride_rr"] > 0)).sum())
    bump_force_pk_lf = float(sub["bumpstop_force_lf"].max())
    bump_force_pk_rf = float(sub["bumpstop_force_rf"].max())
    bump_force_pk_lr = float(sub["bumpstop_force_lr"].max())
    bump_force_pk_rr = float(sub["bumpstop_force_rr"].max())

    # 타이어(압/표면온도) 평균
    tyre_press_mean_lf = float(sub["tyre_press_lf"].mean())
    tyre_press_mean_rf = float(sub["tyre_press_rf"].mean())
    tyre_press_mean_lr = float(sub["tyre_press_lr"].mean())
    tyre_press_mean_rr = float(sub["tyre_press_rr"].mean())
    tyre_tair_mean_lf  = float(sub["tyre_tair_lf"].mean())
    tyre_tair_mean_rf  = float(sub["tyre_tair_rf"].mean())
    tyre_tair_mean_lr  = float(sub["tyre_tair_lr"].mean())
    tyre_tair_mean_rr  = float(sub["tyre_tair_rr"].mean())

    # 브레이크 온도(피크/상승)
    brake_temp_max_lf = float(sub["brake_temp_lf"].max())
    brake_temp_max_rf = float(sub["brake_temp_rf"].max())
    brake_temp_max_lr = float(sub["brake_temp_lr"].max())
    brake_temp_max_rr = float(sub["brake_temp_rr"].max())
    brake_temp_rise_front = float((sub["brake_temp_lf"].iloc[-1] + sub["brake_temp_rf"].iloc[-1]
                                  - sub["brake_temp_lf"].iloc[0] - sub["brake_temp_rf"].iloc[0]) / 2.0)
    brake_temp_rise_rear  = float((sub["brake_temp_lr"].iloc[-1] + sub["brake_temp_rr"].iloc[-1]
                                  - sub["brake_temp_lr"].iloc[0] - sub["brake_temp_rr"].iloc[0]) / 2.0)

    # 타이밍(피크 타임 간 차이)
    try:
        t_brake_peak = float(sub.loc[sub["brake_s"].idxmax(), "time"])
        t_g_lon_min  = float(sub.loc[_smooth(sub["g_lon"]).idxmin(), "time"])
        t_g_lat_pk   = float(sub.loc[_smooth(sub["g_lat"]).abs().idxmax(), "time"])
        delta_brake_to_glon = t_g_lon_min - t_brake_peak
        delta_brake_to_glat = t_g_lat_pk - t_brake_peak
    except Exception:
        delta_brake_to_glon = None
        delta_brake_to_glat = None

    return {
        "start_idx": int(s),
        "end_idx": int(e),
        "start_time": t0,
        "end_time": t1,
        "duration": dur,
        "start_dist": d0,
        "end_dist": d1,
        "speed_start": v0,
        "speed_end": v1,
        "delta_v": dv,
        "decel_avg": decel_avg,
        "brake_peak": brake_peak,
        "brake_auc": brake_auc,
        "brake_slope_initial": slope_init,

        # 트레일/ABS/슬립
        "trail_braking_ratio": trail_ratio,
        "abs_on_ratio": abs_on_ratio,
        "slip_peak_lf": slip_pk_lf,
        "slip_peak_rf": slip_pk_rf,
        "slip_peak_lr": slip_pk_lr,
        "slip_peak_rr": slip_pk_rr,
        "slip_lock_ratio_front": slip_lock_ratio_front,
        "slip_lock_ratio_rear":  slip_lock_ratio_rear,
        "slip_lr_diff_front_mean": float(sub["slip_lr_diff_front"].mean()),
        "slip_lr_diff_rear_mean":  float(sub["slip_lr_diff_rear"].mean()),
        "slip_fb_diff_mean":       float(sub["slip_fb_diff"].mean()),

        # G 지표
        "g_lon_min": g_lon_min,
        "g_lon_mean": g_lon_mean,
        "g_lat_peak_abs": g_lat_peak_abs,

        # 서스피션
        "sus_pk_lf": sus_pk_lf,
        "sus_pk_rf": sus_pk_rf,
        "sus_pk_lr": sus_pk_lr,
        "sus_pk_rr": sus_pk_rr,
        "sus_lr_diff_front": sus_lr_diff_front,
        "sus_lr_diff_rear":  sus_lr_diff_rear,
        "sus_fb_diff":       sus_fb_diff,

        # 범프스톱
        "bump_contact_count_front": bump_contact_cnt_front,
        "bump_contact_count_rear":  bump_contact_cnt_rear,
        "bump_force_pk_lf": bump_force_pk_lf,
        "bump_force_pk_rf": bump_force_pk_rf,
        "bump_force_pk_lr": bump_force_pk_lr,
        "bump_force_pk_rr": bump_force_pk_rr,

        # 타이어
        "tyre_press_mean_lf": tyre_press_mean_lf,
        "tyre_press_mean_rf": tyre_press_mean_rf,
        "tyre_press_mean_lr": tyre_press_mean_lr,
        "tyre_press_mean_rr": tyre_press_mean_rr,
        "tyre_tair_mean_lf":  tyre_tair_mean_lf,
        "tyre_tair_mean_rf":  tyre_tair_mean_rf,
        "tyre_tair_mean_lr":  tyre_tair_mean_lr,
        "tyre_tair_mean_rr":  tyre_tair_mean_rr,

        # 브레이크 온도
        "brake_temp_max_lf": brake_temp_max_lf,
        "brake_temp_max_rf": brake_temp_max_rf,
        "brake_temp_max_lr": brake_temp_max_lr,
        "brake_temp_max_rr": brake_temp_max_rr,
        "brake_temp_rise_front": brake_temp_rise_front,
        "brake_temp_rise_rear":  brake_temp_rise_rear,

        # 타이밍
        "delta_t_brake_to_g_lon": delta_brake_to_glon,
        "delta_t_brake_to_g_lat": delta_brake_to_glat,
    }

def analyze_braking_dynamics(
    df: pd.DataFrame,
    segments: Optional[List[Dict]] = None
) -> Dict:
    """
    전체 랩의 브레이킹 구간 검출 + 구간별 상세 지표 산출 + 요약 통계
    segments: [{corner_index, name, start, end_dist}, ...] (옵션)
    """
    # 컬럼 정규화(대문자 → 소문자)
    df = _normalize_columns(df)

    # 필수 컬럼 검사
    _validate_columns(df)

    # 정렬
    df = df.sort_values("time").reset_index(drop=True)

    # 브레이킹 구간 찾기
    brake_segs = _find_brake_segments(df)

    # 구간별 상세
    per_segment = []
    for seg in brake_segs:
        stat = _segment_stats(df, seg)

        # 코너 매핑(옵션) — 제동 시작 거리로 매칭
        if segments:
            d0 = float(df.at[seg["start_idx"], "distance"])
            corner_idx, seg_name = None, None
            for cg in segments:
                if d0 >= cg["start"] and d0 < cg["end_dist"]:
                    corner_idx = cg.get("corner_index")
                    seg_name = cg.get("name")
                    break
            stat["corner_index"] = corner_idx
            stat["segment_name"] = seg_name

        per_segment.append(stat)

    # 요약 통계
    summary = {}
    if per_segment:
        ds = pd.DataFrame(per_segment)
        def avg(col): return float(ds[col].dropna().mean()) if col in ds else None
        summary = {
            "num_segments": int(len(per_segment)),
            "avg_decel": avg("decel_avg"),
            "avg_brake_peak": avg("brake_peak"),
            "avg_trail_ratio": avg("trail_braking_ratio"),
            "avg_abs_on_ratio": avg("abs_on_ratio"),
            "avg_slip_lock_front": avg("slip_lock_ratio_front"),
            "avg_slip_lock_rear":  avg("slip_lock_ratio_rear"),
            "avg_slip_lr_diff_front": avg("slip_lr_diff_front_mean"),
            "avg_slip_lr_diff_rear":  avg("slip_lr_diff_rear_mean"),
            "avg_slip_fb_diff":       avg("slip_fb_diff_mean"),
            "avg_g_lon_min": avg("g_lon_min"),
            "avg_g_lat_peak_abs": avg("g_lat_peak_abs"),
            "avg_sus_lr_diff_front": avg("sus_lr_diff_front"),
            "avg_sus_lr_diff_rear":  avg("sus_lr_diff_rear"),
            "avg_sus_fb_diff":       avg("sus_fb_diff"),
            "avg_bump_contact_front": avg("bump_contact_count_front"),
            "avg_bump_contact_rear":  avg("bump_contact_count_rear"),
            "avg_brake_temp_rise_front": avg("brake_temp_rise_front"),
            "avg_brake_temp_rise_rear":  avg("brake_temp_rise_rear"),
        }

    return {
        "segments": per_segment,
        "summary": summary
    }
