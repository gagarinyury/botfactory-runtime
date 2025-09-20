"""Pydantic schemas for request validation"""
from pydantic import BaseModel
from typing import Union
import uuid

class PreviewRequest(BaseModel):
    bot_id: Union[str, uuid.UUID]
    text: str

    class Config:
        # Allow both string and UUID types for bot_id
        json_encoders = {
            uuid.UUID: str
        }

class ReloadResponse(BaseModel):
    bot_id: str
    cache_invalidated: bool
    message: str

class HealthResponse(BaseModel):
    ok: bool

class HealthDBResponse(BaseModel):
    db_ok: bool

class BotReplyResponse(BaseModel):
    bot_reply: str