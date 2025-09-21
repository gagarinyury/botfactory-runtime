"""Action implementations for DSL flows"""
import re
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
from time import perf_counter

logger = structlog.get_logger()

class ActionExecutor:
    def __init__(self, session: AsyncSession, bot_id: str, user_id: int, chat_id: int = None):
        self.session = session
        self.bot_id = bot_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.context = {}

    async def execute_action(self, action_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return result"""
        try:
            # Check for rate limit policy first
            if action_def.get("type") == "policy.ratelimit.v1":
                return await self._execute_ratelimit_policy(action_def.get("params", {}))
            elif "action.sql_query.v1" in action_def:
                return await self._execute_sql_query(action_def["action.sql_query.v1"])
            elif "action.sql_exec.v1" in action_def:
                return await self._execute_sql_exec(action_def["action.sql_exec.v1"])
            elif "action.reply_template.v1" in action_def:
                return await self._execute_reply_template(action_def["action.reply_template.v1"])
            elif action_def.get("type") == "ops.broadcast.v1":
                return await self._execute_broadcast(action_def.get("params", {}))
            else:
                raise ValueError(f"Unknown action type: {list(action_def.keys())}")
        except Exception as e:
            logger.error("action_execution_failed", action=action_def, error=str(e))
            return {"success": False, "error": str(e)}

    async def _execute_sql_query(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SQL query action"""
        from .telemetry import bot_sql_query_total, dsl_action_latency_ms

        sql = config["sql"]
        result_var = config["result_var"]
        scalar = config.get("scalar", False)
        flatten = config.get("flatten", False)
        start_time = perf_counter()

        # Set action type for security validation
        self._set_action_type('sql_query')

        # Add automatic LIMIT protection if not present
        sql = self._add_limit_protection(sql)

        # Validate SQL safety and build safe parameterized query
        try:
            self._validate_sql_safety(sql)
            params = self._build_safe_parameters()
            stmt = text(sql)

            result = await self.session.execute(stmt, params)
            rows = result.fetchall()

            # Process result based on mode
            if scalar:
                # Return single scalar value or None
                if rows:
                    result_data = rows[0][0] if len(rows[0]) > 0 else None
                else:
                    result_data = None
            elif flatten and rows and len(result.keys()) == 1:
                # Return list of scalar values from single column
                result_data = [row[0] for row in rows]
            else:
                # Default: return list of dicts
                result_data = []
                if rows:
                    columns = result.keys()
                    result_data = [dict(zip(columns, row)) for row in rows]

            # Store in context
            self.context[result_var] = result_data

            # Record metrics
            duration_ms = (perf_counter() - start_time) * 1000
            bot_sql_query_total.labels(self.bot_id).inc()
            dsl_action_latency_ms.labels("sql_query").observe(duration_ms)

            logger.info("sql_query_executed",
                       bot_id=self.bot_id,
                       user_id=self.user_id,
                       sql_hash=hash(sql) % 10000,
                       rows_count=len(rows),
                       result_var=result_var,
                       scalar=scalar,
                       flatten=flatten,
                       duration_ms=int(duration_ms))

            return {
                "success": True,
                "rows": len(rows),
                "var": result_var
            }

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000

            logger.error("sql_query_failed",
                        bot_id=self.bot_id,
                        user_id=self.user_id,
                        sql_hash=hash(sql) % 10000,
                        error=str(e),
                        duration_ms=int(duration_ms))
            raise

    async def _execute_sql_exec(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SQL exec action"""
        from .telemetry import bot_sql_exec_total, dsl_action_latency_ms

        sql = config["sql"]
        start_time = perf_counter()

        # Set action type for security validation
        self._set_action_type('sql_exec')

        # Validate SQL safety and build safe parameterized query
        try:
            self._validate_sql_safety(sql)
            params = self._build_safe_parameters()
            stmt = text(sql)

            result = await self.session.execute(stmt, params)
            await self.session.commit()

            # Record metrics
            duration_ms = (perf_counter() - start_time) * 1000
            bot_sql_exec_total.labels(self.bot_id).inc()
            dsl_action_latency_ms.labels("sql_exec").observe(duration_ms)

            logger.info("sql_exec_executed",
                       bot_id=self.bot_id,
                       user_id=self.user_id,
                       sql_hash=hash(sql) % 10000,
                       rows_affected=result.rowcount,
                       duration_ms=int(duration_ms))

            return {
                "success": True,
                "status": "ok",
                "rows": result.rowcount
            }

        except Exception as e:
            await self.session.rollback()
            duration_ms = (perf_counter() - start_time) * 1000

            logger.error("sql_exec_failed",
                        bot_id=self.bot_id,
                        user_id=self.user_id,
                        sql_hash=hash(sql) % 10000,
                        error=str(e),
                        duration_ms=int(duration_ms))
            raise

    async def _execute_reply_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute reply template action"""
        from .telemetry import reply_sent_total, reply_failed_total, reply_latency_ms
        from .events_logger import create_events_logger

        start_time = perf_counter()
        text_template = config["text"]
        empty_text = config.get("empty_text")
        keyboard_config = config.get("keyboard", [])
        parse_mode = config.get("parse_mode", "HTML")
        llm_improve = config.get("llm_improve", False)  # New: enable LLM text improvement
        llm_style = config.get("llm_style", "neutral")  # New: "short" | "neutral" | "detailed"
        max_tokens = config.get("max_tokens", 200)  # New: max tokens for LLM response
        llm_decision = None  # Track LLM decision for result tagging

        try:
            # Render template (with i18n support)
            rendered_text = await self._render_template_with_i18n(text_template, empty_text)

            # Optionally improve text with LLM (with A/B testing)
            if rendered_text:
                # Determine if LLM should be used (A/B test or explicit config)
                from .llm_ab_testing import llm_ab_tester

                # Pass the explicit llm_improve config to A/B tester
                llm_config = {"llm_improve": llm_improve} if llm_improve != "ab" else {"llm_improve": "ab"}
                llm_decision = llm_ab_tester.should_use_llm_improve(
                    self.bot_id, self.user_id, llm_config
                )

                if llm_decision["use_llm"]:
                    rendered_text = await self._improve_text_with_llm(rendered_text, llm_style, max_tokens)

                    # Record A/B test result if this was an A/B test
                    if llm_decision["ab_test"]:
                        llm_ab_tester.record_experiment_result(
                            "llm_improve",
                            llm_decision["variant"],
                            self.bot_id,
                            self.user_id,
                            "completion"
                        )

            # Build keyboard if provided
            keyboard = None
            if keyboard_config:
                keyboard = self._build_keyboard(keyboard_config)

            # Record metrics
            duration_ms = (perf_counter() - start_time) * 1000
            reply_sent_total.labels(self.bot_id).inc()
            reply_latency_ms.labels(self.bot_id).observe(duration_ms)

            # Log event
            events_logger = create_events_logger(self.session, self.bot_id, self.user_id)
            await events_logger.log_event("reply_render", {
                "template_hash": hash(text_template) % 10000,
                "rendered_length": len(rendered_text),
                "keyboard_buttons": len(keyboard_config),
                "parse_mode": parse_mode,
                "duration_ms": int(duration_ms)
            })

            logger.info("reply_template_executed",
                       bot_id=self.bot_id,
                       user_id=self.user_id,
                       template_length=len(text_template),
                       rendered_length=len(rendered_text),
                       keyboard_buttons=len(keyboard_config),
                       parse_mode=parse_mode,
                       duration_ms=int(duration_ms))

            result = {
                "type": "reply",
                "text": rendered_text,
                "parse_mode": parse_mode,
                "success": True,
                "template_length": len(text_template)  # Add for events logging
            }

            if keyboard:
                result["keyboard"] = keyboard

            # Store LLM decision for result tagging
            if llm_decision:
                result["llm_decision"] = llm_decision

            return result

        except Exception as e:
            # Record failure metrics
            duration_ms = (perf_counter() - start_time) * 1000
            reply_failed_total.labels(self.bot_id).inc()

            # Log error
            logger.error("reply_template_failed",
                        bot_id=self.bot_id,
                        user_id=self.user_id,
                        template=text_template[:100],  # First 100 chars only
                        error=str(e),
                        duration_ms=int(duration_ms))

            # Return fallback
            return {
                "type": "reply",
                "text": "[template error]",
                "parse_mode": "HTML",
                "success": False,
                "error": str(e)
            }

    async def _render_template_with_i18n(self, template: str, empty_text: Optional[str] = None) -> str:
        """Render template with context variables, each loops, and i18n support"""
        # Check if template starts with t: for i18n
        if template.startswith("t:"):
            return await self._render_i18n_template(template, empty_text)
        else:
            # Use legacy template rendering
            return self._render_template(template, empty_text)

    async def _render_i18n_template(self, template: str, empty_text: Optional[str] = None) -> str:
        """Render i18n template with t:key {placeholder=value} syntax"""
        from .i18n_manager import i18n_manager

        try:
            # Parse template: t:key or t:key {name={{var}}}
            template = template[2:]  # Remove "t:" prefix

            # Check for placeholders: t:key {name={{username}}}
            placeholder_match = re.match(r'^([^\s]+)\s*\{(.+)\}$', template)

            if placeholder_match:
                key = placeholder_match.group(1)
                placeholders_str = placeholder_match.group(2)

                # Parse placeholders: name={{username}}, age={{user_age}}
                placeholders = {}
                for placeholder in placeholders_str.split(','):
                    placeholder = placeholder.strip()
                    if '=' in placeholder:
                        name, value_template = placeholder.split('=', 1)
                        name = name.strip()
                        value_template = value_template.strip()

                        # Render value template with context
                        if value_template.startswith('{{') and value_template.endswith('}}'):
                            var_name = value_template[2:-2]
                            if var_name in self.context:
                                placeholders[name] = str(self.context[var_name])
                            else:
                                placeholders[name] = value_template  # Keep as-is
                        else:
                            placeholders[name] = value_template
            else:
                # Simple key without placeholders
                key = template.strip()
                placeholders = {}

            # Get current locale for this user/chat
            locale = await self._get_current_locale()

            # Translate the key
            translated = await i18n_manager.translate(
                self.session, self.bot_id, key, locale, **placeholders
            )

            return translated

        except Exception as e:
            logger.error("i18n_template_error",
                        bot_id=self.bot_id,
                        template=template,
                        error=str(e))
            # Fallback to key in brackets
            return f"[{template[2:] if template.startswith('t:') else template}]"

    async def _get_current_locale(self) -> str:
        """Get current locale for this user/chat"""
        from .i18n_manager import i18n_manager

        if hasattr(self, 'locale') and self.locale:
            return self.locale

        # Get user's locale with default strategy
        self.locale = await i18n_manager.get_user_locale(
            self.session, self.bot_id, self.user_id, self.chat_id, "user"
        )
        return self.locale

    async def _execute_broadcast(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute broadcast action"""
        from .broadcast_engine import broadcast_engine
        from .telemetry import dsl_action_latency_ms

        start_time = perf_counter()

        try:
            audience = config.get("audience", "all")
            message = config.get("message", "")
            throttle = config.get("throttle", {"per_sec": 30})
            track_metrics = config.get("track_metrics", True)

            # Validate parameters
            if not message:
                raise ValueError("Message is required for broadcast")

            # Handle template message with variables
            if isinstance(message, str) and message.startswith("t:"):
                # i18n template message
                variables = {var_name: var_value for var_name, var_value in self.context.items()}
                message_obj = {
                    "type": "template",
                    "template": message,
                    "variables": variables
                }
            else:
                # Simple text message
                message_obj = message

            # Create and start broadcast
            broadcast_id = await broadcast_engine.create_broadcast(
                self.session, self.bot_id, audience, message_obj, throttle
            )

            started = await broadcast_engine.start_broadcast(self.session, broadcast_id)

            if not started:
                raise RuntimeError("Failed to start broadcast campaign")

            # Record metrics
            duration_ms = (perf_counter() - start_time) * 1000
            dsl_action_latency_ms.labels("broadcast").observe(duration_ms)

            logger.info("broadcast_action_executed",
                       bot_id=self.bot_id,
                       user_id=self.user_id,
                       broadcast_id=broadcast_id,
                       audience=audience,
                       duration_ms=int(duration_ms))

            return {
                "success": True,
                "type": "broadcast",
                "broadcast_id": broadcast_id,
                "audience": audience,
                "status": "running"
            }

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error("broadcast_action_failed",
                        bot_id=self.bot_id,
                        user_id=self.user_id,
                        audience=config.get("audience"),
                        error=str(e),
                        duration_ms=int(duration_ms))
            raise

    def _build_safe_parameters(self) -> Dict[str, Any]:
        """Build safe parameters for SQLAlchemy bound parameters"""
        # Validate SQL action type
        action_type = getattr(self, '_current_action_type', 'unknown')
        if action_type not in ['sql_query', 'sql_exec']:
            raise ValueError(f"Invalid action type: {action_type}")

        # Build parameter dictionary for SQLAlchemy binding
        params = {
            "bot_id": self.bot_id,
            "user_id": int(self.user_id)
        }

        # Add context variables with type validation
        for var_name, var_value in self.context.items():
            if isinstance(var_value, (str, int, float, bool)):
                params[var_name] = var_value
            elif var_value is None:
                params[var_name] = None
            else:
                # For complex types, serialize to JSON
                params[var_name] = json.dumps(var_value)

        return params

    def _validate_sql_safety(self, sql: str) -> None:
        """Validate SQL statement for security"""
        # Check for multiple statements
        if ';' in sql.rstrip(';'):
            raise ValueError("Multiple SQL statements not allowed for security")

        sql_upper = sql.upper().strip()
        action_type = getattr(self, '_current_action_type', 'unknown')

        # Validate statement type based on action
        if action_type == 'sql_query':
            if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
                raise ValueError("Only SELECT and WITH statements allowed for sql_query actions")
        elif action_type == 'sql_exec':
            if not (sql_upper.startswith('INSERT') or sql_upper.startswith('UPDATE') or sql_upper.startswith('DELETE')):
                raise ValueError("Only INSERT, UPDATE and DELETE statements allowed for sql_exec actions")

        # Check for dangerous keywords (additional security layer)
        dangerous_patterns = [
            'DROP ', 'CREATE ', 'ALTER ', 'TRUNCATE ', 'GRANT ', 'REVOKE ',
            'EXEC ', 'EXECUTE ', 'CALL ', 'LOAD_FILE', 'INTO OUTFILE'
        ]

        for pattern in dangerous_patterns:
            if pattern in sql_upper:
                raise ValueError(f"Dangerous SQL pattern detected: {pattern.strip()}")

    def _set_action_type(self, action_type: str):
        """Set current action type for security validation"""
        self._current_action_type = action_type

    def _render_template(self, template: str, empty_text: Optional[str] = None) -> str:
        """Render template with context variables and each loops"""
        # Check if we have any rows for #each loops
        has_data = any(isinstance(v, list) and len(v) > 0 for v in self.context.values())

        # If no data and empty_text provided, return empty_text
        if not has_data and empty_text:
            return empty_text

        result = template

        # Substitute simple variables {{var}}
        for var_name, var_value in self.context.items():
            if isinstance(var_value, str):
                result = result.replace(f"{{{{{var_name}}}}}", var_value)
            elif isinstance(var_value, (int, float)):
                result = result.replace(f"{{{{{var_name}}}}}", str(var_value))

        # Handle {{#each varname}}...{{/each}} loops
        each_pattern = r'\{\{#each\s+(\w+)\}\}(.*?)\{\{/each\}\}'

        def replace_each(match):
            var_name = match.group(1)
            loop_template = match.group(2)

            if var_name not in self.context:
                return ""

            rows = self.context[var_name]
            if not isinstance(rows, list):
                return ""

            loop_result = []
            for row in rows:
                loop_text = loop_template
                if isinstance(row, dict):
                    # Substitute row fields
                    for field_name, field_value in row.items():
                        loop_text = loop_text.replace(f"{{{{{field_name}}}}}", str(field_value))
                loop_result.append(loop_text)

            return "".join(loop_result)

        result = re.sub(each_pattern, replace_each, result, flags=re.DOTALL)

        return result

    def _build_keyboard(self, keyboard_config: List[Any]) -> List[List[Dict[str, str]]]:
        """Build inline keyboard from configuration"""
        keyboard = []

        for item in keyboard_config:
            if isinstance(item, list):
                # Row of buttons
                row = []
                for button_config in item:
                    button = self._build_button(button_config)
                    if button:
                        row.append(button)
                if row:
                    keyboard.append(row)
            else:
                # Single button - create new row
                button = self._build_button(item)
                if button:
                    keyboard.append([button])

        return keyboard

    def _build_button(self, button_config: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Build single keyboard button"""
        if not isinstance(button_config, dict):
            return None

        text = button_config.get("text", "")
        callback = button_config.get("callback", "")

        if not text or not callback:
            return None

        # Determine callback type
        if callback.startswith("/"):
            # This is an intent - will be handled by DSL engine
            callback_data = callback
        else:
            # Regular callback data
            callback_data = callback

        return {
            "text": text,
            "callback_data": callback_data
        }

    def _add_limit_protection(self, sql: str) -> str:
        """Add automatic LIMIT protection if not present"""
        sql_upper = sql.upper().strip()

        # Check if LIMIT is already present
        if 'LIMIT' in sql_upper:
            return sql

        # Check if this is a potentially unbounded query
        has_select = sql_upper.startswith('SELECT') or 'SELECT' in sql_upper
        has_table = any(keyword in sql_upper for keyword in ['FROM', 'JOIN'])

        # Add LIMIT 100 for unbounded SELECT queries
        if has_select and has_table:
            return f"{sql.rstrip()} LIMIT 100"

        return sql

    def set_context_var(self, name: str, value: Any):
        """Set a context variable"""
        self.context[name] = value

    def get_context(self) -> Dict[str, Any]:
        """Get current context"""
        return self.context.copy()

    async def _improve_text_with_llm(self, text: str, llm_style: str = "neutral", max_tokens: int = 200) -> str:
        """Improve text using LLM if enabled"""
        try:
            from .llm_client import llm_client
            from .llm_prompts import BotPromptConfigs
            import os

            # Check if LLM is enabled globally and for this bot
            global_llm_enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
            if not global_llm_enabled:
                return text

            # Check bot-specific LLM settings
            bot_llm_enabled = await self._get_bot_llm_enabled()
            if not bot_llm_enabled:
                return text

            # Skip improvement for very short or already good text
            if len(text) < 10 or len(text) > 500:
                return text

            # Get bot-specific LLM preset if not explicitly provided
            if llm_style == "neutral":  # Use bot preset if default style
                bot_preset = await self._get_bot_llm_preset()
                if bot_preset:
                    llm_style = bot_preset

            # Get prompt configuration with style
            prompt_config = BotPromptConfigs.improve_bot_message(text, llm_style)

            # Call LLM with caching enabled and circuit breaker protection
            response = await llm_client._with_circuit_breaker(
                self.bot_id,
                llm_client.complete(
                    system=prompt_config["system"],
                    user=prompt_config["user"],
                    temperature=prompt_config["temperature"],
                    max_tokens=min(max_tokens, prompt_config.get("max_tokens", 200)),
                    use_cache=True,
                    bot_id=self.bot_id,
                    user_id=self.user_id
                )
            )

            improved_text = response.content.strip()

            # Validate improved text
            if improved_text and len(improved_text) > 0:
                logger.info("llm_text_improved",
                           bot_id=self.bot_id,
                           original_len=len(text),
                           improved_len=len(improved_text),
                           cached=response.cached,
                           duration_ms=response.duration_ms)
                return improved_text
            else:
                from .logging_setup import mask_user_text
                logger.warning("llm_text_improvement_empty",
                             bot_id=self.bot_id,
                             original_text=mask_user_text(text, 50))
                return text

        except Exception as e:
            # Fallback to original text on any error
            from .logging_setup import mask_user_text
            logger.warning("llm_text_improvement_failed",
                         bot_id=self.bot_id,
                         error=str(e),
                         original_text=mask_user_text(text, 50))
            return text

    async def _execute_ratelimit_policy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute rate limit policy"""
        from .ratelimit_policy import rate_limit_policy

        # Check rate limit
        result = await rate_limit_policy.check_rate_limit(
            self.bot_id, self.user_id, self.chat_id, params, self.context
        )

        if not result["allowed"]:
            # Rate limit exceeded - return blocking response
            return {
                "success": True,
                "blocked": True,
                "type": "reply",
                "text": result["message"],
                "retry_in": result["retry_in"]
            }
        else:
            # Rate limit passed - continue processing
            return {
                "success": True,
                "blocked": False
            }

    async def _get_bot_llm_enabled(self) -> bool:
        """Get bot LLM enabled setting"""
        try:
            from sqlalchemy import text
            result = await self.session.execute(
                text("SELECT llm_enabled FROM bots WHERE id = :bot_id"),
                {"bot_id": self.bot_id}
            )
            row = result.fetchone()
            return row[0] if row else False
        except Exception as e:
            logger.warning("bot_llm_enabled_check_failed", bot_id=self.bot_id, error=str(e))
            return False

    async def _get_bot_llm_preset(self) -> Optional[str]:
        """Get bot LLM preset setting"""
        try:
            from sqlalchemy import text
            result = await self.session.execute(
                text("SELECT llm_preset FROM bots WHERE id = :bot_id"),
                {"bot_id": self.bot_id}
            )
            row = result.fetchone()
            preset = row[0] if row else "neutral"

            # Validate preset
            if preset in ["short", "neutral", "detailed"]:
                return preset
            else:
                logger.warning("invalid_bot_llm_preset", bot_id=self.bot_id, preset=preset)
                return "neutral"
        except Exception as e:
            logger.warning("bot_llm_preset_check_failed", bot_id=self.bot_id, error=str(e))
            return "neutral"