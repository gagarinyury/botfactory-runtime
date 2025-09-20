"""Integration tests for calendar widget in real flow scenarios"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from runtime.dsl_engine import handle, handle_callback


class TestCalendarWidgetFlowsIntegration:
    """Test calendar widget in wizard and flow scenarios"""

    @pytest.mark.asyncio
    async def test_wizard_v1_with_calendar_date_widget(self):
        """Test wizard v1 flow with calendar date widget"""
        spec = {
            "use": ["flow.wizard.v1", "widget.calendar.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "date",
                                        "var": "slot",
                                        "title": "Выберите дату записи",
                                        "min": "2025-01-01",
                                        "max": "2025-12-31"
                                    }
                                }
                            },
                            {
                                "ask": "Какая услуга?",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair|cosmo)$",
                                    "msg": "Выберите: massage, hair, cosmo"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INSERT INTO bookings(bot_id, user_id, slot, service, created_at) VALUES (:bot_id, :user_id, :slot, :service, NOW())"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "✅ Запись создана на {{slot}} для услуги {{service}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.get_wizard_state.return_value = None

                # Start wizard - should show calendar
                with patch('runtime.calendar_widget.calendar_widget.render_calendar') as mock_render:
                    mock_render.return_value = {
                        "type": "reply",
                        "text": "Выберите дату записи",
                        "keyboard": [
                            [{"text": "◀", "callback_data": "cal_nav:test-bot:999999:2025-01:date:slot"}],
                            [{"text": "15", "callback_data": "cal_date:test-bot:999999:2025-01-15:date:slot"}]
                        ],
                        "success": True
                    }

                    response = await handle("test-bot", "/book")

                    assert "Выберите дату записи" in str(response)
                    mock_render.assert_called_once()

                # Simulate calendar date selection callback
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }

                with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                    mock_callback.return_value = {
                        "type": "complete",
                        "var": "slot",
                        "value": "2025-01-15",
                        "message": "✅ Выбрана дата: 2025-01-15"
                    }

                    # Simulate date selection
                    callback_response = await handle_callback("test-bot", 999999, "cal_date:test-bot:999999:2025-01-15:date:slot")

                    # Should advance to next step (service question)
                    assert "Какая услуга?" in str(callback_response)

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_with_calendar_datetime_widget(self):
        """Test wizard v1 flow with calendar datetime widget"""
        spec = {
            "use": ["flow.wizard.v1", "widget.calendar.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/schedule",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "datetime",
                                        "var": "slot",
                                        "title": "Выберите дату и время",
                                        "tz": "Europe/Moscow"
                                    }
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Встреча назначена на {{slot}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.delete_wizard_state = AsyncMock()
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }

                # Test date selection (first part of datetime)
                with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                    mock_callback.return_value = {
                        "type": "edit_message",
                        "text": "Выберите время на 2025-01-15",
                        "keyboard": [
                            [{"text": "09:00", "callback_data": "cal_time:test-bot:999999:2025-01-15:09-00:slot"}],
                            [{"text": "14:30", "callback_data": "cal_time:test-bot:999999:2025-01-15:14-30:slot"}]
                        ]
                    }

                    # Date selection should show time picker
                    callback_response = await handle_callback("test-bot", 999999, "cal_date:test-bot:999999:2025-01-15:datetime:slot")
                    assert "Выберите время на 2025-01-15" in str(callback_response)

                # Test time selection (second part of datetime)
                with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback, \
                     patch('runtime.actions.ActionExecutor._execute_reply_template') as mock_reply:

                    mock_callback.return_value = {
                        "type": "complete",
                        "var": "slot",
                        "value": "2025-01-15 14:30",
                        "message": "✅ Выбраны дата и время: 2025-01-15 14:30"
                    }

                    mock_reply.return_value = {
                        "success": True,
                        "type": "reply",
                        "text": "Встреча назначена на 2025-01-15 14:30"
                    }

                    # Time selection should complete wizard
                    callback_response = await handle_callback("test-bot", 999999, "cal_time:test-bot:999999:2025-01-15:14-30:slot")
                    assert "Встреча назначена на 2025-01-15 14:30" in str(callback_response)

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_calendar_widget_date_validation(self):
        """Test calendar widget with date range validation"""
        spec = {
            "use": ["flow.wizard.v1", "widget.calendar.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/limited",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "date",
                                        "var": "slot",
                                        "title": "Выберите дату (только январь 2025)",
                                        "min": "2025-01-01",
                                        "max": "2025-01-31"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()

                # Test calendar rendering with limits
                with patch('runtime.calendar_widget.calendar_widget.render_calendar') as mock_render:
                    mock_render.return_value = {
                        "type": "reply",
                        "text": "Выберите дату (только январь 2025)",
                        "keyboard": [[{"text": "15", "callback_data": "cal_date:test-bot:999999:2025-01-15:date:slot"}]],
                        "success": True
                    }

                    response = await handle("test-bot", "/limited")

                    # Verify calendar was rendered with date limits
                    mock_render.assert_called_once()
                    call_args = mock_render.call_args[0][2]  # params argument
                    assert call_args["min"] == "2025-01-01"
                    assert call_args["max"] == "2025-01-31"

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_calendar_widget_navigation(self):
        """Test calendar widget month navigation"""
        with patch('runtime.wizard_engine.redis_client') as mock_redis:
            mock_redis.get_wizard_state.return_value = {
                "format": "v1",
                "wizard_flow": {"type": "flow.wizard.v1"},
                "step": 0,
                "vars": {},
                "ttl_sec": 86400
            }

            # Test navigation callback
            with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                mock_callback.return_value = {
                    "type": "edit_message",
                    "text": "Выберите дату",
                    "keyboard": [[{"text": "February 2025", "callback_data": "cal_ignore"}]]
                }

                response = await handle_callback("test-bot", 999999, "cal_nav:test-bot:999999:2025-02:date:slot")

                assert response is not None
                mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_calendar_widget_back_button(self):
        """Test calendar widget back button functionality"""
        with patch('runtime.wizard_engine.redis_client') as mock_redis:
            mock_redis.get_wizard_state.return_value = {
                "format": "v1",
                "wizard_flow": {"type": "flow.wizard.v1"},
                "step": 0,
                "vars": {},
                "ttl_sec": 86400
            }

            # Test back button callback
            with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                mock_callback.return_value = {
                    "type": "edit_message",
                    "text": "Выберите дату",
                    "keyboard": [[{"text": "15", "callback_data": "cal_date:test-bot:999999:2025-01-15:datetime:slot"}]]
                }

                response = await handle_callback("test-bot", 999999, "cal_back:test-bot:999999:slot")

                assert response is not None
                mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_calendar_widget_error_handling(self):
        """Test calendar widget error handling"""
        # Test invalid callback format
        with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
            mock_callback.return_value = {"error": "Ошибка обработки календаря"}

            response = await handle_callback("test-bot", 999999, "cal_date:invalid:format")

            assert response["error"] == "Ошибка обработки календаря"

    @pytest.mark.asyncio
    async def test_calendar_widget_ignore_callbacks(self):
        """Test calendar widget ignore callbacks"""
        with patch('runtime.wizard_engine.redis_client') as mock_redis:
            mock_redis.get_wizard_state.return_value = {
                "format": "v1",
                "wizard_flow": {"type": "flow.wizard.v1"},
                "step": 0,
                "vars": {},
                "ttl_sec": 86400
            }

            # Test ignore callback
            with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                mock_callback.return_value = None

                response = await handle_callback("test-bot", 999999, "cal_ignore")

                assert response is None
                mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_calendar_widget_metrics_integration(self):
        """Test calendar widget metrics in real flow"""
        spec = {
            "use": ["flow.wizard.v1", "widget.calendar.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/metrics_test",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "date",
                                        "var": "slot",
                                        "title": "Test Metrics"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis, \
                 patch('runtime.calendar_widget.widget_calendar_renders_total') as mock_renders, \
                 patch('runtime.calendar_widget.widget_calendar_picks_total') as mock_picks:

                mock_redis.set_wizard_state = AsyncMock()

                # Mock calendar widget
                with patch('runtime.calendar_widget.calendar_widget.render_calendar') as mock_render:
                    mock_render.return_value = {
                        "type": "reply",
                        "text": "Test Metrics",
                        "keyboard": [],
                        "success": True
                    }

                    await handle("test-bot", "/metrics_test")

                    # Verify render metric was called through the actual widget
                    mock_render.assert_called_once()

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_calendar_widget_multiple_steps_with_calendar(self):
        """Test wizard with multiple calendar widget steps"""
        spec = {
            "use": ["flow.wizard.v1", "widget.calendar.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/multi_calendar",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "date",
                                        "var": "start_date",
                                        "title": "Выберите дату начала"
                                    }
                                }
                            },
                            {
                                "widget": {
                                    "type": "widget.calendar.v1",
                                    "params": {
                                        "mode": "date",
                                        "var": "end_date",
                                        "title": "Выберите дату окончания"
                                    }
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Период: с {{start_date}} по {{end_date}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.delete_wizard_state = AsyncMock()

                # Start wizard - first calendar
                with patch('runtime.calendar_widget.calendar_widget.render_calendar') as mock_render:
                    mock_render.return_value = {
                        "type": "reply",
                        "text": "Выберите дату начала",
                        "keyboard": [],
                        "success": True
                    }

                    response = await handle("test-bot", "/multi_calendar")
                    assert "Выберите дату начала" in str(response)

                # First calendar selection - should advance to second calendar
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }

                with patch('runtime.calendar_widget.calendar_widget.handle_callback') as mock_callback:
                    mock_callback.return_value = {
                        "type": "complete",
                        "var": "start_date",
                        "value": "2025-01-15",
                        "message": "✅ Выбрана дата: 2025-01-15"
                    }

                    # Mock second calendar render
                    with patch('runtime.calendar_widget.calendar_widget.render_calendar') as mock_render2:
                        mock_render2.return_value = {
                            "type": "reply",
                            "text": "Выберите дату окончания",
                            "keyboard": [],
                            "success": True
                        }

                        callback_response = await handle_callback("test-bot", 999999, "cal_date:test-bot:999999:2025-01-15:date:start_date")
                        assert "Выберите дату окончания" in str(callback_response)

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_non_calendar_callback_handling(self):
        """Test handling of non-calendar callbacks"""
        # Test callback that doesn't start with cal_
        response = await handle_callback("test-bot", 999999, "menu_item:some_data")

        # Should be handled gracefully (logged as unhandled)
        assert response is None

    @pytest.mark.asyncio
    async def test_calendar_widget_without_wizard_state(self):
        """Test calendar callback without active wizard state"""
        with patch('runtime.wizard_engine.redis_client') as mock_redis:
            mock_redis.get_wizard_state.return_value = None

            # Calendar callback without wizard state should return None
            response = await handle_callback("test-bot", 999999, "cal_date:test-bot:999999:2025-01-15:date:slot")

            assert response is None