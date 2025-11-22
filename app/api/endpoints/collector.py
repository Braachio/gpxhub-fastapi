from fastapi import APIRouter, Depends, HTTPException, Request
from supabase import Client
from typing import Dict, Any

from app.core.supabase import get_supabase_client
from app.schemas.iracing import TrainingDataCreate, TrainingDataBatch, ParticipantData


router = APIRouter()


def _convert_participant_to_db_format(participant: ParticipantData) -> Dict[str, Any]:
    """Convert participant data from collector format to database format"""
    features = participant.features
    
    return {
        "subsession_id": participant.subsessionId,
        "cust_id": int(participant.custId),  # Convert string to int for DB
        "i_rating": features.iRating,
        "sof": features.sof,
        "avg_opponent_ir": features.avgOpponentIr,
        "max_opponent_ir": features.maxOpponentIr,
        "min_opponent_ir": features.minOpponentIr,
        "ir_diff_from_avg": features.irDiffFromAvg,
        "safety_rating": features.safetyRating,
        "avg_incidents_per_race": features.avgIncidentsPerRace,
        "dnf_rate": features.dnfRate,
        "recent_avg_finish_position": features.recentAvgFinishPosition,
        "win_rate": features.winRate,
        "ir_trend": features.irTrend,
        "sr_trend": features.srTrend,
        "top5_rate": features.top5Rate,
        "top10_rate": features.top10Rate,
        "track_id": features.trackId,
        "car_id": features.carId,
        "series_id": features.seriesId,
        "starting_position": features.startingPosition,
        "actual_finish_position": features.actualFinishPosition,
        "actual_incidents": features.actualIncidents,
        "total_participants": features.totalParticipants,
        "actual_dnf": features.actualDnf,
        "weather_temp": features.weatherTemp,
        "track_temp": features.trackTemp,
        "relative_humidity": features.relativeHumidity,
        "wind_speed": features.windSpeed,
        "session_start_time": features.sessionStartTime,  # String format, DB will handle conversion
    }


@router.post("/collect/training-data")
async def collect_training_data(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
):
    """
    Collect training data from iRacing session.
    
    Supports two formats:
    1. Batch format (new): {"participants": [...]}
    2. Single format (legacy): single participant object
    
    Args:
        request: FastAPI request object (to parse JSON manually)
        supabase: Supabase client
        
    Returns:
        Upserted data with count
    """
    try:
        # Parse JSON body manually to support both formats
        body = await request.json()
        upsert_payloads: list[Dict[str, Any]] = []
        
        # Try batch format first (new format)
        if "participants" in body:
            batch = TrainingDataBatch(**body)
            upsert_payloads = [
                _convert_participant_to_db_format(p) 
                for p in batch.participants
            ]
        # Fall back to single format (legacy)
        elif "subsession_id" in body and "cust_id" in body:
            single = TrainingDataCreate(**body)
            upsert_payloads = [single.model_dump(mode="json")]
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid payload format. Expected either 'participants' array or single participant object."
            )

        if not upsert_payloads:
            raise HTTPException(
                status_code=400,
                detail="No participant data provided.",
            )

        # Batch upsert all participants
        response = supabase.table("iracing_ml_training_data").upsert(
            upsert_payloads,
            on_conflict="subsession_id,cust_id",
            returning="representation",
        ).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Supabase upsert returned no data.",
            )

        return {
            "data": response.data,
            "count": len(response.data),
            "message": f"Successfully upserted {len(response.data)} participant(s)"
        }
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=str(exc)) from exc

