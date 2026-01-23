from fastapi import APIRouter, Body, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
####### new
from fastapi.responses import Response
from requests import request
##########
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService
from app.schemas.ocr import ImgBody 
from app.core.exceptions import BusinessLogicError
from functools import lru_cache
import xml.etree.ElementTree as ET
########### new
import logging
router = APIRouter()
logger = logging.getLogger(__name__)
###########
import time
import uuid

settings = get_settings()
_last_ms = 0
_counter = 0

router = APIRouter(
    prefix="/ocr-service",
    tags=["ocr-service"],
    responses={404: {"description": "Not found"}},
)

do_service = DOService()
mongo_service = OcrMongoService()
ocr_service_instance = OCRService()
@lru_cache
def get_ocr_service():
    return ocr_service_instance


def next_id():
    global _last_ms, _counter
    ms = int(time.time() * 1000)
    if ms == _last_ms:
        _counter += 1
    else:
        _last_ms = ms
        _counter = 0
    return f"{ms}{_counter:03d}" 
    # return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"



@router.post("/predict",status_code=201)
async def predict(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):

    url = None
    db = None
    session = None

    # call OCR service in thread pool
    result =  await run_in_threadpool(ocr_service.predict, payload.imgBase64)
    
    # destructure result
    ocr_data = {
        "regNum": result.get("regNum"),
        "province": result.get("province"),
        "plate_confidence": result.get("plate_confidence"),
        "ocr_confidence": result.get("ocr_confidence"),
        "latencyMs": result.get("latencyMs"),
        "readStatus": result.get("readStatus"),
        "engine": settings.MODEL,
        "plate_model_name": settings.PLATE_MODEL_NAME,
        "ocr_model_name": settings.OCR_MODEL_NAME,
    }

    image_bytes = {
        "originalImage": result.get("originalImage"),
        "croppedPlateImage": result.get("croppedPlateImage"),
    }
    
    # fetch organization and subId
    camerasData = await mongo_service.mapCamId(payload.camId)
    if not camerasData:
        raise BusinessLogicError(f"Camera ID '{payload.camId}' not found")

    organization, direction = camerasData
    subId = await mongo_service.get_UID_by_organize(organization)
    
    if not organization or not subId or not direction:
        raise BusinessLogicError(f"Organization for Camera ID '{payload.camId}' not found")
    
    # prepare DO image paths
    ts = next_id()

    orig_path = f"{settings.ORI_IMG_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)
    crop_path = f"{settings.PRO_IMG_LOG_PATH_PREFIX}/cropped_{ts}.jpg".replace("subId", subId)
    issue_pro_path = f"{settings.ISSUE_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)
    
        
    read_status = result.get("readStatus")
    match read_status:
        case "complete":
            # send 2 image and creat log
            if not image_bytes.get("originalImage") or not image_bytes.get("croppedPlateImage"):
                raise BusinessLogicError("Missing images for readStatus 'complete'")
            
            url = await do_service.upload_two_images(
                image_bytes.get("originalImage"), 
                image_bytes.get("croppedPlateImage"), 
                orig_path, 
                crop_path)
            db = await mongo_service.log_ocr(ocr_data, organization,url, subId)
            session = await mongo_service.resolve_session_from_log(db,direction, payload.camId)

            
        case "no_text":
            # has 2 images but send only croppedPlateImage to issue  pro path
            if not image_bytes.get("croppedPlateImage"):
                raise BusinessLogicError("Missing croppedPlateImage for readStatus 'no_text'")
            
            url = await do_service.upload_image(
                image_bytes.get("croppedPlateImage"), 
                issue_pro_path, 
                content_type="image/jpeg")
            db = None
            session = None

        case "no_plate":
            # send only originalImage to issue pro path
            if not image_bytes.get("originalImage"):
                raise BusinessLogicError("Missing originalImage for readStatus 'no_plate'")
            
            url = await do_service.upload_image(
                image_bytes.get("originalImage"), 
                issue_pro_path, 
                content_type="image/jpeg")
            db = None
            session = None

        case _:
            raise BusinessLogicError(f"Unknown readStatus '{read_status}'")

            
    
    return {
        "ocr-response": ocr_data, 
        "do-service": url,
        "log": db,
        "session": session.model_dump(by_alias=True) if session else None
    }  
    


@router.post("/base64-to-img",status_code=201)
async def decoded(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()                               
    result = ocr_service.decode_base64(payload.imgBase64)
    if result is None:
        raise BusinessLogicError("Invalid base64 image")
    return {"response": len(result)}  

@router.post("/ml-check",status_code=200)
async def ml_check(imgBase64: str = Body(..., embed=True), ocr_service: OCRService = Depends(get_ocr_service)):
    # call OCR service in thread pool
    result =  await run_in_threadpool(ocr_service.predict, imgBase64)
    ocr_data = {
            "regNum": result.get("regNum"),
            "province": result.get("province"),
            "plate_confidence": result.get("plate_confidence"),
            "ocr_confidence": result.get("ocr_confidence"),
            "latencyMs": result.get("latencyMs"),
            "readStatus": result.get("readStatus"),
            "engine": settings.MODEL,
            "plate_model_name": settings.PLATE_MODEL_NAME,
            "ocr_model_name": settings.OCR_MODEL_NAME,
        }
    return {"ocr-response": ocr_data}

NS = {"hk": "http://www.hikvision.com/ver20/XMLSchema"}
def get_text(root: ET.Element, path: str, default: str | None = None) -> str | None:
    el = root.find(path, NS)
    if el is None or el.text is None:
        return default
    return el.text.strip()

@router.post("/hik/alarm")
async def hik_alarm(request: Request):

    body = await request.body()
    ct = request.headers.get("content-type", "")

    # log เพื่อจับว่าเข้ามาเป็นอะไร
    logger.info("hik_alarm content-type=%s len=%d", ct, len(body))
    logger.info("hik_alarm body(head)=%r", body[:200])

    if not body or body.strip() == b"":
        return Response(content="empty body", status_code=400)

    # กัน BOM + whitespace
    body = body.lstrip(b"\xef\xbb\xbf").strip()

    # parse xml (ส่ง bytes เข้าได้เลย)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        logger.exception("XML parse failed: %s", e)
        return Response(content="invalid xml", status_code=400)

    event_type  = get_text(root, "hk:eventType", default="UNKNOWN")
    target_type = get_text(root, "hk:targetType", default=None)
    ip          = get_text(root, "hk:ipAddress", default=None)
    dt          = get_text(root, "hk:dateTime", default=None)

    logger.info("ip=%s eventType=%s targetType=%s dt=%s",
                ip, event_type, target_type, dt)

    return {
        "ip": ip,
        "eventType": event_type,
        "targetType": target_type,
        "datetime": dt,
    }
    # body = await request.body()
    # xml_text = body.decode("utf-8")

    # # parse xml
    # root = ET.fromstring(xml_text)

    # # namespace ของ Hikvision
    # ns = {"hk": "http://www.hikvision.com/ver20/XMLSchema"}

    # # ดึงค่าที่ต้องใช้
    # event_type = root.find("hk:eventType", ns).text
    # target_type = root.find("hk:targetType", ns).text
    # ip = root.find("hk:ipAddress", ns).text
    # datetime = root.find("hk:dateTime", ns).text

    # x = root.find("hk:targetInfo/hk:targetRect/hk:X", ns).text
    # y = root.find("hk:targetInfo/hk:targetRect/hk:Y", ns).text

    # print("ip:", ip)
    # print("eventType:", event_type)
    # print("targetType:", target_type)   
    # return {
    #     "ip": ip,
    #     "eventType": event_type,
    #     "targetType": target_type,
    #     "datetime": datetime,
    #     "rect": {"x": x, "y": y}
    # }