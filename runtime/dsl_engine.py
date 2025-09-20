from typing import Dict, Any, List
from fastapi import APIRouter
import json
from aiogram import Router

class DSLEngine:
    def __init__(self):
        pass

    def build_router_from_spec(self, spec_json: Dict[str, Any]) -> Dict[str, Any]:
        """Build echo router from spec_json - stub implementation"""
        try:
            # Extract basic info from spec
            intents = spec_json.get("intents", [])
            flows = spec_json.get("flows", [])

            # Create simple echo router configuration
            echo_router = {
                "type": "echo_router",
                "handlers": [
                    {
                        "pattern": ".*",
                        "action": "echo",
                        "response": "Echo: {user_message}"
                    }
                ],
                "fallback": {
                    "action": "echo",
                    "response": "Echo fallback: {user_message}"
                }
            }

            # Return router configuration with meta info
            return {
                "status": "ok",
                "router_built": True,
                "router_type": "echo",
                "intents_count": len(intents),
                "flows_count": len(flows),
                "router_config": echo_router,
                "message": "Echo router built successfully"
            }
        except Exception as e:
            return {
                "status": "error",
                "router_built": False,
                "error": str(e),
                "message": "Failed to build router from spec"
            }

    def build_router_from_jsonb(self, jsonb_config: str) -> APIRouter:
        """Build FastAPI router from JSONB configuration"""
        try:
            config = json.loads(jsonb_config) if isinstance(jsonb_config, str) else jsonb_config
            router = APIRouter()

            # Extract routes from config
            routes = config.get("routes", [])

            for route_config in routes:
                self._add_route_to_router(router, route_config)

            return router
        except Exception as e:
            # Return empty router on error
            return APIRouter()

    def _add_route_to_router(self, router: APIRouter, route_config: Dict[str, Any]):
        """Add a single route to the router based on configuration"""
        method = route_config.get("method", "GET").upper()
        path = route_config.get("path", "/")
        handler_config = route_config.get("handler", {})

        # Create a dynamic handler
        async def dynamic_handler():
            return {"message": f"Handler for {method} {path}", "config": handler_config}

        # Add route to router
        if method == "GET":
            router.get(path)(dynamic_handler)
        elif method == "POST":
            router.post(path)(dynamic_handler)
        elif method == "PUT":
            router.put(path)(dynamic_handler)
        elif method == "DELETE":
            router.delete(path)(dynamic_handler)

    def validate_jsonb_config(self, jsonb_config: str) -> tuple[bool, str]:
        """Validate JSONB configuration"""
        try:
            config = json.loads(jsonb_config) if isinstance(jsonb_config, str) else jsonb_config

            if not isinstance(config, dict):
                return False, "Configuration must be a dictionary"

            routes = config.get("routes", [])
            if not isinstance(routes, list):
                return False, "Routes must be a list"

            for i, route in enumerate(routes):
                if not isinstance(route, dict):
                    return False, f"Route {i} must be a dictionary"

                if "path" not in route:
                    return False, f"Route {i} missing required 'path' field"

            return True, "Valid configuration"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

async def load_spec(bot_id: str) -> Dict[str, Any]:
    """Load spec for bot - using the existing loader"""
    from .loader import BotLoader
    from .main import async_session

    loader = BotLoader()
    async with async_session() as session:
        bot_config = await loader.load_spec_by_bot_id(session, bot_id)
        if bot_config:
            return bot_config["spec_json"]
        return {}

async def handle(bot_id: str, text: str) -> str:
    """Handle incoming text for bot"""
    spec = await load_spec(bot_id)
    reply = next((i["reply"] for i in spec.get("intents", [])
                  if i.get("cmd") == text), "Не знаю эту команду")
    return reply

def build_router(spec) -> Router:
    """Build aiogram Router from spec_json"""
    r = Router()
    from aiogram.types import Message
    from aiogram.filters import Command

    def add_cmd(cmd: str, reply: str):
        cmd_name = cmd.lstrip('/')
        @r.message(Command(commands=[cmd_name]))
        async def _(m: Message, _reply=reply):
            await m.answer(_reply)

    for it in spec.get("intents", []):
        if "cmd" in it:
            add_cmd(it["cmd"], it.get("reply", ""))

    return r