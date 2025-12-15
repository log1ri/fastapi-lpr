from app.models.user_org import User, UserPublic
from app.models.ocr_log import OCRLogImages, OCRLogContent, OCRLogMessage,OCRLog
from app.models.cameras import cameras
from typing import Optional, Dict, Any, List

class OcrMongoService:
    
    #1
    async def mapCamId(self, camid: str) -> Optional[str]:

        data = await cameras.find_one(cameras.camId == camid)
        if not data:
            return None
        return data.organization
    #2
    async def get_UID_by_organize(self, organize: Optional[str]):

        user = await User.find_one(User.organization == organize).project(UserPublic)
        if not user:
            return None
        return str(user.id)

    
    async def log_ocr(self, ocr_data: Dict[str, Any], organization: str, image_url: List[str]) -> Dict[str, Any]:
        try:
            # destructure result
            regNum = ocr_data.get("regNum")
            province = ocr_data.get("province")
            # confidence = result.get("confidence")
            
 
            # organize = await self.mapCamId(camId)
            print("Organization:", organization)
            if not organization:
                return {"error": f"Organization '{organization}' not found in database"}


            uId = await self.get_UID_by_organize(organization)
            if not uId:
                return {"error": f"Organization '{organization}' not found in users"}
 
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
                        reg_num=regNum,
                    ),
                ),
                )
                await log.insert()
                return {
                    "success": True,
                    "logId": str(log.id),
                    "subId": uId,
                    "organization": organization,
                }

            except Exception as e:
                print("Mongo insert error:", e)
                return {"error": f"Mongo insert failed: {e}"}
        
        except Exception as e:
            return {
                "error": f"Mongo failed: {e}",
        }
        

        
        

