from supabase import Client
import pandas as pd
from typing import List


def split_by_fixed_segments(df: pd.DataFrame, segments: List[dict]) -> List[pd.DataFrame]:
    sector_dfs = []
    for i, segment in enumerate(segments):
        start = segment['start']
        end = segment['end_dist']
        sector_df = df[(df['distance'] >= start) & (df['distance'] < end)].copy()
        sector_df['sector'] = i + 1
        sector_df['corner_index'] = segment['corner_index']
        sector_df['segment_name'] = segment['name']
        sector_dfs.append(sector_df)
    return sector_dfs


def fetch_corner_segments(supabase: Client, track_name: str) -> List[dict]:
    """
    Supabase에서 트랙별 코너 세그먼트 정보를 불러옴
    """
    print(f"🔍 Fetching corner_segments for track: '{track_name}'")
    response = (
        supabase.table("corner_segments")
        .select("*")
        .eq("track", track_name.lower())
        .order("corner_index", desc=False)
        .execute()
    )
    print(f"📦 Raw Supabase Response: data={response.data} count={getattr(response, 'count', None)}")
    return response.data or []


def get_track_name_from_lap_id(supabase: Client, lap_id: str) -> str:
    """
    lap_meta 테이블에서 lap_id에 해당하는 track 값을 가져옴
    """
    response = supabase.table("lap_meta").select("track").eq("id", lap_id).execute()
    data = response.data[0] if response.data else None
    if not data or "track" not in data:
        raise ValueError(f"Track not found for lap_id: {lap_id}")
    return data["track"]


def upload_sector_results_by_lap_id(
    supabase: Client,
    lap_id: str,
    user_id: str,
    df: pd.DataFrame,
):
    """
    lap_id 기반으로 track 정보와 고정 corner segment 구간을 불러와 섹터 결과 업로드
    """
    track = get_track_name_from_lap_id(supabase, lap_id)
    segments = fetch_corner_segments(supabase, track)
    sector_dfs = split_by_fixed_segments(df, segments)

    for i, sector_df in enumerate(sector_dfs):
        if sector_df.empty:
            continue
        corner_index = int(sector_df['corner_index'].iloc[0])
        sector_number = int(sector_df['sector'].iloc[0])
        sector_name = sector_df['segment_name'].iloc[0]
        sector_time = sector_df['time'].iloc[-1] - sector_df['time'].iloc[0]
        sector_start = sector_df['distance'].iloc[0]
        sector_end = sector_df['distance'].iloc[-1]

        supabase.table('sector_results').insert({
            'user_id': user_id,
            'lap_id': lap_id,
            'track': track,
            'sector_index': corner_index,  # corner_index를 sector_index로 매핑
            'sector_number': sector_number,
            'sector_time': sector_time,
            'sector_start': sector_start,
            'sector_end': sector_end,
        }).execute()


def get_sector_summary_by_lap_id(supabase: Client, lap_id: str, df: pd.DataFrame) -> List[dict]:
    track = get_track_name_from_lap_id(supabase, lap_id)
    corner_segments = fetch_corner_segments(supabase, track)

    summary = []
    for segment in corner_segments:
        start = segment['start']
        end = segment['end_dist']
        name = segment.get('name') or f"구간 {segment['corner_index'] + 1}"
        segment_df = df[(df['distance'] >= start) & (df['distance'] < end)].copy()

        if segment_df.empty:
            continue

        time = segment_df['time'].iloc[-1] - segment_df['time'].iloc[0]

        summary.append({
            "sector": segment['corner_index'] + 1,
            "name": name,
            "best_time": round(time, 3),
            "sector_start": round(start, 2),
            "sector_end": round(end, 2)
        })

    return summary