"""Pagination widget implementation for paginated lists with inline navigation"""
import re
import math
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
from time import perf_counter

logger = structlog.get_logger()


class PaginationWidget:
    """Pagination widget for inline paginated lists with navigation"""

    def __init__(self):
        self.max_page_size = 50  # Security limit

    async def render_pagination(self, bot_id: str, user_id: int, params: Dict[str, Any],
                              session: AsyncSession, context_vars: Dict[str, Any] = None) -> Dict[str, Any]:
        """Render pagination widget and return message with keyboard"""
        from .telemetry import widget_pagination_renders_total

        start_time = perf_counter()
        context_vars = context_vars or {}

        # Extract parameters
        source = params["source"]
        page_size = min(params.get("page_size", 5), self.max_page_size)
        item_template = params["item_template"]
        select_callback = params["select_callback"]
        id_field = params["id_field"]
        title = params.get("title", "Список:")
        empty_text = params.get("empty_text", "Пусто")
        extra_keyboard = params.get("extra_keyboard", [])
        current_page = params.get("current_page", 0)

        try:
            # Get data from source
            if source["type"] == "sql":
                items, total_count = await self._get_sql_data(
                    source["sql"], bot_id, user_id, page_size, current_page, session, context_vars
                )
            elif source["type"] == "ctx":
                items, total_count = await self._get_ctx_data(
                    source["ctx_var"], page_size, current_page, context_vars
                )
            else:
                raise ValueError(f"Unsupported source type: {source['type']}")

            # Build keyboard
            keyboard = self._build_pagination_keyboard(
                items, bot_id, user_id, current_page, page_size, total_count,
                item_template, select_callback, id_field, extra_keyboard
            )

            # Build message text
            if not items and empty_text:
                message_text = empty_text
            else:
                message_text = self._build_message_text(title, items, item_template, current_page, page_size, total_count)

            # Record metrics
            duration_ms = (perf_counter() - start_time) * 1000
            widget_pagination_renders_total.labels(bot_id).inc()

            logger.info("pagination_render",
                       bot_id=bot_id,
                       user_id=user_id,
                       page=current_page,
                       count=len(items),
                       source=source["type"],
                       duration_ms=int(duration_ms))

            return {
                "type": "reply",
                "text": message_text,
                "keyboard": keyboard,
                "success": True
            }

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error("pagination_render_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        error=str(e),
                        duration_ms=int(duration_ms))

            from .telemetry import errors
            errors.labels(bot_id, "widget_pagination", "render_error").inc()

            return {
                "type": "reply",
                "text": "Ошибка загрузки данных",
                "success": False
            }

    async def _get_sql_data(self, sql: str, bot_id: str, user_id: int, page_size: int,
                           current_page: int, session: AsyncSession, context_vars: Dict[str, Any]) -> tuple:
        """Get data from SQL source"""
        # Security validation
        if ";" in sql:
            raise ValueError("Multiple SQL statements not allowed")

        sql_upper = sql.upper().strip()
        if not sql_upper.startswith("SELECT"):
            raise ValueError("Only SELECT statements allowed for pagination source")

        # Build parameters
        offset = current_page * page_size
        params = {
            "bot_id": bot_id,
            "user_id": user_id,
            "limit": page_size,
            "offset": offset,
            **context_vars
        }

        # Mask sensitive values in params for logging
        safe_params = {k: "***" if "password" in k.lower() or "secret" in k.lower() or "token" in k.lower()
                      else v for k, v in params.items()}

        logger.info("pagination_sql_query",
                   bot_id=bot_id,
                   user_id=user_id,
                   sql_hash=hash(sql) % 10000,
                   params=safe_params)

        try:
            # Execute query for current page
            result = await session.execute(text(sql), params)
            items = [dict(row) for row in result.fetchall()]

            # Count total items (simplified - assumes same query without limit/offset)
            count_sql = re.sub(r'\bLIMIT\s+:\w+', '', sql, flags=re.IGNORECASE)
            count_sql = re.sub(r'\bOFFSET\s+:\w+', '', count_sql, flags=re.IGNORECASE)
            count_sql = f"SELECT COUNT(*) as total FROM ({count_sql}) as subq"

            count_result = await session.execute(text(count_sql), params)
            total_count = count_result.scalar() or 0

            return items, total_count

        except Exception as e:
            logger.error("pagination_sql_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        sql_hash=hash(sql) % 10000,
                        error=str(e))
            raise

    async def _get_ctx_data(self, ctx_var: str, page_size: int, current_page: int,
                           context_vars: Dict[str, Any]) -> tuple:
        """Get data from context variable"""
        items = context_vars.get(ctx_var, [])
        if not isinstance(items, list):
            raise ValueError(f"Context variable {ctx_var} must be a list")

        total_count = len(items)
        offset = current_page * page_size
        paginated_items = items[offset:offset + page_size]

        return paginated_items, total_count

    def _build_pagination_keyboard(self, items: List[Dict], bot_id: str, user_id: int,
                                 current_page: int, page_size: int, total_count: int,
                                 item_template: str, select_callback: str, id_field: str,
                                 extra_keyboard: List[Dict]) -> List[List[Dict[str, str]]]:
        """Build pagination keyboard"""
        keyboard = []

        # Item buttons
        for item in items:
            item_text = self._render_template(item_template, item)
            item_id = item.get(id_field)
            if item_id is not None:
                callback_data = f"pg:sel:{bot_id}:{user_id}:{item_id}"
                keyboard.append([{"text": item_text, "callback_data": callback_data}])

        # Navigation buttons
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        if total_pages > 1:
            nav_row = []

            # Previous button
            if current_page > 0:
                prev_callback = f"pg:prev:{bot_id}:{user_id}:{current_page - 1}"
                nav_row.append({"text": "« Назад", "callback_data": prev_callback})

            # Page indicator
            nav_row.append({"text": f"{current_page + 1}/{total_pages}", "callback_data": "pg:ignore"})

            # Next button
            if current_page < total_pages - 1:
                next_callback = f"pg:next:{bot_id}:{user_id}:{current_page + 1}"
                nav_row.append({"text": "Далее »", "callback_data": next_callback})

            keyboard.append(nav_row)

        # Extra keyboard buttons
        for button in extra_keyboard:
            keyboard.append([button])

        return keyboard

    def _build_message_text(self, title: str, items: List[Dict], item_template: str,
                           current_page: int, page_size: int, total_count: int) -> str:
        """Build message text with title and page info"""
        text_parts = [title]

        if items:
            # Add page info if multiple pages
            total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
            if total_pages > 1:
                text_parts.append(f"\nСтраница {current_page + 1} из {total_pages}")

            # Add items (they will be in keyboard, so just show count)
            text_parts.append(f"\nЭлементов: {len(items)}")
            if total_count > len(items):
                text_parts.append(f" (всего: {total_count})")

        return "".join(text_parts)

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """Render template with context variables"""
        try:
            # Simple template rendering - replace {{var}} with context[var]
            result = template
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value))
            return result
        except Exception as e:
            logger.warning("template_render_error", template=template, error=str(e))
            return template

    async def handle_callback(self, bot_id: str, user_id: int, callback_data: str,
                            session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Handle pagination callback"""
        from .telemetry import widget_pagination_selects_total
        from .events_logger import create_events_logger

        start_time = perf_counter()
        events_logger = create_events_logger(session, bot_id, user_id)

        try:
            if callback_data.startswith("pg:sel:"):
                return await self._handle_selection(callback_data, events_logger)
            elif callback_data.startswith("pg:prev:") or callback_data.startswith("pg:next:"):
                return await self._handle_navigation(callback_data)
            elif callback_data == "pg:ignore":
                return None  # Ignore action
            else:
                logger.warning("pagination_unknown_callback",
                             bot_id=bot_id, user_id=user_id, callback=callback_data)
                return None

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error("pagination_callback_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        callback=callback_data,
                        error=str(e),
                        duration_ms=int(duration_ms))

            from .telemetry import errors
            errors.labels(bot_id, "widget_pagination", "callback_error").inc()

            return {"error": "Ошибка обработки выбора"}

    async def _handle_selection(self, callback_data: str, events_logger) -> Dict[str, Any]:
        """Handle item selection"""
        # Format: pg:sel:bot_id:user_id:item_id
        parts = callback_data.split(":")
        if len(parts) != 5:
            return {"error": "Invalid selection callback"}

        bot_id, user_id, item_id = parts[2], int(parts[3]), parts[4]

        # Log selection
        await events_logger.log_event("pagination_select", {
            "item_id": item_id
        })

        # Record metric
        from .telemetry import widget_pagination_selects_total
        widget_pagination_selects_total.labels(bot_id).inc()

        # Return synthetic input for select_callback
        return {
            "type": "synthetic_input",
            "callback": callback_data,
            "selected_id": item_id
        }

    async def _handle_navigation(self, callback_data: str) -> Dict[str, Any]:
        """Handle page navigation"""
        # Format: pg:prev:bot_id:user_id:page or pg:next:bot_id:user_id:page
        parts = callback_data.split(":")
        if len(parts) != 5:
            return {"error": "Invalid navigation callback"}

        action, bot_id, user_id, page = f"{parts[0]}:{parts[1]}", parts[2], int(parts[3]), int(parts[4])

        return {
            "type": "navigation",
            "action": action,
            "page": page,
            "bot_id": bot_id,
            "user_id": user_id
        }


# Global pagination widget instance
pagination_widget = PaginationWidget()