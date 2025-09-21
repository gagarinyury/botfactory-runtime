"""Integration tests for i18n functionality in real flows"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from runtime.dsl_engine import handle


class TestI18nFlowsIntegration:
    """Test i18n functionality in wizard and flow scenarios"""

    @pytest.mark.asyncio
    async def test_i18n_template_basic_translation(self):
        """Test basic t:key translation in templates"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "i18n": {
                "default_locale": "ru",
                "supported": ["ru", "en"]
            },
            "intents": [
                {"cmd": "/hello", "reply": "t:greeting"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager with translation
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="Привет!")
                mock_i18n.default_locale = "ru"

                response = await handle("test-bot", "/hello")
                assert "Привет!" in str(response)

                # Verify i18n.translate was called
                mock_i18n.translate.assert_called_once()
                call_args = mock_i18n.translate.call_args
                assert call_args[0][2] == "greeting"  # key
                assert call_args[0][3] == "ru"  # locale

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_i18n_template_with_placeholders(self):
        """Test t:key {placeholder=value} syntax"""
        spec_data = {
            "use": ["flow.wizard.v1", "i18n.fluent.v1", "action.reply_template.v1"],
            "i18n": {
                "default_locale": "en",
                "supported": ["ru", "en"]
            },
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/greet",
                    "params": {
                        "steps": [
                            {
                                "ask": "What's your name?",
                                "var": "username"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "t:personalized_greeting {name={{username}}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="Hello, John!")
                mock_i18n.default_locale = "en"

                # Start wizard
                response1 = await handle("test-bot", "/greet")
                assert "What's your name?" in str(response1)

                # Complete wizard with name
                response2 = await handle("test-bot", "John")
                assert "Hello, John!" in str(response2)

                # Verify i18n.translate was called with placeholders
                mock_i18n.translate.assert_called_once()
                call_args = mock_i18n.translate.call_args
                assert call_args[0][2] == "personalized_greeting"  # key
                assert call_args[1]["name"] == "John"  # placeholder

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_i18n_key_miss_fallback(self):
        """Test fallback when translation key is missing"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "i18n": {
                "default_locale": "ru",
                "supported": ["ru", "en"]
            },
            "intents": [
                {"cmd": "/missing", "reply": "t:missing_key"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager returning fallback
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="[missing_key]")
                mock_i18n.default_locale = "ru"

                response = await handle("test-bot", "/missing")
                assert "[missing_key]" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_locale_resolution_user_strategy(self):
        """Test locale resolution with user strategy"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "i18n": {
                "default_locale": "ru",
                "supported": ["ru", "en"],
                "strategy": "user"
            },
            "intents": [
                {"cmd": "/test", "reply": "t:test_message"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.get_user_locale = AsyncMock(return_value="en")
                mock_i18n.translate = AsyncMock(return_value="Test message")
                mock_i18n.default_locale = "ru"

                response = await handle("test-bot", "/test")
                assert "Test message" in str(response)

                # Verify user locale was resolved
                mock_i18n.get_user_locale.assert_called_once()

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_mixed_templates(self):
        """Test mixing i18n and regular templates"""
        spec_data = {
            "use": ["flow.wizard.v1", "i18n.fluent.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/mix",
                    "params": {
                        "steps": [
                            {
                                "ask": "Regular template: Enter your age",
                                "var": "age"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "t:age_confirmation {age={{age}}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="Your age is 25")
                mock_i18n.default_locale = "ru"

                # Start wizard (regular template)
                response1 = await handle("test-bot", "/mix")
                assert "Regular template: Enter your age" in str(response1)

                # Complete wizard (i18n template)
                response2 = await handle("test-bot", "25")
                assert "Your age is 25" in str(response2)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_i18n_error_handling(self):
        """Test error handling in i18n templates"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "intents": [
                {"cmd": "/error", "reply": "t:some_key"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager raising exception
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(side_effect=Exception("DB error"))
                mock_i18n.default_locale = "ru"

                # Should fallback gracefully
                response = await handle("test-bot", "/error")
                assert "[some_key]" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_complex_placeholder_parsing(self):
        """Test complex placeholder parsing in templates"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/complex",
                    "params": {
                        "steps": [
                            {
                                "ask": "Enter data",
                                "var": "data"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "t:complex_message {item={{data}}, count=5, status=active}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="Complex message")
                mock_i18n.default_locale = "ru"

                # Start and complete wizard
                await handle("test-bot", "/complex")
                response = await handle("test-bot", "test_data")

                assert "Complex message" in str(response)

                # Verify correct placeholders were passed
                call_args = mock_i18n.translate.call_args
                assert call_args[1]["item"] == "test_data"
                assert call_args[1]["count"] == "5"
                assert call_args[1]["status"] == "active"

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_cache_behavior(self):
        """Test that i18n cache works correctly"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "intents": [
                {"cmd": "/cached", "reply": "t:cached_message"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager with cache behavior
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                mock_i18n.translate = AsyncMock(return_value="Cached message")
                mock_i18n.default_locale = "ru"

                # First call
                response1 = await handle("test-bot", "/cached")
                assert "Cached message" in str(response1)

                # Second call should use same translation
                response2 = await handle("test-bot", "/cached")
                assert "Cached message" in str(response2)

                # Both calls should have used i18n
                assert mock_i18n.translate.call_count == 2

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_multiple_locales_in_session(self):
        """Test behavior with multiple locales in a session"""
        spec_data = {
            "use": ["i18n.fluent.v1", "action.reply_template.v1"],
            "i18n": {
                "default_locale": "ru",
                "supported": ["ru", "en", "fr"]
            },
            "intents": [
                {"cmd": "/multi", "reply": "t:multi_locale_message"}
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock i18n manager returning different locales
            with patch('runtime.i18n_manager.i18n_manager') as mock_i18n:
                # First call - Russian
                mock_i18n.get_user_locale = AsyncMock(return_value="ru")
                mock_i18n.translate = AsyncMock(return_value="Сообщение")
                mock_i18n.default_locale = "ru"

                response1 = await handle("test-bot", "/multi")
                assert "Сообщение" in str(response1)

                # Change user locale to English
                mock_i18n.get_user_locale = AsyncMock(return_value="en")
                mock_i18n.translate = AsyncMock(return_value="Message")

                response2 = await handle("test-bot", "/multi")
                assert "Message" in str(response2)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec