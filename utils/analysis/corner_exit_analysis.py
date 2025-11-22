from typing import List, Dict
import pandas as pd
from services.ai_feedback import generate_ai_feedback
from utils.feedback_prompt import build_feedback_prompt

def detect_corner_exit(df: pd.DataFrame) -> List[Dict]:
    """
    조건 기반으로 탈출 구간 감지:
    - 브레이크 해제
    - 조향 안정화
    - 스로틀 증가
    - 기어 유지 또는 상승
    - 이후 스로틀 감소로 종료
    """

    if not {"time", "throttle", "brake", "steerangle", "gear"}.issubset(df.columns):
        print("❌ 필요한 컬럼 누락: time, throttle, brake, steerangle, gear")
        return []

    df = df.copy().reset_index(drop=True)

    # 파생 컬럼 생성
    df["throttle_diff"] = df["throttle"].diff().fillna(0)
    df["gear_diff"] = df["gear"].diff().fillna(0)
    df["steer_std"] = df["steerangle"].rolling(window=5, center=True).std().fillna(0)

    in_exit = False
    start_idx = None
    exit_segments = []

    for i in range(1, len(df)):
        row = df.iloc[i]

        if not in_exit:
            if (
                row["brake"] < 5
                and row["steer_std"] < 5
                and row["throttle_diff"] > 0.5
                and row["throttle"] > 5
                and row["gear_diff"] >= 0
            ):
                in_exit = True
                start_idx = i
        else:
            # 종료 조건: 스로틀 감소 + 스로틀 낮음
            window = df.iloc[max(i - 3, 0):i + 1]
            if (
                window["throttle_diff"].mean() < -0.5
                and row["throttle"] < 10
            ):
                exit_segments.append({
                    "start_idx": start_idx,
                    "end_idx": i,
                    "start_time": df.at[start_idx, "time"],
                    "end_time": df.at[i, "time"],
                })
                in_exit = False
                start_idx = None

    # 끝까지 감지 중이면 마무리 처리
    if in_exit and start_idx is not None:
        exit_segments.append({
            "start_idx": start_idx,
            "end_idx": len(df) - 1,
            "start_time": df.at[start_idx, "time"],
            "end_time": df.at[len(df) - 1, "time"],
        })

    print(f"🚩 감지된 탈출 구간 수: {len(exit_segments)}")
    return exit_segments


def calc_slip_ratio(row):
    """
    앞/뒤 좌우 휠 스피드 차이를 기반으로 슬립 발생 강도 계산
    """
    front_diff = abs(row["wheel_speed_lf"] - row["wheel_speed_rf"])
    rear_diff = abs(row["wheel_speed_lr"] - row["wheel_speed_rr"])
    return max(front_diff, rear_diff)

def analyze_corner_exit_and_feedback(
    controls: pd.DataFrame, 
    vehicle: pd.DataFrame, 
    driver_level: str = "beginner"  # 초보자 기본값
) -> List[Dict]:
    """
    코너 탈출 분석 + 슬립률, 스로틀 기울기, 조향 안정성 기반 AI 피드백 생성
    """
    try:
        df_controls = pd.DataFrame(controls)
        df_vehicle = pd.DataFrame(vehicle)

        if "time" not in df_controls.columns or "time" not in df_vehicle.columns:
            print("❌ time 칼럼이 없어 병합 불가")
            return []

        df = pd.merge(df_controls, df_vehicle, on="time", how="inner")

        required_cols = [
            "steerangle", "throttle",
            "wheel_speed_lf", "wheel_speed_rf",
            "wheel_speed_lr", "wheel_speed_rr"
        ]

        if not all(col in df.columns for col in required_cols):
            print("⚠️ 코너 분석에 필요한 칼럼이 부족함 (after merge)")
            return []

        segments = detect_corner_exit(df)

        for i, segment in enumerate(segments):
            sub_df = df.iloc[segment["start_idx"]:segment["end_idx"]].copy()
            sub_df = sub_df.dropna(subset=[
                "wheel_speed_lf", "wheel_speed_rf", "wheel_speed_lr", "wheel_speed_rr"
            ])

            # 🔸 슬립률
            slip_ratios = sub_df.apply(calc_slip_ratio, axis=1)
            segment["max_slip_ratio"] = slip_ratios.max()

            # 🔸 스로틀 기울기 (변화량 평균)
            sub_df["throttle_diff"] = sub_df["throttle"].diff()
            segment["avg_throttle_gradient"] = sub_df["throttle_diff"].mean()

            # 🔸 조향 안정성 (조향각 변화량 평균)
            sub_df["steer_diff"] = sub_df["steerangle"].diff()
            segment["steer_variability"] = sub_df["steer_diff"].abs().mean()

            # 🔸 좌우/전후 휠 속도 차이
            segment["wheel_slip_lr"] = (sub_df["wheel_speed_lf"] - sub_df["wheel_speed_rf"]).abs().mean()
            segment["wheel_slip_fb"] = (sub_df["wheel_speed_lf"] - sub_df["wheel_speed_lr"]).abs().mean()


            # 🧠 프롬프트 생성
            prompt = build_feedback_prompt(segment, i, mode="throttle", driver_level="beginner")

            # 🤖 AI 피드백 생성
            ai_feedback, source = generate_ai_feedback(prompt)
            segment["feedback"] = ai_feedback
            segment["feedback_source"] = source
            segment["raw_prompt"] = prompt  # (선택) 추후 분석용

        return segments

    except Exception as e:
        print(f"❌ 코너 분석 중 오류 발생: {repr(e)}")
        return []