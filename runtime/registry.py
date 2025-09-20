from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text
import uuid

class BotRegistry:
    def __init__(self):
        pass

    async def create_bot(self, session, name: str, token: str) -> Dict[str, Any]:
        """Create a new bot in database"""
        try:
            result = await session.execute(
                text("INSERT INTO bots(name, token) VALUES (:name, :token) RETURNING id, name, token, status"),
                {"name": name, "token": token}
            )
            bot = result.fetchone()
            await session.commit()
            return {
                "id": str(bot.id),
                "name": bot.name,
                "token": bot.token,
                "status": bot.status
            }
        except Exception as e:
            await session.rollback()
            raise e

    async def get_bot(self, session, bot_id: str) -> Optional[Dict[str, Any]]:
        """Get bot by ID from database"""
        try:
            result = await session.execute(
                text("SELECT id, name, token, status FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            bot = result.fetchone()
            if bot:
                return {
                    "id": str(bot.id),
                    "name": bot.name,
                    "token": bot.token,
                    "status": bot.status
                }
            return None
        except Exception:
            return None

    async def update_bot(self, session, bot_id: str, name: str = None, token: str = None, status: str = None) -> Optional[Dict[str, Any]]:
        """Update bot in database"""
        try:
            updates = []
            params = {"bot_id": bot_id}

            if name is not None:
                updates.append("name = :name")
                params["name"] = name
            if token is not None:
                updates.append("token = :token")
                params["token"] = token
            if status is not None:
                updates.append("status = :status")
                params["status"] = status

            if not updates:
                return await self.get_bot(session, bot_id)

            query = f"UPDATE bots SET {', '.join(updates)} WHERE id = :bot_id RETURNING id, name, token, status"
            result = await session.execute(text(query), params)
            bot = result.fetchone()
            await session.commit()

            if bot:
                return {
                    "id": str(bot.id),
                    "name": bot.name,
                    "token": bot.token,
                    "status": bot.status
                }
            return None
        except Exception as e:
            await session.rollback()
            raise e

    async def delete_bot(self, session, bot_id: str) -> bool:
        """Delete bot from database"""
        try:
            result = await session.execute(
                text("DELETE FROM bots WHERE id = :bot_id"),
                {"bot_id": bot_id}
            )
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            return False

    async def list_bots(self, session) -> List[Dict[str, Any]]:
        """List all bots from database"""
        try:
            result = await session.execute(
                text("SELECT id, name, token, status FROM bots ORDER BY name")
            )
            bots = result.fetchall()
            return [
                {
                    "id": str(bot.id),
                    "name": bot.name,
                    "token": bot.token,
                    "status": bot.status
                }
                for bot in bots
            ]
        except Exception:
            return []

    async def db_ok(self, sess) -> bool:
        """Check database connection"""
        try:
            await sess.execute(text("select 1"))
            return True
        except Exception:
            return False