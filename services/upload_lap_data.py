from supabase import Client
import pandas as pd
import hashlib
from services.analyze_sector_times import upload_sector_results

def generate_lap_hash(df: pd.DataFrame) -> str:
    # CSV 형식으로 변환 후 SHA256 해시 생성
    data_str = df.to_csv(index=False)
    return hashlib.sha256(data_str.encode()).hexdigest()

def upload_lap_data(supabase: Client, user_id: str, track: str, df: pd.DataFrame, car: str) -> dict:
    # ✅ 1. 해시 생성
    lap_hash = generate_lap_hash(df)

    # ✅ 2. 중복 검사
    existing = supabase.table("lap_meta").select("id").eq("hash", lap_hash).execute()
    if existing.data:
        return {"error": "❌ 중복된 랩 데이터입니다."}

    # ✅ 3. lap_meta 저장
    lap_time = df['time'].iloc[-1] - df['time'].iloc[0]
    insert_response = supabase.table("lap_meta").insert({
        "user_id": user_id,
        "track": track,
        "car": car,
        "lap_time": lap_time,
        "hash": lap_hash,  # 해시 저장
        "display_name": display_name,
        "lap_time": lap_time,
    }).execute()

    lap_id = insert_response.data[0]['id']

    # ✅ 4. control inputs 저장
    control_data = df[['time', 'throttle', 'brake', 'steering']].to_dict("records")
    for row in control_data:
        row['lap_id'] = lap_id
    supabase.table("lap_controls").insert(control_data).execute()

    # ✅ 5. vehicle telemetry 저장
    telemetry_data = df[['time', 'speed', 'distance', 'rpm', 'gear']].to_dict("records")
    for row in telemetry_data:
        row['lap_id'] = lap_id
    supabase.table("lap_vehicle_status").insert(telemetry_data).execute()

    # ✅ 6. sector_results 저장
    sector_results = upload_sector_results(supabase, lap_id, user_id, track, df)

    return {
        "lap_id": lap_id,
        "sector_results": sector_results
    }
