import logging
import httpx
from app.core.logging_config import setup_logging
from app.services.ocr_camera import HikSnapshotService

setup_logging()
logger = logging.getLogger(__name__)

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import get_settings  
from app.core.exceptions import AppError
from app.core.exception_handlers import app_error_handler, unhandled_error_handler
from app.db.database import  init_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.ocr_session_jobs import cleanup_sessions_job
from app.routers import ocr


settings = get_settings()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ⭐ Startup
    await init_db()

    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=3.0, read=6.0, write=6.0, pool=6.0),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    
    app.state.hik_snapshot_service = HikSnapshotService(
        client=app.state.http_client,
        username=settings.HIK_CAMERA_USER,
        password=settings.HIK_CAMERA_PASSWORD,
    )
    

    # create scheduler in lifespan 
    app.state.scheduler = AsyncIOScheduler(timezone="UTC")

    app.state.scheduler.add_job(
        cleanup_sessions_job,
        trigger="interval",
        minutes=settings.JOB_CHECK_SESSION_INTERVAL,
        id="cleanup_sessions",
        replace_existing=True,  
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    app.state.scheduler.start()
    logger.info(
        "✅ APScheduler started: cleanup_sessions_job every %s minute(s)",
        settings.JOB_CHECK_SESSION_INTERVAL,
    )

    try:
        yield
    finally:
        # ⭐ Shutdown 
        # shutdown scheduler
        sch = getattr(app.state, "scheduler", None)
        if sch:
            try:
                sch.shutdown(wait=False)
            except Exception:
                logger.exception("scheduler shutdown failed")
            app.state.scheduler = None
        
        app.state.hik_snapshot_service = None 
        
        # close http client
        client = getattr(app.state, "http_client", None)
        if client:
            try:
                await client.aclose()
            except Exception:
                logger.exception("http_client close failed")
            app.state.http_client = None





# scheduler = AsyncIOScheduler(timezone="UTC")
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # ⭐ Startup
    
#     await init_db()
    
    
#     app.state.http_client = httpx.AsyncClient(
#         timeout=httpx.Timeout(connect=3.0, read=6.0, write=6.0, pool=6.0),
#         limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
#     )
    
#     # ✅ Start session cleanup scheduler
#     scheduler.add_job(
#         cleanup_sessions_job,
#         trigger="interval",
#         minutes=settings.JOB_CHECK_SESSION_INTERVAL,
#         id="cleanup_sessions",
#         max_instances=1,      # protect job overlap
#         coalesce=True,        # if a run is missed, combine into one run
#         misfire_grace_time=30
#     )
    
#     if not scheduler.running:
#         scheduler.start()
        
#     logger.info("✅ APScheduler started: cleanup_sessions_job every 1 minute")

#     yield  # <– cut line between startup and shutdown

#     # ⭐ Shutdown
#     try:
#         scheduler.shutdown(wait=False)
#     except Exception:
#         pass

#     if app.state.http_client:
#         await app.state.http_client.aclose()
#         app.state.http_client = None

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
# include exception handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
logger.info("🚀 App starting up...")


# Health check endpoint
@app.get("/health",status_code=200, tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "app_name": settings.APP_NAME,
}
    

@api_router.get("/")
async def Who():
    return {"message": "Who are you?"}

