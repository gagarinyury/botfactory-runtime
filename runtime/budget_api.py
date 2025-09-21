"""Budget management API endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from .main import async_session
from .redis_client import redis_client

logger = structlog.get_logger()
router = APIRouter(prefix="/bots", tags=["budget"])


class BudgetSettings(BaseModel):
    daily_budget_limit: int  # In tokens


class BudgetUsage(BaseModel):
    bot_id: str
    daily_limit: int
    current_usage: int
    remaining: int
    percentage_used: float


class BudgetStats(BaseModel):
    bot_id: str
    daily_stats: Dict[str, int]  # date -> tokens used


async def get_session() -> AsyncSession:
    """Dependency to get database session"""
    async with async_session() as session:
        yield session


@router.get("/{bot_id}/budget/usage", response_model=BudgetUsage)
async def get_budget_usage(
    bot_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Get current budget usage for bot"""
    try:
        # Get budget limit from database
        result = await session.execute(
            text("SELECT daily_budget_limit FROM bots WHERE id = :bot_id"),
            {"bot_id": bot_id}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bot not found")

        daily_limit = row[0]
        current_usage = await redis_client.get_daily_budget_usage(bot_id)
        remaining = max(0, daily_limit - current_usage)
        percentage_used = (current_usage / daily_limit * 100) if daily_limit > 0 else 0

        return BudgetUsage(
            bot_id=bot_id,
            daily_limit=daily_limit,
            current_usage=current_usage,
            remaining=remaining,
            percentage_used=round(percentage_used, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_usage_get_failed", bot_id=bot_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get budget usage")


@router.put("/{bot_id}/budget/settings")
async def update_budget_settings(
    bot_id: str,
    settings: BudgetSettings,
    session: AsyncSession = Depends(get_session)
):
    """Update budget settings for bot"""
    try:
        # Validate bot exists
        result = await session.execute(
            text("SELECT id FROM bots WHERE id = :bot_id"),
            {"bot_id": bot_id}
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Bot not found")

        # Validate budget limit
        if settings.daily_budget_limit < 0:
            raise HTTPException(status_code=400, detail="Budget limit cannot be negative")
        if settings.daily_budget_limit > 1000000:  # 1M tokens max
            raise HTTPException(status_code=400, detail="Budget limit too high (max: 1,000,000 tokens)")

        # Update budget limit
        await session.execute(
            text("UPDATE bots SET daily_budget_limit = :limit WHERE id = :bot_id"),
            {"limit": settings.daily_budget_limit, "bot_id": bot_id}
        )
        await session.commit()

        logger.info("budget_settings_updated",
                   bot_id=bot_id,
                   daily_limit=settings.daily_budget_limit)

        return {"message": "Budget settings updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_settings_update_failed", bot_id=bot_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update budget settings")


@router.get("/{bot_id}/budget/stats", response_model=BudgetStats)
async def get_budget_stats(
    bot_id: str,
    days: int = 7,
    session: AsyncSession = Depends(get_session)
):
    """Get budget usage statistics for last N days"""
    try:
        # Validate bot exists
        result = await session.execute(
            text("SELECT id FROM bots WHERE id = :bot_id"),
            {"bot_id": bot_id}
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Bot not found")

        # Validate days parameter
        if days < 1 or days > 30:
            raise HTTPException(status_code=400, detail="Days must be between 1 and 30")

        # Get usage stats from Redis
        daily_stats = await redis_client.get_budget_stats(bot_id, days)

        return BudgetStats(
            bot_id=bot_id,
            daily_stats=daily_stats
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_stats_get_failed", bot_id=bot_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get budget stats")


@router.post("/{bot_id}/budget/reset")
async def reset_daily_budget(
    bot_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Reset daily budget usage (admin operation)"""
    try:
        # Validate bot exists
        result = await session.execute(
            text("SELECT id FROM bots WHERE id = :bot_id"),
            {"bot_id": bot_id}
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Bot not found")

        # Reset budget in Redis
        await redis_client.reset_daily_budget(bot_id)

        logger.info("budget_reset_requested", bot_id=bot_id)

        return {"message": "Daily budget reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_reset_failed", bot_id=bot_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to reset budget")


@router.get("/budget/overview")
async def get_budget_overview(
    session: AsyncSession = Depends(get_session)
):
    """Get budget overview for all bots (admin endpoint)"""
    try:
        # Get all bots with budget info
        result = await session.execute(
            text("""
                SELECT id, name, daily_budget_limit, llm_enabled
                FROM bots
                WHERE daily_budget_limit > 0
                ORDER BY name
            """)
        )
        bots = result.fetchall()

        overview = []
        for bot in bots:
            bot_id, name, daily_limit, llm_enabled = bot
            current_usage = await redis_client.get_daily_budget_usage(bot_id)
            remaining = max(0, daily_limit - current_usage)
            percentage_used = (current_usage / daily_limit * 100) if daily_limit > 0 else 0

            overview.append({
                "bot_id": bot_id,
                "name": name,
                "llm_enabled": llm_enabled,
                "daily_limit": daily_limit,
                "current_usage": current_usage,
                "remaining": remaining,
                "percentage_used": round(percentage_used, 2)
            })

        return {"bots": overview}

    except Exception as e:
        logger.error("budget_overview_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get budget overview")