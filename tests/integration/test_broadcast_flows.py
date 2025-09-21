"""Integration tests for broadcast system in real flow scenarios"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestBroadcastFlowsIntegration:
    """Test broadcast system in DSL flows and API scenarios"""

    @pytest.mark.asyncio
    async def test_broadcast_api_endpoint(self):
        """Test broadcast creation via API endpoint"""
        from runtime.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Mock broadcast engine
        with patch('runtime.broadcast_engine.broadcast_engine') as mock_engine:
            mock_engine.create_broadcast.return_value = "test-broadcast-id"
            mock_engine.start_broadcast.return_value = True

            response = client.post("/bots/test-bot/broadcast", json={
                "audience": "all",
                "message": "Test broadcast message",
                "throttle": {"per_sec": 10}
            })

            assert response.status_code == 200
            data = response.json()
            assert data["broadcast_id"] == "test-broadcast-id"
            assert data["status"] == "running"
            assert "started successfully" in data["message"]

    @pytest.mark.asyncio
    async def test_broadcast_api_validation_error(self):
        """Test broadcast API with validation error"""
        from runtime.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.post("/bots/test-bot/broadcast", json={
            "audience": "invalid-audience",
            "message": "Test message"
        })

        assert response.status_code == 400
        assert "validation_error" in response.json()["code"]

    @pytest.mark.asyncio
    async def test_broadcast_status_api(self):
        """Test broadcast status API endpoint"""
        from runtime.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        mock_status = {
            "id": "test-id",
            "bot_id": "test-bot",
            "status": "completed",
            "audience": "all",
            "total_users": 100,
            "sent_count": 95,
            "failed_count": 5,
            "created_at": "2025-01-01T00:00:00",
            "started_at": "2025-01-01T00:01:00",
            "completed_at": "2025-01-01T00:05:00"
        }

        with patch('runtime.broadcast_engine.broadcast_engine') as mock_engine:
            mock_engine.get_broadcast_status.return_value = mock_status

            response = client.get("/bots/test-bot/broadcasts/test-id")

            assert response.status_code == 200
            data = response.json()
            assert data["broadcast_id"] == "test-id"
            assert data["status"] == "completed"
            assert data["sent_count"] == 95
            assert data["failed_count"] == 5

    @pytest.mark.asyncio
    async def test_broadcast_status_not_found(self):
        """Test broadcast status API for non-existent broadcast"""
        from runtime.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch('runtime.broadcast_engine.broadcast_engine') as mock_engine:
            mock_engine.get_broadcast_status.return_value = None

            response = client.get("/bots/test-bot/broadcasts/non-existent")

            assert response.status_code == 404
            assert "not_found" in response.json()["code"]

    @pytest.mark.asyncio
    async def test_broadcast_in_dsl_flow(self):
        """Test broadcast action in DSL flow"""
        from runtime.actions import ActionExecutor

        # Mock session and broadcast engine
        mock_session = AsyncMock()
        mock_broadcast_engine = AsyncMock()

        with patch('runtime.actions.broadcast_engine', mock_broadcast_engine):
            mock_broadcast_engine.create_broadcast.return_value = "broadcast-123"
            mock_broadcast_engine.start_broadcast.return_value = True

            executor = ActionExecutor(mock_session, "test-bot", 123)
            executor.set_context_var("discount", 20)

            action_def = {
                "type": "ops.broadcast.v1",
                "params": {
                    "audience": "segment:vip_users",
                    "message": "t:broadcast.promo {discount={{discount}}}",
                    "throttle": {"per_sec": 15}
                }
            }

            result = await executor.execute_action(action_def)

            assert result["success"] is True
            assert result["type"] == "broadcast"
            assert result["broadcast_id"] == "broadcast-123"
            assert result["audience"] == "segment:vip_users"
            assert result["status"] == "running"

            mock_broadcast_engine.create_broadcast.assert_called_once()
            mock_broadcast_engine.start_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_with_simple_message(self):
        """Test broadcast with simple text message in DSL"""
        from runtime.actions import ActionExecutor

        mock_session = AsyncMock()
        mock_broadcast_engine = AsyncMock()

        with patch('runtime.actions.broadcast_engine', mock_broadcast_engine):
            mock_broadcast_engine.create_broadcast.return_value = "broadcast-456"
            mock_broadcast_engine.start_broadcast.return_value = True

            executor = ActionExecutor(mock_session, "test-bot", 123)

            action_def = {
                "type": "ops.broadcast.v1",
                "params": {
                    "audience": "active_7d",
                    "message": "Simple text message for active users",
                    "throttle": {"per_sec": 20}
                }
            }

            result = await executor.execute_action(action_def)

            assert result["success"] is True
            assert result["broadcast_id"] == "broadcast-456"
            assert result["audience"] == "active_7d"

    @pytest.mark.asyncio
    async def test_broadcast_action_validation_error(self):
        """Test broadcast action with validation error"""
        from runtime.actions import ActionExecutor

        mock_session = AsyncMock()
        executor = ActionExecutor(mock_session, "test-bot", 123)

        action_def = {
            "type": "ops.broadcast.v1",
            "params": {
                "audience": "all",
                "message": "",  # Empty message should fail
                "throttle": {"per_sec": 10}
            }
        }

        with pytest.raises(ValueError, match="Message is required"):
            await executor.execute_action(action_def)

    @pytest.mark.asyncio
    async def test_broadcast_worker_processing(self):
        """Test broadcast worker processing a queued task"""
        from runtime.broadcast_worker import BroadcastWorker
        from runtime.redis_client import redis_client

        worker = BroadcastWorker()

        # Mock Redis and broadcast engine
        mock_redis = AsyncMock()
        mock_broadcast_engine = AsyncMock()

        with patch.object(redis_client, 'connect'), \
             patch.object(redis_client, 'redis', mock_redis), \
             patch('runtime.broadcast_worker.broadcast_engine', mock_broadcast_engine):

            # Mock queue returning a task
            mock_redis.brpop.return_value = ("broadcast_queue", "test-broadcast-id")

            # Mock worker running flag
            worker.running = False  # Stop after one iteration

            # Mock broadcast execution
            mock_broadcast_engine.execute_broadcast.return_value = None

            # Run worker
            await worker._run_worker_loop()

            # Verify task was processed
            mock_broadcast_engine.execute_broadcast.assert_called_once_with(
                pytest.any, "test-broadcast-id"
            )

    @pytest.mark.asyncio
    async def test_broadcast_execution_end_to_end(self):
        """Test complete broadcast execution flow"""
        from runtime.broadcast_engine import BroadcastEngine

        engine = BroadcastEngine()
        mock_session = AsyncMock()

        # Mock broadcast data
        mock_broadcast = {
            "bot_id": "test-bot",
            "audience": "all",
            "message": '{"type": "text", "text": "Hello everyone!"}',
            "throttle": '{"per_sec": 100}',  # Fast for testing
            "total_users": 3
        }

        # Mock target users
        mock_target_users = [123, 456, 789]

        with patch.object(engine, '_get_broadcast', return_value=mock_broadcast), \
             patch.object(engine, '_get_target_users', return_value=mock_target_users), \
             patch.object(engine, '_render_message', return_value="Hello everyone!"), \
             patch.object(engine, '_send_message', return_value=True), \
             patch.object(engine, '_log_delivery_event'), \
             patch.object(engine, '_update_broadcast_progress'), \
             patch.object(engine, '_complete_broadcast'), \
             patch('asyncio.sleep'):  # Skip actual delays

            await engine.execute_broadcast(mock_session, "test-broadcast-id")

            # Verify all users were processed
            assert engine._send_message.call_count == 3
            assert engine._log_delivery_event.call_count == 3
            engine._complete_broadcast.assert_called_once_with(mock_session, "test-broadcast-id", 3, 0)

    @pytest.mark.asyncio
    async def test_broadcast_with_i18n_template(self):
        """Test broadcast execution with i18n template rendering"""
        from runtime.broadcast_engine import BroadcastEngine

        engine = BroadcastEngine()
        mock_session = AsyncMock()

        message_data = {
            "type": "template",
            "template": "t:broadcast.welcome",
            "variables": {"name": "John"}
        }

        with patch('runtime.broadcast_engine.I18nManager') as mock_i18n_class:
            mock_i18n = AsyncMock()
            mock_i18n_class.return_value = mock_i18n
            mock_i18n.get_user_locale.return_value = "en"
            mock_i18n.translate.return_value = "Welcome, John!"

            result = await engine._render_message(mock_session, "test-bot", 123, message_data)

            assert result == "Welcome, John!"
            mock_i18n.translate.assert_called_once_with(
                mock_session, "test-bot", "broadcast.welcome", "en", name="John"
            )

    @pytest.mark.asyncio
    async def test_broadcast_fault_tolerance(self):
        """Test broadcast fault tolerance with some failed deliveries"""
        from runtime.broadcast_engine import BroadcastEngine

        engine = BroadcastEngine()
        mock_session = AsyncMock()

        mock_broadcast = {
            "bot_id": "test-bot",
            "audience": "all",
            "message": '{"type": "text", "text": "Test message"}',
            "throttle": '{"per_sec": 100}',
            "total_users": 5
        }

        mock_target_users = [123, 456, 789, 101, 202]

        # Mock some failures
        def mock_send_message(bot_id, user_id, message):
            # Fail for user 456 and 202
            return user_id not in [456, 202]

        with patch.object(engine, '_get_broadcast', return_value=mock_broadcast), \
             patch.object(engine, '_get_target_users', return_value=mock_target_users), \
             patch.object(engine, '_render_message', return_value="Test message"), \
             patch.object(engine, '_send_message', side_effect=mock_send_message), \
             patch.object(engine, '_log_delivery_event'), \
             patch.object(engine, '_update_broadcast_progress'), \
             patch.object(engine, '_complete_broadcast'), \
             patch('asyncio.sleep'):

            await engine.execute_broadcast(mock_session, "test-broadcast-id")

            # Verify completion with correct counts
            engine._complete_broadcast.assert_called_once_with(
                mock_session, "test-broadcast-id", 3, 2  # 3 sent, 2 failed
            )

    @pytest.mark.asyncio
    async def test_broadcast_queue_integration(self):
        """Test broadcast queuing and dequeuing"""
        from runtime.broadcast_engine import BroadcastEngine
        from runtime.redis_client import redis_client

        engine = BroadcastEngine()

        with patch.object(redis_client, 'connect'), \
             patch.object(redis_client, 'redis') as mock_redis:

            mock_redis.lpush = AsyncMock()

            await engine._queue_broadcast_task("test-broadcast-id")

            mock_redis.lpush.assert_called_once_with("broadcast_queue", "test-broadcast-id")

    @pytest.mark.asyncio
    async def test_broadcast_metrics_integration(self):
        """Test broadcast metrics are recorded correctly"""
        from runtime.actions import ActionExecutor
        from runtime.telemetry import broadcast_total, dsl_action_latency_ms

        mock_session = AsyncMock()
        mock_broadcast_engine = AsyncMock()

        with patch('runtime.actions.broadcast_engine', mock_broadcast_engine), \
             patch.object(broadcast_total, 'labels') as mock_metric, \
             patch.object(dsl_action_latency_ms, 'labels') as mock_latency:

            mock_broadcast_engine.create_broadcast.return_value = "broadcast-789"
            mock_broadcast_engine.start_broadcast.return_value = True

            mock_metric_instance = MagicMock()
            mock_metric.return_value = mock_metric_instance

            mock_latency_instance = MagicMock()
            mock_latency.return_value = mock_latency_instance

            executor = ActionExecutor(mock_session, "test-bot", 123)

            action_def = {
                "type": "ops.broadcast.v1",
                "params": {
                    "audience": "all",
                    "message": "Metrics test",
                    "throttle": {"per_sec": 30}
                }
            }

            await executor.execute_action(action_def)

            # Verify metrics were recorded
            mock_latency.assert_called_with("broadcast")
            mock_latency_instance.observe.assert_called_once()