"""Integration tests for action.sql_exec.v1 in real flow scenarios"""
import pytest
from unittest.mock import patch, AsyncMock
from runtime.dsl_engine import handle


class TestSqlExecV1FlowsIntegration:
    """Test action.sql_exec.v1 in wizard and menu flows"""

    @pytest.mark.asyncio
    async def test_wizard_v1_with_sql_exec_booking(self):
        """Test wizard v1 flow with SQL exec for booking scenario"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "steps": [
                            {
                                "ask": "Выберите услугу: massage, hair, cosmo",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair|cosmo)$",
                                    "msg": "Выберите услугу из списка"
                                }
                            },
                            {
                                "ask": "Укажите дату (YYYY-MM-DD HH:MM)",
                                "var": "slot",
                                "validate": {
                                    "regex": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
                                    "msg": "Неверный формат даты"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INSERT INTO bookings(bot_id, user_id, service, slot, created_at) VALUES (:bot_id, :user_id, :service, to_timestamp(:slot, 'YYYY-MM-DD HH24:MI'), NOW())"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "✅ Запись создана: {{service}} на {{slot}}"
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
                # Mock wizard progression
                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.delete_wizard_state = AsyncMock()

                # State progression
                states = [
                    None,  # Initial
                    {  # After service input
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 0,
                        "vars": {},
                        "ttl_sec": 86400
                    },
                    {  # After slot input - ready to complete
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 1,
                        "vars": {"service": "massage"},
                        "ttl_sec": 86400
                    }
                ]

                # Start wizard
                mock_redis.get_wizard_state.return_value = states[0]
                response1 = await handle("test-bot", "/book")
                assert "Выберите услугу" in response1

                # Provide service
                mock_redis.get_wizard_state.return_value = states[1]
                response2 = await handle("test-bot", "massage")
                assert "Укажите дату" in response2

                # Complete with SQL exec
                mock_redis.get_wizard_state.return_value = states[2]

                with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql_exec:
                    mock_sql_exec.return_value = {"success": True, "status": "ok", "rows": 1}

                    response3 = await handle("test-bot", "2024-12-25 14:30")
                    assert "Запись создана: massage на 2024-12-25 14:30" in response3

                    # Verify SQL exec was called with correct parameters
                    mock_sql_exec.assert_called_once()
                    call_args = mock_sql_exec.call_args[0][0]
                    assert "INSERT INTO bookings" in call_args["sql"]

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_sql_exec_error_handling(self):
        """Test wizard v1 handles SQL exec errors gracefully"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/test",
                    "params": {
                        "steps": [
                            {"ask": "Input?", "var": "input"}
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INSERT INTO bookings(bot_id, user_id, input) VALUES (:bot_id, :user_id, :input)"
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
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }
                mock_redis.delete_wizard_state = AsyncMock()

                # Mock SQL exec failure
                with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql_exec:
                    mock_sql_exec.side_effect = Exception("Database error")

                    response = await handle("test-bot", "test input")

                    # Should handle error gracefully and return error message
                    assert "ошибка" in response.lower() or "error" in response.lower()

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_update_sql_exec(self):
        """Test wizard v1 with UPDATE SQL exec"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/update_status",
                    "params": {
                        "steps": [
                            {
                                "ask": "Новый статус: confirmed, cancelled",
                                "var": "status",
                                "validate": {
                                    "regex": "^(confirmed|cancelled)$",
                                    "msg": "Выберите статус из списка"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "UPDATE bookings SET status = :status, updated_at = NOW() WHERE bot_id = :bot_id AND user_id = :user_id"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Статус обновлен: {{status}}"
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
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }
                mock_redis.delete_wizard_state = AsyncMock()

                with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql_exec:
                    mock_sql_exec.return_value = {"success": True, "status": "ok", "rows": 2}

                    response = await handle("test-bot", "confirmed")
                    assert "Статус обновлен: confirmed" in response

                    # Verify UPDATE SQL was called
                    call_args = mock_sql_exec.call_args[0][0]
                    assert "UPDATE bookings SET status" in call_args["sql"]

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_delete_sql_exec(self):
        """Test wizard v1 with DELETE SQL exec"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/cancel",
                    "params": {
                        "steps": [
                            {
                                "ask": "Подтвердите отмену (да/нет)",
                                "var": "confirm",
                                "validate": {
                                    "regex": "^(да|нет)$",
                                    "msg": "Ответьте да или нет"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "DELETE FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id AND status = 'pending'"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Записи отменены"
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
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }
                mock_redis.delete_wizard_state = AsyncMock()

                with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql_exec:
                    mock_sql_exec.return_value = {"success": True, "status": "ok", "rows": 1}

                    response = await handle("test-bot", "да")
                    assert "Записи отменены" in response

                    # Verify DELETE SQL was called
                    call_args = mock_sql_exec.call_args[0][0]
                    assert "DELETE FROM bookings" in call_args["sql"]

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_sql_exec_v1_security_validation(self):
        """Test SQL exec v1 blocks dangerous SQL statements"""
        dangerous_specs = [
            {
                "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id"  # SELECT not allowed
            },
            {
                "sql": "DROP TABLE bookings"  # Dangerous statement
            },
            {
                "sql": "INSERT INTO bookings(bot_id) VALUES (:bot_id); DROP TABLE users;"  # Multiple statements
            }
        ]

        for dangerous_sql in dangerous_specs:
            spec = {
                "use": ["flow.wizard.v1", "action.sql_exec.v1"],
                "flows": [
                    {
                        "type": "flow.wizard.v1",
                        "entry_cmd": "/dangerous",
                        "params": {
                            "steps": [{"ask": "Input?", "var": "input"}],
                            "on_complete": [
                                {
                                    "type": "action.sql_exec.v1",
                                    "params": dangerous_sql
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
                    mock_redis.get_wizard_state.return_value = {
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 0,
                        "vars": {},
                        "ttl_sec": 86400
                    }
                    mock_redis.delete_wizard_state = AsyncMock()

                    response = await handle("test-bot", "test input")

                    # Should handle security error gracefully
                    assert "ошибка" in response.lower() or "error" in response.lower()

            finally:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_multiple_sql_exec_actions(self):
        """Test wizard v1 with multiple SQL exec actions"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/multi_sql",
                    "params": {
                        "steps": [
                            {"ask": "Service?", "var": "service"}
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES (:bot_id, :user_id, :service)"
                                }
                            },
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "UPDATE user_stats SET bookings_count = bookings_count + 1 WHERE bot_id = :bot_id AND user_id = :user_id"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Booking created and stats updated"
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
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }
                mock_redis.delete_wizard_state = AsyncMock()

                with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql_exec:
                    mock_sql_exec.return_value = {"success": True, "status": "ok", "rows": 1}

                    response = await handle("test-bot", "massage")
                    assert "Booking created and stats updated" in response

                    # Verify both SQL exec actions were called
                    assert mock_sql_exec.call_count == 2

        finally:
            dsl.load_spec = original_load_spec