"""Integration tests for flow.wizard.v1 functionality"""
import pytest
from unittest.mock import patch, AsyncMock
from runtime.dsl_engine import handle


class TestWizardV1FlowsIntegration:
    """Test wizard v1 flows end-to-end functionality"""

    @pytest.mark.asyncio
    async def test_simple_wizard_v1_flow(self):
        """Test basic wizard v1 flow handling"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "steps": [
                            {
                                "ask": "Какую услугу выберете?",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair)$",
                                    "msg": "Выберите: massage или hair"
                                }
                            },
                            {
                                "ask": "На какое время? (HH:MM)",
                                "var": "time",
                                "validate": {
                                    "regex": "^\\d{2}:\\d{2}$",
                                    "msg": "Формат: HH:MM"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Готово! Забронировано: {{service}} на {{time}}"
                                }
                            }
                        ],
                        "ttl_sec": 3600
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            # Start wizard
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()
                response1 = await handle("test-bot", "/book")
                assert "Какую услугу выберете?" in response1

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_validation_success(self):
        """Test wizard v1 validation success flow"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/test",
                    "params": {
                        "steps": [
                            {
                                "ask": "Enter service:",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair)$",
                                    "msg": "Choose: massage or hair"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Service: {{service}}"
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
                # Mock state transitions
                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 0,
                    "vars": {},
                    "ttl_sec": 86400
                }
                mock_redis.delete_wizard_state = AsyncMock()

                # Start wizard
                await handle("test-bot", "/test")

                # Continue with valid input
                with patch.object(dsl.wizard_engine, '_execute_v1_action') as mock_execute:
                    mock_execute.return_value = {
                        "success": True,
                        "type": "reply",
                        "text": "Service: massage"
                    }

                    response = await handle("test-bot", "massage")
                    assert "Service: massage" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_validation_failure(self):
        """Test wizard v1 validation failure"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/test",
                    "params": {
                        "steps": [
                            {
                                "ask": "Enter service:",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair)$",
                                    "msg": "Choose: massage or hair"
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

                # Continue with invalid input
                response = await handle("test-bot", "invalid_service")
                assert "Choose: massage or hair" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_multi_step_flow(self):
        """Test wizard v1 multi-step flow"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/survey",
                    "params": {
                        "steps": [
                            {
                                "ask": "What's your name?",
                                "var": "name"
                            },
                            {
                                "ask": "How old are you?",
                                "var": "age",
                                "validate": {
                                    "regex": "^\\d+$",
                                    "msg": "Please enter a number"
                                }
                            },
                            {
                                "ask": "What's your favorite color?",
                                "var": "color"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Thanks {{name}}! Age: {{age}}, Color: {{color}}"
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
                # Mock state progression
                states = [
                    None,  # Initial state
                    {  # After step 1
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 0,
                        "vars": {},
                        "ttl_sec": 86400
                    },
                    {  # After step 2
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 1,
                        "vars": {"name": "John"},
                        "ttl_sec": 86400
                    },
                    {  # After step 3
                        "format": "v1",
                        "wizard_flow": spec["flows"][0],
                        "step": 2,
                        "vars": {"name": "John", "age": "25"},
                        "ttl_sec": 86400
                    }
                ]

                mock_redis.set_wizard_state = AsyncMock()
                mock_redis.delete_wizard_state = AsyncMock()

                # Step 1: Start wizard
                mock_redis.get_wizard_state.return_value = states[0]
                response1 = await handle("test-bot", "/survey")
                assert "What's your name?" in response1

                # Step 2: Provide name
                mock_redis.get_wizard_state.return_value = states[1]
                response2 = await handle("test-bot", "John")
                assert "How old are you?" in response2

                # Step 3: Provide age
                mock_redis.get_wizard_state.return_value = states[2]
                response3 = await handle("test-bot", "25")
                assert "What's your favorite color?" in response3

                # Step 4: Complete survey
                mock_redis.get_wizard_state.return_value = states[3]
                with patch.object(dsl.wizard_engine, '_execute_v1_action') as mock_execute:
                    mock_execute.return_value = {
                        "success": True,
                        "type": "reply",
                        "text": "Thanks John! Age: 25, Color: blue"
                    }

                    response4 = await handle("test-bot", "blue")
                    assert "Thanks John!" in response4

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_with_sql_actions(self):
        """Test wizard v1 with SQL actions"""
        spec = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/register",
                    "params": {
                        "steps": [
                            {
                                "ask": "Enter your name:",
                                "var": "name"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INSERT INTO users(bot_id, user_id, name) VALUES(:bot_id, :user_id, :name)"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Welcome {{name}}! You are now registered."
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

                with patch.object(dsl.wizard_engine, '_execute_v1_action') as mock_execute:
                    mock_execute.side_effect = [
                        {"success": True},  # SQL exec
                        {"success": True, "type": "reply", "text": "Welcome Alice! You are now registered."}  # Reply template
                    ]

                    response = await handle("test-bot", "Alice")
                    assert "Welcome Alice!" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_restart_on_entry_cmd(self):
        """Test wizard v1 restarts on entry command during active flow"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/test",
                    "params": {
                        "steps": [
                            {"ask": "Step 1?", "var": "step1"},
                            {"ask": "Step 2?", "var": "step2"}
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
                # Mock that user is in middle of wizard
                mock_redis.get_wizard_state.return_value = {
                    "format": "v1",
                    "wizard_flow": spec["flows"][0],
                    "step": 1,
                    "vars": {"step1": "answer1"},
                    "ttl_sec": 86400
                }
                mock_redis.set_wizard_state = AsyncMock()

                # User enters entry command again - should restart
                response = await handle("test-bot", "/test")
                assert "Step 1?" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_custom_ttl(self):
        """Test wizard v1 with custom TTL"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/short",
                    "params": {
                        "steps": [
                            {"ask": "Quick question?", "var": "answer"}
                        ],
                        "ttl_sec": 300  # 5 minutes
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

                await handle("test-bot", "/short")

                # Verify TTL was set correctly
                call_args = mock_redis.set_wizard_state.call_args
                assert call_args[0][3] == 300  # TTL parameter

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_error_handling(self):
        """Test wizard v1 error handling"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/error_test",
                    "params": {
                        "steps": [
                            {"ask": "Input?", "var": "input"}
                        ],
                        "on_complete": [
                            {
                                "type": "action.sql_exec.v1",
                                "params": {
                                    "sql": "INVALID SQL QUERY"
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

                with patch.object(dsl.wizard_engine, '_execute_v1_action') as mock_execute:
                    mock_execute.return_value = {"success": False, "error": "SQL error"}

                    response = await handle("test-bot", "test input")
                    assert "ошибка" in response.lower()

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_wizard_v1_priority_over_legacy(self):
        """Test wizard v1 has priority over legacy wizard flows"""
        spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/test",
                    "params": {
                        "steps": [
                            {"ask": "V1 wizard question?", "var": "answer"}
                        ]
                    }
                },
                {
                    "entry_cmd": "/test",
                    "steps": [
                        {"ask": "Legacy wizard question?", "var": "answer"}
                    ]
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            with patch('runtime.wizard_engine.redis_client') as mock_redis:
                mock_redis.set_wizard_state = AsyncMock()

                response = await handle("test-bot", "/test")
                # Should get v1 wizard, not legacy
                assert "V1 wizard question?" in response
                assert "Legacy wizard question?" not in response

        finally:
            dsl.load_spec = original_load_spec


class TestWizardV1API:
    """Test wizard v1 flows through API endpoints"""

    @pytest.mark.asyncio
    async def test_wizard_v1_spec_validation(self):
        """Test wizard v1 spec validation"""
        from runtime.schemas import BotSpec

        wizard_spec = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "steps": [
                            {
                                "ask": "Service?",
                                "var": "service",
                                "validate": {
                                    "regex": "^(massage|hair)$",
                                    "msg": "Choose: massage or hair"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Booked: {{service}}"
                                }
                            }
                        ],
                        "ttl_sec": 3600
                    }
                }
            ]
        }

        # Should parse without errors
        bot_spec = BotSpec(**wizard_spec)
        assert bot_spec.use == ["flow.wizard.v1"]
        assert len(bot_spec.flows) == 1