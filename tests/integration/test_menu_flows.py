"""Integration tests for menu flows functionality"""
import pytest
import json
from httpx import AsyncClient
from runtime.dsl_engine import handle


class TestMenuFlowsIntegration:
    """Test menu flows end-to-end functionality"""

    @pytest.mark.asyncio
    async def test_simple_menu_flow(self):
        """Test basic menu flow handling"""
        # Test bot spec with menu flow
        spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "🏠 Welcome to our service!\\nChoose an action:",
                        "options": [
                            {"text": "📅 Book service", "callback": "/book"},
                            {"text": "📋 My bookings", "callback": "/my"},
                            {"text": "❓ Help", "callback": "/help"}
                        ]
                    }
                }
            ]
        }

        # Mock loading spec (would normally come from database)
        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            # Test menu command
            response = await handle("test-bot", "/start")

            # Should return menu title (keyboard handled separately in real bot)
            assert "Welcome to our service!" in response
            assert "Choose an action:" in response

        finally:
            # Restore original function
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_flow_with_category_selection(self):
        """Test menu flow for category selection"""
        spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/services",
                    "params": {
                        "title": "Select service category:",
                        "options": [
                            {"text": "💆 Massage", "callback": "category_massage"},
                            {"text": "💇 Hairdresser", "callback": "category_hair"},
                            {"text": "✨ Cosmetology", "callback": "category_cosmo"},
                            {"text": "🔙 Back to main menu", "callback": "/start"}
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            response = await handle("test-bot", "/services")
            assert "Select service category:" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_flow_not_matching_command(self):
        """Test non-matching command falls back to intents"""
        spec = {
            "use": ["flow.menu.v1"],
            "intents": [
                {"cmd": "/help", "reply": "This is help text"}
            ],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "Menu",
                        "options": [{"text": "Help", "callback": "/help"}]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            # Menu command
            response1 = await handle("test-bot", "/start")
            assert "Menu" in response1

            # Intent command (not menu)
            response2 = await handle("test-bot", "/help")
            assert response2 == "This is help text"

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_multiple_menu_flows(self):
        """Test multiple menu flows in one spec"""
        spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "Main menu",
                        "options": [
                            {"text": "Services", "callback": "/services"},
                            {"text": "Settings", "callback": "/settings"}
                        ]
                    }
                },
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/settings",
                    "params": {
                        "title": "Settings menu",
                        "options": [
                            {"text": "Language", "callback": "setting_lang"},
                            {"text": "Notifications", "callback": "setting_notif"},
                            {"text": "Back", "callback": "/start"}
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            # Test first menu
            response1 = await handle("test-bot", "/start")
            assert "Main menu" in response1

            # Test second menu
            response2 = await handle("test-bot", "/settings")
            assert "Settings menu" in response2

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_flows_in_menu_flows_section(self):
        """Test menu flows defined in dedicated menu_flows section"""
        spec = {
            "use": ["flow.menu.v1"],
            "menu_flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "Welcome menu",
                        "options": [
                            {"text": "Get started", "callback": "/onboarding"}
                        ]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            response = await handle("test-bot", "/start")
            assert "Welcome menu" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_with_wizard_flows_priority(self):
        """Test menu flows have priority over wizard flows for same commands"""
        spec = {
            "use": ["flow.menu.v1", "flow.wizard.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "Menu version",
                        "options": [{"text": "Continue", "callback": "/next"}]
                    }
                },
                {
                    "entry_cmd": "/start",
                    "steps": [{"ask": "Wizard version?", "var": "test"}],
                    "on_complete": []
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            response = await handle("test-bot", "/start")
            # Should get menu response, not wizard
            assert "Menu version" in response
            assert "Wizard version?" not in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_flows_with_empty_options(self):
        """Test menu flows with empty options"""
        spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/empty",
                    "params": {
                        "title": "No options available",
                        "options": []
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            response = await handle("test-bot", "/empty")
            assert "No options available" in response

        finally:
            dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_menu_flows_error_handling(self):
        """Test error handling in menu flows"""
        spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/broken",
                    "params": {
                        # Missing title - should handle gracefully
                        "options": [{"text": "Test", "callback": "test"}]
                    }
                }
            ]
        }

        import runtime.dsl_engine as dsl
        original_load_spec = dsl.load_spec
        dsl.load_spec = lambda bot_id: spec

        try:
            response = await handle("test-bot", "/broken")
            # Should handle gracefully with default title
            assert "Выберите действие:" in response  # Default title

        finally:
            dsl.load_spec = original_load_spec


class TestMenuFlowsAPI:
    """Test menu flows through API endpoints"""

    @pytest.mark.asyncio
    async def test_preview_menu_flow(self, client: AsyncClient):
        """Test menu flow through preview API"""
        # This would be a real integration test with API
        # For now, just test that the endpoint accepts menu flow specs

        menu_spec = {
            "use": ["flow.menu.v1"],
            "flows": [
                {
                    "type": "flow.menu.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "title": "API menu test",
                        "options": [
                            {"text": "Test option", "callback": "/test"}
                        ]
                    }
                }
            ]
        }

        # Note: This test would require setting up a test bot with this spec
        # and then calling the preview endpoint
        # For now, we'll just verify the spec structure is valid
        from runtime.schemas import BotSpec

        # Should parse without errors
        bot_spec = BotSpec(**menu_spec)
        assert bot_spec.use == ["flow.menu.v1"]