"""Integration tests for booking scenario end-to-end"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch
from runtime.dsl_engine import handle
from runtime.schemas import BotSpec
from runtime.wizard_engine import wizard_engine
from runtime.redis_client import redis_client
from runtime.actions import ActionExecutor

# Test booking scenario spec (as per SPRINT_PLAN.md)
BOOKING_SPEC = {
    "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"],
    "flows": [
        {
            "entry_cmd": "/book",
            "steps": [
                {
                    "ask": "Какая услуга?",
                    "var": "service",
                    "validate": {
                        "regex": "^(massage|spa|consultation)$",
                        "msg": "Выберите: massage, spa, consultation"
                    }
                },
                {
                    "ask": "Когда удобно? (YYYY-MM-DD HH:MM)",
                    "var": "slot",
                    "validate": {
                        "regex": "^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$",
                        "msg": "Формат: 2024-01-15 14:00"
                    }
                }
            ],
            "on_complete": [
                {
                    "action.sql_exec.v1": {
                        "sql": "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"
                    }
                },
                {
                    "action.reply_template.v1": {
                        "text": "Забронировано: {{service}} на {{slot}}"
                    }
                }
            ]
        },
        {
            "entry_cmd": "/my",
            "on_enter": [
                {
                    "action.sql_query.v1": {
                        "sql": "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5",
                        "result_var": "bookings"
                    }
                },
                {
                    "action.reply_template.v1": {
                        "text": "Ваши брони:\n{{#each bookings}}{{service}} - {{slot}}\n{{/each}}",
                        "empty_text": "У вас нет активных броней"
                    }
                }
            ]
        },
        {
            "entry_cmd": "/cancel",
            "on_enter": [
                {
                    "action.sql_exec.v1": {
                        "sql": "DELETE FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id AND id=(SELECT id FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 1)"
                    }
                },
                {
                    "action.reply_template.v1": {
                        "text": "Последняя бронь отменена"
                    }
                }
            ]
        }
    ]
}

class TestBookingIntegration:

    @pytest.fixture
    def bot_id(self):
        return "test-bot-123"

    @pytest.fixture
    def user_id(self):
        return 12345

    @pytest.fixture
    async def mock_session(self):
        """Mock database session"""
        session = AsyncMock()

        # Mock query results
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        return session

    @pytest.fixture
    async def setup_redis(self):
        """Setup Redis mock"""
        with patch('runtime.redis_client.redis_client') as mock_redis:
            mock_redis.get_wizard_state = AsyncMock(return_value=None)
            mock_redis.set_wizard_state = AsyncMock()
            mock_redis.delete_wizard_state = AsyncMock()
            yield mock_redis

    def test_booking_spec_validation(self):
        """Test that booking spec is valid according to our schema"""
        try:
            spec = BotSpec(**BOOKING_SPEC)
            assert spec.use == ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"]
            assert len(spec.flows) == 3

            book_flow = spec.flows[0]
            assert book_flow.entry_cmd == "/book"
            assert len(book_flow.steps) == 2
            assert book_flow.steps[0].var == "service"
            assert book_flow.steps[1].var == "slot"

        except Exception as e:
            pytest.fail(f"Booking spec validation failed: {e}")

    async def test_booking_wizard_start(self, bot_id, user_id, mock_session, setup_redis):
        """Test /book command starts wizard"""
        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "/book")

                # Should ask first question
                assert "Какая услуга?" in response

                # Verify Redis state was set
                setup_redis.set_wizard_state.assert_called_once()

    async def test_booking_wizard_validation_success(self, bot_id, user_id, mock_session, setup_redis):
        """Test wizard validation with valid input"""
        # Setup wizard state for step 1 (asking for service)
        wizard_state = {
            "flow": BOOKING_SPEC["flows"][0],
            "step": 0,
            "vars": {},
            "started_at": "2024-01-01T00:00:00Z"
        }
        setup_redis.get_wizard_state.return_value = wizard_state

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "massage")

                # Should move to next step
                assert "Когда удобно?" in response

                # Verify state was updated
                setup_redis.set_wizard_state.assert_called()

    async def test_booking_wizard_validation_failure(self, bot_id, user_id, mock_session, setup_redis):
        """Test wizard validation with invalid input"""
        wizard_state = {
            "flow": BOOKING_SPEC["flows"][0],
            "step": 0,
            "vars": {},
            "started_at": "2024-01-01T00:00:00Z"
        }
        setup_redis.get_wizard_state.return_value = wizard_state

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "invalid_service")

                # Should return validation error
                assert "Выберите: massage, spa, consultation" in response

    async def test_booking_wizard_completion(self, bot_id, user_id, mock_session, setup_redis):
        """Test wizard completion with SQL execution"""
        # Setup wizard state for final step
        wizard_state = {
            "flow": BOOKING_SPEC["flows"][0],
            "step": 1,
            "vars": {"service": "massage"},
            "started_at": "2024-01-01T00:00:00Z"
        }
        setup_redis.get_wizard_state.return_value = wizard_state

        # Mock SQL execution result
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "2024-01-15 14:00")

                # Should complete and render template
                assert "Забронировано: massage на 2024-01-15 14:00" in response

                # Verify SQL was executed
                mock_session.execute.assert_called()
                mock_session.commit.assert_called()

                # Verify wizard state was cleared
                setup_redis.delete_wizard_state.assert_called()

    async def test_my_bookings_empty(self, bot_id, user_id, mock_session, setup_redis):
        """Test /my command with no bookings"""
        # Mock empty query result
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = ["service", "slot"]
        mock_session.execute.return_value = mock_result

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "/my")

                # Should show empty text
                assert "У вас нет активных броней" in response

    async def test_my_bookings_with_data(self, bot_id, user_id, mock_session, setup_redis):
        """Test /my command with existing bookings"""
        # Mock query result with bookings
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = [
            ("massage", "2024-01-15 14:00:00"),
            ("spa", "2024-01-16 15:00:00")
        ]
        mock_result.keys.return_value = ["service", "slot"]
        mock_session.execute.return_value = mock_result

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "/my")

                # Should list bookings
                assert "massage - 2024-01-15 14:00:00" in response
                assert "spa - 2024-01-16 15:00:00" in response

    async def test_cancel_booking(self, bot_id, user_id, mock_session, setup_redis):
        """Test /cancel command"""
        # Mock SQL execution result
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        with patch('runtime.dsl_engine.load_spec', return_value=BOOKING_SPEC):
            with patch('runtime.dsl_engine.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__.return_value = mock_session

                response = await handle(bot_id, "/cancel")

                # Should confirm cancellation
                assert "Последняя бронь отменена" in response

                # Verify SQL was executed
                mock_session.execute.assert_called()
                mock_session.commit.assert_called()

    def test_sql_security_validation(self):
        """Test SQL security validation"""
        from runtime.actions import ActionExecutor

        executor = ActionExecutor(None, "test-bot", 123)

        # Test multiple statements rejection
        with pytest.raises(ValueError, match="Multiple SQL statements not allowed"):
            executor._set_action_type('sql_query')
            executor._substitute_sql_parameters("SELECT * FROM users; DROP TABLE users;")

        # Test non-SELECT for sql_query
        with pytest.raises(ValueError, match="Only SELECT statements allowed"):
            executor._set_action_type('sql_query')
            executor._substitute_sql_parameters("DELETE FROM users")

        # Test invalid statement for sql_exec
        with pytest.raises(ValueError, match="Only INSERT and DELETE statements allowed"):
            executor._set_action_type('sql_exec')
            executor._substitute_sql_parameters("UPDATE users SET name='hack'")

    def test_template_rendering(self):
        """Test template rendering functionality"""
        from runtime.actions import ActionExecutor

        executor = ActionExecutor(None, "test-bot", 123)
        executor.context = {
            "service": "massage",
            "slot": "2024-01-15 14:00",
            "bookings": [
                {"service": "massage", "slot": "2024-01-15 14:00"},
                {"service": "spa", "slot": "2024-01-16 15:00"}
            ]
        }

        # Test simple variable substitution
        result = executor._render_template("Service: {{service}} at {{slot}}")
        assert result == "Service: massage at 2024-01-15 14:00"

        # Test each loop
        result = executor._render_template("{{#each bookings}}{{service}} - {{slot}}\n{{/each}}")
        expected = "massage - 2024-01-15 14:00\nspa - 2024-01-16 15:00\n"
        assert result == expected

        # Test empty text with no data
        executor.context = {"bookings": []}
        result = executor._render_template("{{#each bookings}}{{service}}{{/each}}", "No bookings")
        assert result == "No bookings"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])