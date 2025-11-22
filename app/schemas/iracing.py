from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TrainingDataCreate(BaseModel):
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

