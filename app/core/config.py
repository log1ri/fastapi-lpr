from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    ALLOWED_ORIGINS: list[str] = ["*"]
    
    API_VERSION: str = "/api/v1"
    APP_NAME: str = "LPR FastAPI"
    APP_ENV: str = "development"
    
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "my_database"
    
    DO_SPACES_KEY: str
    DO_SPACES_SECRET: str
    DO_SPACES_REGION: str = "sgp1"
    DO_SPACES_ENDPOINT: str
    DO_SPACES_BUCKET: str
    DO_SPACES_CDN_DOMAIN: str | None = None
    ORI_IMG_LOG_PATH_PREFIX: str
    PRO_IMG_LOG_PATH_PREFIX: str

    ISSUE_LOG_PATH_PREFIX: str
    
    PLATE_MODEL_PATH: str
    OCR_MODEL_PATH: str
    
    MODEL: str = "yolo"
    
    YOLO_PLATE_CONF: float = 0.5
    YOLO_OCR_CONF: float = 0.7
    
    YOLO_IMGSZ: int = 640
    
    PLATE_MODEL_NAME: str
    OCR_MODEL_NAME: str
    
    SESSION_TIMEOUT_MINUTES: int = 15
    JOB_CHECK_SESSION_INTERVAL: int = 1
    
    HIK_CAMERA_USER: str
    HIK_CAMERA_PASSWORD: str
    MIN_DURATION_SEC: int = 60
    T_CONFLICT_SEC: int = 60
    T_CLOSE_SEC: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache
def get_settings() -> Settings:
    return Settings()