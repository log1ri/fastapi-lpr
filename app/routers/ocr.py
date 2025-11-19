from fastapi import APIRouter, HTTPException, Depends
from app.services.ocr_service import OCRService
from app.schemas.ocr import imgBody

router = APIRouter(
    prefix="/ocr-service",
    tags=["ocr-service"],
    responses={404: {"description": "Not foundd"}},
)

async def get_ocr_service():
    return OCRService()


# @router.post("/predict",status_code=201)
# async def predict(payload: imgBody):
#     OCRService()
#     return {"imgBase64": imgBase64}

@router.post("/predict",status_code=201)
async def predict(payload: imgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()
    result = ocr_service.predict(payload.imgBase64)
    return {"response": result}  

@router.post("/base64-to-img",status_code=201)
async def decoded(payload: imgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()
    result = ocr_service.decode_base64(payload.imgBase64)
    return {"response": result}  