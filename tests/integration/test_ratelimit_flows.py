"""Integration tests for rate limit policy in real flow scenarios"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from runtime.dsl_engine import handle
from runtime.actions import ActionExecutor


class TestRateLimitFlowsIntegration:
    """Test rate limit policy in wizard and flow scenarios"""

    @pytest.mark.asyncio
    async def test_ratelimit_blocks_wizard_entry(self):
        """Test rate limit blocking wizard entry"""
        # Test spec with rate limit on wizard entry
        spec_data = {
            "use": ["flow.wizard.v1", "policy.ratelimit.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/start",
                    "params": {
                        "on_enter": [
                            {
                                "type": "policy.ratelimit.v1",
                                "params": {
                                    "scope": "user",
                                    "window_s": 30,
                                    "allowance": 2,
                                    "key_suffix": "{{entry_cmd}}",
                                    "message": "Слишком часто! Подождите {{retry_in}} сек."
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Добро пожаловать! Начинаем wizard."
                                }
                            }
                        ],
                        "steps": [
                            {
                                "ask": "Как вас зовут?",
                                "var": "name"
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            # Mock load_spec
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock Redis to simulate rate limit hit
            with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
                mock_redis_client.redis = AsyncMock()

                # First two calls pass (count 1, 2)
                mock_pipeline = AsyncMock()
                call_count = 0

                def mock_execute():
                    nonlocal call_count
                    call_count += 1
                    return [call_count]  # Return current count

                mock_pipeline.execute.side_effect = mock_execute
                mock_redis_client.redis.pipeline.return_value = mock_pipeline
                mock_redis_client.redis.ttl.return_value = 25

                # First call - should pass
                response1 = await handle("test-bot", "/start")
                assert "Добро пожаловать" in str(response1)

                # Second call - should pass
                response2 = await handle("test-bot", "/start")
                assert "Добро пожаловать" in str(response2)

                # Third call - should be blocked
                response3 = await handle("test-bot", "/start")
                assert "Слишком часто" in str(response3)
                assert "25 сек" in str(response3)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_ratelimit_with_key_suffix_separation(self):
        """Test that different key suffixes don't interfere"""
        spec_data = {
            "use": ["flow.wizard.v1", "policy.ratelimit.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/book",
                    "params": {
                        "on_enter": [
                            {
                                "type": "policy.ratelimit.v1",
                                "params": {
                                    "scope": "user",
                                    "window_s": 60,
                                    "allowance": 1,
                                    "key_suffix": "service:{{service_type}}"
                                }
                            }
                        ],
                        "steps": [
                            {
                                "ask": "Услуга забронирована",
                                "var": "result"
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

            # Mock ActionExecutor to simulate different service types
            with patch('runtime.wizard_engine.ActionExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor

                # Track calls by key suffix
                rate_limit_calls = {}

                def mock_execute_action(action_def):
                    if action_def.get("type") == "policy.ratelimit.v1":
                        # Simulate different contexts for different service types
                        suffix = action_def["params"].get("key_suffix", "")
                        key = f"rl:test-bot:999999:{suffix}"

                        # Track calls per key
                        if key not in rate_limit_calls:
                            rate_limit_calls[key] = 0
                        rate_limit_calls[key] += 1

                        # Allow first call for each key, block subsequent
                        if rate_limit_calls[key] > 1:
                            return {
                                "success": True,
                                "blocked": True,
                                "text": "Уже забронировано для этой услуги"
                            }
                        else:
                            return {"success": True, "blocked": False}
                    return {"success": True}

                mock_executor.execute_action.side_effect = mock_execute_action

                # Set different contexts for different service types
                def set_context_var(name, value):
                    if name == "service_type":
                        mock_executor.context = {"service_type": value}

                mock_executor.set_context_var.side_effect = set_context_var

                # First booking for massage - should pass
                mock_executor.context = {"service_type": "massage"}
                response1 = await handle("test-bot", "/book")
                assert "Услуга забронирована" in str(response1)

                # Second booking for massage - should be blocked
                response2 = await handle("test-bot", "/book")
                assert "Уже забронировано" in str(response2)

                # First booking for spa - should pass (different key suffix)
                mock_executor.context = {"service_type": "spa"}
                response3 = await handle("test-bot", "/book")
                assert "Услуга забронирована" in str(response3)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_ratelimit_different_scopes(self):
        """Test rate limiting with different scopes"""
        spec_data = {
            "use": ["policy.ratelimit.v1"]
        }

        # Test with ActionExecutor directly
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock different counters for different scopes
            scope_counters = {}

            def mock_execute(key_parts):
                # Extract scope from pipeline calls
                incr_call = None
                for call in mock_pipeline.incr.call_args_list:
                    incr_call = call[0][0]  # Get the key from incr call
                    break

                if incr_call:
                    # Extract scope from key (rl:bot:scope_id or rl:bot:scope_id:suffix)
                    if incr_call not in scope_counters:
                        scope_counters[incr_call] = 0
                    scope_counters[incr_call] += 1
                    return [scope_counters[incr_call]]
                return [1]

            mock_pipeline = AsyncMock()
            mock_pipeline.execute.side_effect = lambda: mock_execute(None)
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            session = AsyncMock()

            # Test user scope
            executor_user = ActionExecutor(session, "bot1", 123)
            result1 = await executor_user._execute_ratelimit_policy({
                "scope": "user",
                "allowance": 2,
                "window_s": 60
            })
            assert result1["success"] is True
            assert result1["blocked"] is False

            # Test bot scope - should have separate counter
            executor_bot = ActionExecutor(session, "bot1", 456)  # Different user
            result2 = await executor_bot._execute_ratelimit_policy({
                "scope": "bot",
                "allowance": 1,
                "window_s": 60
            })
            assert result2["success"] is True
            assert result2["blocked"] is False

    @pytest.mark.asyncio
    async def test_ratelimit_on_wizard_step(self):
        """Test rate limiting on wizard step"""
        spec_data = {
            "use": ["flow.wizard.v1", "policy.ratelimit.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/survey",
                    "params": {
                        "steps": [
                            {
                                "ask": "Ваш возраст?",
                                "var": "age"
                            }
                        ],
                        "on_step": [
                            {
                                "type": "policy.ratelimit.v1",
                                "params": {
                                    "scope": "user",
                                    "window_s": 120,
                                    "allowance": 1,
                                    "message": "Один ответ в 2 минуты"
                                }
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Спасибо! Возраст: {{age}}"
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

            # Mock wizard flow handling
            with patch('runtime.wizard_engine.ActionExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor

                call_count = 0

                def mock_execute_action(action_def):
                    nonlocal call_count
                    if action_def.get("type") == "policy.ratelimit.v1":
                        call_count += 1
                        if call_count > 1:
                            return {
                                "success": True,
                                "blocked": True,
                                "text": "Один ответ в 2 минуты"
                            }
                        return {"success": True, "blocked": False}
                    return {"success": True, "type": "reply", "text": "Спасибо! Возраст: 25"}

                mock_executor.execute_action.side_effect = mock_execute_action

                # Start wizard
                response1 = await handle("test-bot", "/survey")
                assert "Ваш возраст?" in str(response1)

                # First answer - should pass
                response2 = await handle("test-bot", "25")
                assert "Спасибо" in str(response2)

                # Restart wizard and try again quickly - should be blocked
                response3 = await handle("test-bot", "/survey")
                response4 = await handle("test-bot", "30")
                assert "Один ответ в 2 минуты" in str(response4)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_ratelimit_redis_failure_graceful(self):
        """Test graceful degradation when Redis fails"""
        spec_data = {
            "use": ["policy.ratelimit.v1"]
        }

        # Mock Redis failure
        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()
            mock_redis_client.redis.pipeline.side_effect = Exception("Redis connection failed")

            session = AsyncMock()
            executor = ActionExecutor(session, "bot1", 123)

            # Should not fail and allow action to proceed
            result = await executor._execute_ratelimit_policy({
                "scope": "user",
                "allowance": 1,
                "window_s": 60
            })

            assert result["success"] is True
            assert result["blocked"] is False

    @pytest.mark.asyncio
    async def test_ratelimit_chat_scope(self):
        """Test rate limiting with chat scope"""
        session = AsyncMock()

        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            # Mock increment operation
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [2]  # Within limit
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            # Test with chat_id
            executor = ActionExecutor(session, "bot1", 123, chat_id=456)
            result = await executor._execute_ratelimit_policy({
                "scope": "chat",
                "allowance": 5,
                "window_s": 60
            })

            assert result["success"] is True
            assert result["blocked"] is False

            # Verify correct key was used (should include chat_id)
            mock_pipeline.incr.assert_called_with("rl:bot1:456")

    @pytest.mark.asyncio
    async def test_ratelimit_metrics_and_logging(self):
        """Test that rate limit generates correct metrics and logs"""
        session = AsyncMock()

        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client, \
             patch('runtime.ratelimit_policy.policy_ratelimit_hits_total') as mock_hits, \
             patch('runtime.ratelimit_policy.policy_ratelimit_pass_total') as mock_pass:

            mock_redis_client.redis = AsyncMock()

            # Mock rate limit hit
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [6]  # Exceeds allowance of 5
            mock_redis_client.redis.pipeline.return_value = mock_pipeline
            mock_redis_client.redis.ttl.return_value = 30

            executor = ActionExecutor(session, "bot1", 123)
            result = await executor._execute_ratelimit_policy({
                "scope": "user",
                "allowance": 5,
                "window_s": 60
            })

            assert result["blocked"] is True

            # Verify metrics were recorded
            mock_hits.labels.assert_called_with("bot1", "user")
            mock_hits.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_ratelimit_complex_key_suffix(self):
        """Test rate limiting with complex key suffix template"""
        session = AsyncMock()

        with patch('runtime.ratelimit_policy.redis_client') as mock_redis_client:
            mock_redis_client.redis = AsyncMock()

            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = [1]
            mock_redis_client.redis.pipeline.return_value = mock_pipeline

            executor = ActionExecutor(session, "bot1", 123)
            executor.set_context_var("service", "massage")
            executor.set_context_var("time", "14:00")

            result = await executor._execute_ratelimit_policy({
                "scope": "user",
                "allowance": 3,
                "window_s": 3600,
                "key_suffix": "book:{{service}}:{{time}}"
            })

            assert result["blocked"] is False

            # Verify complex key was built correctly
            mock_pipeline.incr.assert_called_with("rl:bot1:123:book:massage:14:00")