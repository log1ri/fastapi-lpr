from fastapi import APIRouter, Body, HTTPException, Depends, Request,requests
from fastapi.concurrency import run_in_threadpool
####### new
from fastapi.responses import Response
import requests
from requests.auth import HTTPDigestAuth
import asyncio
import asyncio
import httpx
from app.utils.ocr import parse_alarm_xml
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


# 1) จำกัดจำนวน snapshot พร้อมกันทั้งระบบ
SNAPSHOT_SEM = asyncio.Semaphore(1)   # ปรับเป็น 2-5 ตามแรงเครื่อง/เน็ต

_last_shot = {}  # ip -> monotonic time
COOLDOWN_SEC = 2
client: httpx.AsyncClient | None = None
# client = httpx.AsyncClient(
#     timeout=httpx.Timeout(connect=3.0, read=6.0, write=6.0, pool=6.0),
#     limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
# )

def safe_create_task(coro):
    t = asyncio.create_task(coro)
    def _cb(task: asyncio.Task):
        try:
            task.result()
        except Exception as e:
            logger.exception("snapshot task failed: %s", e)
    t.add_done_callback(_cb)
    return t

async def fetch_snapshot(ip: str):
    now = time.monotonic()

    # cooldown: ถ้ายิงถี่เกิน ข้ามไปเลย
    last = _last_shot.get(ip, 0)
    if now - last < COOLDOWN_SEC:
        return
    _last_shot[ip] = now

    url = f"http://{ip}/ISAPI/Streaming/channels/1/picture"

    async with SNAPSHOT_SEM:
        # retry เบา ๆ สำหรับ timeout/503
        for attempt in range(2):
            try:
                r = await client.get(url, auth=httpx.DigestAuth("admin", "Rival_12"))
                if r.status_code == 200:
                    logger.info("SNAPSHOT OK size=%d", len(r.content))
                    # TODO: save r.content
                    return
                elif r.status_code in (401, 403):
                    logger.warning("SNAPSHOT AUTH %s", r.status_code)
                    # digest บางครั้งต้อง 401 ก่อน เป็นปกติ แต่ถ้าค้างอยู่ 401 ตลอด = user/pass หรือสิทธิ์ผิด
                elif r.status_code == 503:
                    logger.warning("SNAPSHOT 503 (camera busy) attempt=%d", attempt+1)
                else:
                    logger.warning("SNAPSHOT FAIL %s", r.status_code)
                    return
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                logger.warning("SNAPSHOT TIMEOUT attempt=%d", attempt+1)

            await asyncio.sleep(0.2 * (attempt + 1))  # backoff สั้น ๆ












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

# async def fetch_snapshot(camera_ip: str, channel: str = "1") -> bool:
#     url = f"http://{camera_ip}/ISAPI/Streaming/channels/{channel}/picture"

#     try:
#         async with httpx.AsyncClient(timeout=7) as client:
#             r = await client.get(
#                 url,
#                 auth=httpx.DigestAuth("admin", "Rival_12"),
#             )

#         if r.status_code == 200 and r.content:
#             print("✅ SNAPSHOT OK")
#             print("   content-type:", r.headers.get("content-type"))
#             print("   size(bytes):", len(r.content))
#             return True

#         print("❌ SNAPSHOT FAIL:", r.status_code)
#         print("   body:", (r.text or "")[:200])
#         return False

#     except Exception as e:
#         print("💥 SNAPSHOT ERROR:", repr(e))
#         return False
    
# async def fetch_snapshot(CAMERA_IP):
#     try:
#         r = await requests.get(
#             f"http://{CAMERA_IP}/ISAPI/Streaming/channels/1/picture",
#             auth=HTTPDigestAuth("admin", "Rival_12"),
#             timeout=7
#         )
#         if r.ok:
#             print("SNAPSHOT SAVED")
#         else:
#             print("SNAPSHOT FAIL:", r.status_code)
            
#     except Exception as e:
#         print("SNAPSHOT ERROR:", e)
# async def fetch_snapshot(ip: str):
#     url = f"http://{ip}/ISAPI/Streaming/channels/1/picture"
#     async with httpx.AsyncClient(timeout=7) as client:
#         r = await client.get(url, auth=httpx.DigestAuth("admin","Rival_12"))
#         if r.status_code == 200:
#             print("✅ SNAPSHOT OK")
#             print("   content-type:", r.headers.get("content-type"))
#             print("   size(bytes):", len(r.content))
#             return True
#         print("❌ SNAPSHOT FAIL:", r.status_code)
#         return False

# async def parse_alarm_xml(xml_text: str):
#     ns = {"h": "http://www.hikvision.com/ver20/XMLSchema"}
#     root = ET.fromstring(xml_text)

#     data = {
#         "ip": root.findtext("h:ipAddress", namespaces=ns),
#         "channel": root.findtext("h:channelID", namespaces=ns),
#         "time": root.findtext("h:dateTime", namespaces=ns),
#         "event": root.findtext("h:eventType", namespaces=ns),
#         "state": root.findtext("h:eventState", namespaces=ns),
#         "target": root.findtext("h:targetType", namespaces=ns),
#         # "camName": root.findtext("h:channelName", namespaces=ns),
#         "x": root.findtext(".//h:X", namespaces=ns),
#         "y": root.findtext(".//h:Y", namespaces=ns),
#         "w": root.findtext(".//h:width", namespaces=ns),
#         "h": root.findtext(".//h:height", namespaces=ns),
#     }
#     return data

@router.post("/hik/alarm")
async def hik_alarm(request: Request):

    form = await request.form()
    
    if "MoveDetection.xml" in form:
        file = form["MoveDetection.xml"]
        xml_bytes = await file.read()
        xml_text = xml_bytes.decode("utf-8", errors="ignore")

        alarm = await parse_alarm_xml(xml_text)
        print(alarm)

        # ตัวอย่าง logic
        if alarm["event"] == "VMD" and alarm["state"] == "active":
            # asyncio.create_task(fetch_snapshot(alarm["ip"]))  
            safe_create_task(fetch_snapshot(alarm["ip"]))
    else:
        print("NO XML FILE, RAW FORM:", form)

    return Response(status_code=200)
    