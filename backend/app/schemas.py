from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import datetime

class CameraSchema(BaseModel):
    id: int
    name: str
    url: str
    status: str

    class Config:
        orm_mode = True

class TrackedObjectSchema(BaseModel):
    label: str
    bbox: Dict[str, Any]
    confidence: float

class SuspiciousMomentSchema(BaseModel):
    id: int
    timestamp: datetime.datetime
    camera_id: int
    event_type: str
    confidence: float
    thumbnail_path: Optional[str]
    video_path: Optional[str]
    meta: Optional[Dict[str, Any]]

    class Config:
        orm_mode = True
