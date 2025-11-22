# services/preprocessing.py

import csv
from io import StringIO
import pandas as pd

from utils.calculate import calculate_distance
from services.purification import correct_autoblip_throttle  # 순환 이슈 시 try/except로 lazy import 처리


# ── 공통 유틸 ──────────────────────────────────────────────────────────────────
def deduplicate_columns(columns):
    seen, out = {}, []
    for c in columns:
        k = c.strip().lower()
        if k in seen:
            seen[k] += 1
            k = f"{k}_{seen[k]}"
        else:
            seen[k] = 0
        out.append(k)
    return out


def _guess_sep(lines):
    sample = "\n".join(lines[:30])
    try:
        return csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"]).delimiter
    except Exception:
        return ","


def _is_header(tokens):
    toks = [t.strip().lower() for t in tokens]
    return ("time" in toks) and (len(toks) >= 5)


_UNIT_TOKENS = {
    "s","sec","second","seconds","ms","millisecond","milliseconds",
    "km/h","kph","kmh","m/s","mps","mph","mi/h",
    "deg","deg/s","%","no","1/min","c","°c","mm","bar","psi","g","m","n","kn","pa","-",""
}
def _is_units(tokens):
    toks = [t.strip().lower() for t in tokens]
    # 단위 토큰 비율이 40% 이상이면 유닛 행으로 판단
    if not toks:
        return False
    match = sum(1 for t in toks if t in _UNIT_TOKENS or (t.endswith("/s") and t[:-2] in _UNIT_TOKENS))
    return (match / len(toks)) >= 0.4


def _find_header_unit_idx(lines, sep):
    """
    메타 영역 이후부터 스캔하며 헤더/유닛 행 인덱스를 찾아 반환.
    반환: (header_idx, unit_idx or None)
    """
    # 메타 블록은 보통 10~20줄. 5~60줄 범위에서 탐색
    start, end = 0, min(len(lines)-1, 80)
    for i in range(start, end):
        toks = lines[i].rstrip("\n").split(sep)
        if _is_header(toks):
            # 바로 다음 줄이 유닛이면 unit_idx=i+1
            if i+1 < len(lines):
                toks2 = lines[i+1].rstrip("\n").split(sep)
                if _is_units(toks2):
                    return i, i+1
            return i, None
    # 못 찾으면 None
    return None, None


def _normalize_unit(u):
    if not u:
        return None
    u = u.strip().lower()
    if u in {"km/h","kph","kmh"}: return "km/h"
    if u in {"m/s","mps"}:        return "m/s"
    if u in {"mph","mi/h"}:       return "mph"
    if u in {"s","sec","second","seconds"}: return "s"
    if u in {"ms","millisecond","milliseconds"}: return "ms"
    return u


# ── 메인 전처리 ────────────────────────────────────────────────────────────────
def preprocess_csv_data(lines: list[str]) -> pd.DataFrame:
    """
    1) 구분자/헤더/단위 행 자동 탐지
    2) read_csv로 단위 행을 건너뛰어 로드
    3) 컬럼 소문자화+중복정리, 단위 기반 변환(m/s·mph→km/h)
    4) 결측/보조열 정리, distance 생성, 오토블립 보정, gear 정수화
    """
    # (이전 호환: 16번째 줄 제거가 필요했다면 유지)
    if len(lines) > 15:
        lines.pop(15)

    # 1) 구분자/헤더/유닛 탐지
    sep = _guess_sep(lines)
    header_idx, unit_idx = _find_header_unit_idx(lines, sep)

    if header_idx is None:
        raise ValueError("헤더 행(Time, Speed 등)을 찾지 못했습니다. CSV 포맷을 확인하세요.")

    header_line = lines[header_idx].strip()
    unit_line = lines[unit_idx].strip() if unit_idx is not None else ""

    header_cols_raw = [c.strip().lower() for c in header_line.split(sep)]
    header_cols_norm = deduplicate_columns(header_cols_raw)

    unit_vals_raw = [u.strip().lower() for u in unit_line.split(sep)] if unit_line else []
    unit_map_raw = dict(zip(header_cols_norm, unit_vals_raw))
    unit_map = {k: _normalize_unit(v) for k, v in unit_map_raw.items()}

    # 2) 실제 데이터 로드 (헤더부터 읽고, 단위 행은 skip)
    start_from_header = "\n".join(lines[header_idx:])
    skiprows_rel = [1] if unit_idx == header_idx + 1 else None

    read_csv_kwargs = dict(sep=sep, header=0, on_bad_lines="skip", skiprows=skiprows_rel)

    try:
        df = pd.read_csv(StringIO(start_from_header), engine="c", low_memory=False, **read_csv_kwargs)
    except Exception:
        df = pd.read_csv(StringIO(start_from_header), engine="python", **read_csv_kwargs)

    # 컬럼 정규화
    df.columns = deduplicate_columns([c.strip().lower() for c in df.columns])

    # 3) 시간 컬럼 자동 탐지/리네임(+ms→s)
    time_col = next((c for c in df.columns if c.startswith("time")), None)
    if time_col is None and "timestamp" in df.columns:
        time_col = "timestamp"
    if time_col is None:
        # 유닛으로 추정
        cand = [c for c, u in unit_map.items() if c in df.columns and u in ("s","ms")]
        time_col = cand[0] if cand else None
    if time_col is None:
        raise ValueError("'time' 열이 없음 (time/time(s)/timestamp를 찾지 못함)")

    if time_col != "time":
        df.rename(columns={time_col: "time"}, inplace=True)

    time_unit = (unit_map.get(time_col) or "").lower()
    if time_unit in ("ms",):
        df["time"] = pd.to_numeric(df["time"], errors="coerce") / 1000.0

    # 4) 단위 기반 수치 변환 (숫자만 추출 → 숫자화 → 유닛 변환)
    for col in df.columns:
        df[col] = (
            df[col].astype(str)
                   .str.replace(r"[^0-9\.\-eE+]", "", regex=True)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")
        u = unit_map.get(col)
        if u == "m/s":
            df[col] = df[col] * 3.6
        elif u == "mph":
            df[col] = df[col] * 1.609

    # 5) 결측/보조열 정리
    df = df.dropna(subset=["time"])         # time 없는 행 제거
    df = df.dropna()                         # 나머지 결측 제거(필요시 완화 가능)
    df = df[[c for c in df.columns if not c.startswith("time_")]]

    # 6) distance 생성(없으면)
    if "distance" not in df.columns:
        df = calculate_distance(df)

    # 7) 오토블립/브레이크100 보정
    try:
        df, fixed_count = correct_autoblip_throttle(df)
    except Exception:
        from services.purification import correct_autoblip_throttle as _correct
        df, fixed_count = _correct(df)
    print(f"🛠️ 오토블립/브레이크100 보정 행 수: {fixed_count}")

    # 8) 기어 정수화
    if "gear" in df.columns:
        df["gear"] = pd.to_numeric(df["gear"], errors="coerce").fillna(0).astype(int)

    return df
