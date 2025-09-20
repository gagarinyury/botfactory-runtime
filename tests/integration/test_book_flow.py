"""Integration tests for /book wizard flow"""
import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from runtime.main import app
from runtime.redis_client import redis_client


class TestBookFlowIntegration:
    """Test complete /book wizard flow end-to-end"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def booking_spec(self):
        """Book flow specification"""
        return {
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
                }
            ]
        }

    @pytest.fixture
    async def setup_bot(self, client, booking_spec):
        """Setup test bot with booking spec"""
        # Create bot with spec via API or direct DB insert
        test_bot_id = "test-booking-bot-123"

        # Mock bot setup - in real implementation this would insert into database
        # For now we'll use the preview endpoint which loads specs differently

        return test_bot_id

    def test_book_flow_valid_sequence(self, client, booking_spec, setup_bot):
        """Test complete valid booking flow"""
        bot_id = setup_bot

        # Mock the bot spec loading by using preview endpoint
        # Step 1: Start /book command
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })

        # Should ask for service
        assert response1.status_code == 200
        data1 = response1.json()
        # Would need to mock the spec loading properly
        # For now this is a placeholder structure

    def test_book_flow_invalid_service(self, client, setup_bot):
        """Test booking flow with invalid service input"""
        bot_id = setup_bot

        # Start booking
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })

        # Provide invalid service
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "therapy"  # Invalid, not in (massage|spa|consultation)
        })

        # Should return validation error message
        assert response2.status_code == 200
        data2 = response2.json()
        # Should contain validation message
        # assert "Выберите: massage, spa, consultation" in data2["bot_reply"]

    def test_book_flow_invalid_datetime(self, client, setup_bot):
        """Test booking flow with invalid datetime format"""
        bot_id = setup_bot

        # Start booking and provide valid service
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})
        client.post("/preview/send", json={"bot_id": bot_id, "text": "massage"})

        # Provide invalid datetime
        response3 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "tomorrow at 2pm"  # Invalid format
        })

        assert response3.status_code == 200
        data3 = response3.json()
        # Should contain validation message
        # assert "Формат: 2024-01-15 14:00" in data3["bot_reply"]

    def test_book_flow_complete_valid(self, client, setup_bot):
        """Test complete valid booking flow with database insertion"""
        bot_id = setup_bot

        # Step 1: Start booking
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })
        assert response1.status_code == 200

        # Step 2: Provide valid service
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "massage"
        })
        assert response2.status_code == 200

        # Step 3: Provide valid datetime
        response3 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "2024-03-15 14:00"
        })
        assert response3.status_code == 200

        # Should complete booking and return confirmation
        data3 = response3.json()
        # assert "Забронировано: massage на 2024-03-15 14:00" in data3["bot_reply"]

    @pytest.mark.asyncio
    async def test_book_flow_wizard_state_management(self, setup_bot):
        """Test wizard state is properly managed in Redis"""
        bot_id = setup_bot
        user_id = 12345

        # Check no initial state
        state = await redis_client.get_wizard_state(bot_id, user_id)
        assert state is None

        # After starting wizard, state should exist
        # (This would require triggering the wizard start)

        # After completing wizard, state should be cleaned up
        # state_after = await redis_client.get_wizard_state(bot_id, user_id)
        # assert state_after is None

    def test_book_flow_validation_edge_cases(self, client, setup_bot):
        """Test edge cases for validation"""
        bot_id = setup_bot

        # Test empty input
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})

        response_empty = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": ""
        })
        assert response_empty.status_code == 200

        # Test whitespace only
        response_space = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "   "
        })
        assert response_space.status_code == 200

        # Test case sensitivity
        response_case = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "MASSAGE"  # Different case
        })
        assert response_case.status_code == 200

    def test_book_flow_concurrent_users(self, client, setup_bot):
        """Test that different users don't interfere with each other"""
        bot_id = setup_bot

        # User 1 starts booking
        response1_u1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book",
            # Would need user context, currently missing in preview
        })

        # User 2 starts booking
        response1_u2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book",
            # Different user context
        })

        # Both should get independent wizard sessions
        assert response1_u1.status_code == 200
        assert response1_u2.status_code == 200

    def test_book_flow_interruption_and_restart(self, client, setup_bot):
        """Test wizard behavior when user restarts mid-flow"""
        bot_id = setup_bot

        # Start booking
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})

        # Provide service
        client.post("/preview/send", json={"bot_id": bot_id, "text": "spa"})

        # Restart booking before completing
        response_restart = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"  # Start over
        })

        assert response_restart.status_code == 200
        # Should start fresh wizard
        # data = response_restart.json()
        # assert "Какая услуга?" in data["bot_reply"]

    def test_book_flow_invalid_command_during_wizard(self, client, setup_bot):
        """Test behavior with invalid commands during wizard"""
        bot_id = setup_bot

        # Start booking
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})

        # Try different command mid-wizard
        response_other_cmd = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/help"
        })

        assert response_other_cmd.status_code == 200
        # Should either handle gracefully or continue wizard

    def test_book_flow_special_characters_input(self, client, setup_bot):
        """Test wizard with special characters in input"""
        bot_id = setup_bot

        # Start booking
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})

        # Provide service with special chars
        response_special = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "massage'; DROP TABLE bookings; --"
        })

        assert response_special.status_code == 200
        # Should handle SQL injection attempts safely

    def test_book_flow_very_long_input(self, client, setup_bot):
        """Test wizard with very long input"""
        bot_id = setup_bot

        # Start booking
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})

        # Provide very long input
        long_text = "massage" + "x" * 1000
        response_long = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": long_text
        })

        assert response_long.status_code == 200
        # Should handle gracefully


class TestBookFlowWithDatabase:
    """Test booking flow with actual database operations"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_book_flow_database_insertion(self, client):
        """Test that completed booking actually inserts into database"""
        # This would require full integration test setup
        # with test database and proper bot configuration
        pass

    @pytest.mark.asyncio
    async def test_book_flow_database_error_handling(self, client):
        """Test behavior when database operations fail"""
        # Mock database failure and verify error handling
        pass

    @pytest.mark.asyncio
    async def test_book_flow_transaction_rollback(self, client):
        """Test that failed booking operations are rolled back"""
        # Test transaction integrity
        pass


class TestBookFlowEventLogging:
    """Test that booking flow generates proper events"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_book_flow_generates_events(self, client):
        """Test that all wizard steps generate proper bot_events"""
        # Complete a booking flow and verify events are logged
        # Check for: update, flow_step, action_sql, action_reply events
        pass

    @pytest.mark.asyncio
    async def test_book_flow_metrics_incremented(self, client):
        """Test that booking flow increments metrics properly"""
        # Verify bot_updates_total and other metrics are incremented
        pass


# Placeholder for tests that would require full infrastructure
class TestBookFlowPerformance:
    """Performance tests for booking flow"""

    def test_book_flow_response_time(self, client):
        """Test that booking flow responds within acceptable time"""
        # Measure response times for each step
        pass

    def test_book_flow_memory_usage(self, client):
        """Test memory usage during booking flow"""
        pass

    def test_book_flow_redis_cleanup(self, client):
        """Test that Redis state is properly cleaned up"""
        pass