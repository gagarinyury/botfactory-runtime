"""Integration tests for LLM functionality"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from runtime.llm_client import llm_client
from runtime.actions import ActionExecutor


class TestLLMIntegration:
    """Test LLM integration with runtime components"""

    @pytest.mark.asyncio
    async def test_llm_text_improvement_integration(self):
        """Test LLM text improvement in action.reply_template.v1"""
        # Mock LLM response
        mock_llm_response = AsyncMock()
        mock_llm_response.content = "Улучшенный дружелюбный текст с эмодзи! 😊"
        mock_llm_response.cached = False
        mock_llm_response.duration_ms = 150
        mock_llm_response.usage = {"prompt_tokens": 15, "completion_tokens": 20}

        # Mock session
        mock_session = AsyncMock()

        # Create action executor
        executor = ActionExecutor(mock_session, "test-bot", 123)
        executor.set_context_var("user_name", "Иван")

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', return_value=mock_llm_response):

            # Test reply template with LLM improvement enabled
            config = {
                "text": "Привет {{user_name}}. Ваш заказ готов.",
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            assert result["success"] is True
            assert result["type"] == "reply"
            # Should contain improved text
            assert "😊" in result["text"]
            assert "Улучшенный" in result["text"]

    @pytest.mark.asyncio
    async def test_llm_text_improvement_disabled(self):
        """Test that LLM improvement is skipped when disabled"""
        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)
        executor.set_context_var("user_name", "Иван")

        with patch.dict('os.environ', {'LLM_ENABLED': 'false'}):
            config = {
                "text": "Привет {{user_name}}. Ваш заказ готов.",
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            assert result["success"] is True
            assert result["type"] == "reply"
            # Should contain original text without improvement
            assert result["text"] == "Привет Иван. Ваш заказ готов."

    @pytest.mark.asyncio
    async def test_llm_improvement_fallback_on_error(self):
        """Test fallback to original text when LLM fails"""
        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)
        executor.set_context_var("user_name", "Анна")

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', side_effect=Exception("LLM error")):

            config = {
                "text": "Привет {{user_name}}. Как дела?",
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            assert result["success"] is True
            assert result["type"] == "reply"
            # Should fallback to original text
            assert result["text"] == "Привет Анна. Как дела?"

    @pytest.mark.asyncio
    async def test_llm_improvement_skipped_for_short_text(self):
        """Test that very short texts are not improved"""
        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete') as mock_complete:

            config = {
                "text": "OK",  # Too short
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            # LLM should not be called for very short text
            mock_complete.assert_not_called()
            assert result["text"] == "OK"

    @pytest.mark.asyncio
    async def test_llm_improvement_skipped_for_long_text(self):
        """Test that very long texts are not improved"""
        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        long_text = "Lorem ipsum " * 50  # Over 500 chars

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete') as mock_complete:

            config = {
                "text": long_text,
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            # LLM should not be called for very long text
            mock_complete.assert_not_called()
            assert result["text"] == long_text

    @pytest.mark.asyncio
    async def test_llm_caching_integration(self):
        """Test LLM response caching"""
        # First call should hit LLM
        mock_llm_response1 = AsyncMock()
        mock_llm_response1.content = "Первый улучшенный ответ"
        mock_llm_response1.cached = False
        mock_llm_response1.duration_ms = 200

        # Second call should hit cache
        mock_llm_response2 = AsyncMock()
        mock_llm_response2.content = "Первый улучшенный ответ"
        mock_llm_response2.cached = True
        mock_llm_response2.duration_ms = 200

        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', side_effect=[mock_llm_response1, mock_llm_response2]):

            config = {
                "text": "Тестовый текст для улучшения",
                "llm_improve": True
            }

            # First call
            result1 = await executor._execute_reply_template(config)
            assert "Первый улучшенный ответ" in result1["text"]

            # Second call with same text should use cache
            result2 = await executor._execute_reply_template(config)
            assert "Первый улучшенный ответ" in result2["text"]

    @pytest.mark.asyncio
    async def test_llm_metrics_recorded(self):
        """Test that LLM metrics are recorded properly"""
        mock_llm_response = AsyncMock()
        mock_llm_response.content = "Improved text"
        mock_llm_response.cached = False
        mock_llm_response.duration_ms = 180
        mock_llm_response.usage = {"prompt_tokens": 12, "completion_tokens": 8}

        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', return_value=mock_llm_response), \
             patch('runtime.telemetry.llm_requests_total') as mock_requests, \
             patch('runtime.telemetry.llm_latency_ms') as mock_latency, \
             patch('runtime.telemetry.llm_tokens_total') as mock_tokens:

            config = {
                "text": "Text to improve with LLM",
                "llm_improve": True
            }

            await executor._execute_reply_template(config)

            # Verify metrics were recorded
            mock_requests.labels.assert_called_with("chat_completion", "success")
            mock_latency.labels.assert_called_with("chat_completion", "false")
            mock_tokens.labels.assert_called()

    @pytest.mark.asyncio
    async def test_llm_with_keyboard_integration(self):
        """Test LLM improvement with keyboard buttons"""
        mock_llm_response = AsyncMock()
        mock_llm_response.content = "Выберите опцию из меню ниже 👇"
        mock_llm_response.cached = False
        mock_llm_response.duration_ms = 120

        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', return_value=mock_llm_response):

            config = {
                "text": "Выберите опцию",
                "llm_improve": True,
                "keyboard": [
                    {"text": "Опция 1", "callback_data": "opt1"},
                    {"text": "Опция 2", "callback_data": "opt2"}
                ]
            }

            result = await executor._execute_reply_template(config)

            assert result["success"] is True
            assert "👇" in result["text"]  # Improved text
            assert len(result["keyboard"]) == 2  # Keyboard preserved
            assert result["keyboard"][0]["text"] == "Опция 1"

    @pytest.mark.asyncio
    async def test_llm_empty_response_handling(self):
        """Test handling of empty LLM responses"""
        mock_llm_response = AsyncMock()
        mock_llm_response.content = ""  # Empty response
        mock_llm_response.cached = False

        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', return_value=mock_llm_response):

            config = {
                "text": "Original text",
                "llm_improve": True
            }

            result = await executor._execute_reply_template(config)

            # Should fallback to original text
            assert result["text"] == "Original text"

    @pytest.mark.asyncio
    async def test_llm_service_health_check(self):
        """Test LLM service health check"""
        with patch('runtime.llm_client.llm_client._get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_response = AsyncMock()

            # Test healthy service
            mock_response.status = 200
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            assert await llm_client.health_check() is True

            # Test unhealthy service
            mock_response.status = 503
            assert await llm_client.health_check() is False

    @pytest.mark.asyncio
    async def test_llm_concurrent_requests(self):
        """Test concurrent LLM requests"""
        async def mock_complete(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate processing time
            mock_response = AsyncMock()
            mock_response.content = f"Response for {kwargs.get('user', 'unknown')}"
            mock_response.cached = False
            mock_response.duration_ms = 100
            return mock_response

        mock_session = AsyncMock()

        with patch.dict('os.environ', {'LLM_ENABLED': 'true'}), \
             patch('runtime.llm_client.llm_client.complete', side_effect=mock_complete):

            # Create multiple executors for concurrent requests
            executors = [
                ActionExecutor(mock_session, "test-bot", i)
                for i in range(3)
            ]

            configs = [
                {"text": f"Test message {i}", "llm_improve": True}
                for i in range(3)
            ]

            # Execute concurrently
            tasks = [
                executor._execute_reply_template(config)
                for executor, config in zip(executors, configs)
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            for i, result in enumerate(results):
                assert result["success"] is True
                assert "Response for" in result["text"]