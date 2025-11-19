from fastapi import FastAPI, APIRouter
from app.core.config import settings  # ดึง config ที่เราสร้าง
from app.routers import ocr

# setup FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Basic FastAPI setup with core config",
)

# create main API router
api_router = APIRouter()
# include routers with API version prefix
app.include_router(api_router, prefix=settings.API_VERSION) 
# include OCR service router with API version prefix
app.include_router(ocr.router, prefix=settings.API_VERSION)


# Health check endpoint
@app.get("/",status_code=201, tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "app_name": settings.APP_NAME,
}
    

@api_router.get("/test")
async def test():
    return {"message": "Hello World"}

