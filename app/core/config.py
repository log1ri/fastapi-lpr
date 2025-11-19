from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_VERSION: str = "/api/v1"
    APP_NAME: str = "LPR FastAPI"
    APP_ENV: str = "development"
    
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "my_database"


    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()