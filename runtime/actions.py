"""Action implementations for DSL flows"""
import re
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

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
        sql = config["sql"]
        result_var = config["result_var"]

        # Substitute parameters
        sql_with_params = self._substitute_sql_parameters(sql)

        try:
            result = await self.session.execute(text(sql_with_params))
            rows = result.fetchall()

            # Convert to list of dicts
            rows_data = []
            if rows:
                columns = result.keys()
                rows_data = [dict(zip(columns, row)) for row in rows]

            # Store in context
            self.context[result_var] = rows_data

            logger.info("sql_query_executed",
                       sql_hash=hash(sql) % 10000,
                       rows_count=len(rows_data))

            return {
                "success": True,
                "result_var": result_var,
                "rows_count": len(rows_data)
            }

        except Exception as e:
            logger.error("sql_query_failed", sql_hash=hash(sql) % 10000, error=str(e))
            raise

    async def _execute_sql_exec(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SQL exec action"""
        sql = config["sql"]

        # Substitute parameters
        sql_with_params = self._substitute_sql_parameters(sql)

        try:
            result = await self.session.execute(text(sql_with_params))
            await self.session.commit()

            logger.info("sql_exec_executed",
                       sql_hash=hash(sql) % 10000,
                       rows_affected=result.rowcount)

            return {
                "success": True,
                "rows_affected": result.rowcount
            }

        except Exception as e:
            await self.session.rollback()
            logger.error("sql_exec_failed", sql_hash=hash(sql) % 10000, error=str(e))
            raise

    async def _execute_reply_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute reply template action"""
        text_template = config["text"]
        empty_text = config.get("empty_text")

        # Render template
        rendered_text = self._render_template(text_template, empty_text)

        logger.info("reply_template_executed",
                   template_length=len(text_template),
                   rendered_length=len(rendered_text))

        return {
            "success": True,
            "rendered_text": rendered_text
        }

    def _substitute_sql_parameters(self, sql: str) -> str:
        """Substitute SQL parameters with actual values"""
        # Basic parameter substitution for :bot_id, :user_id, and context variables
        params = {
            ":bot_id": f"'{self.bot_id}'",
            ":user_id": str(self.user_id)
        }

        # Add context variables
        for var_name, var_value in self.context.items():
            if isinstance(var_value, str):
                params[f":{var_name}"] = f"'{var_value}'"
            elif isinstance(var_value, (int, float)):
                params[f":{var_name}"] = str(var_value)
            else:
                # For complex types, convert to JSON string
                params[f":{var_name}"] = f"'{json.dumps(var_value)}'"

        result_sql = sql
        for param, value in params.items():
            result_sql = result_sql.replace(param, value)

        return result_sql

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

    def set_context_var(self, name: str, value: Any):
        """Set a context variable"""
        self.context[name] = value

    def get_context(self) -> Dict[str, Any]:
        """Get current context"""
        return self.context.copy()