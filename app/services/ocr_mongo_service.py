from app.models.user_org import User, UserPublic
from app.models.ocr_log import OCRDetectionMetrics, OCRRecognitionMetrics, OCRMetrics, OCRLogImages, OCRLogContent, OCRLogMessage,OCRLog
from app.models.cameras import cameras
from app.models.vehicle_session import VehicleSession, SessionPoint
from app.core.exceptions import MongoLogError, BusinessLogicError
from app.services.ocr_labelMapping import province_to_iso
from typing import Optional, Dict, Any, List
from datetime import datetime
from pymongo import ReturnDocument
import logging
logger = logging.getLogger("MONGO_service")

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
            
            
            # organize = await self.mapCamId(camId)
            # logger.info("Organization: %s", organization)
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
                        # "lastSeenAt": ts,
                        "createdAt": now,
                        # "updatedAt": now,
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

                # 1) close open-session(atomic): ถ้ามีคนอื่นปิดไปแล้ว จะไม่ match และ doc จะเป็น None
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

                    await col.update_one({"_id": doc["_id"]}, {"$set": {"durationSec": duration}})
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
                )
                await conflict.insert()
                logger.info("Created CONFLICT session with ID: %s", str(conflict.id))
                
                return conflict
        except Exception as e:
            # (E) “DB fail” should map  MongoLogError (not BusinessLogicError)
            logger.exception("Mongo operation failed in resolve_session_from_log")
            raise MongoLogError(f"Mongo operation failed: {e}") from e
        return None
        
    # async def resolve_session_from_log(self, log, direction: str, camId: str):
    #     try:
    #         pass
    #         if direction not in ("IN", "OUT"):
    #             raise BusinessLogicError(f"Invalid camera direction: {direction}")
            
    #         open_session = await VehicleSession.find(
    #             VehicleSession.organization == log.get("organization"),
    #             VehicleSession.subId == log.get("subId"),
    #             VehicleSession.reg_num == log.get("regNum"),
    #             VehicleSession.status == "OPEN",
    #         ).sort(-VehicleSession.entry.time).first_or_none()
            
    #         now = datetime.utcnow()
            
    #         if direction == "IN":
    #             if open_session is None:
    #                 sess = VehicleSession(
    #                     organization=log.get("organization"),
    #                     subId=log.get("subId"),
    #                     reg_num=log.get("regNum"),
    #                     province=log.get("province"),
    #                     status="OPEN",
    #                     entry=SessionPoint(
    #                         time=log.get("timestamp"), 
    #                         camId=camId, 
    #                         logId=log.get("logId")
    #                     ),
    #                     exit=None,
    #                     durationSec=None,
    #                     lastSeenAt=log.get("timestamp"),
    #                     createdAt=now,
    #                     updatedAt=now,
    #                 )
    #                 await sess.insert()
    #                 return sess
    #             else:
    #                 # มี OPEN อยู่แล้ว -> ถือว่าเป็นการเจอซ้ำ (รถยังอยู่)
    #                 open_session.lastSeenAt = log.get("timestamp")
    #                 open_session.updatedAt = now
    #                 await open_session.save()
    #                 return open_session
            
            
    #         # 4) กรณี OUT: ปิด session ถ้ามี OPEN / ถ้าไม่มีให้สร้าง CONFLICT
    #         if direction == "OUT":
    #             if open_session is not None:
    #                 open_session.exit = SessionPoint(
    #                     time=log.get("timestamp"), 
    #                     camId=camId, 
    #                     logId=log.get("logId")
    #                 )
    #                 open_session.status = "CLOSED"

    #                 # duration
    #                 if open_session.entry and open_session.entry.time and open_session.exit and open_session.exit.time:
    #                     duration = (open_session.exit.time - open_session.entry.time).total_seconds()
    #                     open_session.durationSec = max(0, int(duration))
    #                 else:
    #                     open_session.durationSec = None
                    
                    
                    
    #                 # duration = (open_session.exit.time - open_session.entry.time).total_seconds()
    #                 # open_session.durationSec = max(0, int(duration))

    #                 open_session.lastSeenAt = log.get("timestamp")
    #                 open_session.updatedAt = now
    #                 await open_session.save()
    #                 return open_session
    #             else:
    #                 # OUT โดยไม่มี OPEN -> conflict session
    #                 sess = VehicleSession(
    #                     organization=log.get("organization"),
    #                     subId=log.get("subId"),
    #                     reg_num=log.get("regNum"),
    #                     province=log.get("province"),
    #                     status="CONFLICT",
    #                     entry=None,
    #                     exit=SessionPoint(time=log.get("timestamp"), camId=camId, logId=log.get("logId")),
    #                     durationSec=None,
    #                     lastSeenAt=log.get("timestamp"),
    #                     createdAt=now,
    #                     updatedAt=now,
    #                 )
    #                 await sess.insert()
    #                 return sess

    #         return None
    #     except Exception as e:
    #         logger.exception("Resolve session failed")
    #         raise BusinessLogicError(f"Resolve session failed: {e}") from e    


    
        

