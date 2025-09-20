"""Pydantic schemas for request validation"""
from pydantic import BaseModel, ConfigDict, UUID4, field_validator
from typing import Union
import uuid

class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_id: Union[str, UUID4]
    text: str

    @field_validator('text')
    @classmethod
    def validate_text(cls, v):
        if not v.strip():
            raise ValueError('text cannot be empty')
        return v.strip()

class ReloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_id: str
    cache_invalidated: bool
    message: str

class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool

class HealthDBResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_ok: bool

class BotReplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_reply: str