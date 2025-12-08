from pydantic import BaseModel

class ImgBody(BaseModel):
    camId: str | None 
    imgBase64: str