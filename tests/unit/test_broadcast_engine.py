"""Unit tests for broadcast engine"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from runtime.broadcast_engine import BroadcastEngine


class TestBroadcastEngine:
    """Test broadcast engine functionality"""

    @pytest.fixture
    def engine(self):
        return BroadcastEngine()

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        session = AsyncMock()
        return session

    def test_validate_audience_all(self, engine):
        """Test audience validation for 'all'"""
        assert engine._validate_audience("all") is True

    def test_validate_audience_active_7d(self, engine):
        """Test audience validation for 'active_7d'"""
        assert engine._validate_audience("active_7d") is True

    def test_validate_audience_segment_valid(self, engine):
        """Test audience validation for valid segment"""
        assert engine._validate_audience("segment:vip_users") is True
        assert engine._validate_audience("segment:premium_123") is True
        assert engine._validate_audience("segment:new_users") is True

    def test_validate_audience_segment_invalid(self, engine):
        """Test audience validation for invalid segment"""
        assert engine._validate_audience("segment:") is False
        assert engine._validate_audience("segment:invalid-chars") is False
        assert engine._validate_audience("segment:with spaces") is False
        assert engine._validate_audience("segment:with@symbol") is False

    def test_validate_audience_invalid(self, engine):
        """Test audience validation for invalid formats"""
        assert engine._validate_audience("invalid") is False
        assert engine._validate_audience("") is False
        assert engine._validate_audience("segment") is False

    @pytest.mark.asyncio
    async def test_estimate_audience_size_all(self, engine, mock_session):
        """Test audience size estimation for 'all'"""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 150
        mock_session.execute.return_value = mock_result

        size = await engine._estimate_audience_size(mock_session, "test-bot", "all")

        assert size == 150
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_estimate_audience_size_active_7d(self, engine, mock_session):
        """Test audience size estimation for 'active_7d'"""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 75
        mock_session.execute.return_value = mock_result

        size = await engine._estimate_audience_size(mock_session, "test-bot", "active_7d")

        assert size == 75
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_estimate_audience_size_segment(self, engine, mock_session):
        """Test audience size estimation for segment"""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 25
        mock_session.execute.return_value = mock_result

        size = await engine._estimate_audience_size(mock_session, "test-bot", "segment:vip_users")

        assert size == 25
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_estimate_audience_size_invalid(self, engine, mock_session):
        """Test audience size estimation for invalid audience"""
        size = await engine._estimate_audience_size(mock_session, "test-bot", "invalid")

        assert size == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_target_users_all(self, engine, mock_session):
        """Test getting target users for 'all' audience"""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(user_id=123),
            MagicMock(user_id=456),
            MagicMock(user_id=789)
        ]
        mock_session.execute.return_value = mock_result

        users = await engine._get_target_users(mock_session, "test-bot", "all")

        assert users == [123, 456, 789]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_target_users_segment(self, engine, mock_session):
        """Test getting target users for segment audience"""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(user_id=123),
            MagicMock(user_id=456)
        ]
        mock_session.execute.return_value = mock_result

        users = await engine._get_target_users(mock_session, "test-bot", "segment:vip_users")

        assert users == [123, 456]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_target_users_invalid(self, engine, mock_session):
        """Test getting target users for invalid audience"""
        users = await engine._get_target_users(mock_session, "test-bot", "invalid")

        assert users == []
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_render_message_simple_text(self, engine, mock_session):
        """Test rendering simple text message"""
        message_data = {"type": "text", "text": "Hello world!"}

        result = await engine._render_message(mock_session, "test-bot", 123, message_data)

        assert result == "Hello world!"

    @pytest.mark.asyncio
    async def test_render_message_template(self, engine, mock_session):
        """Test rendering template message with i18n"""
        message_data = {
            "type": "template",
            "template": "t:broadcast.promo",
            "variables": {"discount": 20}
        }

        with patch('runtime.broadcast_engine.I18nManager') as mock_i18n_class:
            mock_i18n = AsyncMock()
            mock_i18n_class.return_value = mock_i18n
            mock_i18n.get_user_locale.return_value = "ru"
            mock_i18n.translate.return_value = "Скидка 20%!"

            result = await engine._render_message(mock_session, "test-bot", 123, message_data)

            assert result == "Скидка 20%!"
            mock_i18n.translate.assert_called_once_with(
                mock_session, "test-bot", "broadcast.promo", "ru", discount=20
            )

    @pytest.mark.asyncio
    async def test_render_message_fallback(self, engine, mock_session):
        """Test rendering message fallback"""
        message_data = {"some": "data"}

        result = await engine._render_message(mock_session, "test-bot", 123, message_data)

        assert result == str(message_data)

    @pytest.mark.asyncio
    async def test_send_message_success(self, engine):
        """Test message sending success"""
        with patch('random.random', return_value=0.9):  # 95% success rate
            result = await engine._send_message("test-bot", 123, "Hello!")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_message_failure(self, engine):
        """Test message sending failure"""
        with patch('random.random', return_value=0.97):  # 95% success rate, this fails
            result = await engine._send_message("test-bot", 123, "Hello!")
            assert result is False

    @pytest.mark.asyncio
    async def test_create_broadcast_success(self, engine, mock_session):
        """Test successful broadcast creation"""
        with patch.object(engine, '_estimate_audience_size', return_value=100), \
             patch('runtime.broadcast_engine.broadcast_total') as mock_metric:

            mock_session.execute.return_value = None
            mock_session.commit.return_value = None

            broadcast_id = await engine.create_broadcast(
                mock_session, "test-bot", "all", "Hello world!"
            )

            assert isinstance(broadcast_id, str)
            assert len(broadcast_id) == 36  # UUID length
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_metric.labels.assert_called_once_with("test-bot", "all")

    @pytest.mark.asyncio
    async def test_create_broadcast_invalid_audience(self, engine, mock_session):
        """Test broadcast creation with invalid audience"""
        with pytest.raises(ValueError, match="Invalid audience format"):
            await engine.create_broadcast(
                mock_session, "test-bot", "invalid", "Hello world!"
            )

    @pytest.mark.asyncio
    async def test_create_broadcast_audience_too_large(self, engine, mock_session):
        """Test broadcast creation with audience too large"""
        with patch.object(engine, '_estimate_audience_size', return_value=200000):
            with pytest.raises(ValueError, match="exceeds maximum"):
                await engine.create_broadcast(
                    mock_session, "test-bot", "all", "Hello world!"
                )

    @pytest.mark.asyncio
    async def test_create_broadcast_invalid_throttle(self, engine, mock_session):
        """Test broadcast creation with invalid throttle"""
        with patch.object(engine, '_estimate_audience_size', return_value=100):
            with pytest.raises(ValueError, match="Throttle per_sec must be between"):
                await engine.create_broadcast(
                    mock_session, "test-bot", "all", "Hello world!",
                    throttle={"per_sec": 500}  # Exceeds max
                )

    @pytest.mark.asyncio
    async def test_start_broadcast_success(self, engine, mock_session):
        """Test successful broadcast start"""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        with patch.object(engine, '_queue_broadcast_task') as mock_queue:
            result = await engine.start_broadcast(mock_session, "test-id")

            assert result is True
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_queue.assert_called_once_with("test-id")

    @pytest.mark.asyncio
    async def test_start_broadcast_not_pending(self, engine, mock_session):
        """Test broadcast start when not in pending state"""
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows updated
        mock_session.execute.return_value = mock_result

        result = await engine.start_broadcast(mock_session, "test-id")

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_broadcast_task(self, engine):
        """Test queuing broadcast task"""
        from runtime.redis_client import redis_client

        with patch.object(redis_client, 'connect') as mock_connect, \
             patch.object(redis_client, 'redis') as mock_redis:

            mock_redis.lpush = AsyncMock()

            await engine._queue_broadcast_task("test-id")

            mock_redis.lpush.assert_called_once_with("broadcast_queue", "test-id")

    @pytest.mark.asyncio
    async def test_get_broadcast_status(self, engine, mock_session):
        """Test getting broadcast status"""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "test-id",
            "bot_id": "test-bot",
            "status": "running",
            "total_users": 100,
            "sent_count": 50,
            "failed_count": 5
        }
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        status = await engine.get_broadcast_status(mock_session, "test-id")

        assert status["id"] == "test-id"
        assert status["status"] == "running"
        assert status["total_users"] == 100
        assert status["sent_count"] == 50
        assert status["failed_count"] == 5

    @pytest.mark.asyncio
    async def test_get_broadcast_status_not_found(self, engine, mock_session):
        """Test getting broadcast status for non-existent broadcast"""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        status = await engine.get_broadcast_status(mock_session, "test-id")

        assert status is None

    @pytest.mark.asyncio
    async def test_complete_broadcast(self, engine, mock_session):
        """Test completing broadcast"""
        await engine._complete_broadcast(mock_session, "test-id", 95, 5)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_broadcast(self, engine, mock_session):
        """Test failing broadcast"""
        await engine._fail_broadcast(mock_session, "test-id", "Network error")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_delivery_event(self, engine, mock_session):
        """Test logging delivery event"""
        await engine._log_delivery_event(mock_session, "test-id", 123, "sent")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_broadcast_progress(self, engine, mock_session):
        """Test updating broadcast progress"""
        await engine._update_broadcast_progress(mock_session, "test-id", 50, 5)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()