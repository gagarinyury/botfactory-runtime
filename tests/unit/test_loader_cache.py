"""Test bot loader caching functionality"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.loader import BotLoader
from runtime.main import bot_cache

@pytest.mark.anyio
async def test_load_spec_by_bot_id():
    """Test basic spec loading functionality"""
    loader = BotLoader()

    # Mock database session and response
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_row = MagicMock()

    # Configure mock return values
    mock_row.name = "test-bot"
    mock_row.token = "test-token"
    mock_row.status = "active"
    mock_row.version = 1
    mock_row.spec_json = {"intents": [{"cmd": "/test", "reply": "Test"}]}

    mock_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_result

    # Test loading spec
    result = await loader.load_spec_by_bot_id(mock_session, "test-bot-id")

    assert result is not None
    assert result["bot_id"] == "test-bot-id"
    assert result["name"] == "test-bot"
    assert result["token"] == "test-token"
    assert result["version"] == 1
    assert "spec_json" in result

@pytest.mark.anyio
async def test_load_spec_not_found():
    """Test loading spec for non-existent bot"""
    loader = BotLoader()

    # Mock database session with no results
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_session.execute.return_value = mock_result

    # Test loading non-existent spec
    result = await loader.load_spec_by_bot_id(mock_session, "non-existent-bot")

    assert result is None

@pytest.mark.anyio
async def test_load_spec_with_version():
    """Test loading specific version of spec"""
    loader = BotLoader()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_row = MagicMock()

    mock_row.name = "test-bot"
    mock_row.token = "test-token"
    mock_row.status = "active"
    mock_row.version = 2
    mock_row.spec_json = {"intents": [{"cmd": "/test", "reply": "Test v2"}]}

    mock_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_result

    # Test loading specific version
    result = await loader.load_spec_by_bot_id(mock_session, "test-bot-id", version=2)

    assert result is not None
    assert result["version"] == 2

def test_bot_cache_operations():
    """Test bot cache basic operations"""
    # Clear cache first
    bot_cache.clear()

    # Test cache is initially empty
    assert len(bot_cache) == 0

    # Add item to cache
    test_bot_id = "test-cache-bot"
    test_data = {"test": "data"}
    bot_cache[test_bot_id] = test_data

    # Test cache contains item
    assert test_bot_id in bot_cache
    assert bot_cache[test_bot_id] == test_data

    # Test cache removal
    del bot_cache[test_bot_id]
    assert test_bot_id not in bot_cache

def test_cache_invalidation_scenario():
    """Test cache invalidation behavior"""
    # Clear cache
    bot_cache.clear()

    test_bot_id = "cache-test-bot"

    # Simulate cached data
    cached_data = {"cached": True, "version": 1}
    bot_cache[test_bot_id] = cached_data

    # Verify data is cached
    assert bot_cache.get(test_bot_id) == cached_data

    # Simulate cache invalidation (like reload endpoint)
    if test_bot_id in bot_cache:
        del bot_cache[test_bot_id]

    # Verify cache is cleared
    assert test_bot_id not in bot_cache

@pytest.mark.anyio
async def test_load_from_plugin_not_implemented():
    """Test that plugin loading returns None (not implemented)"""
    loader = BotLoader()

    result = await loader.load_from_plugin("test-plugin", "test-bot-id")

    assert result is None

@pytest.mark.anyio
async def test_get_bot_config_fallback():
    """Test get_bot_config fallback behavior"""
    loader = BotLoader()

    # Mock session that returns None from database
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_session.execute.return_value = mock_result

    result = await loader.get_bot_config(mock_session, "non-existent-bot")

    # Should return None when bot not found in DB and no plugins
    assert result is None