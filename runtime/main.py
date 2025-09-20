from fastapi import FastAPI, HTTPException, Response
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from .registry import BotRegistry
from .loader import BotLoader
from .dsl_engine import DSLEngine
from prometheus_client import generate_latest
from .logging_setup import log  # импорт даёт конфиг
from .schemas import PreviewRequest, BotReplyResponse

app = FastAPI()
registry = BotRegistry()
loader = BotLoader()
dsl_engine = DSLEngine()

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
    if bot_id in router_cache:
        return router_cache[bot_id]

    # Load spec and build router
    async with async_session() as session:
        bot_config = await loader.load_spec_by_bot_id(session, bot_id)
        if bot_config:
            from .dsl_engine import build_router
            router = build_router(bot_config["spec_json"])
            router_cache[bot_id] = router
            return router

    return None

@app.get("/health")
def health(): return {"ok": True}

@app.get("/health/db")
async def health_db():
    async with async_session() as session:
        db_status = await registry.db_ok(session)
        return {"db_ok": db_status}

@app.get("/bots/{bot_id}")
async def get_bot_spec(bot_id: str):
    """Get bot spec_json by ID"""
    async with async_session() as session:
        bot_config = await loader.load_spec_by_bot_id(session, bot_id)
        if not bot_config:
            raise HTTPException(status_code=404, detail="Bot not found")

        # Build router using DSL engine
        router_result = dsl_engine.build_router_from_spec(bot_config["spec_json"])

        return {
            "bot": bot_config,
            "router": router_result
        }

@app.post("/bots/{bot_id}/reload")
async def reload_bot(bot_id: str):
    """Invalidate cache for bot"""
    if bot_id in bot_cache:
        del bot_cache[bot_id]
    if bot_id in router_cache:
        del router_cache[bot_id]

    return {"bot_id": bot_id, "cache_invalidated": True, "message": "Bot cache cleared"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.post("/preview/send", response_model=BotReplyResponse)
async def preview_send(p: PreviewRequest):
    bot_id = str(p.bot_id)
    text = p.text
    from .dsl_engine import handle
    from .telemetry import measure
    from .logging import with_trace
    tid = with_trace()
    log.info("preview", trace_id=tid, bot_id=bot_id, text=text[:64])  # limit text in logs
    bot_reply = await measure(bot_id, handle, bot_id, text)
    return {"bot_reply": bot_reply}

@app.post("/tg/{bot_id}")
async def tg_webhook(bot_id: str, update: dict):
    from .telemetry import measure
    from .logging import with_trace

    async def process_update(bot_id: str, update: dict):
        """Process Telegram update"""
        router = await get_router(bot_id)   # пересобери при reload
        # передай update в aiogram Dispatcher, связанный с router (минимальная обвязка)
        return {"ok": True}

    # Add metrics and logging
    tid = with_trace()
    log.info("webhook", trace_id=tid, bot_id=bot_id, update_id=update.get("update_id"))

    result = await measure(bot_id, process_update, bot_id, update)
    return result