from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
class User(Document):
    username: str
    invite_code: str
    organization: str
    email: str 
    password: str
    class Settings:
        name = "users"  
    
class UserPublic(BaseModel):
    id: Optional[PydanticObjectId] = Field(alias="_id")
    username: str
    invite_code: str
    organization: str
