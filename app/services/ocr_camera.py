import httpx
import base64
import asyncio, time, logging
import xml.etree.ElementTree as ET
from pyparsing import lru_cache
from fastapi.concurrency import run_in_threadpool
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService

logger = logging.getLogger(__name__)

_last_ms = 0
_counter = 0

do_service = DOService()
settings = get_settings()
mongo_service = OcrMongoService()
ocr_service_instance = OCRService()

@lru_cache
def get_ocr_service():
    return ocr_service_instance


class HikSnapshotService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        username: str,
        password: str,
        cooldown_sec: float = 5.0,
        alarm_cooldown_sec: float = 5.0,
        max_concurrent: int = 2,
        retries: int = 2,
        backoff_base: float = 0.2,
    ):
        self.client = client
        self.username = username
        self.password = password

        self.cooldown_sec = cooldown_sec
        self.alarm_cooldown_sec = alarm_cooldown_sec
        self.retries = retries
        self.backoff_base = backoff_base

        self._last_shot: dict[str, float] = {}
        self._last_alarm: dict[str, float] = {}
        self._ip_locks: dict[str, asyncio.Lock] = {}
        self._sem = asyncio.Semaphore(max_concurrent)

    def _get_lock(self, ip: str) -> asyncio.Lock:
        lock = self._ip_locks.get(ip)
        if lock is None:
            lock = asyncio.Lock()
            self._ip_locks[ip] = lock
        return lock
    
    def next_id(self):
        global _last_ms, _counter
        ms = int(time.time() * 1000)
        if ms == _last_ms:
            _counter += 1
        else:
            _last_ms = ms
            _counter = 0
        return f"{ms}{_counter:03d}" 

    async def should_trigger(self, ip: str) -> bool:
        """check alarm cooldown"""
        now = time.monotonic()
        async with self._get_lock(ip):
            # get last alarm time
            last = self._last_alarm.get(ip, 0.0)
            # check cooldown
            if now - last < self.alarm_cooldown_sec:
                return False
            self._last_alarm[ip] = now
            return True

    def create_task(self, coro):
        t = asyncio.create_task(coro)
        def _cb(task: asyncio.Task):
            try:
                task.result()
            except Exception as e:
                logger.exception("snapshot task failed: %s", e)
        t.add_done_callback(_cb)
        return t
    
    async def fetch_snapshot(self, ip: str) -> bytes | None:
        """ check snapshot cooldown and fetch snapshot image """
        
        # check cooldown
        now = time.monotonic()
        last = self._last_shot.get(ip, 0.0)
        if now - last < self.cooldown_sec:
            logger.debug("SHOT SKIP cooldown ip=%s", ip)
            return None
        self._last_shot[ip] = now

        url = f"http://{ip}/ISAPI/Streaming/channels/101/picture"

        async with self._sem:
            # try multiple times
            for attempt in range(self.retries):
                try:
                    r = await self.client.get(
                        url,
                        auth=httpx.DigestAuth(self.username, self.password),
                    )
                    if r.status_code == 200:
                        logger.info("SNAPSHOT OK size=%d", len(r.content))
                        return r.content
                    
                    elif r.status_code == 401:
                        logger.warning("SNAPSHOT 401 challenge attempt=%d", attempt+1)
                        continue
                    elif r.status_code == 403:
                        logger.warning("SNAPSHOT 403 forbidden")
                        return None
                    
                    elif r.status_code == 503:
                        logger.warning("SNAPSHOT 503 (camera busy) attempt=%d", attempt+1)
                    else:
                        
                        logger.warning("SNAPSHOT FAIL %s", r.status_code)
                        return None
                    
                except (httpx.ReadTimeout, httpx.ConnectTimeout):
                    logger.warning("SNAPSHOT TIMEOUT attempt=%d", attempt+1)

                await asyncio.sleep(self.backoff_base * (attempt + 1))

        return None
    

    async def parse_alarm_xml(self, xml_text: str):
        ns = {"h": "http://www.hikvision.com/ver20/XMLSchema"}
        root = ET.fromstring(xml_text)

        data = {
            "ip": root.findtext("h:ipAddress", namespaces=ns),
            "channel": root.findtext("h:channelID", namespaces=ns),
            "time": root.findtext("h:dateTime", namespaces=ns),
            "event": root.findtext("h:eventType", namespaces=ns),
            "state": root.findtext("h:eventState", namespaces=ns),
            "target": root.findtext("h:targetType", namespaces=ns),
            "macAddress": root.findtext("h:macAddress", namespaces=ns),

        }
        return data

    async def snap_and_process(self, ip: str, macAddress: str):
        
        url = None
        db = None
        session = None
        
        # fetch snapshot
        img = await self.fetch_snapshot(ip)
        if not img:
            logger.error("No snapshot image fetched ip=%s", ip)
            return
        
        # img encode base64
        img_b64 = base64.b64encode(img).decode("utf-8")
        
        # run ocr in threadpool
        result =  await run_in_threadpool(ocr_service_instance.predict, img_b64)

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
        camerasData = await mongo_service.mapCamId(macAddress)
        if not camerasData:
            logger.warning("Camera not found mac=%s ip=%s", macAddress, ip)
            return

        organization, direction = camerasData
        subId = await mongo_service.get_UID_by_organize(organization)

        if not organization or not subId or not direction:
            logger.warning("Organization/SubId/Direction not found mac=%s ip=%s", macAddress, ip)
            return        
        
        # prepare DO image paths
        ts = self.next_id()

        orig_path = f"{settings.ORI_IMG_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)
        crop_path = f"{settings.PRO_IMG_LOG_PATH_PREFIX}/cropped_{ts}.jpg".replace("subId", subId)
        issue_pro_path = f"{settings.ISSUE_LOG_PATH_PREFIX}/{ts}.jpg".replace("subId", subId)

        
        read_status = result.get("readStatus")
        match read_status:
            case "complete":
                # send 2 image and creat log
                if not image_bytes.get("originalImage") or not image_bytes.get("croppedPlateImage"):
                    logger.error("Missing images for readStatus 'complete' mac=%s ip=%s", macAddress, ip)
                    return
                
                url = await do_service.upload_two_images(
                    image_bytes.get("originalImage"), 
                    image_bytes.get("croppedPlateImage"), 
                    orig_path, 
                    crop_path)
                db = await mongo_service.log_ocr(ocr_data, organization,url, subId)
                session = await mongo_service.resolve_session_from_log(db,direction, macAddress)

                
            case "no_text" | "short_text":
                # has 2 images but send only croppedPlateImage to issue  pro path
                if not image_bytes.get("croppedPlateImage"):
                    logger.error("Missing croppedPlateImage for readStatus 'no_text' mac=%s ip=%s", macAddress, ip)
                    return
                
                url = await do_service.upload_image(
                    image_bytes.get("croppedPlateImage"), 
                    issue_pro_path, 
                    content_type="image/jpeg")
                db = None
                session = None

            case "no_plate":
                # send only originalImage to issue pro path
                if not image_bytes.get("originalImage"):
                    logger.error("Missing originalImage for readStatus 'no_plate' mac=%s ip=%s", macAddress, ip)
                    return
                
                url = await do_service.upload_image(
                    image_bytes.get("originalImage"), 
                    issue_pro_path, 
                    content_type="image/jpeg")
                db = None
                session = None

            case _:
                logger.error("Unknown readStatus '%s' mac=%s ip=%s", read_status, macAddress, ip)
                return  

        logger.info(
            "PIPELINE DONE ip=%s plate=%s status=%s",
            ip,
            ocr_data.get("regNum"),
            ocr_data.get("readStatus"),
        )
    
        
        
        
    
    
    
    

    