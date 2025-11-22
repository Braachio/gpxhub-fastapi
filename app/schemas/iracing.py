from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class TrainingDataCreate(BaseModel):
    """Legacy schema: Single participant training data"""
    subsession_id: int
    cust_id: int

    i_rating: Optional[int] = None
    sof: Optional[int] = None
    avg_opponent_ir: Optional[int] = None
    max_opponent_ir: Optional[int] = None
    min_opponent_ir: Optional[int] = None
    ir_diff_from_avg: Optional[int] = None

    safety_rating: Optional[float] = None
    avg_incidents_per_race: Optional[float] = None
    dnf_rate: Optional[float] = None
    recent_avg_finish_position: Optional[float] = None
    win_rate: Optional[float] = None
    ir_trend: Optional[float] = None
    sr_trend: Optional[float] = None
    top5_rate: Optional[float] = None
    top10_rate: Optional[float] = None

    track_id: Optional[int] = None
    car_id: Optional[int] = None
    series_id: Optional[int] = None
    starting_position: Optional[int] = None
    actual_finish_position: Optional[int] = None
    actual_incidents: Optional[int] = None
    total_participants: Optional[int] = None
    actual_dnf: Optional[bool] = None

    weather_temp: Optional[float] = None
    track_temp: Optional[float] = None
    relative_humidity: Optional[float] = None
    wind_speed: Optional[float] = None

    session_start_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantFeatures(BaseModel):
    """Features for ML training"""
    iRating: Optional[int] = None
    sof: Optional[int] = None
    startingPosition: Optional[int] = None
    avgIncidentsPerRace: Optional[float] = None
    trackId: Optional[int] = None
    carId: Optional[int] = None
    seriesId: Optional[int] = None
    sessionStartTime: Optional[str] = None
    totalParticipants: Optional[int] = None
    safetyRating: Optional[float] = None
    
    # Additional optional features
    avgOpponentIr: Optional[int] = None
    maxOpponentIr: Optional[int] = None
    minOpponentIr: Optional[int] = None
    irDiffFromAvg: Optional[int] = None
    dnfRate: Optional[float] = None
    recentAvgFinishPosition: Optional[float] = None
    winRate: Optional[float] = None
    irTrend: Optional[float] = None
    srTrend: Optional[float] = None
    top5Rate: Optional[float] = None
    top10Rate: Optional[float] = None
    actualFinishPosition: Optional[int] = None
    actualIncidents: Optional[int] = None
    actualDnf: Optional[bool] = None
    weatherTemp: Optional[float] = None
    trackTemp: Optional[float] = None
    relativeHumidity: Optional[float] = None
    windSpeed: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantData(BaseModel):
    """Single participant data with features"""
    subsessionId: int
    custId: str  # String as required by collector
    features: ParticipantFeatures

    model_config = ConfigDict(from_attributes=True)


class TrainingDataBatch(BaseModel):
    """Batch of participants for training data collection"""
    participants: List[ParticipantData]

    model_config = ConfigDict(from_attributes=True)

