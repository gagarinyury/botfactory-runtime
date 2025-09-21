"""API endpoints for bot LLM settings management"""
from fastapi import APIRouter
from runtime.main import async_session
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.get("/bots/{bot_id}/llm/settings")
async def get_bot_llm_settings(bot_id: str):
    """Get bot LLM settings"""
    from .http_errors import fail

    try:
        async with async_session() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT llm_enabled, llm_preset FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            row = result.fetchone()

            if not row:
                fail(404, "not_found", "Bot not found")

            return {
                "bot_id": bot_id,
                "llm_enabled": row[0] or False,
                "llm_preset": row[1] or "neutral"
            }
    except Exception as e:
        if "db" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))


@router.put("/bots/{bot_id}/llm/settings")
async def update_bot_llm_settings(bot_id: str, settings: dict):
    """Update bot LLM settings"""
    from .http_errors import fail

    try:
        llm_enabled = settings.get("llm_enabled")
        llm_preset = settings.get("llm_preset")

        # Validate preset if provided
        if llm_preset and llm_preset not in ["short", "neutral", "detailed"]:
            fail(400, "bad_request", "Invalid llm_preset. Must be: short, neutral, detailed")

        # Build update query dynamically
        update_parts = []
        params = {"bot_id": bot_id}

        if llm_enabled is not None:
            update_parts.append("llm_enabled = :llm_enabled")
            params["llm_enabled"] = bool(llm_enabled)

        if llm_preset is not None:
            update_parts.append("llm_preset = :llm_preset")
            params["llm_preset"] = llm_preset

        if not update_parts:
            fail(400, "bad_request", "No valid settings provided")

        async with async_session() as session:
            from sqlalchemy import text

            # Check if bot exists
            check_result = await session.execute(
                text("SELECT id FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            if not check_result.fetchone():
                fail(404, "not_found", "Bot not found")

            # Update settings
            update_query = f"UPDATE bots SET {', '.join(update_parts)} WHERE id = :bot_id"
            await session.execute(text(update_query), params)
            await session.commit()

            # Log the change
            logger.info("bot_llm_settings_updated",
                       bot_id=bot_id,
                       llm_enabled=params.get("llm_enabled"),
                       llm_preset=params.get("llm_preset"))

            return {
                "bot_id": bot_id,
                "updated": True,
                "settings": {k: v for k, v in params.items() if k != "bot_id"}
            }

    except Exception as e:
        if "db" in str(e).lower():
            fail(503, "db_unavailable", "Database connection failed")
        else:
            fail(500, "internal", "Internal server error", detail=str(e))


@router.get("/bots/{bot_id}/llm/stats")
async def get_bot_llm_stats(bot_id: str):
    """Get LLM usage statistics for bot"""
    from .http_errors import fail

    try:
        # Get basic stats from prometheus metrics
        from .telemetry import llm_requests_total, llm_cache_hits_total, llm_errors_total

        # Note: In production, you would query prometheus directly
        # For now, return basic info
        return {
            "bot_id": bot_id,
            "stats": {
                "requests_today": 0,  # Would be calculated from metrics
                "cache_hit_rate": 0.0,  # Would be calculated from metrics
                "error_rate": 0.0,  # Would be calculated from metrics
                "avg_latency_ms": 0  # Would be calculated from metrics
            },
            "message": "Stats collection not implemented yet"
        }

    except Exception as e:
        fail(500, "internal", "Internal server error", detail=str(e))