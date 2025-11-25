from fastapi import APIRouter
from app.models.sample import Sample

router = APIRouter(prefix="/test", tags=["test"])

@router.post("/mongo")
async def test_mongo():
    doc = Sample(message="test", timestamp="2024-06-01T12:00:00Z")
    await doc.insert()
    return {"msg": "Inserted", "id": str(doc.id)}