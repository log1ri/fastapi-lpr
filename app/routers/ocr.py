from fastapi import APIRouter, HTTPException, Depends
from app.services.ocr_service import OCRService
from app.schemas.ocr import ImgBody
from fastapi.concurrency import run_in_threadpool
from app.services.do_space import DOService
from datetime import datetime


router = APIRouter(
    prefix="/ocr-service",
    tags=["ocr-service"],
    responses={404: {"description": "Not found"}},
)

service = DOService()
ocr_service_instance = OCRService()
def get_ocr_service():
    return ocr_service_instance

CAMID_TO_ORGANIZE = {
    "CAM01": "rmutp",
    "CAM02": "ORG_B",
    # เพิ่มตามจริง
}

def camid_to_organize(camid: str | None) -> str | None:
    if camid is None:
        return None
    return CAMID_TO_ORGANIZE.get(camid, camid)  

@router.post("/predict",status_code=201)
async def predict(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    organize = camid_to_organize(payload.camId)
    result =  await run_in_threadpool(ocr_service.predict, payload.imgBase64, organize)
    return {"response": result}  




@router.post("/base64-to-img",status_code=201)
async def decoded(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()
    result = ocr_service.decode_base64(payload.imgBase64)
    return {"response": len(result)}  

@router.post("/upload-test",status_code=201)
async def test_upload():
    try:
        # สร้างไฟล์ปลอม ๆ ขึ้นมา
        now = datetime.utcnow()
        content = f"Hello from LPR test! {now.isoformat()}".encode("utf-8")

        # ตั้ง path บน DO
        file_path = f"test/{now.timestamp()}.txt"

        url = await service.upload_bytes(content, file_path, content_type="text/plain")

        return {
            "message": "uploaded!",
            "url": url,
            "path": file_path
        }
    except Exception as e:
        return {"error": str(e)}