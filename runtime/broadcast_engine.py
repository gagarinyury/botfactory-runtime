"""Broadcast engine for mass messaging system ops.broadcast.v1"""
import asyncio
import uuid
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
from time import perf_counter
import json

logger = structlog.get_logger()


class BroadcastEngine:
    """Engine for managing broadcast campaigns and message delivery"""

    def __init__(self):
        self.max_audience_size = 100000  # Safety limit
        self.min_throttle_per_sec = 1
        self.max_throttle_per_sec = 100

    async def create_broadcast(self, session: AsyncSession, bot_id: str,
                              audience: str, message: Union[str, Dict[str, Any]],
                              throttle: Dict[str, Any] = None) -> str:
        """Create a new broadcast campaign"""
        from .telemetry import broadcast_total

        start_time = perf_counter()
        broadcast_id = str(uuid.uuid4())

        try:
            # Validate parameters
            if not self._validate_audience(audience):
                raise ValueError(f"Invalid audience format: {audience}")

            # Normalize throttle
            if not throttle:
                throttle = {"per_sec": 30}

            per_sec = throttle.get("per_sec", 30)
            if not (self.min_throttle_per_sec <= per_sec <= self.max_throttle_per_sec):
                raise ValueError(f"Throttle per_sec must be between {self.min_throttle_per_sec} and {self.max_throttle_per_sec}")

            # Prepare message object
            if isinstance(message, str):
                # Simple text message
                message_obj = {"type": "text", "text": message}
            else:
                # Template message with i18n support
                message_obj = message

            # Get audience size estimate
            audience_size = await self._estimate_audience_size(session, bot_id, audience)

            if audience_size > self.max_audience_size:
                raise ValueError(f"Audience size {audience_size} exceeds maximum {self.max_audience_size}")

            # Create broadcast record
            query = text("""
                INSERT INTO broadcasts (
                    id, bot_id, audience, message, throttle, status, total_users, created_at, updated_at
                ) VALUES (
                    :id, :bot_id, :audience, :message, :throttle, 'pending', :total_users, NOW(), NOW()
                )
            """)

            await session.execute(query, {
                "id": broadcast_id,
                "bot_id": bot_id,
                "audience": audience,
                "message": json.dumps(message_obj),
                "throttle": json.dumps(throttle),
                "total_users": audience_size
            })

            await session.commit()

            # Record metrics
            broadcast_total.labels(bot_id, audience).inc()

            duration_ms = (perf_counter() - start_time) * 1000
            logger.info("broadcast_created",
                       broadcast_id=broadcast_id,
                       bot_id=bot_id,
                       audience=audience,
                       total_users=audience_size,
                       duration_ms=int(duration_ms))

            return broadcast_id

        except Exception as e:
            await session.rollback()
            logger.error("broadcast_create_error",
                        bot_id=bot_id,
                        audience=audience,
                        error=str(e))
            raise

    async def start_broadcast(self, session: AsyncSession, broadcast_id: str) -> bool:
        """Start broadcast execution (mark as running and queue background task)"""
        try:
            # Update status to running
            query = text("""
                UPDATE broadcasts
                SET status = 'running', started_at = NOW(), updated_at = NOW()
                WHERE id = :id AND status = 'pending'
            """)
            result = await session.execute(query, {"id": broadcast_id})

            if result.rowcount == 0:
                logger.warning("broadcast_start_failed_not_pending", broadcast_id=broadcast_id)
                return False

            await session.commit()

            # Queue background task (using Redis as simple queue)
            await self._queue_broadcast_task(broadcast_id)

            logger.info("broadcast_started", broadcast_id=broadcast_id)
            return True

        except Exception as e:
            await session.rollback()
            logger.error("broadcast_start_error", broadcast_id=broadcast_id, error=str(e))
            return False

    async def _queue_broadcast_task(self, broadcast_id: str):
        """Queue broadcast task using Redis as simple queue"""
        from .redis_client import redis_client

        try:
            if not redis_client.redis:
                await redis_client.connect()

            # Simple queue using Redis list
            await redis_client.redis.lpush("broadcast_queue", broadcast_id)
            logger.info("broadcast_queued", broadcast_id=broadcast_id)

        except Exception as e:
            logger.error("broadcast_queue_error", broadcast_id=broadcast_id, error=str(e))
            raise

    async def execute_broadcast(self, session: AsyncSession, broadcast_id: str):
        """Execute broadcast delivery (called by background worker)"""
        from .telemetry import broadcast_sent_total, broadcast_failed_total, broadcast_duration_seconds

        start_time = perf_counter()

        try:
            # Get broadcast details
            broadcast = await self._get_broadcast(session, broadcast_id)
            if not broadcast:
                logger.error("broadcast_not_found", broadcast_id=broadcast_id)
                return

            bot_id = broadcast["bot_id"]
            audience = broadcast["audience"]
            message_data = json.loads(broadcast["message"])
            throttle_data = json.loads(broadcast["throttle"])

            logger.info("broadcast_start",
                       broadcast_id=broadcast_id,
                       bot_id=bot_id,
                       audience=audience,
                       total_users=broadcast["total_users"])

            # Get target users
            target_users = await self._get_target_users(session, bot_id, audience)

            if not target_users:
                await self._complete_broadcast(session, broadcast_id, 0, 0)
                logger.info("broadcast_no_users", broadcast_id=broadcast_id)
                return

            # Execute delivery with throttling
            sent_count = 0
            failed_count = 0
            per_sec = throttle_data.get("per_sec", 30)
            delay_between_messages = 1.0 / per_sec

            for user_id in target_users:
                try:
                    # Render message for user
                    rendered_message = await self._render_message(session, bot_id, user_id, message_data)

                    # Send message (mock implementation - in real system would use Bot API)
                    success = await self._send_message(bot_id, user_id, rendered_message)

                    if success:
                        sent_count += 1
                        await self._log_delivery_event(session, broadcast_id, user_id, "sent")
                        broadcast_sent_total.labels(bot_id).inc()
                    else:
                        failed_count += 1
                        await self._log_delivery_event(session, broadcast_id, user_id, "failed")
                        broadcast_failed_total.labels(bot_id).inc()

                    # Update progress periodically
                    if (sent_count + failed_count) % 100 == 0:
                        await self._update_broadcast_progress(session, broadcast_id, sent_count, failed_count)

                    # Throttling delay
                    await asyncio.sleep(delay_between_messages)

                except Exception as e:
                    failed_count += 1
                    logger.error("broadcast_user_delivery_error",
                               broadcast_id=broadcast_id,
                               user_id=user_id,
                               error=str(e))
                    await self._log_delivery_event(session, broadcast_id, user_id, "failed", str(e))

            # Complete broadcast
            await self._complete_broadcast(session, broadcast_id, sent_count, failed_count)

            duration_seconds = perf_counter() - start_time
            broadcast_duration_seconds.labels(bot_id).observe(duration_seconds)

            logger.info("broadcast_completed",
                       broadcast_id=broadcast_id,
                       bot_id=bot_id,
                       sent_count=sent_count,
                       failed_count=failed_count,
                       duration_seconds=int(duration_seconds))

        except Exception as e:
            # Mark broadcast as failed
            await self._fail_broadcast(session, broadcast_id, str(e))
            logger.error("broadcast_execution_error", broadcast_id=broadcast_id, error=str(e))

    def _validate_audience(self, audience: str) -> bool:
        """Validate audience format"""
        if audience in ["all", "active_7d"]:
            return True

        if audience.startswith("segment:"):
            segment_name = audience[8:]  # Remove "segment:" prefix
            # Basic validation - alphanumeric and underscores only
            return re.match(r"^[a-zA-Z0-9_]+$", segment_name) is not None

        return False

    async def _estimate_audience_size(self, session: AsyncSession, bot_id: str, audience: str) -> int:
        """Estimate audience size"""
        if audience == "all":
            query = text("SELECT COUNT(*) FROM bot_users WHERE bot_id = :bot_id AND is_active = true")
            result = await session.execute(query, {"bot_id": bot_id})

        elif audience == "active_7d":
            query = text("""
                SELECT COUNT(*) FROM bot_users
                WHERE bot_id = :bot_id AND is_active = true
                AND last_active >= :since
            """)
            since = datetime.now() - timedelta(days=7)
            result = await session.execute(query, {"bot_id": bot_id, "since": since})

        elif audience.startswith("segment:"):
            segment_tag = audience[8:]
            query = text("""
                SELECT COUNT(*) FROM bot_users
                WHERE bot_id = :bot_id AND is_active = true
                AND :tag = ANY(segment_tags)
            """)
            result = await session.execute(query, {"bot_id": bot_id, "tag": segment_tag})

        else:
            return 0

        return result.scalar() or 0

    async def _get_target_users(self, session: AsyncSession, bot_id: str, audience: str) -> List[int]:
        """Get list of target user IDs"""
        if audience == "all":
            query = text("SELECT user_id FROM bot_users WHERE bot_id = :bot_id AND is_active = true")
            result = await session.execute(query, {"bot_id": bot_id})

        elif audience == "active_7d":
            query = text("""
                SELECT user_id FROM bot_users
                WHERE bot_id = :bot_id AND is_active = true
                AND last_active >= :since
                ORDER BY last_active DESC
            """)
            since = datetime.now() - timedelta(days=7)
            result = await session.execute(query, {"bot_id": bot_id, "since": since})

        elif audience.startswith("segment:"):
            segment_tag = audience[8:]
            query = text("""
                SELECT user_id FROM bot_users
                WHERE bot_id = :bot_id AND is_active = true
                AND :tag = ANY(segment_tags)
                ORDER BY last_active DESC
            """)
            result = await session.execute(query, {"bot_id": bot_id, "tag": segment_tag})

        else:
            return []

        return [row.user_id for row in result.fetchall()]

    async def _get_broadcast(self, session: AsyncSession, broadcast_id: str) -> Optional[Dict[str, Any]]:
        """Get broadcast details"""
        query = text("""
            SELECT id, bot_id, audience, message, throttle, total_users
            FROM broadcasts WHERE id = :id
        """)
        result = await session.execute(query, {"id": broadcast_id})
        row = result.fetchone()

        if row:
            return dict(row._mapping)
        return None

    async def _render_message(self, session: AsyncSession, bot_id: str, user_id: int,
                             message_data: Dict[str, Any]) -> str:
        """Render message template for specific user"""
        if message_data.get("type") == "text":
            return message_data["text"]

        # For i18n template messages
        if "template" in message_data:
            from .i18n_manager import I18nManager

            i18n = I18nManager()
            template_key = message_data["template"]
            variables = message_data.get("variables", {})

            # Get user locale (simplified - could cache this)
            locale = await i18n.get_user_locale(session, bot_id, user_id)

            # Handle fluent template format: "t:key"
            if template_key.startswith("t:"):
                key = template_key[2:]  # Remove "t:" prefix
                return await i18n.translate(session, bot_id, key, locale, **variables)

            return template_key  # Fallback to raw template

        return str(message_data)

    async def _send_message(self, bot_id: str, user_id: int, message: str) -> bool:
        """Send message via Bot API (mock implementation)"""
        # In real implementation, this would call Telegram Bot API
        # For now, just simulate success/failure

        # Simulate 95% success rate
        import random
        success = random.random() < 0.95

        if success:
            logger.debug("message_sent", bot_id=bot_id, user_id=user_id)
        else:
            logger.debug("message_failed", bot_id=bot_id, user_id=user_id)

        return success

    async def _log_delivery_event(self, session: AsyncSession, broadcast_id: str,
                                 user_id: int, status: str, error_message: str = None):
        """Log individual delivery event"""
        try:
            query = text("""
                INSERT INTO broadcast_events (broadcast_id, user_id, status, error_message, sent_at)
                VALUES (:broadcast_id, :user_id, :status, :error_message, NOW())
            """)
            await session.execute(query, {
                "broadcast_id": broadcast_id,
                "user_id": user_id,
                "status": status,
                "error_message": error_message
            })
            await session.commit()

        except Exception as e:
            logger.error("delivery_event_log_error",
                        broadcast_id=broadcast_id,
                        user_id=user_id,
                        error=str(e))

    async def _update_broadcast_progress(self, session: AsyncSession, broadcast_id: str,
                                       sent_count: int, failed_count: int):
        """Update broadcast progress"""
        try:
            query = text("""
                UPDATE broadcasts
                SET sent_count = :sent_count, failed_count = :failed_count, updated_at = NOW()
                WHERE id = :id
            """)
            await session.execute(query, {
                "id": broadcast_id,
                "sent_count": sent_count,
                "failed_count": failed_count
            })
            await session.commit()

        except Exception as e:
            logger.error("broadcast_progress_update_error", broadcast_id=broadcast_id, error=str(e))

    async def _complete_broadcast(self, session: AsyncSession, broadcast_id: str,
                                 sent_count: int, failed_count: int):
        """Complete broadcast campaign"""
        try:
            query = text("""
                UPDATE broadcasts
                SET status = 'completed',
                    sent_count = :sent_count,
                    failed_count = :failed_count,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """)
            await session.execute(query, {
                "id": broadcast_id,
                "sent_count": sent_count,
                "failed_count": failed_count
            })
            await session.commit()

        except Exception as e:
            logger.error("broadcast_completion_error", broadcast_id=broadcast_id, error=str(e))

    async def _fail_broadcast(self, session: AsyncSession, broadcast_id: str, error_message: str):
        """Mark broadcast as failed"""
        try:
            query = text("""
                UPDATE broadcasts
                SET status = 'failed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """)
            await session.execute(query, {"id": broadcast_id})
            await session.commit()

        except Exception as e:
            logger.error("broadcast_fail_update_error", broadcast_id=broadcast_id, error=str(e))

    async def get_broadcast_status(self, session: AsyncSession, broadcast_id: str) -> Optional[Dict[str, Any]]:
        """Get broadcast status and progress"""
        try:
            query = text("""
                SELECT id, bot_id, audience, status, total_users, sent_count, failed_count,
                       created_at, started_at, completed_at
                FROM broadcasts WHERE id = :id
            """)
            result = await session.execute(query, {"id": broadcast_id})
            row = result.fetchone()

            if row:
                return dict(row._mapping)
            return None

        except Exception as e:
            logger.error("get_broadcast_status_error", broadcast_id=broadcast_id, error=str(e))
            return None


# Global broadcast engine instance
broadcast_engine = BroadcastEngine()