from beanie import Document


class cameras(Document):
    camId: str
    organization: str