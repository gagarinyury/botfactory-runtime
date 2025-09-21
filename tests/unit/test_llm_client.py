"""Unit tests for LLM client"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
from runtime.llm_client import LLMClient, LLMConfig, LLMResponse


class TestLLMClient:
    """Test LLM client functionality"""

    @pytest.fixture
    def llm_config(self):
        return LLMConfig(
            base_url="http://test-llm:11434",
            model="test-model",
            timeout=10,
            max_retries=2,
            enabled=True
        )

    @pytest.fixture
    def llm_client(self, llm_config):
        return LLMClient(llm_config)

    @pytest.fixture
    def mock_session_response(self):
        """Mock successful LLM response"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Test response"},
                "text": "Test response"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }
        return mock_response

    def test_llm_config_from_env(self):
        """Test LLM config loading from environment"""
        with patch.dict('os.environ', {
            'LLM_BASE_URL': 'http://custom:8080',
            'LLM_MODEL': 'custom-model',
            'LLM_ENABLED': 'false',
            'LLM_TIMEOUT': '60'
        }):
            config = LLMConfig()
            client = LLMClient(config)

            assert client.config.base_url == 'http://custom:8080'
            assert client.config.model == 'custom-model'
            assert client.config.enabled is False
            assert client.config.timeout == 60

    def test_hash_prompt(self, llm_client):
        """Test prompt hashing for caching"""
        hash1 = llm_client._hash_prompt("system1", "user1", temp=0.2)
        hash2 = llm_client._hash_prompt("system1", "user1", temp=0.2)
        hash3 = llm_client._hash_prompt("system1", "user1", temp=0.3)

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 32  # MD5 hash

    @pytest.mark.asyncio
    async def test_complete_disabled(self, llm_client):
        """Test completion when LLM is disabled"""
        llm_client.config.enabled = False

        with pytest.raises(RuntimeError, match="LLM service is disabled"):
            await llm_client.complete("system", "user")

    @pytest.mark.asyncio
    async def test_complete_success(self, llm_client, mock_session_response):
        """Test successful completion"""
        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__.return_value = mock_session_response
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache', return_value=None), \
                 patch.object(llm_client, '_set_cache') as mock_set_cache:

                response = await llm_client.complete("Test system", "Test user")

                assert isinstance(response, LLMResponse)
                assert response.content == "Test response"
                assert response.usage["prompt_tokens"] == 10
                assert response.usage["completion_tokens"] == 5
                assert not response.cached
                assert response.duration_ms > 0

                # Check cache was called
                mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_cached_response(self, llm_client):
        """Test completion with cached response"""
        cached_response = LLMResponse(
            content="Cached response",
            usage={"prompt_tokens": 5, "completion_tokens": 3},
            model="test-model",
            duration_ms=50
        )

        with patch.object(llm_client, '_get_from_cache', return_value=cached_response):
            response = await llm_client.complete("Test system", "Test user")

            assert response.content == "Cached response"
            assert response.cached is True

    @pytest.mark.asyncio
    async def test_complete_with_retries(self, llm_client):
        """Test completion with HTTP errors and retries"""
        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()

            # First attempt fails, second succeeds
            error_response = AsyncMock()
            error_response.status = 500
            error_response.text.return_value = "Internal Error"

            success_response = AsyncMock()
            success_response.status = 200
            success_response.json.return_value = {
                "choices": [{"message": {"content": "Success on retry"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4}
            }

            mock_session.post.return_value.__aenter__.side_effect = [
                error_response, success_response
            ]
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache', return_value=None), \
                 patch.object(llm_client, '_set_cache'), \
                 patch('asyncio.sleep'):  # Mock sleep to speed up test

                response = await llm_client.complete("Test system", "Test user")

                assert response.content == "Success on retry"

    @pytest.mark.asyncio
    async def test_complete_all_retries_fail(self, llm_client):
        """Test completion when all retries fail"""
        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()

            error_response = AsyncMock()
            error_response.status = 500
            error_response.text.return_value = "Persistent Error"

            mock_session.post.return_value.__aenter__.return_value = error_response
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache', return_value=None), \
                 patch('asyncio.sleep'):  # Mock sleep to speed up test

                with pytest.raises(RuntimeError, match="LLM request failed after .* retries"):
                    await llm_client.complete("Test system", "Test user")

    @pytest.mark.asyncio
    async def test_complete_timeout(self, llm_client):
        """Test completion with timeout"""
        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.post.side_effect = asyncio.TimeoutError()
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache', return_value=None), \
                 patch('asyncio.sleep'):

                with pytest.raises(RuntimeError, match="Request timeout"):
                    await llm_client.complete("Test system", "Test user")

    @pytest.mark.asyncio
    async def test_generate_text_success(self, llm_client, mock_session_response):
        """Test successful text generation"""
        mock_session_response.json.return_value = {
            "choices": [{"text": "Generated text response"}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 8}
        }

        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__.return_value = mock_session_response
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache', return_value=None), \
                 patch.object(llm_client, '_set_cache'):

                response = await llm_client.generate_text("Test prompt")

                assert response.content == "Generated text response"
                assert response.usage["prompt_tokens"] == 15

    @pytest.mark.asyncio
    async def test_complete_with_tools(self, llm_client, mock_session_response):
        """Test completion with tools (no caching)"""
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__.return_value = mock_session_response
            mock_get_session.return_value = mock_session

            with patch.object(llm_client, '_get_from_cache') as mock_get_cache, \
                 patch.object(llm_client, '_set_cache') as mock_set_cache:

                response = await llm_client.complete("Test system", "Test user", tools=tools)

                # Should not check or set cache for tool calls
                mock_get_cache.assert_not_called()
                mock_set_cache.assert_not_called()
                assert response.content == "Test response"

    @pytest.mark.asyncio
    async def test_cache_operations(self, llm_client):
        """Test cache get and set operations"""
        # Test cache miss
        with patch('runtime.llm_client.redis_client') as mock_redis:
            mock_redis.get.return_value = None

            result = await llm_client._get_from_cache("test_key")
            assert result is None

        # Test cache hit
        cached_data = {
            "content": "Cached content",
            "usage": {"prompt_tokens": 5},
            "model": "test-model",
            "duration_ms": 100
        }

        with patch('runtime.llm_client.redis_client') as mock_redis:
            mock_redis.get.return_value = json.dumps(cached_data)

            result = await llm_client._get_from_cache("test_key")
            assert result is not None
            assert result.content == "Cached content"
            assert result.cached is True

        # Test cache set
        response = LLMResponse(
            content="New content",
            usage={"prompt_tokens": 10},
            model="test-model",
            duration_ms=200
        )

        with patch('runtime.llm_client.redis_client') as mock_redis:
            await llm_client._set_cache("test_key", response, 600)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "llm:cache:test_key"
            assert call_args[0][1] == 600  # TTL

    @pytest.mark.asyncio
    async def test_health_check(self, llm_client):
        """Test health check functionality"""
        with patch.object(llm_client, '_get_session') as mock_get_session:
            mock_session = AsyncMock()

            # Test healthy service
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            assert await llm_client.health_check() is True

            # Test unhealthy service
            mock_response.status = 500
            assert await llm_client.health_check() is False

            # Test connection error
            mock_session.get.side_effect = Exception("Connection failed")
            assert await llm_client.health_check() is False

    @pytest.mark.asyncio
    async def test_session_management(self, llm_client):
        """Test HTTP session creation and cleanup"""
        # Test session creation
        session1 = await llm_client._get_session()
        session2 = await llm_client._get_session()

        assert session1 is session2  # Should reuse session

        # Test session cleanup
        await llm_client.close()

        # New session after close
        session3 = await llm_client._get_session()
        assert session3 is not session1

    def test_custom_parameters(self, llm_client):
        """Test custom temperature and max_tokens parameters"""
        # Test that custom parameters override defaults
        assert llm_client.config.temperature == 0.2
        assert llm_client.config.max_tokens == 256

        # These would be tested in integration with actual API calls
        # where we verify the request payload contains the right parameters