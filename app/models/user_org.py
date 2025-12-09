from beanie import Document
from pydantic import Field

class User(Document):
    username: str
    invite_code: str
    organization: str
    email: str
    password: str = Field(..., exclude=True)

    class Settings:
        name = "users"  # ชื่อ collection ใน MongoDB