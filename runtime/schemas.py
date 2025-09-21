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

class KeyboardButton(BaseModel):
    text: str
    callback: str

class ReplyTemplateAction(Action):
    text: str
    empty_text: Optional[str] = None
    keyboard: Optional[List[KeyboardButton]] = None

class MenuOption(BaseModel):
    text: str
    callback: str

class MenuFlow(BaseModel):
    type: str
    entry_cmd: str
    params: Dict[str, Any]

class Flow(BaseModel):
    entry_cmd: str
    steps: Optional[List[FlowStep]] = None
    on_enter: Optional[List[Dict[str, Any]]] = None
    on_step: Optional[List[Dict[str, Any]]] = None
    on_complete: Optional[List[Dict[str, Any]]] = None

class Intent(BaseModel):
    cmd: str
    reply: str

class WizardStep(BaseModel):
    ask: Optional[str] = None
    var: str
    validate: Optional[FlowStepValidation] = None
    widget: Optional[Dict[str, Any]] = None  # For widget steps

class WizardFlow(BaseModel):
    type: str
    entry_cmd: str
    params: Dict[str, Any]

# Broadcast system schemas
class BroadcastThrottle(BaseModel):
    per_sec: int = 30

class BroadcastMessage(BaseModel):
    template: str  # i18n template key like "t:broadcast.promo"
    variables: Dict[str, Any] = {}

class BroadcastParams(BaseModel):
    audience: str  # "all", "active_7d", "segment:tag_name"
    message: Union[str, BroadcastMessage]  # Simple string or template object
    throttle: BroadcastThrottle = BroadcastThrottle()
    track_metrics: bool = True

class BroadcastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: str
    message: Union[str, Dict[str, Any]]
    throttle: Optional[Dict[str, Any]] = None

    @field_validator('audience')
    @classmethod
    def validate_audience(cls, v):
        if not v.strip():
            raise ValueError('audience cannot be empty')
        # Validate audience format
        if v not in ['all', 'active_7d'] and not v.startswith('segment:'):
            raise ValueError('audience must be "all", "active_7d", or "segment:tag_name"')
        return v.strip()

class BroadcastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broadcast_id: str
    status: str
    message: str

class CalendarWidget(BaseModel):
    type: str
    params: Dict[str, Any]

class BotSpec(BaseModel):
    use: Optional[List[str]] = None
    intents: Optional[List[Intent]] = None
    flows: Optional[List[Flow]] = None
    menu_flows: Optional[List[MenuFlow]] = None
    wizard_flows: Optional[List[WizardFlow]] = None