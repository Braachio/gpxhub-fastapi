import pandas as pd
from typing import Tuple

# def remove_straight_sections(df: pd.DataFrame) -> pd.DataFrame:
#     print("🚀 remove_straight_sections 진입")

#     try:
#         if "throttle" not in df.columns or "time" not in df.columns:
#             raise ValueError("❌ 'throttle' 또는 'time' 컬럼이 없습니다.")
        
#         df = df.copy()
#         df = df.dropna(subset=["throttle", "time"])  # ✅ NaN 제거
#         if df.empty:
#             raise ValueError("❌ DataFrame이 비어 있습니다.")

#         drop_indices = []
#         i = 0

#         while i < len(df):
#             try:
#                 if df.loc[i, "throttle"] >= 99.5:
#                     start_idx = i
#                     start_time = df.loc[i, "time"]

#                     while i < len(df) and df.loc[i, "throttle"] >= 99.5:
#                         i += 1

#                     end_idx = i - 1
#                     end_time = df.loc[end_idx, "time"]
#                     duration = end_time - start_time

#                     if duration >= 4.0:
#                         drop_indices.extend(range(start_idx + 100, end_idx + 1 - 100))
#                 else:
#                     i += 1
#             except Exception as inner_e:
#                 print(f"⚠️ 내부 루프 예외 (i={i}): {inner_e}")
#                 i += 1

#         df_cleaned = df.drop(index=drop_indices).reset_index(drop=True)
#         print(f"🧹 직선 구간 {len(drop_indices)}개 행 제거 완료")

#         # ✅ 전체 랩 앞뒤 0.5초 제거
#         total_start_time = df_cleaned["time"].min()
#         total_end_time = df_cleaned["time"].max()

#         df_cleaned = df_cleaned[
#             (df_cleaned["time"] - total_start_time >= 0.6) &
#             (total_end_time - df_cleaned["time"] >= 0.6)
#         ].reset_index(drop=True)

#         print("🧹 전체 랩 앞뒤 0.5초 구간 제거 완료")

#         return df_cleaned

#     except Exception as e:
#         print(f"❌ 내부 에러 발생 in remove_straight_sections: {e}")
#         raise ValueError("🔥 remove_straight_sections 내부 에러")


def correct_autoblip_throttle(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    오토블립 및 브레이크 조건에서 비정상 스로틀 값을 0으로 보정
    - 기어 다운 시, 주변 프레임에서 스로틀 튐 감지 시 0으로 설정

    Returns:
        df: 보정된 DataFrame
        throttle_fixed: 보정된 행 수
    """
    df = df.copy().reset_index(drop=True)
    throttle_fixed = 0

    for i in range(3, len(df) - 70):
        gear_now = df.loc[i, "gear"]
        gear_prev = df.loc[i - 1, "gear"]
        brake_now = df.loc[i, "brake"]

        # 기어 다운 감지
        if gear_now < gear_prev:
            # 오토블립 발생 가능 구간
            for j in range(i - 3, i + 60):  # 앞뒤 3~8프레임
                if 0 <= j < len(df):
                    if df.loc[j, "throttle"] > 0:
                        df.loc[j, "throttle"] = 0.0
                        throttle_fixed += 1

            # 추가로 i+30~70 구간도 확인 (후속 튐 대응)
            for j in range(i + 30, i + 71):
                if 0 <= j < len(df) and df.loc[j, "throttle"] > 0:
                    df.loc[j, "throttle"] = 0.0
                    throttle_fixed += 1

    return df, throttle_fixed
