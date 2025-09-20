"""Wizard state machine engine"""
import re
from typing import Dict, Any, Optional, List
from .redis_client import redis_client
from .actions import ActionExecutor
from .schemas import Flow, FlowStep
from .events_logger import create_events_logger
from .telemetry import wizard_flows, wizard_steps, wizard_completions
import structlog

logger = structlog.get_logger()

class WizardEngine:
    def __init__(self):
        pass

    async def handle_wizard_message(self, bot_id: str, user_id: int, text: str, flows: List[Flow], session) -> str:
        """Handle incoming message in wizard context"""

        # Check if this is an entry command for any flow
        for flow in flows:
            if text == flow.entry_cmd:
                return await self._start_wizard(bot_id, user_id, flow, session)

        # Check if user is in active wizard session
        wizard_state = await redis_client.get_wizard_state(bot_id, user_id)
        if wizard_state:
            return await self._continue_wizard(bot_id, user_id, text, wizard_state, session)

        # No wizard active, return None to let other handlers process
        return None

    async def _start_wizard(self, bot_id: str, user_id: int, flow: Flow, session) -> str:
        """Start a new wizard flow"""
        logger.info("wizard_started", bot_id=bot_id, user_id=user_id, entry_cmd=flow.entry_cmd)

        # Create events logger
        events_logger = create_events_logger(session, bot_id, user_id)
        await events_logger.log_update(flow.entry_cmd)

        # Update metrics
        wizard_flows.labels(bot_id, flow.entry_cmd).inc()

        # Initialize wizard state
        state = {
            "flow": flow.dict(),
            "step": 0,
            "vars": {},
            "started_at": structlog.get_context().get("timestamp")
        }

        # Execute on_enter actions if any
        if flow.on_enter:
            action_executor = ActionExecutor(session, bot_id, user_id)
            for action_def in flow.on_enter:
                result = await action_executor.execute_action(action_def)
                if not result.get("success", False):
                    logger.error("wizard_on_enter_failed", result=result)
                    await events_logger.log_error("wizard_on_enter", str(result))
                    return "Произошла ошибка при запуске."

                # If this is a reply template action, return immediately
                if result.get("type") == "reply":
                    await redis_client.delete_wizard_state(bot_id, user_id)
                    await events_logger.log_action_reply(
                        result.get("template_length", 0),
                        len(result["text"])
                    )
                    # Return structured response for keyboard handling
                    return self._format_response(result)

        # If flow has steps, start with first step
        if flow.steps and len(flow.steps) > 0:
            await redis_client.set_wizard_state(bot_id, user_id, state)
            return flow.steps[0].ask

        # Flow has no steps, just on_enter actions (like /my or /cancel)
        await redis_client.delete_wizard_state(bot_id, user_id)
        return "Готово."

    async def _continue_wizard(self, bot_id: str, user_id: int, text: str, state: Dict[str, Any], session) -> str:
        """Continue existing wizard flow"""
        flow_data = state["flow"]
        current_step = state["step"]
        vars_data = state["vars"]

        flow = Flow(**flow_data)

        if not flow.steps or current_step >= len(flow.steps):
            # Should not happen, but clean up state
            await redis_client.delete_wizard_state(bot_id, user_id)
            return "Визард завершён."

        step = flow.steps[current_step]

        # Validate input if validation is configured
        if step.validate:
            if not re.match(step.validate.regex, text):
                logger.info("wizard_validation_failed",
                           bot_id=bot_id, user_id=user_id,
                           step=current_step, input=text)
                return step.validate.msg

        # Store validated input
        vars_data[step.var] = text

        logger.info("wizard_step_completed",
                   bot_id=bot_id, user_id=user_id,
                   step=current_step, var=step.var)

        # Execute on_step actions if any
        if flow.on_step:
            action_executor = ActionExecutor(session, bot_id, user_id)
            # Set current context
            for var_name, var_value in vars_data.items():
                action_executor.set_context_var(var_name, var_value)

            for action_def in flow.on_step:
                result = await action_executor.execute_action(action_def)
                if not result.get("success", False):
                    logger.error("wizard_on_step_failed", result=result)

        # Move to next step
        next_step = current_step + 1

        if next_step >= len(flow.steps):
            # All steps completed, execute on_complete actions
            return await self._complete_wizard(bot_id, user_id, flow, vars_data, session)
        else:
            # Update state and ask next question
            state["step"] = next_step
            state["vars"] = vars_data
            await redis_client.set_wizard_state(bot_id, user_id, state)
            return flow.steps[next_step].ask

    async def _complete_wizard(self, bot_id: str, user_id: int, flow: Flow, vars_data: Dict[str, Any], session) -> str:
        """Complete wizard flow"""
        logger.info("wizard_completed", bot_id=bot_id, user_id=user_id, vars=vars_data)

        # Clean up wizard state
        await redis_client.delete_wizard_state(bot_id, user_id)

        # Execute on_complete actions
        if flow.on_complete:
            action_executor = ActionExecutor(session, bot_id, user_id)

            # Set all collected variables in context
            for var_name, var_value in vars_data.items():
                action_executor.set_context_var(var_name, var_value)

            final_response = "Готово."

            for action_def in flow.on_complete:
                result = await action_executor.execute_action(action_def)
                if not result.get("success", False):
                    logger.error("wizard_on_complete_failed", result=result)
                    return "Произошла ошибка при завершении."

                # If this is a reply template action, use its response as final response
                if result.get("type") == "reply":
                    final_response = self._format_response(result)

            return final_response

        return "Визард завершён."

    def _format_response(self, result: Dict[str, Any]) -> Any:
        """Format action response for return"""
        # For now, return just the text to maintain compatibility
        # In the future, this could return structured data for keyboard handling
        if "keyboard" in result:
            # TODO: Implement keyboard handling in DSL engine
            # For now, just return text
            return result["text"]
        else:
            return result["text"]

    async def reset_wizard(self, bot_id: str, user_id: int):
        """Reset/cancel current wizard"""
        await redis_client.delete_wizard_state(bot_id, user_id)
        logger.info("wizard_reset", bot_id=bot_id, user_id=user_id)

# Global wizard engine instance
wizard_engine = WizardEngine()