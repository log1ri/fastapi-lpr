from fastapi import APIRouter, Body, HTTPException, Depends, Request,requests
from fastapi.concurrency import run_in_threadpool
####### new
from fastapi.responses import Response
import requests
from requests.auth import HTTPDigestAuth
import asyncio
import asyncio
import httpx
# from app.utils.ocr import parse_alarm_xml
##########
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService
from app.schemas.ocr import ImgBody 
from app.core.exceptions import BusinessLogicError
# from app.services.ocr_camera import HikSnapshotService  

from functools import lru_cache
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


# # 1) จำกัดจำนวน snapshot พร้อมกันทั้งระบบ
# SNAPSHOT_SEM = asyncio.Semaphore(1)   # ปรับเป็น 2-5 ตามแรงเครื่อง/เน็ต

# # _last_shot = {}  # ip -> monotonic time
# # COOLDOWN_SEC = 2
# COOLDOWN_SEC = 2.0
# ALARM_COOLDOWN_SEC = 1.0  
# _last_shot: dict[str, float] = {}
# _last_alarm: dict[str, float] = {}   
# _ip_locks: dict[str, asyncio.Lock] = {}

# def _get_lock(ip: str) -> asyncio.Lock:
#     lock = _ip_locks.get(ip)
#     if lock is None:
#         lock = asyncio.Lock()
#         _ip_locks[ip] = lock
#     return lock

# def safe_create_task(coro):
#     t = asyncio.create_task(coro)
#     def _cb(task: asyncio.Task):
#         try:
#             task.result()
#         except Exception as e:
#             logger.exception("snapshot task failed: %s", e)
#     t.add_done_callback(_cb)
#     return t

# async def fetch_snapshot(ip: str, client: httpx.AsyncClient):
#     now = time.monotonic()

#     # cooldown: ถ้ายิงถี่เกิน ข้ามไปเลย
#     last = _last_shot.get(ip, 0)
#     if now - last < COOLDOWN_SEC:
#         return
#     _last_shot[ip] = now

#     url = f"http://{ip}/ISAPI/Streaming/channels/1/picture"

#     async with SNAPSHOT_SEM:
#         # retry เบา ๆ สำหรับ timeout/503
#         for attempt in range(2):
#             try:
#                 r = await client.get(url, auth=httpx.DigestAuth("admin", "Rival_12"))
#                 if r.status_code == 200:
#                     logger.info("SNAPSHOT OK size=%d", len(r.content))
#                     # TODO: save r.content
#                     return
#                 elif r.status_code in (401, 403):
#                     logger.warning("SNAPSHOT AUTH %s", r.status_code)
#                     # digest บางครั้งต้อง 401 ก่อน เป็นปกติ แต่ถ้าค้างอยู่ 401 ตลอด = user/pass หรือสิทธิ์ผิด
#                 elif r.status_code == 503:
#                     logger.warning("SNAPSHOT 503 (camera busy) attempt=%d", attempt+1)
#                 else:
#                     logger.warning("SNAPSHOT FAIL %s", r.status_code)
#                     return
#             except (httpx.ReadTimeout, httpx.ConnectTimeout):
#                 logger.warning("SNAPSHOT TIMEOUT attempt=%d", attempt+1)

#             await asyncio.sleep(0.2 * (attempt + 1))  # backoff สั้น ๆ


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
        logger.info(alarm)

        # check event type
        if alarm["event"] != "VMD" and alarm["state"] != "active":  
            return Response(status_code=200)
        
        # check Ip
        ip = alarm.get("ip")
        if not ip:
            return Response(status_code=200)
        # check alarm cooldown
        if await svc.should_trigger(ip):
            svc.create_task(svc.snap_and_process(ip))

        
    else:
        logger.warning("NO XML FILE, RAW FORM: %s", form)
    return Response(status_code=200)




















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

    