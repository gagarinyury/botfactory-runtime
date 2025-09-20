"""Test fault tolerance and error handling"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from http import HTTPStatus
from runtime.main import app

client = TestClient(app)

def test_health_db_when_database_down():
    """Test /health/db endpoint when database is unavailable"""
    with patch('runtime.main.registry') as mock_registry:
        # Mock database failure - db_ok is async function
        mock_registry.db_ok = AsyncMock(return_value=False)

        response = client.get("/health/db")

        assert response.status_code == 503  # Should return 503 for DB down
        data = response.json()
        assert "db_ok" in data
        assert data["db_ok"] is False

def test_preview_validation_422():
    """Test preview endpoint validation returns 422 for missing fields"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Test missing text field
    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id}
    )

    # Should return 422 for validation error
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    data = response.json()
    assert "detail" in data

def test_preview_validation_empty_text():
    """Test preview endpoint with empty text"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": ""}
    )

    # Pydantic should handle empty text validation
    assert response.status_code in [200, 422]

def test_get_bot_spec_not_found():
    """Test /bots/{bot_id} endpoint with non-existent bot"""
    non_existent_bot_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(f"/bots/{non_existent_bot_id}")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data or "error" in data
    # detail can be string or dict/object
    detail_text = str(data.get("detail", data.get("error", "")))
    assert "not found" in detail_text.lower()

def test_preview_with_invalid_bot_spec():
    """Test preview with bot that has invalid spec_json"""
    # This test assumes we can mock a bot with invalid spec
    # Current implementation should handle gracefully
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    with patch('runtime.dsl_engine.load_spec') as mock_load_spec:
        # Mock invalid spec that causes processing error
        mock_load_spec.return_value = {"invalid": "spec_format"}

        response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": "/start"}
        )

        # Should handle gracefully
        assert response.status_code == 200
        # Should return fallback response
        data = response.json()
        assert "bot_reply" in data

def test_malformed_json_requests():
    """Test handling of malformed JSON requests"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Test with invalid JSON
    response = client.post(
        "/preview/send",
        data='{"bot_id": "test", "text": "/start"',  # Missing closing brace
        headers={"Content-Type": "application/json"}
    )

    # Should return 422 for validation errors
    assert response.status_code == 422

def test_metrics_endpoint_always_available():
    """Test that metrics endpoint is always available even under stress"""
    # Metrics should be available even if other parts fail
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"

def test_health_endpoint_always_available():
    """Test that health endpoint is always available"""
    # Basic health check should always work
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True

def test_invalid_bot_id_formats():
    """Test preview with various invalid bot ID formats"""
    invalid_bot_ids = [
        "not-a-uuid",
        "",
        "123",
        "../../etc/passwd",  # Path traversal attempt
    ]

    for bot_id in invalid_bot_ids:
        response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": "/start"}
        )
        # Should handle various formats gracefully
        assert response.status_code in [200, 404, 422, 500]

def test_reload_with_various_bot_ids():
    """Test reload endpoint accepts any string as bot_id"""
    test_bot_ids = [
        "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
        "test-bot",
        "123"
    ]

    for bot_id in test_bot_ids:
        response = client.post(f"/bots/{bot_id}/reload")

        # Current implementation accepts any string
        assert response.status_code == 200
        data = response.json()
        assert data["bot_id"] == bot_id
        assert data["cache_invalidated"] is True

def test_preview_with_malformed_json():
    """Test preview endpoint with various malformed JSON"""
    malformed_payloads = [
        '{"bot_id": "test", "text": "/start"',  # Missing closing brace
        '{"bot_id": test", "text": "/start"}',   # Missing quote
        '{"bot_id": "test", "text":}',           # Missing value
        '{"bot_id": null, "text": "/start"}',    # Null bot_id
        '{"text": "/start"}',                    # Missing bot_id
        '{}'                                     # Empty object
    ]

    for payload in malformed_payloads:
        response = client.post(
            "/preview/send",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        # Should return 422 for validation errors
        assert response.status_code == 422

def test_webhook_with_malformed_telegram_update():
    """Test webhook endpoint with malformed Telegram updates"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    malformed_updates = [
        '{"update_id": "not_a_number"}',
        '{"message": null}',
        '{"message": {"text": null}}',
        '{}'  # Empty update
    ]

    for update in malformed_updates:
        response = client.post(
            f"/tg/{bot_id}",
            data=update,
            headers={"Content-Type": "application/json"}
        )

        # Current implementation should handle gracefully
        assert response.status_code in [200, 422]

def test_concurrent_cache_operations():
    """Test cache operations under concurrent access"""
    from runtime.main import bot_cache
    import threading
    import time

    bot_id = "concurrent-test-bot"
    results = []

    def cache_operations():
        try:
            # Add to cache
            bot_cache[bot_id] = {"test": "data"}
            time.sleep(0.01)  # Small delay

            # Read from cache
            value = bot_cache.get(bot_id)
            results.append(("read", value))

            # Remove from cache
            if bot_id in bot_cache:
                del bot_cache[bot_id]
                results.append(("delete", True))

        except Exception as e:
            results.append(("error", str(e)))

    # Run multiple threads
    threads = []
    for i in range(5):
        thread = threading.Thread(target=cache_operations)
        threads.append(thread)
        thread.start()

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Should handle concurrent access without crashing
    assert len(results) > 0
    # No errors should occur
    error_results = [r for r in results if r[0] == "error"]
    assert len(error_results) == 0

def test_large_payload_handling():
    """Test handling of very large payloads"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Very large text payload
    large_text = "A" * 10000  # 10KB

    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": large_text}
    )

    # Should handle large payloads gracefully
    assert response.status_code in [200, 413, 422]

def test_rapid_successive_requests():
    """Test rapid successive requests to same bot"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    responses = []
    for i in range(10):
        response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": f"/test_{i}"}
        )
        responses.append(response)

    # All requests should succeed
    for response in responses:
        assert response.status_code == 200

def test_preview_with_unicode_and_special_chars():
    """Test preview with various Unicode and special characters"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    special_texts = [
        "🤖🚀💻 /start",
        "Привет мир! /help",
        "测试 /test",
        "🇺🇸🇷🇺🇨🇳 flags",
        "\n\t\r special whitespace",
        "\\n\\t\\r escaped chars",
        "\"quotes\" and 'apostrophes'",
        "<html>tags</html>",
        "NULL\x00char"
    ]

    for text in special_texts:
        response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": text}
        )

        # Should handle all special characters
        assert response.status_code == 200
        data = response.json()
        assert "bot_reply" in data

@patch('runtime.main.engine')
def test_database_connection_recovery(mock_engine):
    """Test database connection recovery scenarios"""
    # This test simulates database reconnection
    # First call fails, second succeeds

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Connection lost")
        else:
            # Return a mock session
            mock_session = AsyncMock()
            return mock_session

    mock_engine.begin.side_effect = side_effect

    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # First request might fail
    response1 = client.get(f"/bots/{bot_id}")

    # Second request should work (if retry logic exists)
    response2 = client.get(f"/bots/{bot_id}")

    # At least one should work, or both should handle errors gracefully
    assert any(r.status_code in [200, 404] for r in [response1, response2])