from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService
from app.schemas.ocr import ImgBody 
from functools import lru_cache

settings = get_settings()
class BusinessLogicError(Exception):
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

do_service = DOService()
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
        ocr_data = {
            "regNum": result.get("regNum"),
            "province": result.get("province"),
            "confidence": result.get("confidence"),
            "readStatus": result.get("readStatus"),
        }

        image_bytes = {
            "originalImage": result.get("originalImage"),
            "croppedPlateImage": result.get("croppedPlateImage"),
        }
        
        organization = await mongo_service.mapCamId(payload.camId)
        subId = await mongo_service.get_UID_by_organize(organization)
        
        if not organization or not subId:
            raise BusinessLogicError(f"Organization for Camera ID '{payload.camId}' not found")
        
        
        now = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        orig_path = f"{settings.ORI_IMG_LOG_PATH_PREFIX}/{now}.jpg".replace("subId", subId)
        crop_path = f"{settings.PRO_IMG_LOG_PATH_PREFIX}/{now}.jpg".replace("subId", subId)
        issue_pro_path = f"{settings.ISSUE_LOG_PATH_PREFIX}/{now}.jpg".replace("subId", subId)
        
        if result.get("readStatus") == "complete":
            
            url = await do_service.upload_two_images(image_bytes.get("originalImage"), image_bytes.get("croppedPlateImage"), orig_path, crop_path)
            # db = await mongo_service.log_ocr(ocr_data, organization)
        else:
            orig_path = f"{settings.ISSUE_LOG_PATH_PREFIX}/{now}.jpg".replace("subId", subId)
            print("orig_path:", orig_path)
            url = await do_service.upload_image(image_bytes.get("originalImage"), orig_path, content_type="image/jpeg")
            # db = None
            
        match result.get("readStatus"):
            case "complete":

                url = await do_service.upload_two_images(
                    image_bytes.get("originalImage"), 
                    image_bytes.get("croppedPlateImage"), 
                    orig_path, 
                    crop_path)
                
            case "no_text":
                url = await do_service.upload_image(
                    image_bytes.get("croppedPlateImage"), 
                    issue_pro_path, 
                    content_type="image/jpeg")

            case "no_plate":
                url = await do_service.upload_image(
                    image_bytes.get("originalImage"), 
                    issue_pro_path, 
                    content_type="image/jpeg")
               
        
        return {
            "ocr-response": ocr_data, 
            "do-service": url
            # "log": db
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