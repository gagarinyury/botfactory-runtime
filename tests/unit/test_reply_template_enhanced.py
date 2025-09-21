"""Unit tests for enhanced action.reply_template.v1"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.actions import ActionExecutor


class TestReplyTemplateEnhanced:
    """Test enhanced reply template functionality"""

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def action_executor(self, mock_session):
        """Create ActionExecutor instance"""
        return ActionExecutor(mock_session, "test-bot", 123)

    @pytest.mark.asyncio
    async def test_reply_template_basic(self, action_executor):
        """Test basic reply template rendering"""
        config = {
            "text": "Hello {{name}}!",
            "parse_mode": "HTML"
        }

        # Set context
        action_executor.set_context_var("name", "Alice")

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is True
            assert result["text"] == "Hello Alice!"
            assert result["parse_mode"] == "HTML"
            assert result["type"] == "reply"

    @pytest.mark.asyncio
    async def test_reply_template_default_parse_mode(self, action_executor):
        """Test default parse_mode when not specified"""
        config = {
            "text": "Test message"
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["parse_mode"] == "HTML"  # Default

    @pytest.mark.asyncio
    async def test_reply_template_markdown_parse_mode(self, action_executor):
        """Test MarkdownV2 parse mode"""
        config = {
            "text": "*Bold text* and _italic text_",
            "parse_mode": "MarkdownV2"
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["parse_mode"] == "MarkdownV2"

    @pytest.mark.asyncio
    async def test_reply_template_with_keyboard_single_buttons(self, action_executor):
        """Test reply template with single buttons (original format)"""
        config = {
            "text": "Choose option:",
            "keyboard": [
                {"text": "Option 1", "callback": "/option1"},
                {"text": "Option 2", "callback": "data:option2"}
            ]
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is True
            assert "keyboard" in result
            keyboard = result["keyboard"]

            # Should be 2 rows, each with 1 button
            assert len(keyboard) == 2
            assert len(keyboard[0]) == 1  # First row
            assert len(keyboard[1]) == 1  # Second row

            assert keyboard[0][0]["text"] == "Option 1"
            assert keyboard[0][0]["callback_data"] == "/option1"
            assert keyboard[1][0]["text"] == "Option 2"
            assert keyboard[1][0]["callback_data"] == "data:option2"

    @pytest.mark.asyncio
    async def test_reply_template_with_keyboard_multi_row(self, action_executor):
        """Test reply template with multi-row keyboard"""
        config = {
            "text": "Choose option:",
            "keyboard": [
                # First row with 2 buttons
                [
                    {"text": "Yes", "callback": "yes"},
                    {"text": "No", "callback": "no"}
                ],
                # Second row with 1 button
                {"text": "Cancel", "callback": "/cancel"}
            ]
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            keyboard = result["keyboard"]

            # Should be 2 rows
            assert len(keyboard) == 2

            # First row has 2 buttons
            assert len(keyboard[0]) == 2
            assert keyboard[0][0]["text"] == "Yes"
            assert keyboard[0][0]["callback_data"] == "yes"
            assert keyboard[0][1]["text"] == "No"
            assert keyboard[0][1]["callback_data"] == "no"

            # Second row has 1 button
            assert len(keyboard[1]) == 1
            assert keyboard[1][0]["text"] == "Cancel"
            assert keyboard[1][0]["callback_data"] == "/cancel"

    @pytest.mark.asyncio
    async def test_reply_template_with_invalid_keyboard_buttons(self, action_executor):
        """Test reply template handles invalid keyboard buttons gracefully"""
        config = {
            "text": "Test",
            "keyboard": [
                {"text": "Valid", "callback": "/valid"},
                {"text": "", "callback": "empty_text"},  # Invalid: empty text
                {"text": "No callback"},  # Invalid: no callback
                None,  # Invalid: not a dict
                {"text": "Valid 2", "callback": "valid2"}
            ]
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            keyboard = result["keyboard"]

            # Should only have 2 valid buttons
            assert len(keyboard) == 2
            assert keyboard[0][0]["text"] == "Valid"
            assert keyboard[1][0]["text"] == "Valid 2"

    @pytest.mark.asyncio
    async def test_reply_template_with_each_loop(self, action_executor):
        """Test reply template with {{#each}} loops"""
        config = {
            "text": "Items:\n{{#each items}}• {{name}} - {{price}}₽\n{{/each}}"
        }

        # Set context with items
        action_executor.set_context_var("items", [
            {"name": "Item 1", "price": 100},
            {"name": "Item 2", "price": 200}
        ])

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            expected_text = "Items:\n• Item 1 - 100₽\n• Item 2 - 200₽\n"
            assert result["text"] == expected_text

    @pytest.mark.asyncio
    async def test_reply_template_with_empty_text(self, action_executor):
        """Test reply template with empty_text fallback"""
        config = {
            "text": "Items:\n{{#each items}}• {{name}}\n{{/each}}",
            "empty_text": "No items available"
        }

        # Set context with empty items
        action_executor.set_context_var("items", [])

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["text"] == "No items available"

    @pytest.mark.asyncio
    async def test_reply_template_i18n_simple_key(self, action_executor):
        """Test reply template with i18n simple key"""
        config = {
            "text": "t:welcome"
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
             patch.object(action_executor, '_render_i18n_template') as mock_i18n:

            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            mock_i18n.return_value = "Добро пожаловать!"

            result = await action_executor._execute_reply_template(config)

            assert result["text"] == "Добро пожаловать!"
            mock_i18n.assert_called_once_with("t:welcome", None)

    @pytest.mark.asyncio
    async def test_reply_template_i18n_with_placeholders(self, action_executor):
        """Test reply template with i18n placeholders"""
        config = {
            "text": "t:greet {name={{username}}}"
        }

        action_executor.set_context_var("username", "Alice")

        with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
             patch.object(action_executor, '_render_i18n_template') as mock_i18n:

            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            mock_i18n.return_value = "Привет, Alice!"

            result = await action_executor._execute_reply_template(config)

            assert result["text"] == "Привет, Alice!"

    @pytest.mark.asyncio
    async def test_reply_template_error_handling(self, action_executor):
        """Test reply template error handling and fallback"""
        config = {
            "text": "{{invalid_template"  # Malformed template
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
             patch.object(action_executor, '_render_template_with_i18n') as mock_render:

            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            mock_render.side_effect = Exception("Template error")

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is False
            assert result["text"] == "[template error]"
            assert result["error"] == "Template error"

    @pytest.mark.asyncio
    async def test_reply_template_metrics_success(self, action_executor):
        """Test reply template success metrics"""
        config = {
            "text": "Test message"
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
             patch('runtime.actions.reply_sent_total') as mock_sent, \
             patch('runtime.actions.reply_latency_ms') as mock_latency:

            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            mock_sent_labels = MagicMock()
            mock_sent.labels.return_value = mock_sent_labels
            mock_latency_labels = MagicMock()
            mock_latency.labels.return_value = mock_latency_labels

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is True
            mock_sent.labels.assert_called_once_with("test-bot")
            mock_sent_labels.inc.assert_called_once()
            mock_latency.labels.assert_called_once_with("test-bot")
            mock_latency_labels.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_template_metrics_failure(self, action_executor):
        """Test reply template failure metrics"""
        config = {
            "text": "{{malformed"
        }

        with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
             patch('runtime.actions.reply_failed_total') as mock_failed, \
             patch.object(action_executor, '_render_template_with_i18n') as mock_render:

            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            mock_failed_labels = MagicMock()
            mock_failed.labels.return_value = mock_failed_labels
            mock_render.side_effect = Exception("Template error")

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is False
            mock_failed.labels.assert_called_once_with("test-bot")
            mock_failed_labels.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_template_event_logging(self, action_executor):
        """Test reply template event logging"""
        config = {
            "text": "Hello {{name}}!",
            "keyboard": [{"text": "OK", "callback": "ok"}],
            "parse_mode": "MarkdownV2"
        }

        action_executor.set_context_var("name", "Alice")

        with patch('runtime.actions.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await action_executor._execute_reply_template(config)

            assert result["success"] is True

            # Check event was logged
            mock_logger.log_event.assert_called_once()
            event_call = mock_logger.log_event.call_args
            assert event_call[0][0] == "reply_render"

            event_data = event_call[0][1]
            assert event_data["rendered_length"] == len("Hello Alice!")
            assert event_data["keyboard_buttons"] == 1
            assert event_data["parse_mode"] == "MarkdownV2"
            assert "template_hash" in event_data
            assert "duration_ms" in event_data

    def test_build_button_valid(self, action_executor):
        """Test building valid button"""
        button_config = {"text": "Test", "callback": "/test"}
        button = action_executor._build_button(button_config)

        assert button is not None
        assert button["text"] == "Test"
        assert button["callback_data"] == "/test"

    def test_build_button_invalid(self, action_executor):
        """Test building invalid buttons"""
        # Missing text
        assert action_executor._build_button({"callback": "/test"}) is None

        # Missing callback
        assert action_executor._build_button({"text": "Test"}) is None

        # Empty text
        assert action_executor._build_button({"text": "", "callback": "/test"}) is None

        # Not a dict
        assert action_executor._build_button("invalid") is None