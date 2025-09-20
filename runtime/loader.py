from typing import Optional, Dict, Any
from sqlalchemy import text
import json

class BotLoader:
    def __init__(self):
        pass

    async def load_spec_by_bot_id(self, session, bot_id: str, version: int = None) -> Optional[Dict[str, Any]]:
        """Load bot spec_json from database by bot_id"""
        try:
            if version is not None:
                # Load specific version
                query = text("""
                    SELECT bs.spec_json, bs.version, b.name, b.token, b.status
                    FROM bot_specs bs
                    JOIN bots b ON b.id = bs.bot_id
                    WHERE bs.bot_id = :bot_id AND bs.version = :version
                """)
                result = await session.execute(query, {"bot_id": bot_id, "version": version})
            else:
                # Load latest version
                query = text("""
                    SELECT bs.spec_json, bs.version, b.name, b.token, b.status
                    FROM bot_specs bs
                    JOIN bots b ON b.id = bs.bot_id
                    WHERE bs.bot_id = :bot_id
                    ORDER BY bs.version DESC
                    LIMIT 1
                """)
                result = await session.execute(query, {"bot_id": bot_id})

            row = result.fetchone()
            if row:
                return {
                    "bot_id": bot_id,
                    "name": row.name,
                    "token": row.token,
                    "status": row.status,
                    "version": row.version,
                    "spec_json": row.spec_json
                }
            return None
        except Exception as e:
            print(f"Error loading spec for bot {bot_id}: {e}")
            return None

    async def load_from_db(self, session, bot_id: str) -> Optional[Dict[str, Any]]:
        """Load bot configuration from database"""
        return await self.load_spec_by_bot_id(session, bot_id)

    async def load_from_plugin(self, plugin_name: str, bot_id: str) -> Optional[Dict[str, Any]]:
        """Load bot configuration from plugin"""
        # TODO: Implement plugin loading
        return None

    async def get_bot_config(self, session, bot_id: str) -> Optional[Dict[str, Any]]:
        """Get bot configuration from available sources"""
        # Try database first
        config = await self.load_from_db(session, bot_id)
        if config:
            return config

        # TODO: Try plugins as fallback
        return None