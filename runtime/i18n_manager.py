"""I18n Manager for fluent localization support"""
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from cachetools import TTLCache
import structlog
from time import perf_counter

logger = structlog.get_logger()


class I18nManager:
    """Manager for internationalization using Fluent-style localization"""

    def __init__(self):
        # Cache for i18n keys: (bot_id, locale) -> {key: value}
        self.cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes TTL
        self.default_locale = "ru"
        self.supported_locales = ["ru", "en"]

    async def get_user_locale(self, session: AsyncSession, bot_id: str, user_id: Optional[int] = None,
                             chat_id: Optional[int] = None, strategy: str = "user") -> str:
        """Get user's preferred locale based on strategy"""
        from .telemetry import i18n_renders_total

        start_time = perf_counter()

        try:
            # Build query based on strategy
            if strategy == "user" and user_id:
                query = text("SELECT locale FROM locales WHERE bot_id = :bot_id AND user_id = :user_id AND chat_id IS NULL")
                result = await session.execute(query, {"bot_id": bot_id, "user_id": user_id})
            elif strategy == "chat" and chat_id:
                query = text("SELECT locale FROM locales WHERE bot_id = :bot_id AND chat_id = :chat_id AND user_id IS NULL")
                result = await session.execute(query, {"bot_id": bot_id, "chat_id": chat_id})
            else:
                # Bot-level or fallback
                result = None

            locale = result.scalar() if result else None

            # Fallback to default if not found
            if not locale or locale not in self.supported_locales:
                locale = self.default_locale

            duration_ms = (perf_counter() - start_time) * 1000

            logger.info("i18n_resolve_locale",
                       bot_id=bot_id,
                       user_id=user_id,
                       chat_id=chat_id,
                       strategy=strategy,
                       locale=locale,
                       duration_ms=int(duration_ms))

            return locale

        except Exception as e:
            logger.error("i18n_resolve_locale_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        error=str(e))
            return self.default_locale

    async def set_user_locale(self, session: AsyncSession, bot_id: str, locale: str,
                             user_id: Optional[int] = None, chat_id: Optional[int] = None) -> bool:
        """Set user's locale preference"""
        try:
            if locale not in self.supported_locales:
                return False

            # Use UPSERT (PostgreSQL-specific)
            if user_id and not chat_id:
                query = text("""
                    INSERT INTO locales (bot_id, user_id, chat_id, locale, updated_at)
                    VALUES (:bot_id, :user_id, NULL, :locale, NOW())
                    ON CONFLICT (bot_id, COALESCE(user_id, 0), COALESCE(chat_id, 0))
                    DO UPDATE SET locale = :locale, updated_at = NOW()
                """)
                await session.execute(query, {"bot_id": bot_id, "user_id": user_id, "locale": locale})
            elif chat_id and not user_id:
                query = text("""
                    INSERT INTO locales (bot_id, user_id, chat_id, locale, updated_at)
                    VALUES (:bot_id, NULL, :chat_id, :locale, NOW())
                    ON CONFLICT (bot_id, COALESCE(user_id, 0), COALESCE(chat_id, 0))
                    DO UPDATE SET locale = :locale, updated_at = NOW()
                """)
                await session.execute(query, {"bot_id": bot_id, "chat_id": chat_id, "locale": locale})
            else:
                return False

            await session.commit()

            logger.info("i18n_locale_set",
                       bot_id=bot_id,
                       user_id=user_id,
                       chat_id=chat_id,
                       locale=locale)

            return True

        except Exception as e:
            logger.error("i18n_set_locale_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        chat_id=chat_id,
                        locale=locale,
                        error=str(e))
            await session.rollback()
            return False

    async def get_keys(self, session: AsyncSession, bot_id: str, locale: str) -> Dict[str, str]:
        """Get localization keys for bot and locale with caching"""
        from .telemetry import i18n_cache_hits_total, i18n_cache_misses_total

        cache_key = f"{bot_id}:{locale}"

        # Check cache first
        if cache_key in self.cache:
            i18n_cache_hits_total.labels(bot_id, locale).inc()
            return self.cache[cache_key]

        # Cache miss - load from database
        i18n_cache_misses_total.labels(bot_id, locale).inc()

        try:
            query = text("SELECT key, value FROM i18n_keys WHERE bot_id = :bot_id AND locale = :locale")
            result = await session.execute(query, {"bot_id": bot_id, "locale": locale})

            keys = {row.key: row.value for row in result.fetchall()}

            # Cache the result
            self.cache[cache_key] = keys

            logger.info("i18n_keys_loaded",
                       bot_id=bot_id,
                       locale=locale,
                       keys_count=len(keys))

            return keys

        except Exception as e:
            logger.error("i18n_get_keys_error",
                        bot_id=bot_id,
                        locale=locale,
                        error=str(e))
            return {}

    async def translate(self, session: AsyncSession, bot_id: str, key: str,
                       locale: str, **kwargs) -> str:
        """Translate a key with optional placeholders"""
        from .telemetry import i18n_renders_total, i18n_key_miss_total

        start_time = perf_counter()

        try:
            # Get keys for this bot and locale
            keys = await self.get_keys(session, bot_id, locale)

            if key not in keys:
                # Try fallback to default locale
                if locale != self.default_locale:
                    fallback_keys = await self.get_keys(session, bot_id, self.default_locale)
                    if key in fallback_keys:
                        value = fallback_keys[key]
                    else:
                        # Key not found in either locale
                        i18n_key_miss_total.labels(bot_id, locale).inc()
                        logger.warning("i18n_key_miss",
                                     bot_id=bot_id,
                                     locale=locale,
                                     key=key)
                        return f"[{key}]"
                else:
                    # Key not found in default locale
                    i18n_key_miss_total.labels(bot_id, locale).inc()
                    logger.warning("i18n_key_miss",
                                 bot_id=bot_id,
                                 locale=locale,
                                 key=key)
                    return f"[{key}]"
            else:
                value = keys[key]

            # Apply placeholders if provided
            if kwargs:
                value = self._apply_placeholders(value, kwargs)

            duration_ms = (perf_counter() - start_time) * 1000
            i18n_renders_total.labels(bot_id, locale).inc()

            logger.info("i18n_render",
                       bot_id=bot_id,
                       locale=locale,
                       key=key,
                       has_placeholders=bool(kwargs),
                       duration_ms=int(duration_ms))

            return value

        except Exception as e:
            logger.error("i18n_translate_error",
                        bot_id=bot_id,
                        locale=locale,
                        key=key,
                        error=str(e))
            return f"[{key}]"

    def _apply_placeholders(self, template: str, placeholders: Dict[str, Any]) -> str:
        """Apply Fluent-style placeholders to template"""
        try:
            # Simple placeholder replacement: {name} -> value
            result = template
            for name, value in placeholders.items():
                placeholder = f"{{{name}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value))

            return result

        except Exception as e:
            logger.warning("i18n_placeholder_error",
                          template=template,
                          placeholders=placeholders,
                          error=str(e))
            return template

    async def bulk_set_keys(self, session: AsyncSession, bot_id: str, locale: str,
                           keys: Dict[str, str]) -> bool:
        """Bulk insert/update localization keys"""
        try:
            if locale not in self.supported_locales:
                return False

            # Clear cache for this bot+locale
            cache_key = f"{bot_id}:{locale}"
            if cache_key in self.cache:
                del self.cache[cache_key]

            # Use PostgreSQL UPSERT for efficient bulk operations
            for key, value in keys.items():
                query = text("""
                    INSERT INTO i18n_keys (bot_id, locale, key, value, updated_at)
                    VALUES (:bot_id, :locale, :key, :value, NOW())
                    ON CONFLICT (bot_id, locale, key)
                    DO UPDATE SET value = :value, updated_at = NOW()
                """)
                await session.execute(query, {
                    "bot_id": bot_id,
                    "locale": locale,
                    "key": key,
                    "value": value
                })

            await session.commit()

            logger.info("i18n_bulk_keys_set",
                       bot_id=bot_id,
                       locale=locale,
                       keys_count=len(keys))

            return True

        except Exception as e:
            logger.error("i18n_bulk_set_keys_error",
                        bot_id=bot_id,
                        locale=locale,
                        error=str(e))
            await session.rollback()
            return False

    def invalidate_cache(self, bot_id: str, locale: Optional[str] = None):
        """Invalidate cache for bot (and optionally specific locale)"""
        if locale:
            cache_key = f"{bot_id}:{locale}"
            if cache_key in self.cache:
                del self.cache[cache_key]
        else:
            # Invalidate all locales for this bot
            keys_to_remove = [key for key in self.cache.keys() if key.startswith(f"{bot_id}:")]
            for key in keys_to_remove:
                del self.cache[key]

        logger.info("i18n_cache_invalidated",
                   bot_id=bot_id,
                   locale=locale)

    def configure(self, config: Dict[str, Any]):
        """Configure i18n manager from bot specification"""
        self.default_locale = config.get("default_locale", "ru")
        self.supported_locales = config.get("supported", ["ru", "en"])

        logger.info("i18n_configured",
                   default_locale=self.default_locale,
                   supported_locales=self.supported_locales)


# Global i18n manager instance
i18n_manager = I18nManager()