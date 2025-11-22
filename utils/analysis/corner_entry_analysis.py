import pandas as pd
from typing import List, Dict
from utils.feedback_prompt import build_feedback_prompt
from services.ai_feedback import generate_ai_feedback

def detect_braking_zones(
    df: pd.DataFrame, brake_col: str = 'brake', time_col: str = 'time'
) -> List[Dict]:
    """
    고속 주행 중 급제동을 수행하는 브레이킹 존 감지
    조건: brake > 0, steerangle이 낮은 상태
    """
    zones = []
    in_zone = False
    start_idx = None

    for i in range(len(df)):
        brake = df.iloc[i][brake_col]
        steer = abs(df.iloc[i].get('steerangle', 0))

        if not in_zone and brake > 0.15 and steer < 5:
            in_zone = True
            start_idx = i

        elif in_zone and (brake <= 0.05 or steer >= 5):
            end_idx = i - 1
            zones.append({
                'start_idx': start_idx,
                'end_idx': end_idx,
                'start_time': df.iloc[start_idx][time_col],
                'end_time': df.iloc[end_idx][time_col],
            })
            in_zone = False

    if in_zone:
        end_idx = len(df) - 1
        zones.append({
            'start_idx': start_idx,
            'end_idx': end_idx,
            'start_time': df.iloc[start_idx][time_col],
            'end_time': df.iloc[end_idx][time_col],
        })

    return zones

def detect_corner_entry(
    df: pd.DataFrame,
    brake_col: str = 'brake',
    steer_col: str = 'steerangle',
    time_col: str = 'time'
) -> List[Dict]:
    """
    코너 진입 감지 로직:
    - brake > 0.05
    - steerangle > 5도
    두 조건이 동시에 지속되는 구간 감지
    """
    entry_segments = []
    in_entry = False
    start_idx = None

    for i in range(len(df)):
        brake = df.iloc[i][brake_col]
        steer = abs(df.iloc[i][steer_col])

        if not in_entry and brake < 100 and brake > 0.05 and steer > 5:
            in_entry = True
            start_idx = i
        elif in_entry and (brake <= 0.05):
            end_idx = i - 1
            entry_segments.append({
                'start_idx': start_idx,
                'end_idx': end_idx,
                'start_time': df.iloc[start_idx][time_col],
                'end_time': df.iloc[end_idx][time_col],
            })
            in_entry = False

    if in_entry:
        end_idx = len(df) - 1
        entry_segments.append({
            'start_idx': start_idx,
            'end_idx': end_idx,
            'start_time': df.iloc[start_idx][time_col],
            'end_time': df.iloc[end_idx][time_col],
        })

    print(f"🚩 감지된 진입 구간 수: {len(entry_segments)}")
    return entry_segments

def analyze_corner_entry_and_feedback(
    df: pd.DataFrame, driver_level: str = "beginner"
) -> List[Dict]:
    """
    코너 진입 구간 감지 후 피드백 생성
    - 감속량
    - 조향각 변화
    - 브레이크 평균 강도
    """
    results = []
    entries = detect_corner_entry(df)

    for idx, segment in enumerate(entries):
        try:
            start, end = segment['start_idx'], segment['end_idx']
            segment_df = df.iloc[start:end + 1]

            deceleration = segment_df['speed'].diff().mean() * -1
            steer_variability = segment_df['steerangle'].diff().abs().mean()
            brake_avg = segment_df['brake'].mean()
            duration = segment['end_time'] - segment['start_time']

            segment['avg_deceleration'] = deceleration
            segment['steer_variability'] = steer_variability
            segment['avg_brake'] = brake_avg
            segment['duration'] = duration

            # GPT 피드백 생성
            prompt = build_feedback_prompt(segment, idx, mode="braking", driver_level=driver_level)
            feedback, _ = generate_ai_feedback(prompt)

        except Exception as e:
            print(f"❌ 코너 진입 분석 실패 (구간 {idx + 1}): {repr(e)}")
            feedback = "⚠️ 현재 AI 피드백 서버에 연결할 수 없습니다.\n기본 분석 결과만 제공됩니다."

        segment['feedback'] = feedback
        results.append(segment)

    return results
