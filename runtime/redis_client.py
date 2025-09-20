"""Redis client for wizard state management"""
import os
import json
import aioredis
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
            self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
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
            await self.redis.setex(key, ttl, json.dumps(state))
            logger.debug("wizard_state_set", key=key, ttl=ttl)
        except Exception as e:
            logger.error("wizard_state_set_failed", key=key, error=str(e))
            raise

    async def get_wizard_state(self, bot_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get wizard state"""
        key = f"state:{bot_id}:{user_id}"
        try:
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

# Global Redis client instance
redis_client = RedisClient()