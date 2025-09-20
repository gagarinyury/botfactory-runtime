"""Unit tests for menu engine functionality"""
import pytest
from unittest.mock import AsyncMock
from runtime.menu_engine import MenuEngine
from runtime.schemas import MenuFlow


class TestMenuEngine:
    """Test menu engine logic"""

    def setup_method(self):
        """Setup test fixtures"""
        self.engine = MenuEngine()
        self.mock_session = AsyncMock()
        self.bot_id = "test-bot-id"
        self.user_id = 12345

    @pytest.mark.asyncio
    async def test_simple_menu_handling(self):
        """Test basic menu command handling"""
        menu_flow = MenuFlow(
            type="flow.menu.v1",
            entry_cmd="/start",
            params={
                "title": "Welcome! Choose an action:",
                "options": [
                    {"text": "Book", "callback": "/book"},
                    {"text": "My bookings", "callback": "/my"}
                ]
            }
        )

        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/start", [menu_flow], self.mock_session
        )

        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "Welcome! Choose an action:"
        assert result["success"] is True
        assert "keyboard" in result
        assert len(result["keyboard"]) == 2
        assert result["keyboard"][0][0]["text"] == "Book"
        assert result["keyboard"][0][0]["callback_data"] == "/book"

    @pytest.mark.asyncio
    async def test_menu_with_non_intent_callbacks(self):
        """Test menu with regular callback data"""
        menu_flow = MenuFlow(
            type="flow.menu.v1",
            entry_cmd="/categories",
            params={
                "title": "Select category:",
                "options": [
                    {"text": "Massage", "callback": "service_massage"},
                    {"text": "Hairdresser", "callback": "service_hair"},
                    {"text": "Cosmetology", "callback": "service_cosmo"}
                ]
            }
        )

        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/categories", [menu_flow], self.mock_session
        )

        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "Select category:"
        assert len(result["keyboard"]) == 3
        assert result["keyboard"][0][0]["callback_data"] == "service_massage"
        assert result["keyboard"][1][0]["callback_data"] == "service_hair"
        assert result["keyboard"][2][0]["callback_data"] == "service_cosmo"

    @pytest.mark.asyncio
    async def test_menu_with_mixed_callbacks(self):
        """Test menu with both intent and regular callbacks"""
        menu_flow = MenuFlow(
            type="flow.menu.v1",
            entry_cmd="/menu",
            params={
                "title": "Main menu:",
                "options": [
                    {"text": "Book service", "callback": "/book"},
                    {"text": "Massage", "callback": "service_massage"},
                    {"text": "Help", "callback": "/help"}
                ]
            }
        )

        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/menu", [menu_flow], self.mock_session
        )

        assert result is not None
        assert len(result["keyboard"]) == 3
        assert result["keyboard"][0][0]["callback_data"] == "/book"  # Intent
        assert result["keyboard"][1][0]["callback_data"] == "service_massage"  # Regular
        assert result["keyboard"][2][0]["callback_data"] == "/help"  # Intent

    @pytest.mark.asyncio
    async def test_no_matching_menu_command(self):
        """Test handling non-matching command"""
        menu_flow = MenuFlow(
            type="flow.menu.v1",
            entry_cmd="/start",
            params={
                "title": "Welcome!",
                "options": [{"text": "Book", "callback": "/book"}]
            }
        )

        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/unknown", [menu_flow], self.mock_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_menu_flows(self):
        """Test handling with empty menu flows list"""
        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/start", [], self.mock_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_menu_with_empty_options(self):
        """Test menu with empty options list"""
        menu_flow = MenuFlow(
            type="flow.menu.v1",
            entry_cmd="/empty",
            params={
                "title": "Empty menu",
                "options": []
            }
        )

        result = await self.engine.handle_menu_command(
            self.bot_id, self.user_id, "/empty", [menu_flow], self.mock_session
        )

        assert result is not None
        assert result["text"] == "Empty menu"
        assert result["keyboard"] == []

    def test_parse_menu_flows_from_menu_flows_section(self):
        """Test parsing menu flows from menu_flows section"""
        spec_data = {
            "menu_flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "Welcome!",
                        "options": [{"text": "Book", "callback": "/book"}]
                    }
                }
            ]
        }

        menu_flows = self.engine.parse_menu_flows(spec_data)

        assert len(menu_flows) == 1
        assert menu_flows[0].entry_cmd == "/start"
        assert menu_flows[0].type == "flow.menu.v1"

    def test_parse_menu_flows_from_flows_section(self):
        """Test parsing menu flows from flows section"""
        spec_data = {
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/menu",
                    "params": {
                        "title": "Main menu",
                        "options": [{"text": "Help", "callback": "/help"}]
                    }
                },
                {
                    "entry_cmd": "/wizard",
                    "steps": [{"ask": "Name?", "var": "name"}]
                }
            ]
        }

        menu_flows = self.engine.parse_menu_flows(spec_data)

        assert len(menu_flows) == 1
        assert menu_flows[0].entry_cmd == "/menu"
        assert menu_flows[0].type == "flow.menu.v1"

    def test_parse_menu_flows_both_sections(self):
        """Test parsing menu flows from both sections"""
        spec_data = {
            "menu_flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {"title": "Start", "options": []}
                }
            ],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/menu",
                    "params": {"title": "Menu", "options": []}
                }
            ]
        }

        menu_flows = self.engine.parse_menu_flows(spec_data)

        assert len(menu_flows) == 2
        entry_cmds = [flow.entry_cmd for flow in menu_flows]
        assert "/start" in entry_cmds
        assert "/menu" in entry_cmds

    def test_parse_menu_flows_empty_spec(self):
        """Test parsing menu flows from empty spec"""
        spec_data = {}
        menu_flows = self.engine.parse_menu_flows(spec_data)
        assert menu_flows == []

    def test_build_menu_keyboard_simple(self):
        """Test building simple menu keyboard"""
        options = [
            {"text": "Option 1", "callback": "opt1"},
            {"text": "Option 2", "callback": "opt2"}
        ]

        keyboard = self.engine._build_menu_keyboard(options)

        expected = [
            [{"text": "Option 1", "callback_data": "opt1"}],
            [{"text": "Option 2", "callback_data": "opt2"}]
        ]
        assert keyboard == expected

    def test_build_menu_keyboard_with_intents(self):
        """Test building keyboard with intent callbacks"""
        options = [
            {"text": "Book", "callback": "/book"},
            {"text": "Help", "callback": "/help"},
            {"text": "Category", "callback": "cat_massage"}
        ]

        keyboard = self.engine._build_menu_keyboard(options)

        expected = [
            [{"text": "Book", "callback_data": "/book"}],
            [{"text": "Help", "callback_data": "/help"}],
            [{"text": "Category", "callback_data": "cat_massage"}]
        ]
        assert keyboard == expected

    def test_build_menu_keyboard_empty(self):
        """Test building keyboard with empty options"""
        options = []
        keyboard = self.engine._build_menu_keyboard(options)
        assert keyboard == []