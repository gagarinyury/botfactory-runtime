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
    def __init__(self, session: AsyncSession, bot_id: str, user_id: int):
        self.session = session
        self.bot_id = bot_id
        self.user_id = user_id
        self.context = {}

    async def execute_action(self, action_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return result"""
        try:
            if "action.sql_query.v1" in action_def:
                return await self._execute_sql_query(action_def["action.sql_query.v1"])
            elif "action.sql_exec.v1" in action_def:
                return await self._execute_sql_exec(action_def["action.sql_exec.v1"])
            elif "action.reply_template.v1" in action_def:
                return await self._execute_reply_template(action_def["action.reply_template.v1"])
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
        text_template = config["text"]
        empty_text = config.get("empty_text")
        keyboard_config = config.get("keyboard", [])

        # Render template
        rendered_text = self._render_template(text_template, empty_text)

        # Build keyboard if provided
        keyboard = None
        if keyboard_config:
            keyboard = self._build_keyboard(keyboard_config)

        logger.info("reply_template_executed",
                   template_length=len(text_template),
                   rendered_length=len(rendered_text),
                   keyboard_buttons=len(keyboard_config))

        result = {
            "type": "reply",
            "text": rendered_text,
            "success": True
        }

        if keyboard:
            result["keyboard"] = keyboard

        return result

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

    def _build_keyboard(self, keyboard_config: List[Dict[str, str]]) -> List[List[Dict[str, str]]]:
        """Build inline keyboard from configuration"""
        keyboard = []

        for button_config in keyboard_config:
            text = button_config["text"]
            callback = button_config["callback"]

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

            # Each button on its own row for simplicity
            keyboard.append([button])

        return keyboard

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