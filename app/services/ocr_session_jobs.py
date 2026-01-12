# app/scheduler/session_jobs.py
from app.services.ocr_session_services import SessionService
from app.core.config import get_settings  
import logging
logger = logging.getLogger("session-job")
settings = get_settings()

async def cleanup_sessions_job():
    try:

        abandoned1 = await SessionService.mark_abandoned_sessions(timeout_minutes=settings.SESSION_TIMEOUT_MINUTES)
        abandoned2 = await SessionService.mark_stale_open_sessions_without_lastseen(timeout_minutes=settings.SESSION_TIMEOUT_MINUTES)

        if abandoned1 or abandoned2:
            logger.info(f"[session-job] abandoned updated: {abandoned1 + abandoned2}")
    except Exception:
        logger.exception("cleanup_sessions_job failed")