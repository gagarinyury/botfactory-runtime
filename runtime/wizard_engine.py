from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup
from fastapi import HTTPException
from typing import Dict, Any, Optional
import re
import json
from .redis_client import redis_client
from .actions import ActionExecutor
from .main import async_session # For DB access
from .telemetry import wizard_active_total, wizard_steps_total, wizard_errors_total

# --- State Management ---

async def get_wizard_state(bot_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    return await redis_client.get_wizard_state(bot_id, user_id)

async def set_wizard_state(bot_id: str, user_id: int, state: Dict[str, Any]):
    await redis_client.set_wizard_state(bot_id, user_id, state)

async def delete_wizard_state(bot_id: str, user_id: int):
    await redis_client.delete_wizard_state(bot_id, user_id)

# --- Flow Logic ---

async def start_wizard(bot_id: str, user_id: int, flow: Dict[str, Any]) -> str:
    wizard_active_total.labels(bot_id).inc()
    initial_state = {
        "flow_id": flow["entry_cmd"],
        "step_index": 0,
        "vars": {}
    }
    await set_wizard_state(bot_id, user_id, initial_state)
    first_step = flow["params"]["steps"][0]
    return first_step["ask"]

async def handle_step(bot_id: str, user_id: int, text: str, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state = await get_wizard_state(bot_id, user_id)
    if not state:
        return None

    flow = next((f for f in spec.get("flows", []) if f.get("entry_cmd") == state["flow_id"]), None)
    if not flow:
        wizard_errors_total.labels(bot_id, state.get("flow_id")).inc()
        await delete_wizard_state(bot_id, user_id)
        wizard_active_total.labels(bot_id).dec()
        return {"text": "Error: Wizard configuration not found. Your session has been reset."}

    steps = flow["params"]["steps"]
    current_step_index = state["step_index"]
    
    if current_step_index >= len(steps):
        await delete_wizard_state(bot_id, user_id)
        wizard_active_total.labels(bot_id).dec()
        return {"text": "You have already completed the wizard."}

    current_step = steps[current_step_index]

    if "validate_regex" in current_step:
        if not re.match(current_step["validate_regex"], text):
            wizard_errors_total.labels(bot_id, flow["entry_cmd"]).inc()
            return {"text": f"Invalid input. Please try again.\n{current_step['ask']}"}

    state["vars"][current_step["var"]] = text
    state["step_index"] += 1
    wizard_steps_total.labels(bot_id, flow["entry_cmd"]).inc()

    if state["step_index"] >= len(steps):
        await delete_wizard_state(bot_id, user_id)
        wizard_active_total.labels(bot_id).dec()
        return await execute_actions(bot_id, user_id, flow["params"].get("on_complete", []), state.get("vars", {}))
    else:
        next_step = steps[state["step_index"]]
        await set_wizard_state(bot_id, user_id, state)
        return {"text": next_step["ask"]}

async def cancel_wizard(bot_id: str, user_id: int) -> str:
    state = await get_wizard_state(bot_id, user_id)
    if state:
        await delete_wizard_state(bot_id, user_id)
        wizard_active_total.labels(bot_id).dec()
    return "Your operation has been cancelled."

async def execute_actions(bot_id: str, user_id: int, actions: list, context_vars: dict) -> Optional[Dict[str, Any]]:
    final_reply = None
    async with async_session() as session:
        executor = ActionExecutor(session, bot_id, user_id)
        executor.context = context_vars

        for action_def in actions:
            action_key = action_def["type"].replace(".", "_")
            adapted_action = {action_key.replace("_", "."): action_def["params"]}
            
            action_result = await executor.execute_action(adapted_action)
            if not action_result.get("success"):
                # Consider logging the error more formally
                return {"text": f"An error occurred: {action_result.get('error', 'Unknown error')}"}
            
            if action_result.get("type") == "reply":
                final_reply = action_result

    return final_reply or {"text": "Actions completed successfully."}

# --- Router Registration ---

def find_flow_by_cmd(spec: dict, command: str) -> Optional[dict]:
    for flow in spec.get("flows", []):
        if flow.get("entry_cmd") == command:
            return flow
    return None

def register_wizard_flows(router: Router, spec: dict):
    for flow in spec.get("flows", []):
        flow_type = flow.get("type")
        command = flow.get("entry_cmd")

        if not (command and command.startswith("/")):
            continue

        cmd_name = command.lstrip('/')

        if flow_type == "flow.wizard.v1":
            @router.message(Command(commands=[cmd_name]))
            async def wizard_start_handler(message: Message, s=spec, c=command):
                bot_id = getattr(message, 'bot_id', 'unknown')
                user_id = message.from_user.id
                flow_def = find_flow_by_cmd(s, c)
                if flow_def:
                    reply_text = await start_wizard(bot_id, user_id, flow_def)
                    await message.answer(reply_text)
        
        elif flow_type == "flow.generic.v1":
            @router.message(Command(commands=[cmd_name]))
            async def generic_flow_handler(message: Message, s=spec, c=command):
                bot_id = getattr(message, 'bot_id', 'unknown')
                user_id = message.from_user.id
                flow_def = find_flow_by_cmd(s, c)
                if flow_def:
                    result = await execute_actions(bot_id, user_id, flow_def["params"].get("on_enter", []), {})
                    if result and result.get("text"):
                        reply_markup = None
                        if result.get("reply_markup") and isinstance(result["reply_markup"], dict):
                            reply_markup = InlineKeyboardMarkup(**result["reply_markup"])
                        await message.answer(result["text"], reply_markup=reply_markup)

    @router.message(Command(commands=["cancel"]))
    async def cancel_handler(message: Message):
        bot_id = getattr(message, 'bot_id', 'unknown')
        user_id = message.from_user.id
        reply_text = await cancel_wizard(bot_id, user_id)
        await message.answer(reply_text)
