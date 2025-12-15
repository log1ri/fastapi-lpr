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
    # IMG_LOG_PATH_PREFIX: str
    ORI_IMG_LOG_PATH_PREFIX: str
    PRO_IMG_LOG_PATH_PREFIX: str

    ISSUE_LOG_PATH_PREFIX: str

    class Config:
        env_file = ".env"
        case_sensitive = True

# settings = Settings()
@lru_cache
def get_settings() -> Settings:
    return Settings()