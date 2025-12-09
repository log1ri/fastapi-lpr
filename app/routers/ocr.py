from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService
from app.schemas.ocr import ImgBody 
from functools import lru_cache


class BusinessLogicError(Exception):
    pass

class OCRServiceError(Exception):
    pass

class StorageServiceError(Exception):
    pass

class MongoLogError(Exception):
    pass

router = APIRouter(
    prefix="/ocr-service",
    tags=["ocr-service"],
    responses={404: {"description": "Not found"}},
)

service = DOService()
mongo_service = OcrMongoService()
ocr_service_instance = OCRService()
def get_ocr_service():
    return ocr_service_instance

# @lru_cache
# def get_ocr_service() -> OCRService:
#     return OCRService()


@router.post("/predict",status_code=201)
async def predict(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    try:
        result =  await run_in_threadpool(ocr_service.predict, payload.imgBase64)
        organization = await mongo_service.mapCamId(payload.camId)
        if not organization:
            raise BusinessLogicError(f"Organization for Camera ID '{payload.camId}' not found")
        if result.get("readStatus") == "complete":
            db = await mongo_service.log_ocr(result, organization)
        else:
            db = None
        
        return {
            "ocr-response": result, 
            "log": db
        }  
    
    except BusinessLogicError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except OCRServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))  # 502: Bad Gateway 

    except StorageServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))  # 503: Storage/Service unavailable

    except MongoLogError as e:
        raise HTTPException(status_code=500, detail=str(e))  # internal server error log

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")



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