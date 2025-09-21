"""Rate limit policy implementation for preventing spam and accidental duplicates"""
import re
from typing import Dict, Any, Optional
from time import perf_counter
import structlog

logger = structlog.get_logger()


class RateLimitPolicy:
    """Rate limiting policy to control action frequency"""

    def __init__(self):
        pass

    async def check_rate_limit(self, bot_id: str, user_id: int, chat_id: Optional[int],
                             params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Check rate limit and return result

        Returns:
            Dict with keys:
            - allowed: bool - whether action is allowed
            - message: str - message to return if blocked
            - retry_in: int - seconds until retry is allowed (if blocked)
        """
        from .telemetry import policy_ratelimit_hits_total, policy_ratelimit_pass_total, errors
        from .redis_client import redis_client

        start_time = perf_counter()
        context = context or {}

        # Validate parameters
        scope = params.get("scope", "user")
        window_s = params.get("window_s", 60)
        allowance = params.get("allowance", 5)
        key_suffix = params.get("key_suffix", "")
        message_template = params.get("message", "Слишком часто. Попробуйте позже.")

        # Validate parameters
        if allowance <= 0 or window_s <= 0:
            logger.warning("ratelimit_invalid_params",
                         bot_id=bot_id, allowance=allowance, window_s=window_s)
            await self._log_bypass(bot_id, scope, "invalid_params")
            return {"allowed": True, "message": "", "retry_in": 0}

        if scope not in ["user", "chat", "bot"]:
            logger.warning("ratelimit_invalid_scope",
                         bot_id=bot_id, scope=scope)
            await self._log_bypass(bot_id, scope, "invalid_scope")
            return {"allowed": True, "message": "", "retry_in": 0}

        # Build rate limit key
        try:
            scope_id = self._get_scope_id(scope, bot_id, user_id, chat_id)
            if scope_id is None:
                logger.warning("ratelimit_missing_scope_id",
                             bot_id=bot_id, scope=scope)
                await self._log_bypass(bot_id, scope, "missing_scope_id")
                return {"allowed": True, "message": "", "retry_in": 0}

            # Render key suffix template
            rendered_suffix = self._render_key_suffix(key_suffix, context)
            rl_key = self._build_rate_limit_key(bot_id, scope_id, rendered_suffix)

            # Check rate limit in Redis
            try:
                if not redis_client.redis:
                    logger.warning("ratelimit_redis_unavailable", bot_id=bot_id)
                    await self._log_bypass(bot_id, scope, "redis_unavailable")
                    return {"allowed": True, "message": "", "retry_in": 0}

                # Atomic increment with TTL
                current_count = await self._increment_with_ttl(rl_key, window_s)

                if current_count > allowance:
                    # Rate limit exceeded
                    retry_in = await self._get_retry_time(rl_key)
                    message = self._render_message(message_template, {"retry_in": retry_in})

                    # Log hit
                    await self._log_hit(bot_id, scope, rl_key, current_count, allowance, window_s, retry_in)
                    policy_ratelimit_hits_total.labels(bot_id, scope).inc()

                    duration_ms = (perf_counter() - start_time) * 1000
                    logger.info("ratelimit_hit",
                               bot_id=bot_id,
                               scope=scope,
                               key=rl_key,
                               count=current_count,
                               allowance=allowance,
                               window_s=window_s,
                               retry_in=retry_in,
                               duration_ms=int(duration_ms))

                    return {
                        "allowed": False,
                        "message": message,
                        "retry_in": retry_in
                    }
                else:
                    # Rate limit passed
                    await self._log_pass(bot_id, scope, rl_key, current_count, allowance, window_s)
                    policy_ratelimit_pass_total.labels(bot_id, scope).inc()

                    duration_ms = (perf_counter() - start_time) * 1000
                    logger.debug("ratelimit_pass",
                               bot_id=bot_id,
                               scope=scope,
                               key=rl_key,
                               count=current_count,
                               allowance=allowance,
                               window_s=window_s,
                               duration_ms=int(duration_ms))

                    return {
                        "allowed": True,
                        "message": "",
                        "retry_in": 0
                    }

            except Exception as e:
                logger.error("ratelimit_redis_error",
                           bot_id=bot_id, key=rl_key, error=str(e))
                errors.labels(bot_id, "ratelimit", "redis_error").inc()
                await self._log_bypass(bot_id, scope, "redis_error")
                return {"allowed": True, "message": "", "retry_in": 0}

        except Exception as e:
            logger.error("ratelimit_unexpected_error",
                       bot_id=bot_id, error=str(e))
            errors.labels(bot_id, "ratelimit", "unexpected_error").inc()
            await self._log_bypass(bot_id, scope, "unexpected_error")
            return {"allowed": True, "message": "", "retry_in": 0}

    def _get_scope_id(self, scope: str, bot_id: str, user_id: int, chat_id: Optional[int]) -> Optional[str]:
        """Get scope ID based on scope type"""
        if scope == "user":
            return str(user_id)
        elif scope == "chat":
            return str(chat_id) if chat_id is not None else None
        elif scope == "bot":
            return bot_id
        return None

    def _render_key_suffix(self, key_suffix: str, context: Dict[str, Any]) -> str:
        """Render key suffix template with context variables"""
        if not key_suffix:
            return ""

        try:
            # Simple template rendering - replace {{var}} with context[var]
            result = key_suffix
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value))
            return result
        except Exception as e:
            logger.warning("ratelimit_key_suffix_render_error",
                         template=key_suffix, error=str(e))
            return ""  # Ignore suffix on error

    def _build_rate_limit_key(self, bot_id: str, scope_id: str, suffix: str) -> str:
        """Build Redis key for rate limiting"""
        key_parts = ["rl", bot_id, scope_id]
        if suffix:
            key_parts.append(suffix)
        return ":".join(key_parts)

    async def _increment_with_ttl(self, key: str, ttl: int) -> int:
        """Atomically increment counter and set TTL if key is new"""
        from .redis_client import redis_client

        # Use pipeline for atomic operations
        pipeline = redis_client.redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, ttl)
        results = await pipeline.execute()

        return results[0]  # Return the incremented value

    async def _get_retry_time(self, key: str) -> int:
        """Get remaining TTL for the key"""
        from .redis_client import redis_client

        try:
            ttl = await redis_client.redis.ttl(key)
            return max(0, ttl)
        except Exception:
            return 0

    def _render_message(self, template: str, context: Dict[str, Any]) -> str:
        """Render rate limit message template"""
        try:
            result = template
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value))
            return result
        except Exception as e:
            logger.warning("ratelimit_message_render_error",
                         template=template, error=str(e))
            return "Слишком часто. Попробуйте позже."

    async def _log_hit(self, bot_id: str, scope: str, key: str, count: int,
                      allowance: int, window_s: int, retry_in: int):
        """Log rate limit hit event"""
        from .events_logger import create_events_logger
        from .main import async_session

        try:
            async with async_session() as session:
                events_logger = create_events_logger(session, bot_id, 0)  # user_id=0 for policy events
                await events_logger.log_event("ratelimit_hit", {
                    "scope": scope,
                    "key": key,
                    "count": count,
                    "allowance": allowance,
                    "window_s": window_s,
                    "retry_in": retry_in
                })
        except Exception as e:
            logger.warning("ratelimit_log_hit_failed", error=str(e))

    async def _log_pass(self, bot_id: str, scope: str, key: str, count: int,
                       allowance: int, window_s: int):
        """Log rate limit pass event"""
        from .events_logger import create_events_logger
        from .main import async_session

        try:
            async with async_session() as session:
                events_logger = create_events_logger(session, bot_id, 0)
                await events_logger.log_event("ratelimit_pass", {
                    "scope": scope,
                    "key": key,
                    "count": count,
                    "allowance": allowance,
                    "window_s": window_s
                })
        except Exception as e:
            logger.warning("ratelimit_log_pass_failed", error=str(e))

    async def _log_bypass(self, bot_id: str, scope: str, reason: str):
        """Log rate limit bypass event"""
        from .events_logger import create_events_logger
        from .main import async_session

        try:
            async with async_session() as session:
                events_logger = create_events_logger(session, bot_id, 0)
                await events_logger.log_event("ratelimit_bypass", {
                    "scope": scope,
                    "reason": reason
                })
        except Exception as e:
            logger.warning("ratelimit_log_bypass_failed", error=str(e))


# Global rate limit policy instance
rate_limit_policy = RateLimitPolicy()