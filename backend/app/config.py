from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://atlas:atlas_pass@db:5432/atlas"
    STORAGE_PATH: str = "./storage"
    CAMERA_URLS: List[str] = []
    MOTION_SENSITIVITY: float = 0.02
    PROCESS_EVERY_NTH_FRAME: int = 3
    BUFFER_SECONDS: int = 60
    PRE_EVENT_SECONDS: int = 10
    POST_EVENT_SECONDS: int = 10
    YOLO_MODEL_PATH: str = "/app/yolov8n.pt"

    class Config:
        env_file = ".env"

settings = Settings()
