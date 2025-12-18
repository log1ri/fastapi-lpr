import logging
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import get_settings  
from app.core.exceptions import AppError
from app.core.exception_handlers import app_error_handler, unhandled_error_handler
from app.db.database import  init_db
from app.routers import ocr
from app.routers import test


settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ⭐ Startup
    await init_db()
    # print("\n" + "=" * 60)
    # print("✅  MongoDB Connected")
    # print(f"📂  DB    : {settings.MONGO_DB_NAME}")
    # print("=" * 60 + "\n")

    yield  # <– cut line between startup and shutdown

    # ⭐ Shutdown
    # client.close()
    # print("\n" + "=" * 60)
    # print("🛑  MongoDB Disconnected")
    # print("=" * 60 + "\n")

# setup FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Basic FastAPI setup with core config",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# create main API router
api_router = APIRouter()
# include routers with API version prefix
app.include_router(api_router, prefix=settings.API_VERSION) 
# include OCR service router with API version prefix
app.include_router(ocr.router, prefix=settings.API_VERSION)
app.include_router(test.router, prefix=settings.API_VERSION)
# include exception handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
logger.info("🚀 App starting up...")



@app.on_event("startup")
async def startup_db_client():
    pass


@app.on_event("shutdown")
async def shutdown_db_client():
    pass

# Health check endpoint
@app.get("/health",status_code=200, tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "app_name": settings.APP_NAME,
}
    

@api_router.get("/")
async def test():
    return {"message": "Who are you?"}

