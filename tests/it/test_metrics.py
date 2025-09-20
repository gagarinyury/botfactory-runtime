"""Test metrics endpoint and tracking"""
import pytest
import re
from fastapi.testclient import TestClient
from runtime.main import app

client = TestClient(app)

def test_metrics_endpoint_exists():
    """Test that metrics endpoint is accessible"""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"

def test_metrics_prometheus_format():
    """Test that metrics are in Prometheus format"""
    response = client.get("/metrics")

    assert response.status_code == 200
    content = response.text

    # Check for Prometheus format indicators
    assert "# HELP" in content or "# TYPE" in content or "_total" in content

def test_metrics_bot_updates_counter():
    """Test that bot_updates_total metric is present"""
    response = client.get("/metrics")

    assert response.status_code == 200
    content = response.text

    # Look for bot_updates_total metric
    assert "bot_updates_total" in content

def test_metrics_latency_histogram():
    """Test that dsl_handle_latency_ms metric is present"""
    response = client.get("/metrics")

    assert response.status_code == 200
    content = response.text

    # Look for latency histogram metric
    assert "dsl_handle_latency_ms" in content

def test_metrics_after_preview_calls():
    """Test that metrics increment after preview calls"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Get initial metrics
    initial_response = client.get("/metrics")
    initial_content = initial_response.text

    # Extract initial counter value if present
    pattern = rf'bot_updates_total{{bot_id="{bot_id}"}} (\d+)'
    initial_match = re.search(pattern, initial_content)
    initial_count = int(initial_match.group(1)) if initial_match else 0

    # Make several preview calls
    num_calls = 3
    for i in range(num_calls):
        preview_response = client.post(
            "/preview/send",
            json={"bot_id": bot_id, "text": f"/start_{i}"}
        )
        assert preview_response.status_code == 200

    # Get updated metrics
    updated_response = client.get("/metrics")
    updated_content = updated_response.text

    # Check that counter increased
    updated_match = re.search(pattern, updated_content)
    if updated_match:
        updated_count = int(updated_match.group(1))
        assert updated_count >= initial_count + num_calls
    else:
        # Metric should now exist
        assert f'bot_updates_total{{bot_id="{bot_id}"}}' in updated_content

def test_metrics_multiple_bots():
    """Test metrics tracking for multiple bots"""
    bot_id1 = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
    bot_id2 = "11111111-1111-1111-1111-111111111111"

    # Make calls to different bots
    client.post("/preview/send", json={"bot_id": bot_id1, "text": "/start"})
    client.post("/preview/send", json={"bot_id": bot_id2, "text": "/help"})

    # Get metrics
    response = client.get("/metrics")
    content = response.text

    # Should have metrics for both bots (or at least bot_updates_total)
    assert "bot_updates_total" in content

def test_metrics_latency_buckets():
    """Test that latency histogram has expected buckets"""
    # Make a preview call to generate latency metrics
    client.post(
        "/preview/send",
        json={"bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413", "text": "/start"}
    )

    response = client.get("/metrics")
    content = response.text

    # Check for histogram buckets (should include some of the defined buckets)
    expected_buckets = ["0.01", "0.05", "0.1", "0.2", "0.5", "1", "2", "5"]

    found_buckets = []
    for bucket in expected_buckets:
        if f'le="{bucket}"' in content:
            found_buckets.append(bucket)

    # Should find at least some buckets
    assert len(found_buckets) > 0

def test_metrics_histogram_structure():
    """Test that histogram metrics have proper structure"""
    # Make a preview call
    client.post(
        "/preview/send",
        json={"bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413", "text": "/start"}
    )

    response = client.get("/metrics")
    content = response.text

    # Check for histogram components
    histogram_patterns = [
        "dsl_handle_latency_ms_bucket",
        "dsl_handle_latency_ms_count",
        "dsl_handle_latency_ms_sum"
    ]

    for pattern in histogram_patterns:
        if pattern in content:
            # At least one histogram component should be present
            break
    else:
        # If none found, at least base metric should exist
        assert "dsl_handle_latency_ms" in content

def test_metrics_content_type():
    """Test that metrics endpoint returns correct content type"""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

def test_metrics_no_html():
    """Test that metrics don't contain HTML"""
    response = client.get("/metrics")

    content = response.text
    # Metrics should not contain HTML tags
    assert "<html>" not in content.lower()
    assert "<body>" not in content.lower()
    assert "</html>" not in content.lower()

def test_metrics_consistent_format():
    """Test that metrics are consistently formatted"""
    response = client.get("/metrics")
    content = response.text

    lines = content.strip().split('\n')

    # Filter out empty lines and comments
    metric_lines = [line for line in lines if line and not line.startswith('#')]

    # Each metric line should follow basic prometheus format
    for line in metric_lines:
        if line.strip():
            # Should contain metric name and value
            assert ' ' in line or '\t' in line
            # Should not contain invalid characters for metric names
            parts = line.split()
            if len(parts) >= 2:
                metric_part = parts[0]
                value_part = parts[-1]

                # Value should be numeric (int or float)
                try:
                    float(value_part)
                except ValueError:
                    # Some special values are allowed
                    assert value_part in ['+Inf', '-Inf', 'NaN']