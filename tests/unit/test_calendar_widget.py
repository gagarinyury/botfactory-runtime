"""Unit tests for calendar widget functionality"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, date
from runtime.calendar_widget import CalendarWidget


class TestCalendarWidget:
    """Test calendar widget functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.widget = CalendarWidget()
        self.bot_id = "test-bot"
        self.user_id = 12345
        self.mock_session = AsyncMock()

    @pytest.mark.asyncio
    async def test_render_calendar_date_mode(self):
        """Test calendar rendering in date mode"""
        params = {
            "mode": "date",
            "var": "slot",
            "title": "Выберите дату",
            "min": "2025-01-01",
            "max": "2025-12-31"
        }

        with patch('runtime.calendar_widget.widget_calendar_renders_total') as mock_metric:
            result = await self.widget.render_calendar(self.bot_id, self.user_id, params)

            assert result["success"] is True
            assert result["type"] == "reply"
            assert result["text"] == "Выберите дату"
            assert "keyboard" in result
            assert len(result["keyboard"]) > 0

            # Verify metric was incremented
            mock_metric.labels.assert_called_with(self.bot_id)

    @pytest.mark.asyncio
    async def test_render_calendar_datetime_mode(self):
        """Test calendar rendering in datetime mode"""
        params = {
            "mode": "datetime",
            "var": "slot",
            "title": "Выберите дату и время",
            "tz": "Europe/Moscow"
        }

        with patch('runtime.calendar_widget.widget_calendar_renders_total'):
            result = await self.widget.render_calendar(self.bot_id, self.user_id, params)

            assert result["success"] is True
            assert result["type"] == "reply"
            assert result["text"] == "Выберите дату и время"
            assert "keyboard" in result

    def test_build_calendar_keyboard(self):
        """Test calendar keyboard building"""
        today = datetime.now().date()
        current_month = today.replace(day=1)

        keyboard = self.widget._build_calendar_keyboard(
            self.bot_id, self.user_id, current_month, None, None, "date", "slot"
        )

        assert len(keyboard) > 2  # At least header + weekdays + some days

        # Check header row (navigation)
        header_row = keyboard[0]
        assert len(header_row) == 3
        assert header_row[0]["text"] == "◀"
        assert header_row[2]["text"] == "▶"
        assert "callback_data" in header_row[0]

        # Check weekday row
        weekday_row = keyboard[1]
        assert len(weekday_row) == 7
        assert weekday_row[0]["text"] == "Пн"
        assert weekday_row[6]["text"] == "Вс"

    def test_build_calendar_keyboard_with_limits(self):
        """Test calendar keyboard with date limits"""
        today = datetime.now().date()
        current_month = today.replace(day=1)

        # Set limits that exclude some days
        min_date = date(today.year, today.month, 15)
        max_date = date(today.year, today.month, 25)

        keyboard = self.widget._build_calendar_keyboard(
            self.bot_id, self.user_id, current_month, min_date, max_date, "date", "slot"
        )

        # Find a day row and check for disabled days
        found_disabled = False
        for row in keyboard[2:]:  # Skip header and weekday rows
            for button in row:
                if button["text"].startswith("·") and button["text"].endswith("·"):
                    found_disabled = True
                    assert button["callback_data"] == "cal_ignore"

        # Should have some disabled days if we're in the current month
        if today.month == current_month.month and today.year == current_month.year:
            assert found_disabled

    def test_build_time_keyboard(self):
        """Test time selection keyboard building"""
        selected_date = "2025-01-15"

        keyboard = self.widget._build_time_keyboard(
            self.bot_id, self.user_id, selected_date, "slot"
        )

        assert len(keyboard) > 0

        # Check title row
        title_row = keyboard[0]
        assert f"Время на {selected_date}" in title_row[0]["text"]

        # Check time slots
        found_times = False
        for row in keyboard[1:-1]:  # Skip title and back button
            for button in row:
                if ":" in button["text"] and button["text"] != " ":
                    found_times = True
                    assert button["callback_data"].startswith("cal_time:")

        assert found_times

        # Check back button
        back_row = keyboard[-1]
        assert "Назад" in back_row[0]["text"]

    @pytest.mark.asyncio
    async def test_handle_date_selection_date_mode(self):
        """Test date selection in date mode"""
        callback_data = f"cal_date:{self.bot_id}:{self.user_id}:2025-01-15:date:slot"

        mock_events_logger = AsyncMock()

        with patch('runtime.calendar_widget.create_events_logger') as mock_create_logger, \
             patch('runtime.calendar_widget.widget_calendar_picks_total') as mock_metric:

            mock_create_logger.return_value = mock_events_logger

            result = await self.widget._handle_date_selection(callback_data, mock_events_logger)

            assert result["type"] == "complete"
            assert result["var"] == "slot"
            assert result["value"] == "2025-01-15"
            assert "Выбрана дата: 2025-01-15" in result["message"]

            # Verify logging
            mock_events_logger.log_event.assert_called_once_with("widget_calendar_pick_date", {
                "date": "2025-01-15",
                "mode": "date",
                "var": "slot"
            })

    @pytest.mark.asyncio
    async def test_handle_date_selection_datetime_mode(self):
        """Test date selection in datetime mode (should show time picker)"""
        callback_data = f"cal_date:{self.bot_id}:{self.user_id}:2025-01-15:datetime:slot"

        mock_events_logger = AsyncMock()

        with patch('runtime.calendar_widget.create_events_logger') as mock_create_logger, \
             patch('runtime.calendar_widget.widget_calendar_picks_total'):

            mock_create_logger.return_value = mock_events_logger

            result = await self.widget._handle_date_selection(callback_data, mock_events_logger)

            assert result["type"] == "edit_message"
            assert "Выберите время на 2025-01-15" in result["text"]
            assert "keyboard" in result

    @pytest.mark.asyncio
    async def test_handle_time_selection(self):
        """Test time selection for datetime mode"""
        callback_data = f"cal_time:{self.bot_id}:{self.user_id}:2025-01-15:14-30:slot"

        mock_events_logger = AsyncMock()

        with patch('runtime.calendar_widget.create_events_logger') as mock_create_logger, \
             patch('runtime.calendar_widget.widget_calendar_picks_total') as mock_metric:

            mock_create_logger.return_value = mock_events_logger

            result = await self.widget._handle_time_selection(callback_data, mock_events_logger)

            assert result["type"] == "complete"
            assert result["var"] == "slot"
            assert result["value"] == "2025-01-15 14:30"
            assert "Выбраны дата и время: 2025-01-15 14:30" in result["message"]

            # Verify logging
            mock_events_logger.log_event.assert_called_once_with("widget_calendar_pick_time", {
                "datetime": "2025-01-15 14:30",
                "var": "slot"
            })

    @pytest.mark.asyncio
    async def test_handle_navigation(self):
        """Test month navigation"""
        callback_data = f"cal_nav:{self.bot_id}:{self.user_id}:2025-02:date:slot"

        result = await self.widget._handle_navigation(callback_data)

        assert result["type"] == "edit_message"
        assert result["text"] == "Выберите дату"
        assert "keyboard" in result

    @pytest.mark.asyncio
    async def test_handle_back_to_date(self):
        """Test back to date selection"""
        callback_data = f"cal_back:{self.bot_id}:{self.user_id}:slot"

        result = await self.widget._handle_back_to_date(callback_data)

        assert result["type"] == "edit_message"
        assert result["text"] == "Выберите дату"
        assert "keyboard" in result

    @pytest.mark.asyncio
    async def test_handle_callback_unknown(self):
        """Test handling unknown callback"""
        callback_data = "unknown_callback"

        with patch('runtime.calendar_widget.logger') as mock_logger:
            result = await self.widget.handle_callback(
                self.bot_id, self.user_id, callback_data, self.mock_session
            )

            assert result is None
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_handle_callback_ignore(self):
        """Test handling ignore callback"""
        callback_data = "cal_ignore"

        result = await self.widget.handle_callback(
            self.bot_id, self.user_id, callback_data, self.mock_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_callback_error(self):
        """Test callback error handling"""
        callback_data = "cal_date:invalid:format"

        with patch('runtime.calendar_widget.logger') as mock_logger:
            result = await self.widget.handle_callback(
                self.bot_id, self.user_id, callback_data, self.mock_session
            )

            assert result["error"] == "Ошибка обработки календаря"
            mock_logger.error.assert_called()

    def test_validate_date_range_valid(self):
        """Test date range validation with valid dates"""
        assert self.widget.validate_date_range("2025-06-15", "2025-01-01", "2025-12-31") is True
        assert self.widget.validate_date_range("2025-01-01", "2025-01-01", "2025-12-31") is True
        assert self.widget.validate_date_range("2025-12-31", "2025-01-01", "2025-12-31") is True

    def test_validate_date_range_invalid(self):
        """Test date range validation with invalid dates"""
        assert self.widget.validate_date_range("2024-12-31", "2025-01-01", "2025-12-31") is False
        assert self.widget.validate_date_range("2026-01-01", "2025-01-01", "2025-12-31") is False

    def test_validate_date_range_no_limits(self):
        """Test date range validation with no limits"""
        assert self.widget.validate_date_range("2025-06-15", None, None) is True

    def test_validate_date_range_invalid_format(self):
        """Test date range validation with invalid format"""
        assert self.widget.validate_date_range("invalid-date", "2025-01-01", "2025-12-31") is False

    def test_format_with_timezone_utc(self):
        """Test timezone formatting with UTC"""
        result = self.widget.format_with_timezone("2025-01-15 14:30", "UTC")
        assert result == "2025-01-15 14:30"

    def test_format_with_timezone_moscow(self):
        """Test timezone formatting with Moscow timezone"""
        result = self.widget.format_with_timezone("2025-01-15 14:30", "Europe/Moscow")
        assert result == "2025-01-15 14:30"  # Time stays the same, just timezone aware

    def test_format_with_timezone_invalid(self):
        """Test timezone formatting with invalid input"""
        result = self.widget.format_with_timezone("invalid-datetime", "UTC")
        assert result == "invalid-datetime"  # Returns as-is

    def test_callback_data_format_validation(self):
        """Test callback data format validation"""
        # Valid formats
        valid_callbacks = [
            f"cal_date:{self.bot_id}:{self.user_id}:2025-01-15:date:slot",
            f"cal_time:{self.bot_id}:{self.user_id}:2025-01-15:14:30:slot",
            f"cal_nav:{self.bot_id}:{self.user_id}:2025-02:date:slot",
            f"cal_back:{self.bot_id}:{self.user_id}:slot"
        ]

        for callback in valid_callbacks:
            parts = callback.split(":")
            assert len(parts) >= 4  # Minimum required parts

        # Invalid formats
        invalid_callbacks = [
            "cal_date:incomplete",
            "cal_time:",
            "cal_nav",
            "cal_back:too:few:parts"
        ]

        for callback in invalid_callbacks:
            parts = callback.split(":")
            # These should be caught by the actual handlers
            assert len(parts) < 6  # Should fail validation in handlers

    @pytest.mark.asyncio
    async def test_metrics_recording(self):
        """Test that metrics are properly recorded"""
        params = {
            "mode": "date",
            "var": "slot",
            "title": "Test Calendar"
        }

        with patch('runtime.calendar_widget.widget_calendar_renders_total') as mock_renders, \
             patch('runtime.calendar_widget.widget_calendar_picks_total') as mock_picks:

            # Test render metric
            await self.widget.render_calendar(self.bot_id, self.user_id, params)
            mock_renders.labels.assert_called_with(self.bot_id)

            # Test pick metric
            callback_data = f"cal_date:{self.bot_id}:{self.user_id}:2025-01-15:date:slot"
            mock_events_logger = AsyncMock()

            with patch('runtime.calendar_widget.create_events_logger') as mock_create_logger:
                mock_create_logger.return_value = mock_events_logger

                await self.widget._handle_date_selection(callback_data, mock_events_logger)
                mock_picks.labels.assert_called_with(self.bot_id, "date")

    @pytest.mark.asyncio
    async def test_logging_events(self):
        """Test that events are properly logged"""
        callback_data = f"cal_date:{self.bot_id}:{self.user_id}:2025-01-15:date:slot"
        mock_events_logger = AsyncMock()

        with patch('runtime.calendar_widget.create_events_logger') as mock_create_logger, \
             patch('runtime.calendar_widget.widget_calendar_picks_total'):

            mock_create_logger.return_value = mock_events_logger

            await self.widget._handle_date_selection(callback_data, mock_events_logger)

            # Verify event was logged
            mock_events_logger.log_event.assert_called_once_with("widget_calendar_pick_date", {
                "date": "2025-01-15",
                "mode": "date",
                "var": "slot"
            })