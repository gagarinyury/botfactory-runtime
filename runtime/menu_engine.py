"""Menu flow engine for simple navigation menus"""
from typing import Dict, Any, List, Optional
from .schemas import MenuFlow, MenuOption
from .events_logger import create_events_logger
from .telemetry import wizard_flows, template_renders
import structlog

logger = structlog.get_logger()

class MenuEngine:
    def __init__(self):
        pass

    async def handle_menu_command(self, bot_id: str, user_id: int, text: str, menu_flows: List[MenuFlow], session) -> Optional[Dict[str, Any]]:
        """Handle menu command and return structured response"""

        # Check if this is an entry command for any menu flow
        for menu_flow in menu_flows:
            if text == menu_flow.entry_cmd:
                return await self._build_menu_response(bot_id, user_id, menu_flow, session)

        return None

    async def _build_menu_response(self, bot_id: str, user_id: int, menu_flow: MenuFlow, session) -> Dict[str, Any]:
        """Build menu response with title and inline keyboard"""
        logger.info("menu_flow_started", bot_id=bot_id, user_id=user_id, entry_cmd=menu_flow.entry_cmd)

        # Create events logger
        events_logger = create_events_logger(session, bot_id, user_id)
        await events_logger.log_update(menu_flow.entry_cmd)

        # Update metrics
        wizard_flows.labels(bot_id, menu_flow.entry_cmd).inc()
        template_renders.labels(bot_id).inc()

        # Extract parameters
        params = menu_flow.params
        title = params.get("title", "Выберите действие:")
        options = params.get("options", [])

        # Build inline keyboard
        keyboard = self._build_menu_keyboard(options)

        # Log menu display
        await events_logger.log_action_reply(len(title), len(title))

        logger.info("menu_flow_completed",
                   bot_id=bot_id, user_id=user_id,
                   options_count=len(options))

        return {
            "type": "reply",
            "text": title,
            "keyboard": keyboard,
            "success": True
        }

    def _build_menu_keyboard(self, options: List[Dict[str, str]]) -> List[List[Dict[str, str]]]:
        """Build inline keyboard from menu options"""
        keyboard = []

        for option in options:
            text = option["text"]
            callback = option["callback"]

            # Determine callback type
            if callback.startswith("/"):
                # This is an intent - will be handled by DSL engine
                callback_data = callback
            else:
                # Regular callback data
                callback_data = callback

            button = {
                "text": text,
                "callback_data": callback_data
            }

            # Each button on its own row for better UX in menus
            keyboard.append([button])

        return keyboard

    def parse_menu_flows(self, spec_data: Dict[str, Any]) -> List[MenuFlow]:
        """Parse menu flows from bot specification"""
        menu_flows = []

        # Check for direct menu_flows section
        if "menu_flows" in spec_data:
            for menu_data in spec_data["menu_flows"]:
                menu_flow = MenuFlow(**menu_data)
                menu_flows.append(menu_flow)

        # Also check in flows section for type: "flow.menu.v1"
        if "flows" in spec_data:
            for flow_data in spec_data["flows"]:
                if isinstance(flow_data, dict) and flow_data.get("type") == "flow.menu.v1":
                    menu_flow = MenuFlow(**flow_data)
                    menu_flows.append(menu_flow)

        return menu_flows

# Global instance
menu_engine = MenuEngine()