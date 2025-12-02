from fastapi import APIRouter, HTTPException, Depends
from app.services.ocr_service import OCRService
from app.schemas.ocr import ImgBody
from fastapi.concurrency import run_in_threadpool


router = APIRouter(
    prefix="/ocr-service",
    tags=["ocr-service"],
    responses={404: {"description": "Not foundd"}},
)

ocr_service_instance = OCRService()
def get_ocr_service():
    return ocr_service_instance


# @router.post("/predict",status_code=201)
# async def predict(payload: ImgBody):
#     OCRService()
#     return {"imgBase64": imgBase64}

@router.post("/predict",status_code=201)
async def predict(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()
    result =  await run_in_threadpool(ocr_service.predict, payload.imgBase64)
    return {"response": result}  

@router.post("/base64-to-img",status_code=201)
async def decoded(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()
    result = ocr_service.decode_base64(payload.imgBase64)
    return {"response": len(result)}  