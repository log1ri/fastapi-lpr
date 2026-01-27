import asyncio, time, logging
import xml.etree.ElementTree as ET
import httpx
import base64
from pyparsing import lru_cache
from fastapi.concurrency import run_in_threadpool
from app.core.config import get_settings 
from app.services.ocr_service import OCRService
from app.services.ocr_mongo_service import OcrMongoService
from app.services.do_space import DOService

logger = logging.getLogger(__name__)

settings = get_settings()
do_service = DOService()
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

    
    async def snap_and_process(self, ip: str, alarm: dict):
        
        url = None
        db = None
        session = None
        
        img = await self.fetch_snapshot(ip)
        if not img:
            return
        img_b64 = base64.b64encode(img).decode("utf-8")
        
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
        
        
        
        
        
        
    
    
    
    

    