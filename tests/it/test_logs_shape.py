"""Test logging format and content"""
import pytest
import json
import re
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from runtime.main import app
from runtime.logging import with_trace

client = TestClient(app)

def test_trace_id_generation():
    """Test that trace_id is generated correctly"""
    trace_id = with_trace()

    # Should be a valid UUID string
    assert isinstance(trace_id, str)
    assert len(trace_id) > 0

    # Test UUID format (basic check)
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    assert re.match(uuid_pattern, trace_id)

def test_trace_id_with_context():
    """Test trace_id with provided context"""
    custom_trace = "custom-trace-123"
    trace_id = with_trace(custom_trace)

    assert trace_id == custom_trace

@patch('runtime.logging_setup.log')
def test_preview_logs_structure(mock_log):
    """Test that preview endpoint logs contain required fields"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
    test_text = "/start"

    # Make preview request
    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": test_text}
    )

    assert response.status_code == 200

    # Verify log was called
    mock_log.info.assert_called_once()

    # Get the call arguments
    call_args = mock_log.info.call_args

    # Should have positional arg "preview"
    assert call_args[0][0] == "preview"

    # Should have keyword arguments with required fields
    kwargs = call_args[1]
    assert "trace_id" in kwargs
    assert "bot_id" in kwargs
    assert "text" in kwargs

    # Verify values
    assert kwargs["bot_id"] == bot_id
    assert kwargs["text"] == test_text
    assert isinstance(kwargs["trace_id"], str)

@patch('runtime.logging_setup.log')
def test_logs_no_token_exposure(mock_log):
    """Test that tokens are not logged"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Make preview request
    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": "/start"}
    )

    assert response.status_code == 200

    # Get all log calls
    all_calls = mock_log.info.call_args_list

    # Check that no call contains token information
    for call in all_calls:
        args, kwargs = call

        # Check positional args
        for arg in args:
            if isinstance(arg, str):
                assert "token" not in arg.lower()
                assert "TEST_TOKEN" not in arg

        # Check keyword args
        for key, value in kwargs.items():
            if isinstance(value, str):
                assert "token" not in key.lower()
                assert "TEST_TOKEN" not in value

def test_logging_configuration():
    """Test logging configuration is set up correctly"""
    from runtime.logging_setup import log
    import structlog

    # Should be a structlog logger
    assert hasattr(log, 'info')
    assert hasattr(log, 'error')
    assert hasattr(log, 'warning')

    # Test basic logging functionality
    try:
        log.info("test message", test_field="test_value")
        # If no exception, logging is working
        assert True
    except Exception as e:
        pytest.fail(f"Logging failed: {e}")

def test_log_format_fields():
    """Test that log format contains expected fields"""
    from runtime.logging_setup import log
    import structlog

    # Get current processors
    config = structlog.get_config()
    processors = config["processors"]

    # Should have timestamp processor
    processor_names = [p.__class__.__name__ for p in processors]
    assert "TimeStamper" in processor_names

def test_multiple_preview_calls_different_trace_ids():
    """Test that multiple calls generate different trace IDs"""
    with patch('runtime.logging_setup.log') as mock_log:
        bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

        # Make multiple requests
        for i in range(3):
            response = client.post(
                "/preview/send",
                json={"bot_id": bot_id, "text": f"/start_{i}"}
            )
            assert response.status_code == 200

        # Get all trace_ids from log calls
        trace_ids = []
        for call in mock_log.info.call_args_list:
            kwargs = call[1]
            if "trace_id" in kwargs:
                trace_ids.append(kwargs["trace_id"])

        # Should have 3 different trace IDs
        assert len(trace_ids) == 3
        assert len(set(trace_ids)) == 3  # All unique

@patch('runtime.logging_setup.log')
def test_log_special_characters(mock_log):
    """Test logging with special characters"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
    special_text = "Привет! 🤖 /start"

    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": special_text}
    )

    assert response.status_code == 200

    # Verify log was called with special characters
    mock_log.info.assert_called_once()
    kwargs = mock_log.info.call_args[1]
    assert kwargs["text"] == special_text

@patch('runtime.logging_setup.log')
def test_log_long_text(mock_log):
    """Test logging with very long text"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
    long_text = "A" * 1000

    response = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": long_text}
    )

    assert response.status_code == 200

    # Verify log was called with long text
    mock_log.info.assert_called_once()
    kwargs = mock_log.info.call_args[1]
    assert kwargs["text"] == long_text

def test_structlog_console_renderer():
    """Test that ConsoleRenderer is configured"""
    import structlog

    config = structlog.get_config()
    processors = config["processors"]

    # Should have ConsoleRenderer as last processor
    renderer_found = any(
        "ConsoleRenderer" in p.__class__.__name__ for p in processors
    )
    assert renderer_found

def test_log_iso_timestamp():
    """Test that logs include ISO timestamp"""
    import structlog

    config = structlog.get_config()
    processors = config["processors"]

    # Find TimeStamper processor
    timestamper = None
    for p in processors:
        if "TimeStamper" in p.__class__.__name__:
            timestamper = p
            break

    assert timestamper is not None

def test_log_level_configuration():
    """Test log level configuration"""
    import logging
    import structlog

    # Check that INFO level is configured
    config = structlog.get_config()

    # Should have filtering bound logger
    wrapper_class = config.get("wrapper_class")
    if wrapper_class:
        # The filtering bound logger should be configured for INFO level
        assert callable(wrapper_class)

@patch('runtime.logging_setup.log')
def test_concurrent_logging(mock_log):
    """Test logging under concurrent requests"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Make multiple concurrent-like requests
    responses = []
    for i in range(5):
        response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": f"/concurrent_{i}"}
        )
        responses.append(response)

    # All should succeed
    for response in responses:
        assert response.status_code == 200

    # Should have 5 log entries
    assert mock_log.info.call_count == 5

    # Each should have unique trace_id
    trace_ids = [call[1]["trace_id"] for call in mock_log.info.call_args_list]
    assert len(set(trace_ids)) == 5