"""Test bot reload functionality"""
import pytest
from fastapi.testclient import TestClient
from runtime.main import app, bot_cache

client = TestClient(app)

def test_reload_endpoint_basic():
    """Test basic reload endpoint functionality"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # First, add something to cache to test invalidation
    bot_cache[bot_id] = {"cached": "data"}

    # Call reload endpoint
    response = client.post(f"/bots/{bot_id}/reload")

    assert response.status_code == 200
    data = response.json()
    assert data["bot_id"] == bot_id
    assert data["cache_invalidated"] is True
    assert "message" in data

    # Verify cache was cleared
    assert bot_id not in bot_cache

def test_reload_non_cached_bot():
    """Test reload endpoint for bot not in cache"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Ensure bot is not in cache
    if bot_id in bot_cache:
        del bot_cache[bot_id]

    response = client.post(f"/bots/{bot_id}/reload")

    assert response.status_code == 200
    data = response.json()
    assert data["bot_id"] == bot_id
    assert data["cache_invalidated"] is True

def test_reload_invalid_bot_id():
    """Test reload endpoint with invalid bot ID format"""
    invalid_bot_id = "invalid-uuid"

    response = client.post(f"/bots/{invalid_bot_id}/reload")

    # Should still work - endpoint doesn't validate UUID format
    assert response.status_code == 200
    data = response.json()
    assert data["bot_id"] == invalid_bot_id

def test_multiple_reloads():
    """Test multiple consecutive reloads"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Add to cache
    bot_cache[bot_id] = {"test": "data"}

    # First reload
    response1 = client.post(f"/bots/{bot_id}/reload")
    assert response1.status_code == 200

    # Second reload (cache already empty)
    response2 = client.post(f"/bots/{bot_id}/reload")
    assert response2.status_code == 200

    # Third reload
    response3 = client.post(f"/bots/{bot_id}/reload")
    assert response3.status_code == 200

    # All should succeed
    for response in [response1, response2, response3]:
        data = response.json()
        assert data["cache_invalidated"] is True

@pytest.mark.asyncio
async def test_reload_affects_preview():
    """Test that reload affects subsequent preview calls"""
    # This test would require mocking database updates
    # For now, test basic integration
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Get initial response
    response1 = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": "/start"}
    )
    initial_reply = response1.json()["bot_reply"]

    # Reload bot
    reload_response = client.post(f"/bots/{bot_id}/reload")
    assert reload_response.status_code == 200

    # Get response after reload
    response2 = client.post(
        "/preview/send",
        json={"bot_id": bot_id, "text": "/start"}
    )
    after_reload_reply = response2.json()["bot_reply"]

    # Both should be successful
    assert response1.status_code == 200
    assert response2.status_code == 200

    # Note: Without actual database changes, replies will be the same
    # In a full test, we would update the database between calls

def test_reload_concurrent_access():
    """Test reload under concurrent cache access"""
    bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Simulate concurrent access by multiple operations
    bot_cache[bot_id] = {"concurrent": "test"}

    # Multiple reload calls
    responses = []
    for i in range(5):
        response = client.post(f"/bots/{bot_id}/reload")
        responses.append(response)

    # All should succeed
    for response in responses:
        assert response.status_code == 200
        assert response.json()["cache_invalidated"] is True

    # Cache should be empty
    assert bot_id not in bot_cache

def test_reload_different_bots():
    """Test reload with different bot IDs"""
    bot_id1 = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
    bot_id2 = "11111111-1111-1111-1111-111111111111"

    # Add both to cache
    bot_cache[bot_id1] = {"bot1": "data"}
    bot_cache[bot_id2] = {"bot2": "data"}

    # Reload only first bot
    response1 = client.post(f"/bots/{bot_id1}/reload")
    assert response1.status_code == 200

    # First bot should be removed from cache, second should remain
    assert bot_id1 not in bot_cache
    assert bot_id2 in bot_cache

    # Reload second bot
    response2 = client.post(f"/bots/{bot_id2}/reload")
    assert response2.status_code == 200

    # Now both should be removed
    assert bot_id1 not in bot_cache
    assert bot_id2 not in bot_cache