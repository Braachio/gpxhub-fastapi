# services/analyze_sector_times.py

from supabase import Client
import pandas as pd

def split_into_sectors(df: pd.DataFrame, num_sectors: int = 3) -> list[pd.DataFrame]:
    max_distance = df['distance'].max()
    sector_length = max_distance / num_sectors
    sectors = []
    for i in range(num_sectors):
        start = i * sector_length
        end = (i + 1) * sector_length
        sector_df = df[(df['distance'] >= start) & (df['distance'] < end)].copy()
        sector_df['sector'] = i + 1  # sector_number (1부터 시작)
        sector_df['sector_index'] = i  # sector_index (0부터 시작)
        sectors.append(sector_df)
    return sectors

def upload_sector_results(supabase: Client, lap_id: str, user_id: str, track: str, df: pd.DataFrame):
    sector_dfs = split_into_sectors(df)
    for sector_df in sector_dfs:
        sector_number = int(sector_df['sector'].iloc[0])
        sector_index = int(sector_df['sector_index'].iloc[0])
        sector_time = sector_df['time'].iloc[-1] - sector_df['time'].iloc[0]
        sector_start = sector_df['distance'].iloc[0]
        sector_end = sector_df['distance'].iloc[-1]

        supabase.table('sector_results').insert({
            'user_id': user_id,
            'lap_id': lap_id,
            'track': track,
            'sector_index': sector_index,   # ✅ DB 내부 정렬용 (0부터)
            'sector_number': sector_number, # ✅ 사용자 표시용 (1부터)
            'sector_time': sector_time,
            'sector_start': sector_start,
            'sector_end': sector_end,
        }).execute()

def get_sector_summary(df: pd.DataFrame, num_sectors: int = 3) -> list[dict]:
    """응답용 sector summary 리스트 반환"""
    sectors = split_into_sectors(df, num_sectors)
    summary = []
    for sector_df in sectors:
        sector_num = int(sector_df['sector'].iloc[0])
        time = sector_df['time'].iloc[-1] - sector_df['time'].iloc[0]
        summary.append({"sector": sector_num, "best_time": round(time, 3)})
    return summary
