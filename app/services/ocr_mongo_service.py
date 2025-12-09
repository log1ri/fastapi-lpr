from app.models.user_org import User
from app.models.ocr_log import OCRLogImages, OCRLogContent, OCRLogMessage,OCRLog
from app.models.cameras import cameras
from typing import Optional, Dict, Any

class OcrMongoService:
    
    #1
    async def mapCamId(self, camid: str) -> Optional[str]:

        data = await cameras.find_one(cameras.camId == camid)
        if not data:
            return None
        return data.organization
    #2
    async def get_UID_by_organize(self, organize: Optional[str]):

        print("Organization to lookup:", organize)
        user = await User.find_one(User.organization == organize)
        print("Found user:", user)
        if not user:
            return None
        return str(user.id)

    
    async def log_ocr(self, result: Dict[str, Any], organization: str):
        try:
            # destructure result
            regNum = result.get("regNum")
            province = result.get("province")
            # confidence = result.get("confidence")
            
 
            # organize = await self.mapCamId(camId)
            print("Organization:", organization)
            if not organization:
                return {"error": f"Organization '{organization}' not found in database"}


            uId = await self.get_UID_by_organize(organization)
            print("User ID:", uId)
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
                        original="test",
                        processed="test",
                    ),
                    content=OCRLogContent(
                        province=province,
                        reg_num=regNum,
                    ),
                ),
                )
                await log.insert()
                return {"success": True}

            except Exception as e:
                print("Mongo insert error:", e)
                return {"error": f"Mongo insert failed: {e}"}
        
        except Exception as e:
            return {
                "error": f"Mongo failed: {e}",
        }
        

        
        

