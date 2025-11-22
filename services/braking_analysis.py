import pandas as pd
from typing import List

def analyze_braking_segments(df: pd.DataFrame, segments: List[dict], brake_threshold: float = 5.0) -> List[dict]:
    """
    각 코너 구간에 대해 브레이크 타이밍, 지속시간, 제동 강도 등을 분석해 리턴
    """
    results = []

    for seg in segments:
        try:
            start_dist = seg['start']
            end_dist = seg['end_dist']
            corner_index = seg['corner_index']

            sector_df = df[(df['distance'] >= start_dist) & (df['distance'] <= end_dist)].copy()
            if sector_df.empty:
                print(f"❌ [코너 {corner_index}] 세그먼트 내 데이터 없음 (거리 {start_dist}~{end_dist})")
                continue

            # 브레이크가 threshold 이상인 지점만 추출
            braking = sector_df[sector_df['brake'] > brake_threshold]
            if braking.empty:
                print(f"⚠️ [코너 {corner_index}] 브레이크 감지 안됨 (threshold={brake_threshold})")
                continue

            brake_start_idx = braking.index[0]

            # 브레이크 해제 지점 탐색
            below_thresh = braking[braking['brake'] < brake_threshold].index
            after_start = below_thresh[below_thresh > brake_start_idx]
            brake_end_idx = after_start.min() if not after_start.empty else sector_df.index[-1]

            if brake_end_idx < brake_start_idx:
                print(f"❌ [코너 {corner_index}] 브레이크 끝이 시작보다 앞에 있음 → skip")
                continue

            start_row = sector_df.loc[brake_start_idx]
            end_row = sector_df.loc[brake_end_idx]

            brake_start_dist = start_row['distance']
            brake_start_speed = start_row['speed']
            brake_duration = end_row['time'] - start_row['time']
            brake_distance = end_row['distance'] - start_row['distance']

            # 예외 처리: brake_duration 0 or NaN 방지
            if pd.isna(brake_duration) or brake_duration == 0:
                print(f"⚠️ [코너 {corner_index}] 브레이크 지속시간 0 또는 NaN → skip")
                continue

            end_speed = end_row['speed']
            brake_slope = (brake_start_speed - end_speed) / brake_duration if brake_duration > 0 else None

            result = {
                "corner_index": corner_index,
                "brake_start_dist": round(brake_start_dist, 2),
                "brake_start_speed": round(brake_start_speed, 2),
                "brake_duration": round(brake_duration, 3),
                "brake_distance": round(brake_distance, 2),
                "brake_slope": round(brake_slope, 2) if brake_slope is not None else None,
            }
            results.append(result)

            print(
                f"✅ [코너 {corner_index}] 제동 시작: {result['brake_start_dist']}m, "
                f"속도: {result['brake_start_speed']}km/h, 시간: {result['brake_duration']}s, "
                f"거리: {result['brake_distance']}m, 감속률: {result['brake_slope']}km/h/s"
            )

        except Exception as e:
            print(f"❌ [코너 {seg.get('corner_index', '?')}] 분석 중 오류 발생: {e}")

    return results
