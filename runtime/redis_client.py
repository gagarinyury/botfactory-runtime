"""Redis client for wizard state management"""
import os
import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()

class RedisClient:
    def __init__(self):
        self.redis = None
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379")

    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            await self.redis.ping()
            logger.info("redis_connected", redis_url=self.redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            logger.info("redis_disconnected")

    async def set_wizard_state(self, bot_id: str, user_id: int, state: Dict[str, Any], ttl: int = 86400):
        """Set wizard state with TTL (default 24 hours)"""
        key = f"state:{bot_id}:{user_id}"
        try:
            # Auto-connect if not connected
            if not self.redis:
                await self.connect()
            await self.redis.setex(key, ttl, json.dumps(state))
            logger.debug("wizard_state_set", key=key, ttl=ttl)
        except Exception as e:
            logger.error("wizard_state_set_failed", key=key, error=str(e))
            raise

    async def get_wizard_state(self, bot_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get wizard state"""
        key = f"state:{bot_id}:{user_id}"
        try:
            # Auto-connect if not connected
            if not self.redis:
                await self.connect()
            data = await self.redis.get(key)
            if data:
                state = json.loads(data)
                logger.debug("wizard_state_retrieved", key=key)
                return state
            return None
        except Exception as e:
            logger.error("wizard_state_get_failed", key=key, error=str(e))
            return None

    async def delete_wizard_state(self, bot_id: str, user_id: int):
        """Delete wizard state"""
        key = f"state:{bot_id}:{user_id}"
        try:
            # Auto-connect if not connected
            if not self.redis:
                await self.connect()
            await self.redis.delete(key)
            logger.debug("wizard_state_deleted", key=key)
        except Exception as e:
            logger.error("wizard_state_delete_failed", key=key, error=str(e))

    async def extend_wizard_ttl(self, bot_id: str, user_id: int, ttl: int = 86400):
        """Extend wizard state TTL"""
        key = f"state:{bot_id}:{user_id}"
        try:
            await self.redis.expire(key, ttl)
            logger.debug("wizard_state_ttl_extended", key=key, ttl=ttl)
        except Exception as e:
            logger.error("wizard_state_ttl_extend_failed", key=key, error=str(e))

    # Budget management methods
    async def get_daily_budget_usage(self, bot_id: str) -> int:
        """Get current daily budget usage for bot (in tokens)"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"budget:daily:{bot_id}:{today}"
        try:
            usage = await self.redis.get(key)
            return int(usage) if usage else 0
        except Exception as e:
            logger.error("budget_usage_get_failed", bot_id=bot_id, error=str(e))
            return 0

    async def increment_daily_budget_usage(self, bot_id: str, tokens: int) -> int:
        """Increment daily budget usage and return new total"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"budget:daily:{bot_id}:{today}"
        try:
            # Increment with atomic operation
            new_total = await self.redis.incr(key, tokens)

            # Set expiry for midnight of next day if this is first increment today
            if new_total == tokens:
                # Calculate seconds until midnight
                from datetime import datetime, timedelta
                now = datetime.now()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = int((tomorrow - now).total_seconds())
                await self.redis.expire(key, seconds_until_midnight)

            logger.debug("budget_usage_incremented",
                        bot_id=bot_id, tokens=tokens, new_total=new_total)
            return new_total
        except Exception as e:
            logger.error("budget_usage_increment_failed",
                        bot_id=bot_id, tokens=tokens, error=str(e))
            raise

    async def check_budget_limit(self, bot_id: str, daily_limit: int) -> bool:
        """Check if bot is within daily budget limit"""
        try:
            current_usage = await self.get_daily_budget_usage(bot_id)
            within_limit = current_usage < daily_limit

            logger.debug("budget_limit_checked",
                        bot_id=bot_id,
                        current_usage=current_usage,
                        daily_limit=daily_limit,
                        within_limit=within_limit)

            return within_limit
        except Exception as e:
            logger.error("budget_limit_check_failed", bot_id=bot_id, error=str(e))
            # Fail safe: allow operation if we can't check budget
            return True

    async def reset_daily_budget(self, bot_id: str):
        """Reset daily budget for bot (admin operation)"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"budget:daily:{bot_id}:{today}"
        try:
            await self.redis.delete(key)
            logger.info("budget_reset", bot_id=bot_id, date=today)
        except Exception as e:
            logger.error("budget_reset_failed", bot_id=bot_id, error=str(e))

    async def get_budget_stats(self, bot_id: str, days: int = 7) -> Dict[str, int]:
        """Get budget usage stats for last N days"""
        from datetime import datetime, timedelta
        stats = {}

        try:
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                key = f"budget:daily:{bot_id}:{date}"
                usage = await self.redis.get(key)
                stats[date] = int(usage) if usage else 0

            logger.debug("budget_stats_retrieved", bot_id=bot_id, days=days)
            return stats
        except Exception as e:
            logger.error("budget_stats_get_failed", bot_id=bot_id, error=str(e))
            return {}

# Global Redis client instance
redis_client = RedisClient()