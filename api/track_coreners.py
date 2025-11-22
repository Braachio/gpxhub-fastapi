from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client, Client
from schemas.track import CornerSegment
from services.track_corners import get_corner_segments_for_track
from typing import List
import os

router = APIRouter()

def get_supabase_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)

@router.get("/api/track-corners/{track_name}", response_model=List[CornerSegment])
def track_corners(track_name: str, supabase: Client = Depends(get_supabase_client)):
    corners = get_corner_segments_for_track(supabase, track_name)
    if not corners:
        raise HTTPException(status_code=404, detail="Track not found or no corner segments.")
    return corners
