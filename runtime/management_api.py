# runtime/management_api.py

import asyncio
import json
import re
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, Extra
from sqlalchemy import text, Table, Column, MetaData, BigInteger, Text, DateTime, Uuid, func, Identity
from sqlalchemy.exc import IntegrityError

# Import configuration
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import config
except ImportError:
    # Fallback configuration
    class FallbackConfig:
        class WebhookConfig:
            domain = "localhost:8000"
            use_ngrok = False
            path_prefix = "/tg"
            def get_webhook_url(self, bot_id):
                return f"https://{self.domain}{self.path_prefix}/{bot_id}"
        webhook = WebhookConfig()
    config = FallbackConfig()

# Import from local packages
from .database import async_session
from cachetools import TTLCache
spec_cache = TTLCache(maxsize=256, ttl=600)  # Обновляем на spec_cache
from .registry import BotRegistry
from .redis_client import redis_client
from .i18n_manager import i18n_manager
from .telemetry import api_requests_total, dsl_validate_errors_total, bot_reload_total, bot_prepare_total

# Pydantic Schemas
class CreateBotIn(BaseModel, extra=Extra.forbid):
    name: str
    token: str = Field(..., min_length=20)

class CreateBotOut(BaseModel):
    bot_id: UUID
    name: str
    status: str
    webhook_configured: bool = False
    webhook_url: Optional[str] = None

class PutSpecOut(BaseModel):
    bot_id: UUID
    version: int
    stored: bool

class ErrorItem(BaseModel):
    path: str
    msg: str

class ValidateOut(BaseModel):
    ok: bool
    errors: List[ErrorItem] = []

class PrepareOut(BaseModel):
    bot_id: UUID
    migrations_applied: List[str]

class ReloadOut(BaseModel):
    bot_id: UUID
    reloaded: bool
    version: int

class StatusOut(BaseModel):
    bot_id: UUID
    db_ok: bool
    redis_ok: bool
    webhook_ok: bool
    spec_version: Optional[int]
    last_reload_at: Optional[datetime]

class WebhookIn(BaseModel, extra=Extra.forbid):
    set: Optional[bool] = None
    delete: Optional[bool] = None

class WebhookOut(BaseModel):
    bot_id: UUID
    webhook_ok: bool
    url: Optional[str]

class UpdateBotIn(BaseModel, extra=Extra.forbid):
    name: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None

class UpdateBotOut(BaseModel):
    bot_id: UUID
    name: str
    version: int
    updated: bool

class UpdateTokenIn(BaseModel, extra=Extra.forbid):
    token: str

class UpdateTokenOut(BaseModel):
    bot_id: UUID
    token_updated: bool
    webhook_updated: bool

class LLMSubmitRequest(BaseModel, extra=Extra.forbid):
    raw_dsl: str
    llm_model: Optional[str] = None
    attempt: int = 1

class LLMSubmitOut(BaseModel):
    success: bool
    bot_id: UUID
    fixes_applied: Optional[List[str]] = None
    final_spec: Optional[Dict[str, Any]] = None
    errors: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    fallback_template: Optional[Dict[str, Any]] = None
    message: str
    version: Optional[int] = None

class DeleteBotOut(BaseModel):
    bot_id: UUID
    deleted: bool
    message: str

class ListBotsOut(BaseModel):
    bots: List[Dict[str, Any]]
    total: int

class ClearDataOut(BaseModel):
    bot_id: UUID
    data_cleared: bool
    tables_cleared: List[str]

class BotInfoOut(BaseModel):
    bot_id: UUID
    name: str
    status: str
    token: str
    created_at: Optional[datetime]
    spec_version: Optional[int]
    webhook_url: Optional[str]

# Routers
router = APIRouter(prefix="/bots", tags=["Bot Management"])
spec_router = APIRouter(tags=["Bot Management"])

# --- Logic ---

async def get_ngrok_url() -> Optional[str]:
    """Get current ngrok URL from ngrok API"""
    if not config.webhook.use_ngrok:
        return None
        
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(config.webhook.ngrok_api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    tunnels = data.get("tunnels", [])
                    for tunnel in tunnels:
                        if tunnel.get("proto") == "https":
                            return tunnel.get("public_url")
    except Exception:
        pass
    return None

async def get_webhook_domain() -> str:
    """Get webhook domain based on configuration"""
    if config.webhook.domain == "auto-ngrok":
        ngrok_url = await get_ngrok_url()
        if ngrok_url:
            return ngrok_url.replace("https://", "")
        else:
            raise ValueError("Ngrok is not running or not accessible")
    else:
        return config.webhook.domain

async def setup_webhook_automatically(bot_id: UUID, token: str) -> bool:
    """Automatically setup webhook for a bot"""
    try:
        domain = await get_webhook_domain()
        webhook_url = config.webhook.get_webhook_url(str(bot_id)).replace(config.webhook.domain, domain)
        
        async with aiohttp.ClientSession() as http_session:
            api_url = f"https://api.telegram.org/bot{token}/setWebhook"
            payload = {
                "url": webhook_url,
                "allowed_updates": ["message", "callback_query"]
            }
            async with http_session.post(api_url, json=payload) as response:
                data = await response.json()
                return response.status == 200 and data.get("ok", False)
    except Exception:
        return False

async def validate_spec_logic(spec: Dict[str, Any]) -> List[ErrorItem]:
    errors: List[ErrorItem] = []
    known_blocks = {
        "flow.menu.v1", "flow.wizard.v1", "flow.generic.v1",
        "action.reply_template.v1", "action.sql_query.v1", "action.sql_exec.v1",
        "widget.calendar.v1", "widget.pagination.v1",
        "i18n.fluent.v1", "ops.broadcast.v1"
    }
    used_blocks = set(spec.get("use", []))
    if unknown := used_blocks - known_blocks:
        errors.append(ErrorItem(path="use", msg=f"Unknown blocks: {sorted(list(unknown))}"))

    for i, flow in enumerate(spec.get("flows", [])):
        path = f"flows[{i}]"
        if not flow.get("entry_cmd", "").startswith("/"):
            errors.append(ErrorItem(path=f"{path}.entry_cmd", msg="must start with '/'"))
        
        if flow.get("type") == "flow.wizard.v1":
            step_vars = set()
            for j, step in enumerate(flow.get("params", {}).get("steps", [])):
                if var_name := step.get("var"):
                    if var_name in step_vars:
                        errors.append(ErrorItem(path=f"{path}.params.steps[{j}].var", msg=f"Duplicate var '{var_name}' found"))
                    step_vars.add(var_name)

        actions = flow.get("params", {}).get("on_complete", []) + flow.get("params", {}).get("on_enter", [])
        for k, action in enumerate(actions):
            action_path = f"{path}.params.actions[{k}]"
            action_type = action.get("type")
            sql = action.get("params", {}).get("sql", "").strip().upper()
            if action_type == "action.sql_query.v1" and not sql.startswith("SELECT"):
                errors.append(ErrorItem(path=action_path, msg="sql_query must be a SELECT statement"))
            if action_type == "action.sql_exec.v1" and not (sql.startswith("INSERT") or sql.startswith("UPDATE") or sql.startswith("DELETE")):
                errors.append(ErrorItem(path=action_path, msg="sql_exec must be INSERT, UPDATE, or DELETE"))
    return errors

# --- Endpoints ---

@router.get("", response_model=ListBotsOut)
async def list_bots():
    """Get list of all bots"""
    try:
        registry = BotRegistry()
        async with async_session() as session:
            bots = await registry.list_bots(session)
        api_requests_total.labels(route="/bots", code=200).inc()
        return ListBotsOut(bots=bots, total=len(bots))
    except Exception as e:
        api_requests_total.labels(route="/bots", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.get("/{bot_id}", response_model=BotInfoOut)
async def get_bot_info(bot_id: UUID):
    """Get bot information"""
    try:
        async with async_session() as session:
            # Get bot basic info
            result = await session.execute(
                text("SELECT id, name, status, token FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            bot_row = result.fetchone()
            if not bot_row:
                api_requests_total.labels(route="/bots/{bot_id}", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")
            
            # Get latest spec version
            spec_result = await session.execute(
                text("SELECT MAX(version) FROM bot_specs WHERE bot_id = :bot_id"),
                {"bot_id": bot_id}
            )
            spec_version = spec_result.scalar_one_or_none()
            
            # Generate webhook URL
            try:
                domain = await get_webhook_domain()
                webhook_url = config.webhook.get_webhook_url(str(bot_id)).replace(config.webhook.domain, domain)
            except Exception:
                webhook_url = f"https://example.com{config.webhook.path_prefix}/{bot_id}"
            
            api_requests_total.labels(route="/bots/{bot_id}", code=200).inc()
            return BotInfoOut(
                bot_id=bot_row.id,
                name=bot_row.name,
                status=bot_row.status,
                token=bot_row.token,
                created_at=None,
                spec_version=spec_version,
                webhook_url=webhook_url
            )
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.post("", status_code=201, response_model=CreateBotOut)
async def create_bot(bot_in: CreateBotIn):
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT id, name, status FROM bots WHERE name = :name"), {"name": bot_in.name})
            if existing_bot := result.fetchone():
                api_requests_total.labels(route="/bots", code=200).inc()
                # For existing bot, check webhook status
                webhook_configured = await setup_webhook_automatically(existing_bot.id, bot_in.token)
                if webhook_configured:
                    try:
                        domain = await get_webhook_domain()
                        webhook_url = config.webhook.get_webhook_url(str(existing_bot.id)).replace(config.webhook.domain, domain)
                    except Exception:
                        webhook_url = None
                else:
                    webhook_url = None
                return CreateBotOut(
                    bot_id=existing_bot.id, 
                    name=existing_bot.name, 
                    status=existing_bot.status,
                    webhook_configured=webhook_configured,
                    webhook_url=webhook_url
                )
            
            new_bot_id = uuid4()
            try:
                await session.execute(
                    text("INSERT INTO bots (id, name, token, status) VALUES (:id, :name, :token, 'active')"),
                    {"id": new_bot_id, "name": bot_in.name, "token": bot_in.token}
                )
                await session.commit()
                
                # Automatically setup webhook for new bot
                webhook_configured = await setup_webhook_automatically(new_bot_id, bot_in.token)
                if webhook_configured:
                    try:
                        domain = await get_webhook_domain()
                        webhook_url = config.webhook.get_webhook_url(str(new_bot_id)).replace(config.webhook.domain, domain)
                    except Exception:
                        webhook_url = None
                else:
                    webhook_url = None
                
            except IntegrityError:
                await session.rollback()
                api_requests_total.labels(route="/bots", code=409).inc()
                raise HTTPException(status_code=409, detail="A bot with this ID or name already exists.")
            api_requests_total.labels(route="/bots", code=201).inc()
            return CreateBotOut(
                bot_id=new_bot_id, 
                name=bot_in.name, 
                status="active",
                webhook_configured=webhook_configured,
                webhook_url=webhook_url
            )
    except Exception as e:
        api_requests_total.labels(route="/bots", code=500).inc()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@spec_router.post("/spec/validate", response_model=ValidateOut)
async def validate_spec_endpoint(spec: Dict[str, Any]):
    errors = await validate_spec_logic(spec)
    if errors:
        dsl_validate_errors_total.inc()
        api_requests_total.labels(route="/spec/validate", code=422).inc()
    else:
        api_requests_total.labels(route="/spec/validate", code=200).inc()
    return ValidateOut(ok=not errors, errors=errors)

@router.put("/{bot_id}/spec", response_model=PutSpecOut)
async def put_bot_spec(bot_id: UUID, spec: Dict[str, Any]):
    errors = await validate_spec_logic(spec)
    if errors:
        dsl_validate_errors_total.inc()
        api_requests_total.labels(route="/bots/{bot_id}/spec", code=422).inc()
        raise HTTPException(status_code=422, detail={"ok": False, "errors": [e.dict() for e in errors]})

    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT MAX(version) as max_version FROM bot_specs WHERE bot_id = :bot_id"), {"bot_id": bot_id})
            new_version = (result.scalar_one_or_none() or 0) + 1
            await session.execute(
                text("INSERT INTO bot_specs (bot_id, version, spec_json) VALUES (:bot_id, :version, :spec_json)"),
                {"bot_id": bot_id, "version": new_version, "spec_json": json.dumps(spec)}
            )
            await session.commit()
            api_requests_total.labels(route="/bots/{bot_id}/spec", code=200).inc()
            return PutSpecOut(bot_id=bot_id, version=new_version, stored=True)
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/spec", code=500).inc()
        # await session.rollback() # rollback is not needed with async with
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.post("/{bot_id}/prepare", response_model=PrepareOut)
async def prepare_bot(bot_id: UUID):
    metadata = MetaData()
    bookings_table = Table(
        "bookings", metadata,
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("bot_id", Uuid, nullable=False),
        Column("user_id", BigInteger, nullable=False),
        Column("service", Text),
        Column("slot", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
    )
    try:
        async with async_session() as session, session.begin():
            await session.run_sync(lambda sync_session: bookings_table.create(sync_session.get_bind(), checkfirst=True))
        bot_prepare_total.labels(bot_id=str(bot_id)).inc()
        api_requests_total.labels(route="/bots/{bot_id}/prepare", code=200).inc()
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/prepare", code=500).inc()
        raise HTTPException(status_code=500, detail=f"DB preparation failed: {e}")
    return PrepareOut(bot_id=bot_id, migrations_applied=["bookings"])

@router.post("/{bot_id}/reload", response_model=ReloadOut)
async def reload_bot_endpoint(bot_id: UUID):
    keys_to_remove = [key for key in spec_cache.keys() if key.startswith(str(bot_id))]
    for key in keys_to_remove:
        del spec_cache[key]
    i18n_manager.invalidate_cache(str(bot_id))
    async with async_session() as session:
        result = await session.execute(text("SELECT MAX(version) FROM bot_specs WHERE bot_id = :bot_id"), {"bot_id": bot_id})
        latest_version = result.scalar_one_or_none() or 0
    bot_reload_total.labels(bot_id=str(bot_id)).inc()
    api_requests_total.labels(route="/bots/{bot_id}/reload", code=200).inc()
    return ReloadOut(bot_id=bot_id, reloaded=True, version=latest_version)

@router.get("/{bot_id}/status", response_model=StatusOut)
async def get_bot_status(bot_id: UUID):
    async with async_session() as session:
        try:
            db_ok = await BotRegistry().db_ok(session)
            token_res = await session.execute(text("SELECT token FROM bots WHERE id = :bot_id"), {"bot_id": bot_id})
            token = token_res.scalar_one_or_none()
            spec_res = await session.execute(text("SELECT MAX(version) FROM bot_specs WHERE bot_id = :bot_id"), {"bot_id": bot_id})
            spec_version = spec_res.scalar_one_or_none()
        except Exception:
            db_ok = False
            token = None
            spec_version = None

    try:
        if not redis_client.redis: await redis_client.connect()
        await redis_client.redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    webhook_ok = False
    if token:
        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(f"https://api.telegram.org/bot{token}/getWebhookInfo") as response:
                    if response.status == 200 and (await response.json()).get("result", {}).get("url"):
                        webhook_ok = True
        except Exception:
            pass

    return StatusOut(bot_id=bot_id, db_ok=db_ok, redis_ok=redis_ok, webhook_ok=webhook_ok, spec_version=spec_version, last_reload_at=datetime.now())

@router.post("/{bot_id}/webhook", response_model=WebhookOut)
async def set_bot_webhook(bot_id: UUID, webhook_in: WebhookIn):
    if not webhook_in.set and not webhook_in.delete:
        raise HTTPException(status_code=400, detail="Either 'set' or 'delete' must be true")
    async with async_session() as session:
        token_res = await session.execute(text("SELECT token FROM bots WHERE id = :bot_id"), {"bot_id": bot_id})
        if not (token := token_res.scalar_one_or_none()):
            raise HTTPException(status_code=404, detail="Bot not found or token missing")

    domain = os.getenv("WEBHOOK_DOMAIN", "example.com")
    webhook_url = f"https://{domain}/tg/{bot_id}"
    
    try:
        async with aiohttp.ClientSession() as http_session:
            if webhook_in.set:
                api_url, payload = f"https://api.telegram.org/bot{token}/setWebhook", {"url": webhook_url}
            else: # webhook_in.delete
                api_url, payload = f"https://api.telegram.org/bot{token}/deleteWebhook", None

            async with http_session.post(api_url, json=payload) as response:
                data = await response.json()
                if not (response.status == 200 and data.get("ok")):
                    raise HTTPException(status_code=response.status, detail=data)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Telegram API call failed: {e}")

    return WebhookOut(bot_id=bot_id, webhook_ok=True, url=webhook_url if webhook_in.set else None)

@router.put("/{bot_id}", response_model=UpdateBotOut)
async def update_bot(bot_id: UUID, update_data: UpdateBotIn):
    """Update bot name and/or spec_json"""
    if not update_data.name and not update_data.spec_json:
        raise HTTPException(status_code=400, detail="At least name or spec_json must be provided")

    # Validate spec if provided
    if update_data.spec_json:
        errors = await validate_spec_logic(update_data.spec_json)
        if errors:
            dsl_validate_errors_total.inc()
            raise HTTPException(status_code=422, detail={"errors": [{"path": e.path, "msg": e.msg} for e in errors]})

    try:
        async with async_session() as session:
            # Check if bot exists
            result = await session.execute(
                text("SELECT name, version FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            bot_row = result.fetchone()
            if not bot_row:
                api_requests_total.labels(route="/bots/{bot_id}", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

            current_name = bot_row.name
            current_version = bot_row.version or 1
            new_version = current_version + 1

            # Update bot table
            update_fields = []
            update_params = {"bot_id": bot_id, "version": new_version}

            if update_data.name:
                update_fields.append("name = :name")
                update_params["name"] = update_data.name
                final_name = update_data.name
            else:
                final_name = current_name

            if update_data.spec_json:
                update_fields.append("spec_json = :spec_json, version = :version")
                update_params["spec_json"] = json.dumps(update_data.spec_json)

            if update_fields:
                update_query = f"UPDATE bots SET {', '.join(update_fields)} WHERE id = :bot_id"
                await session.execute(text(update_query), update_params)
                await session.commit()

                # Clear spec cache
                keys_to_remove = [key for key in router_cache.keys() if key.startswith(str(bot_id))]
                for key in keys_to_remove:
                    del router_cache[key]

                # Clear i18n cache
                i18n_manager.invalidate_cache(str(bot_id))

                api_requests_total.labels(route="/bots/{bot_id}", code=200).inc()
                return UpdateBotOut(bot_id=bot_id, name=final_name, version=new_version, updated=True)

            api_requests_total.labels(route="/bots/{bot_id}", code=200).inc()
            return UpdateBotOut(bot_id=bot_id, name=final_name, version=current_version, updated=False)

    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.delete("/{bot_id}", response_model=DeleteBotOut)
async def delete_bot_endpoint(bot_id: UUID):
    """Delete bot and all associated data"""
    print(f"DEBUG: DELETE endpoint called with bot_id: {bot_id}")
    try:
        registry = BotRegistry()
        async with async_session() as session:
            print(f"DEBUG: About to call registry.delete_bot for {bot_id}")
            deleted = await registry.delete_bot(session, str(bot_id))
            print(f"DEBUG: registry.delete_bot returned: {deleted}")
            if not deleted:
                api_requests_total.labels(route="/bots/{bot_id}", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

            # Clear caches
            keys_to_remove = [k for k in router_cache.keys() if k.startswith(str(bot_id))]
            for key in keys_to_remove:
                del router_cache[key]
            i18n_manager.invalidate_cache(str(bot_id))

        api_requests_total.labels(route="/bots/{bot_id}", code=200).inc()
        return DeleteBotOut(bot_id=bot_id, deleted=True, message="Bot deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.put("/{bot_id}/token", response_model=UpdateTokenOut)
async def update_bot_token(bot_id: UUID, token_data: UpdateTokenIn):
    """Update bot token and refresh webhook"""
    try:
        async with async_session() as session:
            # Check if bot exists
            result = await session.execute(
                text("SELECT id FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            if not result.fetchone():
                api_requests_total.labels(route="/bots/{bot_id}/token", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

            # Update token
            await session.execute(
                text("UPDATE bots SET token = :token WHERE id = :bot_id"),
                {"bot_id": bot_id, "token": token_data.token}
            )
            await session.commit()

            # Clear spec cache for this bot
            keys_to_remove = [key for key in router_cache.keys() if key.startswith(str(bot_id))]
            for key in keys_to_remove:
                del router_cache[key]

        # Try to update webhook with new token
        webhook_updated = await setup_webhook_automatically(bot_id, token_data.token)

        api_requests_total.labels(route="/bots/{bot_id}/token", code=200).inc()
        return UpdateTokenOut(bot_id=bot_id, token_updated=True, webhook_updated=webhook_updated)

    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/token", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.post("/{bot_id}/spec/llm-submit", response_model=LLMSubmitOut)
async def submit_llm_generated_spec(bot_id: UUID, request: LLMSubmitRequest):
    """LLM-friendly endpoint для отправки DSL с автофиксом"""
    from .llm_dsl_validator import LLMDSLValidator

    try:
        # 1. Проверяем что бот существует
        async with async_session() as session:
            result = await session.execute(
                text("SELECT id FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            if not result.fetchone():
                api_requests_total.labels(route="/bots/{bot_id}/spec/llm-submit", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

        # 2. Валидация и автофикс DSL
        validator = LLMDSLValidator()
        validation_result = validator.validate_and_fix(request.raw_dsl)

        if validation_result.success:
            # 3. Сохраняем исправленную версию
            async with async_session() as session:
                # Получаем новую версию
                result = await session.execute(
                    text("SELECT MAX(version) as max_version FROM bot_specs WHERE bot_id = :bot_id"),
                    {"bot_id": bot_id}
                )
                new_version = (result.scalar_one_or_none() or 0) + 1

                # Сохраняем новую спецификацию
                await session.execute(
                    text("INSERT INTO bot_specs (bot_id, version, spec_json) VALUES (:bot_id, :version, :spec_json)"),
                    {
                        "bot_id": bot_id,
                        "version": new_version,
                        "spec_json": json.dumps(validation_result.fixed_spec)
                    }
                )
                await session.commit()

                # Очищаем кеш спецификации
                keys_to_remove = [key for key in router_cache.keys() if key.startswith(str(bot_id))]
                for key in keys_to_remove:
                    del router_cache[key]

            api_requests_total.labels(route="/bots/{bot_id}/spec/llm-submit", code=200).inc()
            return LLMSubmitOut(
                success=True,
                bot_id=bot_id,
                fixes_applied=validation_result.fixes_applied,
                final_spec=validation_result.fixed_spec,
                message=f"DSL processed successfully with {len(validation_result.fixes_applied)} fixes applied",
                version=new_version
            )
        else:
            # 4. Возвращаем ошибки для retry
            api_requests_total.labels(route="/bots/{bot_id}/spec/llm-submit", code=400).inc()
            return LLMSubmitOut(
                success=False,
                bot_id=bot_id,
                errors=validation_result.errors,
                suggestions=validation_result.suggestions,
                fallback_template=validation_result.fallback_template,
                message=f"DSL validation failed with {len(validation_result.errors)} errors"
            )

    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/spec/llm-submit", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.get("/{bot_id}/spec")
async def get_bot_spec(bot_id: UUID):
    """Get bot DSL specification"""
    try:
        async with async_session() as session:
            result = await session.execute(
                text("SELECT spec_json FROM bot_specs WHERE bot_id = :bot_id ORDER BY version DESC LIMIT 1"),
                {"bot_id": bot_id}
            )
            row = result.fetchone()
            if not row:
                api_requests_total.labels(route="/bots/{bot_id}/spec", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot spec not found")

        api_requests_total.labels(route="/bots/{bot_id}/spec", code=200).inc()
        return row.spec_json
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/spec", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.delete("/{bot_id}/data", response_model=ClearDataOut)
async def clear_bot_data(bot_id: UUID):
    """Clear all user data for bot"""
    try:
        async with async_session() as session:
            # Check if bot exists first
            result = await session.execute(
                text("SELECT id FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            if not result.fetchone():
                api_requests_total.labels(route="/bots/{bot_id}/data", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

            # Clear related data tables
            tables_cleared = []

            # Clear bookings
            result = await session.execute(
                text("DELETE FROM bookings WHERE bot_id = :bot_id"),
                {"bot_id": bot_id}
            )
            if result.rowcount > 0:
                tables_cleared.append("bookings")

            await session.commit()

        api_requests_total.labels(route="/bots/{bot_id}/data", code=200).inc()
        return ClearDataOut(bot_id=bot_id, data_cleared=True, tables_cleared=tables_cleared)
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/data", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.post("/{bot_id}/validate", response_model=ValidateOut)
async def validate_bot_spec(bot_id: UUID, spec: Dict[str, Any]):
    """Validate bot DSL specification without saving"""
    try:
        # Check if bot exists
        async with async_session() as session:
            result = await session.execute(
                text("SELECT id FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            if not result.fetchone():
                api_requests_total.labels(route="/bots/{bot_id}/validate", code=404).inc()
                raise HTTPException(status_code=404, detail="Bot not found")

        # Validate spec
        errors = await validate_spec_logic(spec)
        if errors:
            dsl_validate_errors_total.inc()
            api_requests_total.labels(route="/bots/{bot_id}/validate", code=422).inc()
        else:
            api_requests_total.labels(route="/bots/{bot_id}/validate", code=200).inc()

        return ValidateOut(ok=not errors, errors=errors)
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(route="/bots/{bot_id}/validate", code=500).inc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
