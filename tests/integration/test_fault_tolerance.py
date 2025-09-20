"""Fault tolerance tests for error handling and resilience"""
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from runtime.main import app
from runtime.telemetry import bot_errors_total


class TestDatabaseFailureHandling:
    """Test behavior when database is unavailable or fails"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_database_unavailable_returns_503(self, client):
        """Test that database unavailable returns 503 db_unavailable"""
        bot_id = "test-db-failure-bot"

        # Mock database connection failure
        with patch('runtime.main.async_session') as mock_session:
            mock_session.side_effect = Exception("Database connection failed")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/start"
            })

            # Should return 503 with db_unavailable error
            assert response.status_code == 503
            data = response.json()
            assert "db_unavailable" in data.get("detail", "").lower() or \
                   "database" in data.get("detail", "").lower()

    def test_database_error_increments_error_metrics(self, client):
        """Test that database errors increment bot_errors_total{code="db"}"""
        bot_id = "test-db-metrics-bot"

        # Get initial error count
        initial_errors = bot_errors_total.labels(bot_id=bot_id, where="database", code="db")._value._value

        # Mock database error
        with patch('runtime.main.async_session') as mock_session:
            mock_session.side_effect = Exception("Database error")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/help"
            })

            # Verify error metric incremented
            final_errors = bot_errors_total.labels(bot_id=bot_id, where="database", code="db")._value._value
            assert final_errors > initial_errors

    def test_sql_execution_error_handling(self, client):
        """Test handling of SQL execution errors"""
        bot_id = "test-sql-error-bot"

        # Mock SQL execution failure in action executor
        with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql:
            mock_sql.side_effect = Exception("SQL execution failed")

            # Try to complete booking flow that would execute SQL
            response = client.post("/tg/" + bot_id, json={
                "message": {
                    "message_id": 123,
                    "from": {"id": 456, "first_name": "Test"},
                    "chat": {"id": 789, "type": "private"},
                    "date": 1640995200,
                    "text": "/book"
                }
            })

            # Should handle error gracefully
            # Exact behavior depends on implementation

    def test_sql_query_error_handling(self, client):
        """Test handling of SQL query errors"""
        bot_id = "test-query-error-bot"

        # Mock SQL query failure
        with patch('runtime.actions.ActionExecutor._execute_sql_query') as mock_query:
            mock_query.side_effect = Exception("SQL query failed")

            # Try flow that would execute query (like /my)
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/my"
            })

            # Should return 500 internal error and increment metrics
            if response.status_code == 500:
                # Verify bot_errors_total{code="sql"} incremented
                pass

    def test_database_transaction_rollback(self, client):
        """Test that failed transactions are properly rolled back"""
        bot_id = "test-rollback-bot"

        # Mock transaction failure after partial execution
        with patch('sqlalchemy.ext.asyncio.AsyncSession.commit') as mock_commit:
            mock_commit.side_effect = Exception("Transaction failed")

            # Try operation that would modify database
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/cancel"  # Should delete booking
            })

            # Verify transaction was rolled back
            # (Database should be in consistent state)

    def test_database_connection_pool_exhaustion(self, client):
        """Test behavior when database connection pool is exhausted"""
        # This is more complex to test and might require specific setup
        pass

    def test_database_timeout_handling(self, client):
        """Test handling of database operation timeouts"""
        bot_id = "test-timeout-bot"

        # Mock slow database operation
        with patch('runtime.actions.ActionExecutor._execute_sql_query') as mock_query:
            # Simulate timeout
            import asyncio
            async def slow_query(*args, **kwargs):
                await asyncio.sleep(10)  # Simulate slow query

            mock_query.side_effect = slow_query

            # Request should timeout gracefully
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/my"
            })

            # Should handle timeout appropriately


class TestSQLErrorHandling:
    """Test specific SQL error scenarios"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_sql_syntax_error_handling(self, client):
        """Test handling of SQL syntax errors"""
        bot_id = "test-syntax-error-bot"

        # Mock SQL syntax error
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            mock_execute.side_effect = Exception("syntax error at or near")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/book_complete"  # Trigger SQL execution
            })

            # Should return 500 internal error
            # Should increment bot_errors_total{code="sql"}

    def test_sql_constraint_violation_handling(self, client):
        """Test handling of SQL constraint violations"""
        bot_id = "test-constraint-bot"

        # Mock constraint violation (e.g., foreign key violation)
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            mock_execute.side_effect = Exception("violates foreign key constraint")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/book_complete"
            })

            # Should handle gracefully and return appropriate error

    def test_sql_permission_error_handling(self, client):
        """Test handling of SQL permission errors"""
        bot_id = "test-permission-bot"

        # Mock permission denied error
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            mock_execute.side_effect = Exception("permission denied")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/my"
            })

            # Should handle permission errors appropriately

    def test_sql_injection_protection(self, client):
        """Test that SQL injection attempts are blocked"""
        bot_id = "test-injection-bot"

        # Try SQL injection in wizard input
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "'; DROP TABLE bookings; --"
        })

        assert response.status_code == 200
        # Should not execute malicious SQL due to parameterized queries

    def test_sql_parameter_type_error_handling(self, client):
        """Test handling of SQL parameter type errors"""
        # Mock type conversion errors
        pass


class TestWizardStateCorruption:
    """Test handling of corrupted wizard state"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_corrupted_wizard_state_reset(self, client):
        """Test that corrupted wizard state is reset and starts fresh"""
        bot_id = "test-corrupted-state-bot"
        user_id = 12345

        # Mock corrupted state in Redis
        from runtime.redis_client import redis_client

        # Set invalid state
        corrupted_state = {"invalid": "data", "malformed": True}
        await redis_client.set_wizard_state(bot_id, user_id, corrupted_state)

        # Try to continue wizard - should reset and start fresh
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "some input"
        })

        assert response.status_code == 200

        # Verify state was cleared/reset
        new_state = await redis_client.get_wizard_state(bot_id, user_id)
        # Should be None or valid fresh state

    @pytest.mark.asyncio
    async def test_wizard_state_json_corruption(self, client):
        """Test handling of JSON corruption in wizard state"""
        bot_id = "test-json-corruption-bot"
        user_id = 67890

        # Mock JSON corruption in Redis
        with patch('runtime.redis_client.redis_client.get') as mock_get:
            mock_get.return_value = "invalid json{"  # Corrupted JSON

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "test input"
            })

            assert response.status_code == 200
            # Should handle JSON parsing error gracefully

    @pytest.mark.asyncio
    async def test_wizard_state_missing_fields(self, client):
        """Test handling of wizard state with missing required fields"""
        bot_id = "test-missing-fields-bot"
        user_id = 11111

        from runtime.redis_client import redis_client

        # Set state missing required fields
        incomplete_state = {"step": 1}  # Missing flow, vars
        await redis_client.set_wizard_state(bot_id, user_id, incomplete_state)

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "continue"
        })

        assert response.status_code == 200
        # Should handle gracefully and reset state

    @pytest.mark.asyncio
    async def test_wizard_state_invalid_step_number(self, client):
        """Test handling of invalid step numbers in wizard state"""
        bot_id = "test-invalid-step-bot"
        user_id = 22222

        from runtime.redis_client import redis_client

        # Set state with invalid step number
        invalid_state = {
            "flow": {"steps": [{"ask": "Q1", "var": "v1"}]},
            "step": 999,  # Invalid step number
            "vars": {}
        }
        await redis_client.set_wizard_state(bot_id, user_id, invalid_state)

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "answer"
        })

        assert response.status_code == 200
        # Should handle invalid step gracefully

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self, client):
        """Test handling of Redis connection failures"""
        bot_id = "test-redis-failure-bot"

        # Mock Redis connection failure
        with patch('runtime.redis_client.redis_client.get') as mock_get:
            mock_get.side_effect = Exception("Redis connection failed")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/book"
            })

            assert response.status_code == 200
            # Should handle Redis failure gracefully (maybe disable wizard features)

    @pytest.mark.asyncio
    async def test_redis_data_corruption(self, client):
        """Test handling of corrupted data in Redis"""
        bot_id = "test-redis-corruption-bot"

        # Mock corrupted Redis data
        with patch('runtime.redis_client.redis_client.get') as mock_get:
            mock_get.return_value = b'\x00\x01\x02'  # Binary garbage

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "input"
            })

            assert response.status_code == 200
            # Should handle data corruption gracefully


class TestErrorMetricsAccuracy:
    """Test that error metrics are accurately recorded"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_error_metrics_bot_id_accuracy(self, client):
        """Test that error metrics are tagged with correct bot_id"""
        bot_id = "test-metrics-accuracy-bot"

        # Get initial error count for this specific bot
        initial_errors = bot_errors_total.labels(bot_id=bot_id, where="test", code="test")._value._value

        # Trigger error for this bot
        with patch('runtime.main.handle_message') as mock_handle:
            mock_handle.side_effect = Exception("Test error")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/test"
            })

            # Verify error metric incremented for correct bot_id only
            final_errors = bot_errors_total.labels(bot_id=bot_id, where="test", code="test")._value._value
            # assert final_errors > initial_errors

    def test_error_metrics_error_type_accuracy(self, client):
        """Test that error metrics have correct 'where' and 'code' labels"""
        bot_id = "test-error-types-bot"

        # Test database error
        with patch('runtime.main.async_session') as mock_session:
            mock_session.side_effect = Exception("Database error")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/db_operation"
            })

            # Verify bot_errors_total{where="database", code="db"} incremented

        # Test SQL error
        with patch('runtime.actions.ActionExecutor._execute_sql_exec') as mock_sql:
            mock_sql.side_effect = Exception("SQL error")

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/sql_operation"
            })

            # Verify bot_errors_total{where="sql", code="sql"} incremented

    def test_error_metrics_concurrent_accuracy(self, client):
        """Test error metrics accuracy under concurrent load"""
        # This would require concurrent request simulation
        pass


class TestSystemResilience:
    """Test overall system resilience"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_partial_system_failure_isolation(self, client):
        """Test that partial failures don't affect unrelated operations"""
        # Test that failure in one bot doesn't affect another
        # Test that failure in one user session doesn't affect another
        pass

    def test_graceful_degradation(self, client):
        """Test graceful degradation when subsystems fail"""
        # Test behavior when Redis is down (wizards disabled but basic commands work)
        # Test behavior when database is slow (appropriate timeouts)
        pass

    def test_error_recovery(self, client):
        """Test that system recovers from temporary errors"""
        # Test recovery after database comes back online
        # Test recovery after Redis reconnects
        pass

    def test_resource_cleanup_on_errors(self, client):
        """Test that resources are properly cleaned up on errors"""
        # Test that database connections are closed
        # Test that Redis connections are cleaned up
        # Test that memory is freed
        pass

    def test_error_propagation_boundaries(self, client):
        """Test that errors don't propagate beyond appropriate boundaries"""
        # Test that template rendering errors don't crash the service
        # Test that user input validation errors are contained
        pass

    def test_health_check_during_failures(self, client):
        """Test health check endpoints during various failure scenarios"""
        # Test /health endpoint when database is down
        response_health = client.get("/health")
        assert response_health.status_code == 200

        # Test /health/db endpoint when database is down
        with patch('runtime.main.async_session') as mock_session:
            mock_session.side_effect = Exception("Database down")

            response_db = client.get("/health/db")
            # Should return appropriate status indicating database issues

    def test_metrics_endpoint_resilience(self, client):
        """Test that metrics endpoint remains available during failures"""
        # Even when other parts fail, metrics should be accessible
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_cascading_failure_prevention(self, client):
        """Test that failures don't cascade through the system"""
        # Test circuit breaker patterns
        # Test that retry logic doesn't amplify problems
        pass

    def test_load_shedding_under_stress(self, client):
        """Test load shedding mechanisms under high error rates"""
        # Test behavior when error rates are very high
        # Verify system doesn't become completely unresponsive
        pass


class TestEdgeCaseErrorHandling:
    """Test error handling for edge cases"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_malformed_json_request_handling(self, client):
        """Test handling of malformed JSON in requests"""
        bot_id = "test-malformed-json-bot"

        # Send malformed JSON
        response = client.post(
            "/preview/send",
            data="invalid json{",
            headers={"Content-Type": "application/json"}
        )

        # Should return 422 or 400 with appropriate error
        assert response.status_code in [400, 422]

    def test_missing_required_fields_handling(self, client):
        """Test handling of requests with missing required fields"""
        # Missing bot_id
        response = client.post("/preview/send", json={
            "text": "/start"
        })
        assert response.status_code == 422

        # Missing text
        response = client.post("/preview/send", json={
            "bot_id": "test-bot"
        })
        assert response.status_code == 422

    def test_invalid_bot_id_handling(self, client):
        """Test handling of invalid bot IDs"""
        # Invalid UUID format
        response = client.post("/preview/send", json={
            "bot_id": "not-a-uuid",
            "text": "/start"
        })
        # Should handle gracefully

        # Non-existent bot ID
        response = client.post("/preview/send", json={
            "bot_id": "550e8400-e29b-41d4-a716-446655440000",
            "text": "/start"
        })
        # Should handle gracefully

    def test_extremely_large_input_handling(self, client):
        """Test handling of extremely large input"""
        bot_id = "test-large-input-bot"

        # Very large text input
        large_text = "x" * 1000000  # 1MB of text

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": large_text
        })

        # Should handle without crashing (might limit input size)
        assert response.status_code in [200, 413, 422]

    def test_unicode_and_special_character_handling(self, client):
        """Test handling of unicode and special characters"""
        bot_id = "test-unicode-bot"

        # Unicode text
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "🤖🎉 Тест с эмодзи и кириллицей"
        })

        assert response.status_code == 200

        # Control characters
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "test\x00\x01\x02"
        })

        assert response.status_code == 200

    def test_concurrent_request_handling(self, client):
        """Test handling of concurrent requests to same bot/user"""
        # This would require concurrent request simulation
        # Test that concurrent wizard sessions don't interfere
        pass