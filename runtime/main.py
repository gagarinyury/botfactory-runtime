from fastapi import FastAPI, HTTPException, Response
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from .registry import BotRegistry
from .loader import BotLoader
from .dsl_engine import DSLEngine
from prometheus_client import generate_latest
from .logging_setup import log, bind_ctx, mask_sensitive_data  # импорт даёт конфиг
from .schemas import PreviewRequest, BotReplyResponse

app = FastAPI()
registry = BotRegistry()
loader = BotLoader()
dsl_engine = DSLEngine()

# Initialize metrics by importing them
from .telemetry import updates, lat, webhook_lat, errors

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://dev:dev@pg:5432/botfactory")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Simple cache for invalidation demo
bot_cache = {}
from cachetools import TTLCache
router_cache = TTLCache(maxsize=256, ttl=600)  # 256 ботов, 10 минут

async def get_router(bot_id: str):
    """Get cached router for bot_id, rebuild if not cached"""
    # Load spec to get version
    async with async_session() as session:
        bot_config = await loader.load_spec_by_bot_id(session, bot_id)
        if not bot_config:
            return None

        # Use (bot_id, version) as cache key
        spec_version = bot_config.get("version", 1)
        cache_key = f"{bot_id}:{spec_version}"

        if cache_key in router_cache:
            return router_cache[cache_key]

        # Build router and cache it
        from .dsl_engine import build_router
        router = build_router(bot_config["spec_json"])
        router_cache[cache_key] = router
        return router

@app.get("/health")
def health(): return {"ok": True}

@app.get("/health/db")
async def health_db():
    from fastapi import Response
    try:
        async with async_session() as session:
            db_status = await registry.db_ok(session)
            if not db_status:
                return Response(content='{"db_ok": false}', status_code=503, media_type="application/json")
            return {"db_ok": True}
    except Exception:
        return Response(content='{"db_ok": false}', status_code=503, media_type="application/json")

@app.get("/bots/{bot_id}")
async def get_bot_spec(bot_id: str):
    """Get bot spec_json by ID"""
    from .http_errors import fail

    try:
        async with async_session() as session:
            bot_config = await loader.load_spec_by_bot_id(session, bot_id)
            if not bot_config:
                fail(404, "not_found", "Bot not found", bot_id=bot_id)

            # Build router using DSL engine
            router_result = dsl_engine.build_router_from_spec(bot_config["spec_json"])

            return {
                "bot": bot_config,
                "router": router_result
            }
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.post("/bots/{bot_id}/reload")
async def reload_bot(bot_id: str):
    """Invalidate cache for bot"""
    # Clear simple cache
    if bot_id in bot_cache:
        del bot_cache[bot_id]

    # Clear all versioned router cache entries for this bot
    keys_to_remove = [key for key in router_cache.keys() if key.startswith(f"{bot_id}:")]
    for key in keys_to_remove:
        del router_cache[key]

    return {"bot_id": bot_id, "cache_invalidated": True, "message": "Bot cache cleared"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.post("/preview/send", response_model=BotReplyResponse)
async def preview_send(p: PreviewRequest):
    bot_id = str(p.bot_id)
    text = p.text
    from .dsl_engine import handle
    from .telemetry import measured_preview
    from .logging import with_trace
    from .http_errors import fail

    tid = with_trace()
    log.info("preview", bot_id=bot_id, trace_id=tid, text=text[:64])  # limit text in logs

    try:
        bot_reply = await measured_preview(bot_id, handle, bot_id, text)
        return {"bot_reply": bot_reply}
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except ValueError as e:
        fail(400, "bad_request", str(e))
    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        elif isinstance(e, KeyError):
            fail(400, "bad_request", "Invalid input data", field=str(e))
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.post("/tg/{bot_id}")
async def tg_webhook(bot_id: str, update: dict):
    from .telemetry import measured_webhook
    from .logging import with_trace
    from .http_errors import fail

    async def process_update(bot_id: str, update: dict):
        """Process Telegram update"""
        router = await get_router(bot_id)   # пересобери при reload
        # передай update в aiogram Dispatcher, связанный с router (минимальная обвязка)
        return {"ok": True}

    # Add metrics and logging
    tid = with_trace()

    # Mask sensitive data in update
    masked_update = mask_sensitive_data(update)
    log.info("webhook", bot_id=bot_id, trace_id=tid, update_id=update.get("update_id"), update_preview=str(masked_update)[:200])

    try:
        result = await measured_webhook(bot_id, process_update, bot_id, update)
        return result
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        elif isinstance(e, KeyError):
            fail(400, "bad_request", "Invalid input data", field=str(e))
        else:
            fail(500, "internal", "Internal server error", detail=str(e))