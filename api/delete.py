from services.lap_data import fetch_lap_meta_and_data
from fastapi import APIRouter, Depends, HTTPException
from utils.supabase_client import supabase
from utils.auth import get_current_user_id

router = APIRouter()

@router.delete("/lap/{lap_id}")
def delete_lap(lap_id: str, user_id: str = Depends(get_current_user_id)):
    lap = fetch_lap_meta_and_data(lap_id)

    # ❌ 데이터가 없거나
    # ❌ 해당 user_id의 소유가 아닌 경우
    if not lap or lap["meta"]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="해당 랩을 찾을 수 없거나 권한이 없습니다.")

    # ✅ 삭제 처리
    supabase.table("lap_meta").delete().eq("id", lap_id).execute()
    supabase.table("lap_controls").delete().eq("lap_id", lap_id).execute()
    supabase.table("lap_vehicle_status").delete().eq("lap_id", lap_id).execute()
    supabase.table("lap_raw").delete().eq("lap_id", lap_id).execute()
    supabase.table("sector_results").delete().eq("lap_id", lap_id).execute()

    return {"status": "✅ 삭제 완료"}
