# services/lap_data.py
from utils.supabase_client import supabase
from services.insert import fetch_all_controls, fetch_all_vehicle_status

def fetch_lap_meta_and_data(lap_id: str):
    response = supabase.table("lap_meta").select("*").eq("id", lap_id).execute()
    meta = response.data[0] if response.data else None
    if not meta:
        return None

    controls = fetch_all_controls(lap_id)
    vehicle = fetch_all_vehicle_status(lap_id)

    return {
        "meta": meta,
        "controls": controls,
        "vehicle": vehicle
        # "sector_results" 제거 ✅
    }
