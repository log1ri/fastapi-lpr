from typing import Optional, List, Literal
from datetime import datetime
from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel

SessionStatus = Literal["OPEN", "CLOSED", "CONFLICT", "ABANDONED"]

class SessionPoint(BaseModel):
    time: datetime
    camId: str
    logId: str

class VehicleSession(Document):
    organization: str
    subId: str

    reg_num: str
    province: Optional[str] = None

    status: SessionStatus = "OPEN"

    entry: Optional[SessionPoint]
    exit: Optional[SessionPoint] = None
    
    durationSec: Optional[int] = None

    lastSeenAt: Optional[datetime] = None

    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    lockedUntil: Optional[datetime] = None

    class Settings:
        name = "vehicle_sessions"
        indexes = [
            # list session
            [("organization", 1), ("subId", 1), ("status", 1), ("entry.time", -1)],
            
            # find lastest_session
            [("organization", 1), ("subId", 1), ("reg_num", 1)],

            # find open session 
            IndexModel(
                [("organization", 1), ("subId", 1), ("reg_num", 1), ("status", 1)],
                name="organization_1_subId_1_reg_num_1_status_1",
                unique=True,
                partialFilterExpression={"status": "OPEN"},
            ),

            # filter with entry cam
            [("organization", 1), ("entry.camId", 1)],
            
            # cleanup abandoned 
            [("status", 1), ("lastSeenAt", 1)],
        ]
