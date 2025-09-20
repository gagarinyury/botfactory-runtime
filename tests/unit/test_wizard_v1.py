"""Unit tests for flow.wizard.v1 functionality"""
import pytest
from unittest.mock import AsyncMock, patch
from runtime.wizard_engine import WizardEngine
from runtime.schemas import WizardFlow


class TestWizardV1Engine:
    """Test wizard v1 engine logic"""

    def setup_method(self):
        """Setup test fixtures"""
        self.engine = WizardEngine()
        self.mock_session = AsyncMock()
        self.bot_id = "test-bot-id"
        self.user_id = 12345

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_start_simple_wizard_v1(self, mock_redis):
        """Test starting simple wizard v1 flow"""
        wizard_flow = WizardFlow(
            type="flow.wizard.v1",
            entry_cmd="/book",
            params={
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
                        "ask": "На какое время?",
                        "var": "slot"
                    }
                ],
                "ttl_sec": 3600
            }
        )

        mock_redis.set_wizard_state = AsyncMock()

        result = await self.engine._start_wizard_v1(
            self.bot_id, self.user_id, wizard_flow, self.mock_session
        )

        assert result == "Какую услугу выберете?"
        mock_redis.set_wizard_state.assert_called_once()

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_continue_wizard_v1_valid_input(self, mock_redis):
        """Test continuing wizard v1 with valid input"""
        wizard_state = {
            "format": "v1",
            "wizard_flow": {
                "type": "flow.wizard.v1",
                "entry_cmd": "/book",
                "params": {
                    "steps": [
                        {
                            "ask": "Услуга?",
                            "var": "service",
                            "validate": {"regex": "^(massage|hair)$", "msg": "Выберите: massage или hair"}
                        },
                        {
                            "ask": "Время?",
                            "var": "slot"
                        }
                    ]
                }
            },
            "step": 0,
            "vars": {},
            "ttl_sec": 3600
        }

        mock_redis.set_wizard_state = AsyncMock()

        result = await self.engine._continue_wizard_v1(
            self.bot_id, self.user_id, "massage", wizard_state, self.mock_session
        )

        assert result == "Время?"
        mock_redis.set_wizard_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_wizard_v1_invalid_input(self):
        """Test wizard v1 validation failure"""
        wizard_state = {
            "format": "v1",
            "wizard_flow": {
                "type": "flow.wizard.v1",
                "entry_cmd": "/book",
                "params": {
                    "steps": [
                        {
                            "ask": "Услуга?",
                            "var": "service",
                            "validate": {"regex": "^(massage|hair)$", "msg": "Выберите: massage или hair"}
                        }
                    ]
                }
            },
            "step": 0,
            "vars": {}
        }

        result = await self.engine._continue_wizard_v1(
            self.bot_id, self.user_id, "invalid_service", wizard_state, self.mock_session
        )

        assert result == "Выберите: massage или hair"

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_complete_wizard_v1_with_actions(self, mock_redis):
        """Test completing wizard v1 with on_complete actions"""
        wizard_flow = WizardFlow(
            type="flow.wizard.v1",
            entry_cmd="/book",
            params={
                "steps": [
                    {"ask": "Service?", "var": "service"}
                ],
                "on_complete": [
                    {
                        "type": "action.sql_exec.v1",
                        "params": {
                            "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES(:bot_id, :user_id, :service)"
                        }
                    },
                    {
                        "type": "action.reply_template.v1",
                        "params": {
                            "text": "Забронировано: {{service}}"
                        }
                    }
                ]
            }
        )

        vars_data = {"service": "massage"}

        # Mock SQL execution
        with patch.object(self.engine, '_execute_v1_action') as mock_execute:
            mock_execute.side_effect = [
                {"success": True},  # SQL exec result
                {"success": True, "type": "reply", "text": "Забронировано: massage"}  # Template result
            ]

            mock_redis.delete_wizard_state = AsyncMock()

            result = await self.engine._complete_wizard_v1(
                self.bot_id, self.user_id, wizard_flow, vars_data, self.mock_session
            )

            assert result == "Забронировано: massage"
            assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_v1_action_sql_exec(self):
        """Test executing SQL exec action in v1 format"""
        action_def = {
            "type": "action.sql_exec.v1",
            "params": {
                "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES(:bot_id, :user_id, :service)"
            }
        }

        mock_executor = AsyncMock()
        mock_executor._execute_sql_exec = AsyncMock(return_value={"success": True, "rows_affected": 1})

        result = await self.engine._execute_v1_action(mock_executor, action_def)

        assert result["success"] is True
        assert result["rows_affected"] == 1
        mock_executor._execute_sql_exec.assert_called_once_with(action_def["params"])

    @pytest.mark.asyncio
    async def test_execute_v1_action_sql_query(self):
        """Test executing SQL query action in v1 format"""
        action_def = {
            "type": "action.sql_query.v1",
            "params": {
                "sql": "SELECT * FROM bookings WHERE bot_id=:bot_id",
                "result_var": "bookings"
            }
        }

        mock_executor = AsyncMock()
        mock_executor._execute_sql_query = AsyncMock(return_value={
            "success": True,
            "result_var": "bookings",
            "rows_count": 2
        })

        result = await self.engine._execute_v1_action(mock_executor, action_def)

        assert result["success"] is True
        assert result["result_var"] == "bookings"
        mock_executor._execute_sql_query.assert_called_once_with(action_def["params"])

    @pytest.mark.asyncio
    async def test_execute_v1_action_reply_template(self):
        """Test executing reply template action in v1 format"""
        action_def = {
            "type": "action.reply_template.v1",
            "params": {
                "text": "Hello {{name}}!",
                "keyboard": [
                    {"text": "Continue", "callback": "/next"}
                ]
            }
        }

        mock_executor = AsyncMock()
        mock_executor._execute_reply_template = AsyncMock(return_value={
            "success": True,
            "type": "reply",
            "text": "Hello John!",
            "keyboard": [[{"text": "Continue", "callback_data": "/next"}]]
        })

        result = await self.engine._execute_v1_action(mock_executor, action_def)

        assert result["success"] is True
        assert result["type"] == "reply"
        assert "keyboard" in result
        mock_executor._execute_reply_template.assert_called_once_with(action_def["params"])

    @pytest.mark.asyncio
    async def test_execute_v1_action_unknown_type(self):
        """Test executing unknown action type"""
        action_def = {
            "type": "action.unknown.v1",
            "params": {}
        }

        mock_executor = AsyncMock()

        result = await self.engine._execute_v1_action(mock_executor, action_def)

        assert result["success"] is False
        assert "Unknown action type" in result["error"]

    def test_parse_wizard_flows_from_wizard_flows_section(self):
        """Test parsing wizard flows from wizard_flows section"""
        spec_data = {
            "wizard_flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "steps": [{"ask": "Name?", "var": "name"}]
                    }
                }
            ]
        }

        wizard_flows = self.engine.parse_wizard_flows(spec_data)

        assert len(wizard_flows) == 1
        assert wizard_flows[0].entry_cmd == "/book"
        assert wizard_flows[0].type == "flow.wizard.v1"

    def test_parse_wizard_flows_from_flows_section(self):
        """Test parsing wizard flows from flows section"""
        spec_data = {
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/survey",
                    "params": {
                        "steps": [{"ask": "Age?", "var": "age"}]
                    }
                },
                {
                    "entry_cmd": "/menu",
                    "steps": [{"ask": "Choice?", "var": "choice"}]
                }
            ]
        }

        wizard_flows = self.engine.parse_wizard_flows(spec_data)

        assert len(wizard_flows) == 1
        assert wizard_flows[0].entry_cmd == "/survey"
        assert wizard_flows[0].type == "flow.wizard.v1"

    def test_parse_wizard_flows_both_sections(self):
        """Test parsing wizard flows from both sections"""
        spec_data = {
            "wizard_flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {"steps": []}
                }
            ],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/survey",
                    "params": {"steps": []}
                }
            ]
        }

        wizard_flows = self.engine.parse_wizard_flows(spec_data)

        assert len(wizard_flows) == 2
        entry_cmds = [flow.entry_cmd for flow in wizard_flows]
        assert "/book" in entry_cmds
        assert "/survey" in entry_cmds

    def test_parse_wizard_flows_empty_spec(self):
        """Test parsing wizard flows from empty spec"""
        spec_data = {}
        wizard_flows = self.engine.parse_wizard_flows(spec_data)
        assert wizard_flows == []

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_wizard_v1_with_ttl(self, mock_redis):
        """Test wizard v1 respects custom TTL"""
        wizard_flow = WizardFlow(
            type="flow.wizard.v1",
            entry_cmd="/book",
            params={
                "steps": [{"ask": "Name?", "var": "name"}],
                "ttl_sec": 1800  # 30 minutes
            }
        )

        mock_redis.set_wizard_state = AsyncMock()

        await self.engine._start_wizard_v1(
            self.bot_id, self.user_id, wizard_flow, self.mock_session
        )

        # Verify TTL was passed correctly
        call_args = mock_redis.set_wizard_state.call_args
        assert call_args[0][3] == 1800  # TTL parameter

    @pytest.mark.asyncio
    async def test_wizard_v1_invalid_regex_graceful_handling(self):
        """Test wizard v1 handles invalid regex gracefully"""
        wizard_state = {
            "format": "v1",
            "wizard_flow": {
                "type": "flow.wizard.v1",
                "entry_cmd": "/test",
                "params": {
                    "steps": [
                        {
                            "ask": "Input?",
                            "var": "input",
                            "validate": {"regex": "[invalid regex", "msg": "Invalid format"}
                        }
                    ]
                }
            },
            "step": 0,
            "vars": {}
        }

        # Should not raise exception and accept input as valid
        result = await self.engine._continue_wizard_v1(
            self.bot_id, self.user_id, "any input", wizard_state, self.mock_session
        )

        # Should complete since it's the only step and regex error was gracefully handled
        assert "завершён" in result or "Готово" in result

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_handle_wizard_v1_message_entry_cmd(self, mock_redis):
        """Test handling wizard v1 message with entry command"""
        wizard_flows = [
            WizardFlow(
                type="flow.wizard.v1",
                entry_cmd="/start",
                params={
                    "steps": [{"ask": "Name?", "var": "name"}]
                }
            )
        ]

        mock_redis.set_wizard_state = AsyncMock()

        result = await self.engine.handle_wizard_v1_message(
            self.bot_id, self.user_id, "/start", wizard_flows, self.mock_session
        )

        assert result == "Name?"

    @pytest.mark.asyncio
    @patch('runtime.wizard_engine.redis_client')
    async def test_handle_wizard_v1_message_continue(self, mock_redis):
        """Test handling wizard v1 message continuation"""
        wizard_flows = []

        mock_redis.get_wizard_state.return_value = {
            "format": "v1",
            "wizard_flow": {
                "type": "flow.wizard.v1",
                "entry_cmd": "/test",
                "params": {
                    "steps": [{"ask": "Input?", "var": "input"}]
                }
            },
            "step": 0,
            "vars": {}
        }

        result = await self.engine.handle_wizard_v1_message(
            self.bot_id, self.user_id, "test input", wizard_flows, self.mock_session
        )

        assert result is not None