"""Unit tests for rate limit policy"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.ratelimit_policy import RateLimitPolicy


class TestRateLimitPolicy:
    """Test rate limit policy functionality"""

    @pytest.fixture
    def policy(self):
        return RateLimitPolicy()

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis_mock = AsyncMock()
        redis_mock.redis = AsyncMock()
        return redis_mock

    def test_get_scope_id_user(self, policy):
        """Test scope ID generation for user scope"""
        scope_id = policy._get_scope_id("user", "bot1", 123, 456)
        assert scope_id == "123"

    def test_get_scope_id_chat(self, policy):
        """Test scope ID generation for chat scope"""
        scope_id = policy._get_scope_id("chat", "bot1", 123, 456)
        assert scope_id == "456"

    def test_get_scope_id_chat_missing(self, policy):
        """Test scope ID generation for chat scope without chat_id"""
        scope_id = policy._get_scope_id("chat", "bot1", 123, None)
        assert scope_id is None

    def test_get_scope_id_bot(self, policy):
        """Test scope ID generation for bot scope"""
        scope_id = policy._get_scope_id("bot", "bot1", 123, 456)
        assert scope_id == "bot1"

    def test_get_scope_id_invalid(self, policy):
        """Test scope ID generation for invalid scope"""
        scope_id = policy._get_scope_id("invalid", "bot1", 123, 456)
        assert scope_id is None

    def test_render_key_suffix_basic(self, policy):
        """Test basic key suffix rendering"""
        context = {"cmd": "/start", "flow": "booking"}
        suffix = policy._render_key_suffix("{{cmd}}", context)
        assert suffix == "/start"

    def test_render_key_suffix_multiple_vars(self, policy):
        """Test key suffix rendering with multiple variables"""
        context = {"cmd": "/book", "service": "massage"}
        suffix = policy._render_key_suffix("{{cmd}}:{{service}}", context)
        assert suffix == "/book:massage"

    def test_render_key_suffix_missing_var(self, policy):
        """Test key suffix rendering with missing variable"""
        context = {"cmd": "/start"}
        suffix = policy._render_key_suffix("{{cmd}}:{{missing}}", context)
        assert suffix == "/start:{{missing}}"

    def test_render_key_suffix_empty(self, policy):
        """Test empty key suffix rendering"""
        context = {"cmd": "/start"}
        suffix = policy._render_key_suffix("", context)
        assert suffix == ""

    def test_render_key_suffix_error(self, policy):
        """Test key suffix rendering with error"""
        # Simulate error by passing non-dict context
        suffix = policy._render_key_suffix("{{cmd}}", "invalid")
        assert suffix == ""

    def test_build_rate_limit_key_with_suffix(self, policy):
        """Test rate limit key building with suffix"""
        key = policy._build_rate_limit_key("bot1", "123", "start")
        assert key == "rl:bot1:123:start"

    def test_build_rate_limit_key_without_suffix(self, policy):
        """Test rate limit key building without suffix"""
        key = policy._build_rate_limit_key("bot1", "123", "")
        assert key == "rl:bot1:123"

    def test_render_message_basic(self, policy):
        """Test basic message rendering"""
        message = policy._render_message("Retry in {{retry_in}} seconds", {"retry_in": 30})
        assert message == "Retry in 30 seconds"

    def test_render_message_no_vars(self, policy):
        """Test message rendering without variables"""
        message = policy._render_message("Too fast", {})
        assert message == "Too fast"

    def test_render_message_error(self, policy):
        """Test message rendering with error"""
        # Simulate error by passing non-dict context
        message = policy._render_message("Retry in {{retry_in}}", "invalid")
        assert message == "Слишком часто. Попробуйте позже."

    @pytest.mark.asyncio
    async def test_check_rate_limit_invalid_params(self, policy):
        """Test rate limit check with invalid parameters"""
        # Zero allowance
        result = await policy.check_rate_limit(
            "bot1", 123, None, {"allowance": 0, "window_s": 60}
        )
        assert result["allowed"] is True

        # Negative window
        result = await policy.check_rate_limit(
            "bot1", 123, None, {"allowance": 5, "window_s": -1}
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_invalid_scope(self, policy):
        """Test rate limit check with invalid scope"""
        result = await policy.check_rate_limit(
            "bot1", 123, None, {"scope": "invalid", "allowance": 5, "window_s": 60}
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_missing_scope_id(self, policy):
        """Test rate limit check with missing scope ID (chat without chat_id)"""
        result = await policy.check_rate_limit(
            "bot1", 123, None, {"scope": "chat", "allowance": 5, "window_s": 60}
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_unavailable(self, policy):
        """Test rate limit check when Redis is unavailable"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = None

            result = await policy.check_rate_limit(
                "bot1", 123, None, {"scope": "user", "allowance": 5, "window_s": 60}
            )
            assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_pass(self, policy):
        """Test rate limit check when limit is not exceeded"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock increment operation
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [3]  # Current count is 3
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            result = await policy.check_rate_limit(
                "bot1", 123, None,
                {"scope": "user", "allowance": 5, "window_s": 60}
            )

            assert result["allowed"] is True
            assert result["retry_in"] == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_hit(self, policy):
        """Test rate limit check when limit is exceeded"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock increment operation - exceeded limit
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [6]  # Current count is 6 > allowance 5
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            # Mock TTL check
            mock_redis_client.redis.ttl.return_value = 45

            result = await policy.check_rate_limit(
                "bot1", 123, None,
                {"scope": "user", "allowance": 5, "window_s": 60}
            )

            assert result["allowed"] is False
            assert "Слишком часто" in result["message"]
            assert result["retry_in"] == 45

    @pytest.mark.asyncio
    async def test_check_rate_limit_custom_message(self, policy):
        """Test rate limit check with custom message"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock increment operation - exceeded limit
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [6]
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            # Mock TTL check
            mock_redis_client.redis.ttl.return_value = 30

            result = await policy.check_rate_limit(
                "bot1", 123, None,
                {
                    "scope": "user",
                    "allowance": 5,
                    "window_s": 60,
                    "message": "Wait {{retry_in}} seconds"
                }
            )

            assert result["allowed"] is False
            assert result["message"] == "Wait 30 seconds"
            assert result["retry_in"] == 30

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_key_suffix(self, policy):
        """Test rate limit check with key suffix"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock increment operation
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [2]
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            context = {"entry_cmd": "/start"}
            result = await policy.check_rate_limit(
                "bot1", 123, None,
                {
                    "scope": "user",
                    "allowance": 5,
                    "window_s": 60,
                    "key_suffix": "{{entry_cmd}}"
                },
                context
            )

            assert result["allowed"] is True
            # Verify the key was built correctly with suffix
            mock_pipeline.incr.assert_called_with("rl:bot1:123:/start")

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_error(self, policy):
        """Test rate limit check when Redis throws an error"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock Redis error
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.side_effect = Exception("Redis error")
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            result = await policy.check_rate_limit(
                "bot1", 123, None,
                {"scope": "user", "allowance": 5, "window_s": 60}
            )

            # Should bypass on Redis error
            assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_increment_with_ttl(self, policy):
        """Test atomic increment with TTL"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock pipeline operations
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [3]
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            result = await policy._increment_with_ttl("test:key", 60)

            assert result == 3
            mock_pipeline.incr.assert_called_once_with("test:key")
            mock_pipeline.expire.assert_called_once_with("test:key", 60)

    @pytest.mark.asyncio
    async def test_get_retry_time_success(self, policy):
        """Test getting retry time successfully"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()
            mock_redis_client.redis.ttl.return_value = 45

            retry_time = await policy._get_retry_time("test:key")
            assert retry_time == 45

    @pytest.mark.asyncio
    async def test_get_retry_time_negative(self, policy):
        """Test getting retry time when TTL is negative"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()
            mock_redis_client.redis.ttl.return_value = -1

            retry_time = await policy._get_retry_time("test:key")
            assert retry_time == 0

    @pytest.mark.asyncio
    async def test_get_retry_time_error(self, policy):
        """Test getting retry time when Redis throws error"""
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()
            mock_redis_client.redis.ttl.side_effect = Exception("Redis error")

            retry_time = await policy._get_retry_time("test:key")
            assert retry_time == 0