from supabase import Client
from typing import List


def get_corner_segments_for_track(supabase: Client, track_name: str) -> List[dict]:
    print(f"🔍 Fetching corner_segments for track: '{track_name.lower()}'")

    response = supabase.table("corner_segments") \
        .select("corner_index, name, start, end_dist") \
        .eq("track", track_name.lower()) \
        .order("corner_index") \
        .execute()

    print("📦 Raw Supabase Response:", response)

    return response.data or []
