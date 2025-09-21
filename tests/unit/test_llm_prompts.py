"""Unit tests for LLM prompts"""
import pytest
import json
from runtime.llm_prompts import LLMPrompts, PromptTemplate, BotPromptConfigs


class TestLLMPrompts:
    """Test LLM prompt templates and configurations"""

    def test_prompt_template_creation(self):
        """Test PromptTemplate creation"""
        template = PromptTemplate(
            system="Test system",
            user_template="User: {message}",
            temperature=0.5,
            max_tokens=100,
            response_format="json"
        )

        assert template.system == "Test system"
        assert template.user_template == "User: {message}"
        assert template.temperature == 0.5
        assert template.max_tokens == 100
        assert template.response_format == "json"

    def test_get_template_by_name(self):
        """Test getting template by name"""
        template = LLMPrompts.get_template("improve_text")
        assert template is not None
        assert isinstance(template, PromptTemplate)
        assert "улучшения текстов" in template.system

        # Test non-existent template
        assert LLMPrompts.get_template("non_existent") is None

    def test_list_templates(self):
        """Test listing all available templates"""
        templates = LLMPrompts.list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert "improve_text" in templates
        assert "validate_input" in templates
        assert "generate_menu" in templates

    def test_format_prompt_success(self):
        """Test successful prompt formatting"""
        template = PromptTemplate(
            system="System with {context}",
            user_template="User message: {message}"
        )

        system, user = LLMPrompts.format_prompt(
            template,
            context="test context",
            message="test message"
        )

        assert system == "System with test context"
        assert user == "User message: test message"

    def test_format_prompt_missing_variable(self):
        """Test prompt formatting with missing variable"""
        template = PromptTemplate(
            system="System with {context}",
            user_template="User message: {message}"
        )

        with pytest.raises(ValueError, match="Missing template variable"):
            LLMPrompts.format_prompt(template, context="test")  # missing 'message'

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON responses"""
        # Test object response
        json_str = '{"valid": true, "reason": "test"}'
        result = LLMPrompts.parse_json_response(json_str)
        assert result == {"valid": True, "reason": "test"}

        # Test with extra text
        json_str = 'Here is the JSON: {"valid": false} and some extra text'
        result = LLMPrompts.parse_json_response(json_str)
        assert result == {"valid": False}

        # Test array response
        json_str = '[{"text": "Option 1"}, {"text": "Option 2"}]'
        result = LLMPrompts.parse_json_response(json_str)
        assert result == {"items": [{"text": "Option 1"}, {"text": "Option 2"}]}

    def test_parse_json_response_invalid(self):
        """Test parsing invalid JSON responses"""
        with pytest.raises(ValueError, match="Invalid JSON response"):
            LLMPrompts.parse_json_response("Not valid JSON at all")

        with pytest.raises(ValueError, match="Invalid JSON response"):
            LLMPrompts.parse_json_response('{"incomplete": ')

    def test_validate_response_format_text(self):
        """Test text response format validation"""
        assert LLMPrompts.validate_response_format("Valid text", "text") is True
        assert LLMPrompts.validate_response_format("   ", "text") is False
        assert LLMPrompts.validate_response_format("", "text") is False

    def test_validate_response_format_json(self):
        """Test JSON response format validation"""
        assert LLMPrompts.validate_response_format('{"valid": true}', "json") is True
        assert LLMPrompts.validate_response_format('[1, 2, 3]', "json") is True
        assert LLMPrompts.validate_response_format("Not JSON", "json") is False

    def test_improve_text_template(self):
        """Test IMPROVE_TEXT template"""
        template = LLMPrompts.IMPROVE_TEXT
        assert template.temperature == 0.3
        assert template.max_tokens == 200
        assert "улучшения текстов" in template.system
        assert "{text}" in template.user_template

    def test_validate_input_template(self):
        """Test VALIDATE_INPUT template"""
        template = LLMPrompts.VALIDATE_INPUT
        assert template.response_format == "json"
        assert template.temperature == 0.1
        assert "валидатор" in template.system
        assert "{expectation}" in template.user_template
        assert "{input}" in template.user_template

    def test_generate_menu_template(self):
        """Test GENERATE_MENU template"""
        template = LLMPrompts.GENERATE_MENU
        assert template.response_format == "json"
        assert template.temperature == 0.4
        assert "генератор меню" in template.system
        assert "{context}" in template.user_template
        assert "{topic}" in template.user_template

    def test_classify_intent_template(self):
        """Test CLASSIFY_INTENT template"""
        template = LLMPrompts.CLASSIFY_INTENT
        assert template.response_format == "json"
        assert template.temperature == 0.1
        assert "классификатор намерений" in template.system
        assert "{intents}" in template.system
        assert "{message}" in template.user_template


class TestBotPromptConfigs:
    """Test ready-to-use bot prompt configurations"""

    def test_improve_bot_message(self):
        """Test improve bot message configuration"""
        config = BotPromptConfigs.improve_bot_message("Original text", "context")

        assert "system" in config
        assert "user" in config
        assert "temperature" in config
        assert "max_tokens" in config
        assert "Original text" in config["user"]
        assert config["temperature"] == 0.3

    def test_smart_validate_input(self):
        """Test smart input validation configuration"""
        config = BotPromptConfigs.smart_validate_input("user input", "expected format")

        assert "system" in config
        assert "user" in config
        assert "user input" in config["user"]
        assert "expected format" in config["user"]
        assert config["temperature"] == 0.1

    def test_generate_dynamic_menu(self):
        """Test dynamic menu generation configuration"""
        config = BotPromptConfigs.generate_dynamic_menu("booking context", "services")

        assert "system" in config
        assert "user" in config
        assert "booking context" in config["user"]
        assert "services" in config["user"]
        assert config["temperature"] == 0.4

    def test_classify_user_intent(self):
        """Test user intent classification configuration"""
        intents = ["book_service", "cancel_booking", "get_info"]
        config = BotPromptConfigs.classify_user_intent("I want to book", intents)

        assert "system" in config
        assert "user" in config
        assert "I want to book" in config["user"]
        assert "book_service, cancel_booking, get_info" in config["system"]
        assert config["temperature"] == 0.1

    def test_generate_contextual_reply(self):
        """Test contextual reply generation configuration"""
        context = {"user_name": "John", "service": "massage"}
        history = ["Hello", "I want to book", "What services do you have?"]

        config = BotPromptConfigs.generate_contextual_reply(
            "Book massage please",
            context,
            history
        )

        assert "system" in config
        assert "user" in config
        assert "Book massage please" in config["user"]
        assert "John" in config["user"]  # Context should be in user message
        assert "What services do you have?" in config["user"]  # Recent history
        assert config["temperature"] == 0.4

    def test_generate_contextual_reply_no_history(self):
        """Test contextual reply with no history"""
        context = {"user_name": "Jane"}

        config = BotPromptConfigs.generate_contextual_reply(
            "Hello",
            context,
            None
        )

        assert "Нет истории" in config["user"]

    def test_generate_contextual_reply_long_history(self):
        """Test contextual reply with long history (should truncate)"""
        context = {"service": "spa"}
        history = ["msg1", "msg2", "msg3", "msg4", "msg5", "msg6"]

        config = BotPromptConfigs.generate_contextual_reply(
            "Continue please",
            context,
            history
        )

        # Should only include last 3 messages
        assert "msg4" in config["user"]
        assert "msg5" in config["user"]
        assert "msg6" in config["user"]
        assert "msg1" not in config["user"]
        assert "msg2" not in config["user"]

    def test_all_configs_have_required_fields(self):
        """Test that all configurations have required fields"""
        configs = [
            BotPromptConfigs.improve_bot_message("test"),
            BotPromptConfigs.smart_validate_input("input", "expectation"),
            BotPromptConfigs.generate_dynamic_menu("context", "topic"),
            BotPromptConfigs.classify_user_intent("message", ["intent1"]),
            BotPromptConfigs.generate_contextual_reply("message", {})
        ]

        for config in configs:
            assert "system" in config
            assert "user" in config
            assert "temperature" in config
            assert "max_tokens" in config
            assert isinstance(config["temperature"], (int, float))
            assert isinstance(config["max_tokens"], int)
            assert 0 <= config["temperature"] <= 1
            assert config["max_tokens"] > 0