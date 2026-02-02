from app.models.user_org import User, UserPublic
from app.models.ocr_log import OCRDetectionMetrics, OCRRecognitionMetrics, OCRMetrics, OCRLogImages, OCRLogContent, OCRLogMessage,OCRLog
from app.models.cameras import cameras
from app.models.vehicle_session import VehicleSession, SessionPoint
from app.core.exceptions import MongoLogError, BusinessLogicError
from app.services.ocr_labelMapping import province_to_iso
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pymongo import ReturnDocument
from app.core.config import get_settings 
import logging

logger = logging.getLogger("MONGO_service")
settings = get_settings()

class OcrMongoService:
    
    #1
    async def mapCamId(self, camid: str) -> Optional[tuple[str, str]]:

        data = await cameras.find_one(cameras.camId == camid)
        if not data or not data.organization or not data.direction: 
            return None
        return (data.organization, data.direction)
    #2
    async def get_UID_by_organize(self, organize: Optional[str]) -> Optional[str]:

        user = await User.find_one(User.organization == organize).project(UserPublic)
        if not user:
            return None
        return str(user.id)
    
    async def latest_session(self, org:str, subId:str, regNum:str):
        
        col = VehicleSession.get_pymongo_collection()
        # find latest session by org, subId, regNum (projection only needed fields)
        doc = await col.find_one(
            {"organization": org, "subId": subId, "reg_num": regNum},
            projection={
                "_id": 1,
                "status": 1,
                "lockedUntil": 1,
                "updatedAt": 1,
                "createdAt": 1,
            },
            sort=[("updatedAt", -1), ("createdAt", -1)],
        )
        return doc
    
    async def open_session(self, org: str, subId: str, regNum: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the current OPEN session for (org, subId, reg_num).
        Used for OUT minDuration check (entry.time).
        Returns raw Mongo doc (dict) or None.
        """

        #find without beanie model
        col = VehicleSession.get_pymongo_collection()

        doc = await col.find_one(
            {
                "organization": org,
                "subId": subId,
                "reg_num": regNum,
                "status": "OPEN",
            },
            projection={
                "_id": 1,
                "entry.time": 1,   # ✅ only what we need for minDuration
                "entry.camId": 1,  # optional
                "lastSeenAt": 1,   # optional (debug)
                "updatedAt": 1,    # optional (debug)
            },
        )
        return doc

    
    async def log_ocr(self, ocr_data: Dict[str, Any], organization: str, image_url: List[str], uId: str) -> Dict[str, Any]:
        try:
            # destructure result
            regNum = ocr_data.get("regNum")
            province = ocr_data.get("province")
            plate_confidence = ocr_data.get("plate_confidence")
            ocr_confidence = ocr_data.get("ocr_confidence")
            latencyMs = ocr_data.get("latencyMs")
            engine = ocr_data.get("engine")
            plate_model_name = ocr_data.get("plate_model_name")
            ocr_model_name = ocr_data.get("ocr_model_name")
            
            
            if not organization:
                raise BusinessLogicError("organization is required")

 
            try:
                log = OCRLog(
                level="info",
                action="extract_data_yolo",
                message=OCRLogMessage(
                    subId=uId,
                    status=200,
                    images=OCRLogImages(
                        original=image_url[0],
                        processed=image_url[1],
                    ),
                    content=OCRLogContent(
                        province=province,
                        province_iso=province_to_iso.get(province),
                        reg_num=regNum,
                        engine=engine,
                    ),
                    metrics=OCRMetrics(
                        detection=OCRDetectionMetrics(
                            model_name=plate_model_name,
                            model_version="v1.0",
                            plate_confidence=plate_confidence,
                        ),
                        recognition=OCRRecognitionMetrics(
                            model_name=ocr_model_name,
                            model_version="v1.0",
                            ocr_confidence=ocr_confidence,
                        ),
                    )
                ),
                )
                await log.insert()
                logger.info("OCR log inserted with ID: %s", str(log.id))
                return {
                    "success": True,
                    "logId": str(log.id),
                    "subId": uId,
                    "timestamp": log.timestamp,
                    "organization": organization,
                    "regNum": regNum,
                    "province": province,
                }

            except Exception as e:
                logger.exception("Mongo insert error")
                raise MongoLogError(f"Mongo insert failed: {e}") from e
        
        except BusinessLogicError:
            raise  
        except MongoLogError:
            raise  
        except Exception as e:
            logger.exception("Mongo failed")
            raise MongoLogError(f"Mongo failed: {e}") from e
        
    
    async def resolve_session_from_log(self, log, direction: str, camId: str):
        
        if direction not in ("IN", "OUT"):
            raise BusinessLogicError(f"Invalid camera direction: {direction}")

        now = datetime.utcnow()
        
        try:
            ts = log["timestamp"]
            org = log["organization"]
            sub = log["subId"]
            reg = log["regNum"]
            prov = log.get("province")
            log_id = log["logId"]
        except (KeyError, TypeError) as e:
            raise BusinessLogicError(f"Invalid log payload: missing/invalid field: {e}") from e

        try:
            col = VehicleSession.get_pymongo_collection()
        except Exception as e:
            raise BusinessLogicError("VehicleSession collection is not initialized (init_beanie failed?)") from e
        
        
        # -------- IN (UPSERT ATOMIC) --------
        try:
            if direction == "IN":
                q = {
                    "organization": org,
                    "subId": sub,
                    "reg_num": reg,
                    "status": "OPEN",
                }

                update = {
                    # has open-session or not -> update lastSeenAt/updatedAt
                    "$set": {
                        "lastSeenAt": ts,
                        "updatedAt": now,
                    },
                    # Not has open-session -> create this field
                    "$setOnInsert": {
                        "organization": org,
                        "subId": sub,
                        "reg_num": reg,
                        "province": prov,
                        "status": "OPEN",
                        "entry": {"time": ts, "camId": camId, "logId": log_id},
                        "exit": None,
                        "durationSec": None,
                        "createdAt": now,
                    },
                }

                # atomic upsert
                doc = await col.find_one_and_update(
                    q,
                    update,
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                logger.info("Upserted IN session with ID: %s", str(doc["_id"]))
                return VehicleSession.model_validate(doc)

            # -------- OUT (ATOMIC CLOSE) --------
            if direction == "OUT":
                q = {
                    "organization": org,
                    "subId": sub,
                    "reg_num": reg,
                    "status": "OPEN",
                }

                # 1) close open-session(atomic): if close it will not match and doc = None
                doc = await col.find_one_and_update(
                    q,
                    {
                        "$set": {
                            "exit": {"time": ts, "camId": camId, "logId": log_id},
                            "status": "CLOSED",
                            "lastSeenAt": ts,
                            "updatedAt": now,
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )

                # condition by doc found or not
                if doc:
                    # 2) calculate duration and update again (another atomic command)
                    #    (do it this way because it's easiest and most reliable to calculate in code)
                    entry_time = doc.get("entry", {}).get("time")
                    if entry_time:
                        duration = int(max(0, (ts - entry_time).total_seconds()))
                    else:
                        duration = None

                    locked_until = now + timedelta(seconds=settings.T_CLOSE_SEC)

                    await col.update_one(
                        {"_id": doc["_id"]}, 
                        {
                            "$set": {
                            "durationSec": duration,
                            "lockedUntil": locked_until
                            }
                        }
                    )
                    logger.info("Closed OUT session with ID: %s, durationSec: %s", str(doc["_id"]), str(duration))
                    
                    doc["durationSec"] = duration
                    return VehicleSession.model_validate(doc)

                # 3) no OPEN to close -> create CONFLICT
                conflict = VehicleSession(
                    organization=org,
                    subId=sub,
                    reg_num=reg,
                    province=prov,
                    status="CONFLICT",
                    entry=None,
                    exit=SessionPoint(time=ts, camId=camId, logId=log_id),
                    durationSec=None,
                    lastSeenAt=ts,
                    createdAt=now,
                    updatedAt=now,
                    lockedUntil=now + timedelta(seconds=settings.T_CONFLICT_SEC),

                )
                await conflict.insert()
                logger.info("Created CONFLICT session with ID: %s", str(conflict.id))
                
                return conflict
        except Exception as e:
            # (E) “DB fail” should map  MongoLogError (not BusinessLogicError)
            logger.exception("Mongo operation failed in resolve_session_from_log")
            raise MongoLogError(f"Mongo operation failed: {e}") from e
        return None
