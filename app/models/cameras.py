from beanie import Document
from typing import Optional, Literal

CameraDirection = Literal["IN", "OUT"]
class cameras(Document):
    camId: str
    organization: str
    direction: Optional[CameraDirection] = None
    
    class Settings:
        name = "cameras"
        indexes = [
            "organization",
            "camId",
            "direction",
            [("organization", 1), ("camId", 1)],
        ]