from fastapi import APIRouter, Body, HTTPException, Depends, Request,requests
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from datetime import datetime
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService
from app.schemas.ocr import ImgBody 
from app.core.exceptions import BusinessLogicError
from functools import lru_cache
import time

import logging
router = APIRouter()
logger = logging.getLogger(__name__)
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
    
def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)   


# for Hikvision alarm webhook
@router.post("/hik/alarm")
async def hik_alarm(request: Request):

    # get form data
    form = await request.form()
    
    # process MoveDetection.xml
    if "MoveDetection.xml" in form:
        file = form["MoveDetection.xml"]
        xml_bytes = await file.read()
        xml_text = xml_bytes.decode("utf-8", errors="ignore")
        
        # call hik snapshot service
        svc = request.app.state.hik_snapshot_service

        # parse XML
        alarm = await svc.parse_alarm_xml(xml_text)
        # logger.info(alarm)

        # check event type
        if alarm["event"] != "VMD" and alarm["state"] != "active" and alarm["target"] != "vehicle":  
            return Response(status_code=200)
        
        # check Ip
        ip = alarm.get("ip")
        if not ip:
            return Response(status_code=200)
        # check alarm cooldown
        if await svc.should_trigger(ip):
            svc.create_task(svc.snap_and_process(ip, alarm["macAddress"]))

    else:
        logger.warning("NO XML FILE, RAW FORM: %s", form)
    return Response(status_code=200)



# api test endpoint
@router.post("/predict",status_code=201)
async def predict(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):

    url = None
    db = None
    session = None
    timings: dict[str, int] = {}
    t_req = time.perf_counter()
    
    print("\n\n")
    logger.info("OCR Predict Start!!!")
    
    # -------call OCR service in thread pool -------
    t0 = time.perf_counter()
    result =  await run_in_threadpool(ocr_service.predict, payload.imgBase64)
    timings["ocr_ms"] = _ms(t0)
    
    # ------- destructure result -------
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
    
    # ------- fetch camera data -------
    t0 = time.perf_counter()
    camerasData = await mongo_service.mapCamId(payload.camId)
    timings["mongo_mapCamId_ms"] = _ms(t0)

    if not camerasData:
        raise BusinessLogicError(f"Camera ID '{payload.camId}' not found")

    organization, direction = camerasData
    
    # ------- fetch subId -------
    t0 = time.perf_counter()
    subId = await mongo_service.get_UID_by_organize(organization)
    timings["mongo_get_UID_ms"] = _ms(t0)
    
    if not organization or not subId or not direction:
        raise BusinessLogicError(f"Organization for Camera ID '{payload.camId}' not found")
    
    # ------- prepare DO image paths -------
    ts = next_id()

    # create do paths
    orig_path = f"{settings.ORI_IMG_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)
    crop_path = f"{settings.PRO_IMG_LOG_PATH_PREFIX}/cropped_{ts}.jpg".replace("subId", subId)
    issue_pro_path = f"{settings.ISSUE_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)
    
    # ------- process according to readStatus -------
    read_status = result.get("readStatus")
    match read_status:
        case "complete":
            now = datetime.utcnow()
            
            if not image_bytes.get("originalImage") or not image_bytes.get("croppedPlateImage"):
                raise BusinessLogicError("Missing images for readStatus 'complete'")
            
            t0 = time.perf_counter()
            latest = await mongo_service.latest_session(organization, subId, ocr_data["regNum"])
            timings["mongo_latest_session_ms"] = _ms(t0)
            
            # lock check
            if latest and latest.get("lockedUntil") and now < latest["lockedUntil"]:
                # LOCKED -> ignore
                logger.info("IGNORE %s org=%s reg=%s", "LOCKED", organization, ocr_data["regNum"])
                return {
                        "ocr-response": ocr_data,
                        "do-service": None,
                        "log": None,
                        "session": None,
                        "ignored": True,
                        "reason": "LOCKED",
                }
            
            # out duration check
            if direction == 'OUT':
                t0 = time.perf_counter()
                open_doc = await mongo_service.open_session(organization, subId, ocr_data["regNum"])
                timings["mongo_open_session_ms"] = _ms(t0)


                if open_doc:
                    entry_time = (open_doc.get("entry") or {}).get("time")
                    if entry_time and (now - entry_time).total_seconds() < settings.MIN_DURATION_SEC:
                        logger.info("IGNORE %s org=%s reg=%s", "MIN_DURATION", organization, ocr_data["regNum"])
                        return {
                            "ocr-response": ocr_data,
                            "do-service": None,
                            "log": None,
                            "session": None,
                            "ignored": True,
                            "reason": "MIN_DURATION",
                        }
            
            # upload images
            t0 = time.perf_counter()
            url = await do_service.upload_two_images(
                image_bytes.get("originalImage"), 
                image_bytes.get("croppedPlateImage"), 
                orig_path, 
                crop_path)
            timings["upload_ms"] = _ms(t0)
            
            # insert log 
            t0 = time.perf_counter()
            db = await mongo_service.log_ocr(ocr_data, organization,url, subId)
            timings["log_ms"] = _ms(t0)
            
            # insert session
            t0 = time.perf_counter()
            session = await mongo_service.resolve_session_from_log(db,direction, payload.camId)
            timings["session_ms"] = _ms(t0)
            
        case "no_text" | "short_text":
            # has 2 images but send only croppedPlateImage to issue  pro path
            if not image_bytes.get("croppedPlateImage"):
                raise BusinessLogicError("Missing croppedPlateImage for readStatus 'no_text'")
            
            t0 = time.perf_counter()
            url = await do_service.upload_image(
                image_bytes.get("croppedPlateImage"), 
                issue_pro_path, 
                content_type="image/jpeg")
            timings["upload_ms"] = _ms(t0)
            
            db = None
            session = None

        case "no_plate":
            # send only originalImage to issue pro path
            if not image_bytes.get("originalImage"):
                raise BusinessLogicError("Missing originalImage for readStatus 'no_plate'")
            
            t0 = time.perf_counter()
            url = await do_service.upload_image(
                image_bytes.get("originalImage"), 
                issue_pro_path, 
                content_type="image/jpeg")
            timings["upload_ms"] = _ms(t0)
            
            db = None
            session = None

        case _:
            raise BusinessLogicError(f"Unknown readStatus '{read_status}'")
    
    timings["total_ms"] = _ms(t_req)
    logger.info("timings=%s", timings)

    
    return {
        "ocr-response": ocr_data, 
        "do-service": url,
        "log": db,
        "session": session.model_dump(by_alias=True) if session else None,
        "timings": timings,
    }  
    

# base64 to image size test endpoint
@router.post("/base64-to-img",status_code=201)
async def decoded(payload: ImgBody, ocr_service: OCRService = Depends(get_ocr_service)):
    # OCRService()                               
    result = ocr_service.decode_base64(payload.imgBase64)
    if result is None:
        raise BusinessLogicError("Invalid base64 image")
    return {"response": len(result)}  

# ml check endpoint
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

    