"""Pydantic schemas for request validation"""
from pydantic import BaseModel, ConfigDict, UUID4, field_validator
from typing import Union, List, Optional, Dict, Any
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

# DSL Schema Models
class FlowStepValidation(BaseModel):
    regex: str
    msg: str

class FlowStep(BaseModel):
    ask: str
    var: str
    validate: Optional[FlowStepValidation] = None

class Action(BaseModel):
    pass

class SqlQueryAction(Action):
    sql: str
    result_var: str

class SqlExecAction(Action):
    sql: str

class ReplyTemplateAction(Action):
    text: str
    empty_text: Optional[str] = None

class Flow(BaseModel):
    entry_cmd: str
    steps: Optional[List[FlowStep]] = None
    on_enter: Optional[List[Dict[str, Any]]] = None
    on_step: Optional[List[Dict[str, Any]]] = None
    on_complete: Optional[List[Dict[str, Any]]] = None

class Intent(BaseModel):
    cmd: str
    reply: str

class BotSpec(BaseModel):
    use: Optional[List[str]] = None
    intents: Optional[List[Intent]] = None
    flows: Optional[List[Flow]] = None