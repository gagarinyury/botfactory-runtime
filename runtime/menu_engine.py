from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import HTTPException
from typing import Dict, Any

def build_menu_message(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds the message text and inline keyboard for a menu flow.
    """
    text = params.get("title", "Menu")
    options = params.get("options", [])
    
    buttons = []
    for option in options:
        buttons.append([InlineKeyboardButton(text=option["text"], callback_data=option["callback"])])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    return {"text": text, "reply_markup": keyboard}

def register_menu_flows(router: Router, spec: dict):
    """
    Registers handlers for menu flows.
    """
    import structlog
    logger = structlog.get_logger()

    flows = spec.get("flows", [])
    for flow in flows:
        if flow.get("type") == "flow.menu.v1":
            command = flow.get("entry_cmd")
            if command and command.startswith("/"):
                cmd_name = command.lstrip('/')
                logger.info("registering_menu_cmd", cmd=command, cmd_name=cmd_name)

                @router.message(Command(commands=[cmd_name]))
                async def menu_handler(message: Message, f=flow):
                    logger.info("menu_cmd_triggered", cmd=cmd_name, message_text=message.text, user_id=message.from_user.id)
                    menu_data = build_menu_message(f.get("params", {}))
                    await message.answer(text=menu_data["text"], reply_markup=menu_data["reply_markup"])

# Legacy compatibility - создаем объект menu_engine для обратной совместимости
class MenuEngine:
    """Legacy compatibility wrapper for menu engine functions"""
    pass

# Создаем экземпляр для импорта
menu_engine = MenuEngine()
