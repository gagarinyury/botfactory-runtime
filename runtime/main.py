from fastapi import FastAPI, HTTPException, Response
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from .registry import BotRegistry
from .loader import BotLoader
from .dsl_engine import DSLEngine
from prometheus_client import generate_latest
from .logging_setup import log, bind_ctx, mask_sensitive_data, mask_user_input_in_logs, mask_user_text  # импорт даёт конфиг
from .schemas import PreviewRequest, BotReplyResponse, BroadcastRequest, BroadcastResponse

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

@app.get("/health/pg")
async def health_pg():
    """PostgreSQL health check"""
    from fastapi import Response
    try:
        async with async_session() as session:
            db_status = await registry.db_ok(session)
            if not db_status:
                return Response(content='{"pg_ok": false}', status_code=503, media_type="application/json")
            return {"pg_ok": True}
    except Exception:
        return Response(content='{"pg_ok": false}', status_code=503, media_type="application/json")

@app.get("/health/redis")
async def health_redis():
    """Redis health check"""
    from fastapi import Response
    from .redis_client import redis_client
    try:
        if not redis_client.redis:
            await redis_client.connect()
        await redis_client.redis.ping()
        return {"redis_ok": True}
    except Exception:
        return Response(content='{"redis_ok": false}', status_code=503, media_type="application/json")

@app.get("/health/llm")
async def health_llm():
    """LLM service health check"""
    from fastapi import Response
    from .llm_client import LLMClient
    try:
        # Test basic LLM connectivity
        llm_client = LLMClient()
        is_healthy = await llm_client.health_check()
        if is_healthy:
            return {"llm_ok": True}
        else:
            return Response(content='{"llm_ok": false}', status_code=503, media_type="application/json")
    except Exception:
        return Response(content='{"llm_ok": false}', status_code=503, media_type="application/json")

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

    # Clear i18n cache for this bot
    from .i18n_manager import i18n_manager
    i18n_manager.invalidate_cache(bot_id)

    return {"bot_id": bot_id, "cache_invalidated": True, "message": "Bot cache cleared"}

# I18n API endpoints
@app.post("/bots/{bot_id}/i18n/keys")
async def set_i18n_keys(bot_id: str, data: dict):
    """Bulk set i18n keys for bot"""
    from .i18n_manager import i18n_manager
    from .http_errors import fail

    try:
        locale = data.get("locale")
        keys = data.get("keys", {})

        if not locale:
            fail(400, "bad_request", "Locale is required")

        if not isinstance(keys, dict):
            fail(400, "bad_request", "Keys must be a dictionary")

        async with async_session() as session:
            success = await i18n_manager.bulk_set_keys(session, bot_id, locale, keys)

            if success:
                # Invalidate cache for this bot
                i18n_manager.invalidate_cache(bot_id, locale)

                return {
                    "bot_id": bot_id,
                    "locale": locale,
                    "keys_count": len(keys),
                    "success": True
                }
            else:
                fail(400, "bad_request", "Failed to set i18n keys")

    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.get("/bots/{bot_id}/i18n/keys")
async def get_i18n_keys(bot_id: str, locale: str = "ru"):
    """Get i18n keys for bot and locale"""
    from .i18n_manager import i18n_manager
    from .http_errors import fail

    try:
        async with async_session() as session:
            keys = await i18n_manager.get_keys(session, bot_id, locale)

            return {
                "bot_id": bot_id,
                "locale": locale,
                "keys": keys,
                "keys_count": len(keys)
            }

    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.post("/bots/{bot_id}/i18n/locale")
async def set_user_locale(bot_id: str, data: dict):
    """Set user locale preference"""
    from .i18n_manager import i18n_manager
    from .http_errors import fail

    try:
        locale = data.get("locale")
        user_id = data.get("user_id")
        chat_id = data.get("chat_id")

        if not locale:
            fail(400, "bad_request", "Locale is required")

        if not user_id and not chat_id:
            fail(400, "bad_request", "Either user_id or chat_id is required")

        async with async_session() as session:
            success = await i18n_manager.set_user_locale(
                session, bot_id, locale, user_id, chat_id
            )

            if success:
                return {
                    "bot_id": bot_id,
                    "locale": locale,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "success": True
                }
            else:
                fail(400, "bad_request", "Failed to set user locale")

    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.post("/bots/{bot_id}/broadcast", response_model=BroadcastResponse)
async def create_broadcast(bot_id: str, request: BroadcastRequest):
    """Create and start a broadcast campaign"""
    from .broadcast_engine import broadcast_engine
    from .http_errors import fail

    try:
        async with async_session() as session:
            # Create broadcast
            broadcast_id = await broadcast_engine.create_broadcast(
                session, bot_id, request.audience, request.message, request.throttle
            )

            # Start broadcast execution
            started = await broadcast_engine.start_broadcast(session, broadcast_id)

            if started:
                return BroadcastResponse(
                    broadcast_id=broadcast_id,
                    status="running",
                    message="Broadcast campaign started successfully"
                )
            else:
                fail(500, "start_failed", "Failed to start broadcast campaign")

    except ValueError as e:
        fail(400, "validation_error", str(e))
    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

@app.get("/bots/{bot_id}/broadcasts/{broadcast_id}")
async def get_broadcast_status(bot_id: str, broadcast_id: str):
    """Get broadcast campaign status and progress"""
    from .broadcast_engine import broadcast_engine
    from .http_errors import fail

    try:
        async with async_session() as session:
            status = await broadcast_engine.get_broadcast_status(session, broadcast_id)

            if not status:
                fail(404, "not_found", "Broadcast not found")

            if status["bot_id"] != bot_id:
                fail(403, "forbidden", "Broadcast belongs to different bot")

            return {
                "broadcast_id": broadcast_id,
                "bot_id": bot_id,
                "status": status["status"],
                "audience": status["audience"],
                "total_users": status["total_users"],
                "sent_count": status["sent_count"],
                "failed_count": status["failed_count"],
                "created_at": status["created_at"],
                "started_at": status["started_at"],
                "completed_at": status["completed_at"]
            }

    except Exception as e:
        if "db" in str(e).lower() or "database" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))

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
    log.info("preview", bot_id=bot_id, trace_id=tid, text=mask_user_text(text))  # mask user text in logs

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
        from aiogram import Bot, Dispatcher
        from aiogram.types import Update
        from .dsl_engine import build_router

        # Load bot spec and build router
        async with async_session() as session:
            bot_config = await loader.load_spec_by_bot_id(session, bot_id)
            if not bot_config:
                return {"ok": False, "error": "Bot not found"}

            # Get bot token from database
            from sqlalchemy import text
            bot_token_query = await session.execute(
                text("SELECT token FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            bot_token_result = bot_token_query.fetchone()
            if not bot_token_result:
                return {"ok": False, "error": "Bot token not found"}

            bot_token = bot_token_result[0]

            # Create aiogram instances
            bot = Bot(token=bot_token)
            dp = Dispatcher()

            # Build and include router from spec
            router = build_router(bot_config["spec_json"])
            dp.include_router(router)

            # Process the update
            aiogram_update = Update.model_validate(update)
            await dp.feed_update(bot, aiogram_update)

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

# Include additional routers
from .budget_api import router as budget_router
app.include_router(budget_router)
