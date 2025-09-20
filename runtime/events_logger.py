"""Bot events logging to database"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
import time

logger = structlog.get_logger()

class EventsLogger:
    def __init__(self, session: AsyncSession, bot_id: str, user_id: int):
        self.session = session
        self.bot_id = bot_id
        self.user_id = user_id

    async def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        """Log event to bot_events table"""
        try:
            # Prepare data with compact format
            event_data = data or {}

            # Insert event
            sql = """
                INSERT INTO bot_events (bot_id, user_id, type, data)
                VALUES (:bot_id, :user_id, :type, :data)
            """

            await self.session.execute(
                text(sql),
                {
                    "bot_id": self.bot_id,
                    "user_id": self.user_id,
                    "type": event_type,
                    "data": event_data
                }
            )

            # Don't commit here - let caller decide
            logger.info("event_logged",
                       bot_id=self.bot_id,
                       user_id=self.user_id,
                       type=event_type)

        except Exception as e:
            logger.error("event_logging_failed",
                        bot_id=self.bot_id,
                        user_id=self.user_id,
                        type=event_type,
                        error=str(e))

    async def log_update(self, cmd: Optional[str] = None):
        """Log update event"""
        await self.log_event("update", {"cmd": cmd})

    async def log_flow_step(self, flow_cmd: str, step: int, var: str, duration_ms: Optional[int] = None):
        """Log flow step event"""
        data = {
            "flow_cmd": flow_cmd,
            "step": step,
            "var": var
        }
        if duration_ms is not None:
            data["duration_ms"] = duration_ms

        await self.log_event("flow_step", data)

    async def log_action_sql(self, sql_hash: int, duration_ms: Optional[int] = None, rows_affected: Optional[int] = None):
        """Log SQL action event"""
        data = {
            "sql_hash": sql_hash
        }
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        if rows_affected is not None:
            data["rows_affected"] = rows_affected

        await self.log_event("action_sql", data)

    async def log_action_reply(self, template_length: int, rendered_length: int):
        """Log reply action event"""
        await self.log_event("action_reply", {
            "template_length": template_length,
            "rendered_length": rendered_length
        })

    async def log_error(self, error_code: str, error_message: str, context: Optional[Dict[str, Any]] = None):
        """Log error event"""
        data = {
            "code": error_code,
            "message": error_message
        }
        if context:
            data.update(context)

        await self.log_event("error", data)

# Helper function to create events logger
def create_events_logger(session: AsyncSession, bot_id: str, user_id: int) -> EventsLogger:
    """Create events logger instance"""
    return EventsLogger(session, bot_id, user_id)