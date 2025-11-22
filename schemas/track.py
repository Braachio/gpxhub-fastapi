from pydantic import BaseModel

class CornerSegment(BaseModel):
    corner_index: int
    name: str
    start: float
    end_dist: float
