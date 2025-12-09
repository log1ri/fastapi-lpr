from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import get_settings 
from app.models.sample import Sample
from app.models.user_org import User
from app.models.ocr_log import OCRLogImages, OCRLogContent, OCRLogMessage,OCRLog
from app.models.cameras import cameras


# create a MongoDB client using settings to avoid unused-import lint errors
client: AsyncIOMotorClient | None = None
db = None
settings = get_settings()

async def init_db():
    global client
    client = AsyncIOMotorClient(settings.MONGO_URL)
    await init_beanie(
        database=client[settings.MONGO_DB_NAME],
        document_models=[
            Sample,
            OCRLog,
            User,
            cameras,
        ],  
    )
    
print("\n" + "=" * 60)
print("✅  MongoDB / Beanie Initialized")
print(f"📂  DB  : {settings.MONGO_DB_NAME}")
print("=" * 60 + "\n")