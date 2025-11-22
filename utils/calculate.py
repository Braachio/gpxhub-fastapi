import pandas as pd

def calculate_distance(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if 'time' not in df.columns or 'speed' not in df.columns:
        raise ValueError("CSV에 'time' 또는 'speed' 열이 없습니다.")

    df = df.sort_values('time')
    df['distance'] = 0.0

    for i in range(1, len(df)):
        dt = df.iloc[i]['time'] - df.iloc[i - 1]['time']
        speed_kmh = df.iloc[i - 1]['speed']
        speed_ms = speed_kmh / 3.6
        df.at[df.index[i], 'distance'] = df.at[df.index[i - 1], 'distance'] + speed_ms * dt

    return df


# def convert_speed_to_kmph(df: pd.DataFrame) -> pd.DataFrame:
#     """
#     speed 열이 m/s 단위일 경우, km/h로 변환하여 덮어씌웁니다.
#     """
#     df = df.copy()
#     if 'speed' in df.columns:
#         df['speed'] = pd.to_numeric(df['speed'], errors='coerce') * 3.6
#     return df