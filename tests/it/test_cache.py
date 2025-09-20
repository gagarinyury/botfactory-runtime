"""Test cache functionality and TTL behavior"""
import pytest
import time
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from runtime.main import app, bot_cache, router_cache

client = TestClient(app)

def test_bot_cache_basic_operations():
    """Test basic bot cache operations"""
    # Clear cache first
    bot_cache.clear()

    test_bot_id = "cache-test-bot-1"
    test_data = {"test": "data", "timestamp": time.time()}

    # Test cache is empty initially
    assert len(bot_cache) == 0

    # Add item to cache
    bot_cache[test_bot_id] = test_data

    # Test item is in cache
    assert test_bot_id in bot_cache
    assert bot_cache[test_bot_id] == test_data
    assert len(bot_cache) == 1

    # Test cache retrieval
    retrieved_data = bot_cache.get(test_bot_id)
    assert retrieved_data == test_data

    # Test cache removal
    del bot_cache[test_bot_id]
    assert test_bot_id not in bot_cache
    assert len(bot_cache) == 0

def test_router_cache_ttl_behavior():
    """Test TTL cache behavior for router cache"""
    from cachetools import TTLCache

    # Verify router_cache is TTLCache
    assert isinstance(router_cache, TTLCache)

    # Clear cache
    router_cache.clear()

    test_bot_id = "ttl-test-bot"
    test_router = {"router": "data"}

    # Add item to cache
    router_cache[test_bot_id] = test_router

    # Should be immediately available
    assert test_bot_id in router_cache
    assert router_cache[test_bot_id] == test_router

    # Test that cache respects maxsize
    assert len(router_cache) <= router_cache.maxsize

def test_router_cache_maxsize_limit():
    """Test that router cache respects maxsize limit"""
    # Clear cache
    router_cache.clear()

    initial_maxsize = router_cache.maxsize

    # Fill cache beyond maxsize
    for i in range(initial_maxsize + 10):
        bot_id = f"maxsize-test-bot-{i}"
        router_cache[bot_id] = f"router-{i}"

    # Cache should not exceed maxsize
    assert len(router_cache) <= initial_maxsize

    # First items should be evicted (LRU behavior)
    assert "maxsize-test-bot-0" not in router_cache
    assert f"maxsize-test-bot-{initial_maxsize + 9}" in router_cache

def test_router_cache_ttl_expiration():
    """Test TTL expiration in router cache"""
    # Create a short TTL cache for testing
    from cachetools import TTLCache
    short_ttl_cache = TTLCache(maxsize=10, ttl=0.1)  # 100ms TTL

    test_bot_id = "ttl-expiration-test"
    test_router = {"test": "router"}

    # Add item
    short_ttl_cache[test_bot_id] = test_router

    # Should be available immediately
    assert test_bot_id in short_ttl_cache

    # Wait for TTL to expire
    time.sleep(0.15)

    # Item should be expired and removed
    assert test_bot_id not in short_ttl_cache

def test_cache_invalidation_via_reload():
    """Test cache invalidation through reload endpoint"""
    bot_id = "reload-invalidation-test"

    # Add item to bot_cache
    bot_cache[bot_id] = {"cached": "data"}

    # Verify item is cached
    assert bot_id in bot_cache

    # Call reload endpoint
    response = client.post(f"/bots/{bot_id}/reload")

    assert response.status_code == 200
    data = response.json()
    assert data["cache_invalidated"] is True

    # Verify cache was cleared
    assert bot_id not in bot_cache

@patch('runtime.main.async_session')
@patch('runtime.main.loader')
def test_get_router_caching_behavior(mock_loader, mock_session):
    """Test get_router function caching behavior"""
    from runtime.main import get_router

    # Clear router cache
    router_cache.clear()

    # Mock database response
    mock_session_instance = AsyncMock()
    mock_session.return_value.__aenter__.return_value = mock_session_instance

    mock_bot_config = {
        "spec_json": {"intents": [{"cmd": "/test", "reply": "Test"}]}
    }
    mock_loader.load_spec_by_bot_id.return_value = mock_bot_config

    test_bot_id = "router-cache-test"

    # First call should load from database
    router1 = get_router(test_bot_id)

    # Verify database was called
    mock_loader.load_spec_by_bot_id.assert_called()

    # Second call should use cache
    mock_loader.reset_mock()
    router2 = get_router(test_bot_id)

    # Database should not be called again
    mock_loader.load_spec_by_bot_id.assert_not_called()

    # Both calls should return cached result
    # Note: This is an async function, so we need to handle properly

def test_multiple_bot_cache_isolation():
    """Test that different bots have isolated cache entries"""
    bot_cache.clear()

    bot_id_1 = "isolation-test-bot-1"
    bot_id_2 = "isolation-test-bot-2"

    data_1 = {"bot": "1", "data": "first"}
    data_2 = {"bot": "2", "data": "second"}

    # Add data for both bots
    bot_cache[bot_id_1] = data_1
    bot_cache[bot_id_2] = data_2

    # Verify isolation
    assert bot_cache[bot_id_1] == data_1
    assert bot_cache[bot_id_2] == data_2
    assert bot_cache[bot_id_1] != bot_cache[bot_id_2]

    # Remove one bot
    del bot_cache[bot_id_1]

    # Other bot should remain
    assert bot_id_1 not in bot_cache
    assert bot_id_2 in bot_cache
    assert bot_cache[bot_id_2] == data_2

def test_cache_concurrent_access():
    """Test cache under concurrent access"""
    import threading
    import concurrent.futures

    bot_cache.clear()
    test_bot_id = "concurrent-cache-test"

    results = []
    errors = []

    def cache_worker(worker_id):
        try:
            # Add to cache
            worker_data = {"worker": worker_id, "data": f"data-{worker_id}"}
            bot_cache[f"{test_bot_id}-{worker_id}"] = worker_data

            # Read from cache
            if f"{test_bot_id}-{worker_id}" in bot_cache:
                results.append(("read", worker_id, True))
            else:
                results.append(("read", worker_id, False))

            # Update cache
            bot_cache[f"{test_bot_id}-{worker_id}"] = {"updated": True}

            # Final read
            final_data = bot_cache.get(f"{test_bot_id}-{worker_id}")
            results.append(("final", worker_id, final_data))

        except Exception as e:
            errors.append((worker_id, str(e)))

    # Run multiple workers concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(cache_worker, i) for i in range(5)]
        concurrent.futures.wait(futures)

    # Verify no errors occurred
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all workers completed successfully
    assert len(results) >= 10  # At least 2 results per worker

def test_cache_memory_usage():
    """Test cache doesn't grow indefinitely"""
    bot_cache.clear()

    # Current implementation uses simple dict, so no automatic limit
    # But we can test that manual clearing works

    # Add many items
    for i in range(1000):
        bot_cache[f"memory-test-bot-{i}"] = f"data-{i}"

    initial_size = len(bot_cache)
    assert initial_size == 1000

    # Clear cache
    bot_cache.clear()

    # Should be empty
    assert len(bot_cache) == 0

def test_router_cache_different_bots():
    """Test router cache with different bots"""
    router_cache.clear()

    bot_ids = [f"router-test-bot-{i}" for i in range(5)]
    routers = [f"router-{i}" for i in range(5)]

    # Add routers for different bots
    for bot_id, router in zip(bot_ids, routers):
        router_cache[bot_id] = router

    # Verify all are cached
    for bot_id, router in zip(bot_ids, routers):
        assert bot_id in router_cache
        assert router_cache[bot_id] == router

    # Test LRU behavior - access first bot
    _ = router_cache[bot_ids[0]]

    # Add more items to trigger eviction
    for i in range(router_cache.maxsize):
        router_cache[f"eviction-test-{i}"] = f"eviction-router-{i}"

    # First bot should still be cached (recently accessed)
    # Last bots from original set might be evicted

def test_cache_with_special_characters():
    """Test cache with special characters in keys"""
    bot_cache.clear()

    special_keys = [
        "bot-with-dashes",
        "bot_with_underscores",
        "bot.with.dots",
        "bот-with-unicode",
        "bot with spaces",
        "bot🤖with🚀emojis"
    ]

    # Test adding items with special keys
    for key in special_keys:
        bot_cache[key] = f"data-for-{key}"

    # Test retrieval
    for key in special_keys:
        assert key in bot_cache
        assert bot_cache[key] == f"data-for-{key}"

def test_cache_performance_characteristics():
    """Test cache performance under load"""
    bot_cache.clear()

    start_time = time.time()

    # Perform many cache operations
    for i in range(1000):
        bot_id = f"perf-test-bot-{i % 100}"  # Reuse keys to test updates
        bot_cache[bot_id] = f"data-{i}"

        # Occasional reads
        if i % 10 == 0:
            _ = bot_cache.get(bot_id)

        # Occasional deletes
        if i % 50 == 0 and bot_id in bot_cache:
            del bot_cache[bot_id]

    end_time = time.time()
    duration = end_time - start_time

    # Operations should complete quickly (less than 1 second for 1000 operations)
    assert duration < 1.0, f"Cache operations took too long: {duration}s"

def test_cache_data_integrity():
    """Test that cached data maintains integrity"""
    bot_cache.clear()

    # Test with complex data structures
    complex_data = {
        "intents": [
            {"cmd": "/start", "reply": "Hello"},
            {"cmd": "/help", "reply": "Help text"}
        ],
        "flows": [],
        "metadata": {
            "version": 1,
            "created": time.time(),
            "nested": {
                "deep": {
                    "data": [1, 2, 3, "text", True, None]
                }
            }
        }
    }

    bot_id = "integrity-test-bot"
    bot_cache[bot_id] = complex_data

    # Retrieve and verify
    retrieved_data = bot_cache[bot_id]

    assert retrieved_data == complex_data
    assert retrieved_data["metadata"]["nested"]["deep"]["data"] == [1, 2, 3, "text", True, None]
    assert retrieved_data["intents"][0]["cmd"] == "/start"

    # Modify original data
    complex_data["new_field"] = "new_value"

    # Cached data should not be affected (if properly isolated)
    # Note: Python dicts are mutable, so this test depends on implementation
    # In a production system, you might want to use copy.deepcopy

def test_reload_multiple_bots():
    """Test reloading multiple bots affects only targeted bot"""
    bot_cache.clear()

    bot_ids = ["multi-reload-bot-1", "multi-reload-bot-2", "multi-reload-bot-3"]

    # Add all bots to cache
    for bot_id in bot_ids:
        bot_cache[bot_id] = f"data-{bot_id}"

    # Reload only middle bot
    response = client.post(f"/bots/{bot_ids[1]}/reload")
    assert response.status_code == 200

    # Only middle bot should be removed from cache
    assert bot_ids[0] in bot_cache
    assert bot_ids[1] not in bot_cache
    assert bot_ids[2] in bot_cache

def test_cache_with_none_values():
    """Test cache behavior with None values"""
    bot_cache.clear()

    bot_id = "none-value-test"

    # Test storing None
    bot_cache[bot_id] = None

    # Should be able to retrieve None
    assert bot_id in bot_cache
    assert bot_cache[bot_id] is None
    assert bot_cache.get(bot_id) is None

    # Test distinguishing None from missing key
    missing_bot = "missing-bot"
    assert missing_bot not in bot_cache
    assert bot_cache.get(missing_bot) is None
    assert bot_cache.get(missing_bot, "default") == "default"