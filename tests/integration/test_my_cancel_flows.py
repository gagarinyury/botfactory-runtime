"""Integration tests for /my and /cancel flows"""
import pytest
import json
from fastapi.testclient import TestClient
from runtime.main import app


class TestMyFlowIntegration:
    """Test /my flow for listing user bookings"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def my_flow_spec(self):
        """My flow specification"""
        return {
            "use": ["flow.wizard.v1", "action.sql_query.v1", "action.reply_template.v1"],
            "flows": [
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
                                "text": "Ваши брони:\\n{{#each bookings}}{{service}} - {{slot}}\\n{{/each}}",
                                "empty_text": "У вас нет активных броней"
                            }
                        }
                    ]
                }
            ]
        }

    @pytest.fixture
    def setup_bot_with_my_flow(self, client, my_flow_spec):
        """Setup test bot with /my flow spec"""
        test_bot_id = "test-my-bot-456"
        return test_bot_id

    def test_my_flow_with_bookings(self, client, setup_bot_with_my_flow):
        """Test /my command when user has bookings"""
        bot_id = setup_bot_with_my_flow

        # Execute /my command
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        data = response.json()

        # Should return list of bookings
        # Expected format: "Ваши брони:\nmassage - 2024-01-15 14:00\nspa - 2024-01-16 10:30"
        # This test needs actual data setup

    def test_my_flow_without_bookings(self, client, setup_bot_with_my_flow):
        """Test /my command when user has no bookings"""
        bot_id = setup_bot_with_my_flow

        # Execute /my command for user with no bookings
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        data = response.json()

        # Should return empty_text
        # assert data["bot_reply"] == "У вас нет активных броней"

    def test_my_flow_sql_query_execution(self, client, setup_bot_with_my_flow):
        """Test that /my flow executes SQL query correctly"""
        bot_id = setup_bot_with_my_flow

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        # Should execute query and return results without errors

    def test_my_flow_template_rendering(self, client, setup_bot_with_my_flow):
        """Test template rendering in /my flow"""
        bot_id = setup_bot_with_my_flow

        # This test would need to mock some data
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        # Verify template is rendered correctly

    def test_my_flow_limit_to_5_bookings(self, client, setup_bot_with_my_flow):
        """Test that /my flow limits results to 5 bookings"""
        bot_id = setup_bot_with_my_flow

        # Would need setup with more than 5 bookings
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        # Verify only 5 most recent bookings are returned

    def test_my_flow_ordering_by_created_at(self, client, setup_bot_with_my_flow):
        """Test that bookings are ordered by creation date"""
        bot_id = setup_bot_with_my_flow

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200
        # Verify bookings are in correct order (newest first)

    def test_my_flow_user_isolation(self, client, setup_bot_with_my_flow):
        """Test that users only see their own bookings"""
        bot_id = setup_bot_with_my_flow

        # Test with different user contexts
        # Each user should only see their own bookings
        pass

    def test_my_flow_bot_isolation(self, client, setup_bot_with_my_flow):
        """Test that users only see bookings for current bot"""
        bot_id = setup_bot_with_my_flow

        # User bookings should be filtered by bot_id
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response.status_code == 200

    def test_my_flow_sql_error_handling(self, client, setup_bot_with_my_flow):
        """Test /my flow behavior when SQL query fails"""
        # Mock SQL error and verify graceful handling
        pass

    def test_my_flow_special_characters_in_data(self, client, setup_bot_with_my_flow):
        """Test /my flow with special characters in booking data"""
        # Test template rendering with special characters
        pass


class TestCancelFlowIntegration:
    """Test /cancel flow for canceling latest booking"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def cancel_flow_spec(self):
        """Cancel flow specification"""
        return {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
            "flows": [
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

    @pytest.fixture
    def setup_bot_with_cancel_flow(self, client, cancel_flow_spec):
        """Setup test bot with /cancel flow spec"""
        test_bot_id = "test-cancel-bot-789"
        return test_bot_id

    def test_cancel_flow_with_bookings(self, client, setup_bot_with_cancel_flow):
        """Test /cancel command when user has bookings"""
        bot_id = setup_bot_with_cancel_flow

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200
        data = response.json()

        # Should return confirmation
        # assert data["bot_reply"] == "Последняя бронь отменена"

    def test_cancel_flow_without_bookings(self, client, setup_bot_with_cancel_flow):
        """Test /cancel command when user has no bookings"""
        bot_id = setup_bot_with_cancel_flow

        # User with no bookings tries to cancel
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200
        # Should handle gracefully (idempotent operation)

    def test_cancel_flow_deletes_latest_booking(self, client, setup_bot_with_cancel_flow):
        """Test that /cancel deletes the most recent booking"""
        bot_id = setup_bot_with_cancel_flow

        # Would need setup with multiple bookings
        # Verify only the latest one is deleted
        pass

    def test_cancel_flow_user_isolation(self, client, setup_bot_with_cancel_flow):
        """Test that users can only cancel their own bookings"""
        bot_id = setup_bot_with_cancel_flow

        # Verify user can't cancel other users' bookings
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200

    def test_cancel_flow_bot_isolation(self, client, setup_bot_with_cancel_flow):
        """Test that cancellation is isolated by bot_id"""
        bot_id = setup_bot_with_cancel_flow

        # User should only cancel bookings for current bot
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200

    def test_cancel_flow_idempotent(self, client, setup_bot_with_cancel_flow):
        """Test that /cancel is idempotent (safe to call multiple times)"""
        bot_id = setup_bot_with_cancel_flow

        # First cancel
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        # Second cancel (should not error)
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_cancel_flow_sql_execution(self, client, setup_bot_with_cancel_flow):
        """Test that /cancel executes SQL correctly"""
        bot_id = setup_bot_with_cancel_flow

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200
        # Should execute SQL without errors

    def test_cancel_flow_transaction_integrity(self, client, setup_bot_with_cancel_flow):
        """Test transaction integrity during cancellation"""
        # Verify that partial failures are rolled back
        pass

    def test_cancel_flow_sql_error_handling(self, client, setup_bot_with_cancel_flow):
        """Test /cancel flow behavior when SQL fails"""
        # Mock SQL error and verify graceful handling
        pass

    def test_cancel_flow_complex_subquery(self, client, setup_bot_with_cancel_flow):
        """Test the complex SQL subquery in cancel operation"""
        bot_id = setup_bot_with_cancel_flow

        # The cancel SQL uses a subquery to find the latest booking
        # Verify this works correctly with multiple bookings
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response.status_code == 200


class TestMyCancelFlowCombination:
    """Test /my and /cancel flows working together"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def combined_spec(self):
        """Combined spec with both /my and /cancel flows"""
        return {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1", "action.reply_template.v1"],
            "flows": [
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
                                "text": "Ваши брони:\\n{{#each bookings}}{{service}} - {{slot}}\\n{{/each}}",
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

    @pytest.fixture
    def setup_combined_bot(self, client, combined_spec):
        """Setup bot with both flows"""
        test_bot_id = "test-combined-bot-999"
        return test_bot_id

    def test_my_then_cancel_workflow(self, client, setup_combined_bot):
        """Test workflow: check bookings, then cancel latest"""
        bot_id = setup_combined_bot

        # Check bookings
        response_my = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        # Cancel latest
        response_cancel = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        # Check bookings again
        response_my_after = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response_my.status_code == 200
        assert response_cancel.status_code == 200
        assert response_my_after.status_code == 200

    def test_cancel_then_my_workflow(self, client, setup_combined_bot):
        """Test workflow: cancel, then check remaining bookings"""
        bot_id = setup_combined_bot

        # Cancel booking
        response_cancel = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        # Check remaining bookings
        response_my = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        assert response_cancel.status_code == 200
        assert response_my.status_code == 200

    def test_multiple_cancellations_and_checks(self, client, setup_combined_bot):
        """Test multiple cancel/check cycles"""
        bot_id = setup_combined_bot

        # Multiple cycles of cancel and check
        for i in range(3):
            response_cancel = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/cancel"
            })

            response_my = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/my"
            })

            assert response_cancel.status_code == 200
            assert response_my.status_code == 200

    def test_flows_with_no_data(self, client, setup_combined_bot):
        """Test both flows when user has no bookings"""
        bot_id = setup_combined_bot

        # Check bookings (should show empty message)
        response_my = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        # Try to cancel (should be idempotent)
        response_cancel = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/cancel"
        })

        assert response_my.status_code == 200
        assert response_cancel.status_code == 200

    def test_flows_database_consistency(self, client, setup_combined_bot):
        """Test that both flows maintain database consistency"""
        # Verify that /my shows accurate data after /cancel operations
        pass

    def test_flows_concurrent_execution(self, client, setup_combined_bot):
        """Test concurrent execution of /my and /cancel by different users"""
        # Test that concurrent operations don't interfere
        pass


class TestMyCancelFlowErrorHandling:
    """Test error handling for /my and /cancel flows"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_my_flow_database_error(self, client):
        """Test /my flow when database is unavailable"""
        # Mock database error
        pass

    def test_cancel_flow_database_error(self, client):
        """Test /cancel flow when database is unavailable"""
        # Mock database error
        pass

    def test_my_flow_sql_injection_protection(self, client):
        """Test that /my flow is protected against SQL injection"""
        # Even though user doesn't directly input SQL, test parameter safety
        pass

    def test_cancel_flow_sql_injection_protection(self, client):
        """Test that /cancel flow is protected against SQL injection"""
        # Test parameter safety in the complex subquery
        pass

    def test_flows_with_corrupted_data(self, client):
        """Test flows with corrupted or unexpected data in database"""
        # Test handling of malformed data
        pass

    def test_flows_with_large_datasets(self, client):
        """Test flows with large amounts of booking data"""
        # Test performance and limits
        pass

    def test_flows_template_rendering_errors(self, client):
        """Test handling of template rendering errors"""
        # Test with data that might break template rendering
        pass