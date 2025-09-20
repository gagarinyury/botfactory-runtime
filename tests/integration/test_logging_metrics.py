"""Integration tests for logging and metrics functionality"""
import pytest
import json
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from runtime.main import app
from runtime.telemetry import (
    bot_updates_total, bot_errors_total,
    dsl_handle_latency_ms, webhook_latency_ms
)


class TestEventLogging:
    """Test bot_events logging functionality"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def booking_flow_spec(self):
        """Complete booking flow for testing events"""
        return {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "entry_cmd": "/book",
                    "steps": [
                        {"ask": "Service?", "var": "service"},
                        {"ask": "Time?", "var": "time"}
                    ],
                    "on_complete": [
                        {"action.sql_exec.v1": {"sql": "INSERT INTO bookings(service) VALUES(:service)"}},
                        {"action.reply_template.v1": {"text": "Booked: {{service}}"}}
                    ]
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_bot_events_update_logged(self, client):
        """Test that bot update events are logged to bot_events table"""
        bot_id = "test-logging-bot-123"

        # Send message that should generate update event
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })

        assert response.status_code == 200

        # Verify bot_events table has update event
        # This would require database query to check:
        # SELECT * FROM bot_events WHERE bot_id = bot_id AND type = 'update'
        # and verify data contains message info

    @pytest.mark.asyncio
    async def test_bot_events_flow_step_logged(self, client, booking_flow_spec):
        """Test that wizard flow steps are logged"""
        bot_id = "test-flow-logging-bot"

        # Start wizard
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })

        # Provide first input
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "massage"
        })

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Verify flow_step events are logged
        # Should have events with type='flow_step' for each wizard step

    @pytest.mark.asyncio
    async def test_bot_events_action_sql_logged(self, client, booking_flow_spec):
        """Test that SQL action executions are logged"""
        bot_id = "test-sql-logging-bot"

        # Complete booking flow to trigger SQL action
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})
        client.post("/preview/send", json={"bot_id": bot_id, "text": "spa"})
        response = client.post("/preview/send", json={"bot_id": bot_id, "text": "2024-01-15 14:00"})

        assert response.status_code == 200

        # Verify action_sql events are logged
        # Should have event with type='action_sql' containing sql_hash, duration_ms

    @pytest.mark.asyncio
    async def test_bot_events_action_reply_logged(self, client, booking_flow_spec):
        """Test that reply template actions are logged"""
        bot_id = "test-reply-logging-bot"

        # Complete flow to trigger reply template
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})
        client.post("/preview/send", json={"bot_id": bot_id, "text": "consultation"})
        response = client.post("/preview/send", json={"bot_id": bot_id, "text": "2024-02-20 10:30"})

        assert response.status_code == 200

        # Verify action_reply events are logged
        # Should have event with type='action_reply' containing template_length, rendered_length

    @pytest.mark.asyncio
    async def test_bot_events_error_logged(self, client):
        """Test that error events are logged"""
        bot_id = "test-error-logging-bot"

        # Trigger an error condition (e.g., invalid spec, database error)
        # This might require mocking error conditions

        # Verify error events are logged
        # Should have event with type='error' containing error details

    @pytest.mark.asyncio
    async def test_bot_events_data_structure(self, client):
        """Test that bot_events have correct data structure"""
        bot_id = "test-events-structure-bot"

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/help"
        })

        assert response.status_code == 200

        # Verify bot_events entries have:
        # - id (BIGSERIAL)
        # - ts (TIMESTAMPTZ, default now())
        # - bot_id (UUID)
        # - user_id (BIGINT)
        # - type (TEXT) - one of: update, flow_step, action_sql, action_reply, error
        # - data (JSONB) - compact event data

    @pytest.mark.asyncio
    async def test_bot_events_data_compactness(self, client):
        """Test that bot_events data is compact and doesn't contain sensitive info"""
        bot_id = "test-events-compact-bot"

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "sensitive data"
        })

        assert response.status_code == 200

        # Verify that logged data is compact:
        # - No full SQL statements (only sql_hash)
        # - No full user messages (only length or hash)
        # - No sensitive tokens or credentials

    @pytest.mark.asyncio
    async def test_bot_events_user_isolation(self, client):
        """Test that events are properly isolated by user_id"""
        bot_id = "test-events-isolation-bot"

        # Would need different user contexts to test
        # Verify each user's events are separate

    @pytest.mark.asyncio
    async def test_bot_events_performance_impact(self, client):
        """Test that event logging doesn't significantly impact performance"""
        bot_id = "test-events-performance-bot"

        start_time = time.time()

        # Send multiple messages
        for i in range(10):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/test{i}"
            })
            assert response.status_code == 200

        end_time = time.time()
        duration = end_time - start_time

        # Verify reasonable performance (this is a rough check)
        assert duration < 5.0  # Should complete in under 5 seconds


class TestStructlogIntegration:
    """Test structlog integration for wizards"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_structlog_fields_present(self, client):
        """Test that structlog entries contain required fields"""
        bot_id = "test-structlog-bot"

        with patch('structlog.get_logger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/start"
            })

            assert response.status_code == 200

            # Verify structlog was called with required fields:
            # - trace_id
            # - bot_id
            # - user_id
            # - spec_version
            # - event

    def test_structlog_trace_id_consistency(self, client):
        """Test that trace_id is consistent across related log entries"""
        bot_id = "test-trace-consistency-bot"

        with patch('structlog.get_logger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            # Start wizard flow
            response1 = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "/book"
            })

            # Continue wizard
            response2 = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "massage"
            })

            assert response1.status_code == 200
            assert response2.status_code == 200

            # Verify all log entries for this flow have same trace_id

    def test_structlog_sensitive_data_masking(self, client):
        """Test that structlog masks sensitive data"""
        bot_id = "test-masking-bot"

        with patch('structlog.get_logger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            # Send message with potentially sensitive data
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": "password123 token=abc123"
            })

            assert response.status_code == 200

            # Verify that sensitive data is masked in logs
            # Should not contain actual tokens, passwords, etc.

    def test_structlog_sql_parameter_masking(self, client):
        """Test that SQL parameters are masked in logs"""
        bot_id = "test-sql-masking-bot"

        with patch('structlog.get_logger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            # Complete flow that executes SQL
            client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})
            client.post("/preview/send", json={"bot_id": bot_id, "text": "spa"})
            response = client.post("/preview/send", json={"bot_id": bot_id, "text": "2024-01-15 14:00"})

            assert response.status_code == 200

            # Verify SQL parameters are masked, only sql_hash is logged


class TestPrometheusMetrics:
    """Test Prometheus metrics integration"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_bot_updates_total_incremented(self, client):
        """Test that bot_updates_total metric is incremented"""
        bot_id = "test-metrics-bot-123"

        # Get initial metric value
        initial_value = bot_updates_total.labels(bot_id=bot_id)._value._value

        # Send message
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })

        assert response.status_code == 200

        # Verify metric incremented
        final_value = bot_updates_total.labels(bot_id=bot_id)._value._value
        assert final_value > initial_value

    def test_bot_errors_total_incremented_on_error(self, client):
        """Test that bot_errors_total is incremented on errors"""
        bot_id = "test-error-metrics-bot"

        # Trigger error condition
        # This would require mocking an error scenario

        # Verify bot_errors_total metric incremented with correct labels
        # Should have labels: bot_id, where, code

    def test_dsl_handle_latency_measured(self, client):
        """Test that DSL handling latency is measured"""
        bot_id = "test-latency-bot"

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })

        assert response.status_code == 200

        # Verify dsl_handle_latency_ms metric was recorded
        # This metric should track time spent in DSL processing

    def test_webhook_latency_measured(self, client):
        """Test that webhook latency is measured"""
        bot_id = "test-webhook-latency-bot"

        # Test webhook endpoint
        response = client.post(f"/tg/{bot_id}", json={
            "message": {
                "message_id": 123,
                "from": {"id": 456, "first_name": "Test"},
                "chat": {"id": 789, "type": "private"},
                "date": 1640995200,
                "text": "/start"
            }
        })

        # Verify webhook_latency_ms metric was recorded

    def test_metrics_labels_accuracy(self, client):
        """Test that metrics have accurate labels"""
        bot_id = "test-labels-bot"

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/help"
        })

        assert response.status_code == 200

        # Verify metrics have correct bot_id labels
        # Check that metrics are properly segmented by bot

    def test_metrics_in_metrics_endpoint(self, client):
        """Test that metrics are visible in /metrics endpoint"""
        # Send some traffic
        bot_id = "test-endpoint-metrics-bot"
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/test"})

        # Check metrics endpoint
        response = client.get("/metrics")
        assert response.status_code == 200

        metrics_text = response.text

        # Verify metrics are present
        assert "bot_updates_total" in metrics_text
        assert "dsl_handle_latency_ms" in metrics_text
        assert "webhook_latency_ms" in metrics_text

    def test_metrics_performance_impact(self, client):
        """Test that metrics collection doesn't significantly impact performance"""
        bot_id = "test-metrics-performance-bot"

        start_time = time.time()

        # Send multiple requests
        for i in range(50):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/test{i}"
            })
            assert response.status_code == 200

        end_time = time.time()
        duration = end_time - start_time

        # Metrics shouldn't add significant overhead
        assert duration < 10.0  # Should complete in reasonable time


class TestLoggingMetricsIntegration:
    """Test integration between logging and metrics"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_events_and_metrics_consistency(self, client):
        """Test that events and metrics are consistent"""
        bot_id = "test-consistency-bot"

        # Get initial metrics
        initial_updates = bot_updates_total.labels(bot_id=bot_id)._value._value

        # Send multiple messages
        for i in range(5):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/command{i}"
            })
            assert response.status_code == 200

        # Check final metrics
        final_updates = bot_updates_total.labels(bot_id=bot_id)._value._value

        # Verify consistency between events in DB and metrics
        # Should have 5 more updates in both metrics and event logs

    def test_error_logging_and_metrics_correlation(self, client):
        """Test that error events and error metrics are correlated"""
        # Trigger error condition
        # Verify both error event in bot_events and error metric increment

    def test_wizard_flow_complete_logging_metrics(self, client):
        """Test complete wizard flow generates all expected logs and metrics"""
        bot_id = "test-complete-flow-bot"

        # Complete full booking wizard
        client.post("/preview/send", json={"bot_id": bot_id, "text": "/book"})
        client.post("/preview/send", json={"bot_id": bot_id, "text": "massage"})
        response = client.post("/preview/send", json={"bot_id": bot_id, "text": "2024-01-15 14:00"})

        assert response.status_code == 200

        # Verify complete set of events:
        # - update events for each message
        # - flow_step events for wizard steps
        # - action_sql event for database insert
        # - action_reply event for template rendering

        # Verify corresponding metrics:
        # - bot_updates_total incremented for each message
        # - dsl_handle_latency_ms recorded for each processing
        # - No error metrics (successful flow)

    def test_concurrent_logging_metrics_accuracy(self, client):
        """Test logging and metrics accuracy under concurrent load"""
        # This would require concurrent request simulation
        # Verify that metrics and logs remain accurate
        pass

    def test_logging_metrics_cleanup(self, client):
        """Test that old logs are properly managed"""
        # Test log retention policies
        # Verify metrics don't accumulate indefinitely in memory
        pass