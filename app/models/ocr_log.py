from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field, ConfigDict

class OCRDetectionMetrics(BaseModel):
    model_name: str | None = None
    model_version: str | None = None
    ocr_confidence: float | None = None

class OCRRecognitionMetrics(BaseModel):
    model_name: str | None = None
    model_version: str | None = None
    plate_confidence: float | None = None

class OCRMetrics(BaseModel):
    detection: OCRDetectionMetrics | None = None
    recognition: OCRRecognitionMetrics | None = None
    
class OCRLogImages(BaseModel):
    original: Optional[str] = None     
    processed: Optional[str] = None    


class OCRLogContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  
    province: Optional[str] = None
    province_iso: Optional[str] = None
    reg_num: Optional[str] = Field(None, alias="reg-num")  
    engine: str = "yolo"     


class OCRLogMessage(BaseModel):
    subId: Optional[str] = None
    status: Optional[int] = None
    images: Optional[OCRLogImages] = None
    content: Optional[OCRLogContent] = None
    metrics: Optional[OCRMetrics] = None


class OCRLog(Document):
    level: str = "info"                          
    action: str = "extract_data_yolo"            
    timestamp: datetime = datetime.utcnow()      
    message: OCRLogMessage                       

    class Settings:
        name = "services_logs"  