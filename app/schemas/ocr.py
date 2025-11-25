from pydantic import BaseModel

class ImgBody(BaseModel):
    imgBase64: str