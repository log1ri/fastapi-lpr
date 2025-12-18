from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field, ConfigDict


class OCRLogImages(BaseModel):
    original: Optional[str] = None     # URL รูปเต็ม
    processed: Optional[str] = None    # URL รูปที่ผ่าน OCR/crop แล้ว


class OCRLogContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  # <-- add
    province: Optional[str] = None
    engine: str = "yolo"       # เช่น "yolo"
    reg_num: Optional[str] = Field(None, alias="reg-num")      # ใช้ชื่อ field แบบ reg_num จะอ่านง่าย


class OCRLogMessage(BaseModel):
    subId: Optional[str] = None
    status: Optional[int] = None
    images: Optional[OCRLogImages] = None
    content: Optional[OCRLogContent] = None


class OCRLog(Document):
    level: str = "info"                             # info / error ฯลฯ
    action: str = "extract_data_yolo"              # ชื่อ action
    timestamp: datetime = datetime.utcnow()        # เวลา log
    message: OCRLogMessage                         # detail ด้านใน

    class Settings:
        name = "services_logs"  # ชื่อ collection ใน MongoDB`