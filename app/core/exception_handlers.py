from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.exceptions import AppError
import logging
logger = logging.getLogger(__name__)

async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "extra": exc.extra,
        },
    )
    


async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error", "code": "UNHANDLED"},
    )