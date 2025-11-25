# app/models/log.py
from beanie import Document

class Sample(Document):
    message: str
    timestamp: str