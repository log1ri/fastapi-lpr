from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings 

# create a MongoDB client using settings to avoid unused-import lint errors
client: AsyncIOMotorClient | None = None
db = None


def get_client() -> AsyncIOMotorClient:
    global client
    if client is None:
        client = AsyncIOMotorClient(settings.MONGO_URL)
    return client

def get_database():
    global db
    if db is None:
        db = get_client()[settings.MONGO_DB_NAME]
    return db