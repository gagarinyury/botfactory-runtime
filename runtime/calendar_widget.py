"""Calendar widget implementation for date/datetime selection"""
import calendar
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo
import structlog
from time import perf_counter

logger = structlog.get_logger()


class CalendarWidget:
    """Calendar widget for inline date/datetime selection"""

    def __init__(self):
        self.time_slots = [
            "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
            "12:00", "12:30", "13:00", "13:30", "14:00", "14:30",
            "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
            "18:00", "18:30", "19:00", "19:30", "20:00"
        ]

    async def render_calendar(self, bot_id: str, user_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """Render calendar widget and return keyboard markup"""
        from .telemetry import widget_calendar_renders_total

        start_time = perf_counter()

        # Extract parameters
        mode = params.get("mode", "date")  # date or datetime
        var_name = params["var"]
        title = params.get("title", "Выберите дату")
        min_date = params.get("min")  # YYYY-MM-DD
        max_date = params.get("max")  # YYYY-MM-DD
        timezone = params.get("tz", "UTC")

        # Parse date boundaries
        min_dt = datetime.strptime(min_date, "%Y-%m-%d").date() if min_date else None
        max_dt = datetime.strptime(max_date, "%Y-%m-%d").date() if max_date else None

        # Current month view (start with current month)
        today = datetime.now().date()
        current_month = today.replace(day=1)

        # Build keyboard
        keyboard = self._build_calendar_keyboard(
            bot_id, user_id, current_month, min_dt, max_dt, mode, var_name
        )

        # Record metrics
        duration_ms = (perf_counter() - start_time) * 1000
        widget_calendar_renders_total.labels(bot_id).inc()

        logger.info("widget_calendar_render",
                   bot_id=bot_id,
                   user_id=user_id,
                   mode=mode,
                   var=var_name,
                   duration_ms=int(duration_ms))

        return {
            "type": "reply",
            "text": title,
            "keyboard": keyboard,
            "success": True
        }

    def _build_calendar_keyboard(self, bot_id: str, user_id: int, month: date,
                                min_date: Optional[date], max_date: Optional[date],
                                mode: str, var_name: str) -> List[List[Dict[str, str]]]:
        """Build calendar keyboard for given month"""
        keyboard = []

        # Header with month/year and navigation
        month_year = month.strftime("%B %Y")
        prev_month = month - timedelta(days=1)
        prev_month = prev_month.replace(day=1)

        next_month_day = month.replace(day=28) + timedelta(days=4)
        next_month = next_month_day.replace(day=1)

        # Navigation row
        nav_row = [
            {"text": "◀", "callback_data": f"cal_nav:{bot_id}:{user_id}:{prev_month.strftime('%Y-%m')}:{mode}:{var_name}"},
            {"text": month_year, "callback_data": "cal_ignore"},
            {"text": "▶", "callback_data": f"cal_nav:{bot_id}:{user_id}:{next_month.strftime('%Y-%m')}:{mode}:{var_name}"}
        ]
        keyboard.append(nav_row)

        # Days of week header
        weekday_row = []
        for day_name in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
            weekday_row.append({"text": day_name, "callback_data": "cal_ignore"})
        keyboard.append(weekday_row)

        # Calendar grid
        cal = calendar.monthcalendar(month.year, month.month)

        for week in cal:
            week_row = []
            for day_num in week:
                if day_num == 0:
                    # Empty cell
                    week_row.append({"text": " ", "callback_data": "cal_ignore"})
                else:
                    day_date = date(month.year, month.month, day_num)

                    # Check if day is available
                    available = True
                    if min_date and day_date < min_date:
                        available = False
                    if max_date and day_date > max_date:
                        available = False

                    if available:
                        callback_data = f"cal_date:{bot_id}:{user_id}:{day_date.strftime('%Y-%m-%d')}:{mode}:{var_name}"
                        week_row.append({"text": str(day_num), "callback_data": callback_data})
                    else:
                        # Disabled day
                        week_row.append({"text": f"·{day_num}·", "callback_data": "cal_ignore"})

            keyboard.append(week_row)

        return keyboard

    def _build_time_keyboard(self, bot_id: str, user_id: int, selected_date: str,
                           var_name: str) -> List[List[Dict[str, str]]]:
        """Build time selection keyboard"""
        keyboard = []

        # Title row
        title_row = [{"text": f"Время на {selected_date}", "callback_data": "cal_ignore"}]
        keyboard.append(title_row)

        # Time slots in rows of 3
        for i in range(0, len(self.time_slots), 3):
            time_row = []
            for j in range(3):
                if i + j < len(self.time_slots):
                    time_slot = self.time_slots[i + j]
                    # Replace : with - in time to avoid callback parsing issues
                    time_safe = time_slot.replace(":", "-")
                    callback_data = f"cal_time:{bot_id}:{user_id}:{selected_date}:{time_safe}:{var_name}"
                    time_row.append({"text": time_slot, "callback_data": callback_data})
                else:
                    time_row.append({"text": " ", "callback_data": "cal_ignore"})
            keyboard.append(time_row)

        # Back button
        back_row = [{"text": "◀ Назад к дате", "callback_data": f"cal_back:{bot_id}:{user_id}:{var_name}"}]
        keyboard.append(back_row)

        return keyboard

    async def handle_callback(self, bot_id: str, user_id: int, callback_data: str,
                            session) -> Optional[Dict[str, Any]]:
        """Handle calendar callback and return result"""
        from .telemetry import widget_calendar_picks_total
        from .events_logger import create_events_logger

        start_time = perf_counter()
        events_logger = create_events_logger(session, bot_id, user_id)

        try:
            # Parse callback data
            if callback_data.startswith("cal_nav:"):
                return await self._handle_navigation(callback_data)
            elif callback_data.startswith("cal_date:"):
                return await self._handle_date_selection(callback_data, events_logger)
            elif callback_data.startswith("cal_time:"):
                return await self._handle_time_selection(callback_data, events_logger)
            elif callback_data.startswith("cal_back:"):
                return await self._handle_back_to_date(callback_data)
            elif callback_data == "cal_ignore":
                return None  # Ignore action
            else:
                # Unknown callback
                logger.warning("calendar_unknown_callback",
                             bot_id=bot_id, user_id=user_id, callback=callback_data)
                return None

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error("calendar_callback_error",
                        bot_id=bot_id,
                        user_id=user_id,
                        callback=callback_data,
                        error=str(e),
                        duration_ms=int(duration_ms))
            return {"error": "Ошибка обработки календаря"}

    async def _handle_navigation(self, callback_data: str) -> Dict[str, Any]:
        """Handle month navigation"""
        # Format: cal_nav:bot_id:user_id:YYYY-MM:mode:var_name
        parts = callback_data.split(":")
        if len(parts) != 6:
            return {"error": "Invalid navigation callback"}

        bot_id, user_id, month_str, mode, var_name = parts[1], int(parts[2]), parts[3], parts[4], parts[5]

        # Parse target month
        target_month = datetime.strptime(month_str, "%Y-%m").date()

        # Build new calendar
        keyboard = self._build_calendar_keyboard(bot_id, user_id, target_month, None, None, mode, var_name)

        return {
            "type": "edit_message",
            "text": "Выберите дату",
            "keyboard": keyboard
        }

    async def _handle_date_selection(self, callback_data: str, events_logger) -> Dict[str, Any]:
        """Handle date selection"""
        # Format: cal_date:bot_id:user_id:YYYY-MM-DD:mode:var_name
        parts = callback_data.split(":")
        if len(parts) != 6:
            return {"error": "Invalid date callback"}

        bot_id, user_id, selected_date, mode, var_name = parts[1], int(parts[2]), parts[3], parts[4], parts[5]

        # Log date selection
        await events_logger.log_event("widget_calendar_pick_date", {
            "date": selected_date,
            "mode": mode,
            "var": var_name
        })

        # Record metric
        from .telemetry import widget_calendar_picks_total
        widget_calendar_picks_total.labels(bot_id, mode).inc()

        if mode == "date":
            # Return final date value
            return {
                "type": "complete",
                "var": var_name,
                "value": selected_date,
                "message": f"✅ Выбрана дата: {selected_date}"
            }
        elif mode == "datetime":
            # Show time selection
            keyboard = self._build_time_keyboard(bot_id, user_id, selected_date, var_name)
            return {
                "type": "edit_message",
                "text": f"Выберите время на {selected_date}",
                "keyboard": keyboard
            }

    async def _handle_time_selection(self, callback_data: str, events_logger) -> Dict[str, Any]:
        """Handle time selection for datetime mode"""
        # Format: cal_time:bot_id:user_id:YYYY-MM-DD:HH-MM:var_name
        parts = callback_data.split(":")
        if len(parts) != 6:
            return {"error": "Invalid time callback"}

        bot_id, user_id, selected_date, time_safe, var_name = (
            parts[1], int(parts[2]), parts[3], parts[4], parts[5]
        )

        # Convert time back from HH-MM to HH:MM
        time_str = time_safe.replace("-", ":")

        # Combine date and time
        datetime_value = f"{selected_date} {time_str}"

        # Log time selection
        await events_logger.log_event("widget_calendar_pick_time", {
            "datetime": datetime_value,
            "var": var_name
        })

        # Record metric
        from .telemetry import widget_calendar_picks_total
        widget_calendar_picks_total.labels(bot_id, "datetime").inc()

        return {
            "type": "complete",
            "var": var_name,
            "value": datetime_value,
            "message": f"✅ Выбраны дата и время: {datetime_value}"
        }

    async def _handle_back_to_date(self, callback_data: str) -> Dict[str, Any]:
        """Handle back to date selection"""
        # Format: cal_back:bot_id:user_id:var_name
        parts = callback_data.split(":")
        if len(parts) != 4:
            return {"error": "Invalid back callback"}

        bot_id, user_id, var_name = parts[1], int(parts[2]), parts[3]

        # Go back to current month calendar
        today = datetime.now().date()
        current_month = today.replace(day=1)

        keyboard = self._build_calendar_keyboard(bot_id, user_id, current_month, None, None, "datetime", var_name)

        return {
            "type": "edit_message",
            "text": "Выберите дату",
            "keyboard": keyboard
        }

    def validate_date_range(self, selected_date: str, min_date: Optional[str], max_date: Optional[str]) -> bool:
        """Validate if selected date is within allowed range"""
        try:
            sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()

            if min_date:
                min_dt = datetime.strptime(min_date, "%Y-%m-%d").date()
                if sel_dt < min_dt:
                    return False

            if max_date:
                max_dt = datetime.strptime(max_date, "%Y-%m-%d").date()
                if sel_dt > max_dt:
                    return False

            return True
        except ValueError:
            return False

    def format_with_timezone(self, datetime_str: str, timezone: str = "UTC") -> str:
        """Format datetime string with timezone"""
        try:
            # Parse datetime
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")

            # Apply timezone
            if timezone != "UTC":
                tz = ZoneInfo(timezone)
                dt = dt.replace(tzinfo=tz)

            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return datetime_str  # Return as-is if formatting fails


# Global calendar widget instance
calendar_widget = CalendarWidget()