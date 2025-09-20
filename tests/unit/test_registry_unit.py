"""Test bot registry CRUD operations"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.registry import BotRegistry

@pytest.mark.asyncio
async def test_create_bot():
    """Test creating a new bot"""
    registry = BotRegistry()

    # Mock database session and result
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_bot = MagicMock()

    # Configure mock bot object
    mock_bot.id = "test-uuid-123"
    mock_bot.name = "test-bot"
    mock_bot.token = "test-token"
    mock_bot.status = "active"

    mock_result.fetchone.return_value = mock_bot
    mock_session.execute.return_value = mock_result

    # Test bot creation
    result = await registry.create_bot(mock_session, "test-bot", "test-token")

    assert result is not None
    assert result["name"] == "test-bot"
    assert result["token"] == "test-token"
    assert result["status"] == "active"
    assert "id" in result

    # Verify session.commit was called
    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_create_bot_error():
    """Test bot creation with database error"""
    registry = BotRegistry()

    # Mock session that raises exception
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")

    # Test that exception is raised and rollback is called
    with pytest.raises(Exception, match="Database error"):
        await registry.create_bot(mock_session, "test-bot", "test-token")

    mock_session.rollback.assert_called_once()

@pytest.mark.asyncio
async def test_get_bot():
    """Test getting a bot by ID"""
    registry = BotRegistry()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_bot = MagicMock()

    mock_bot.id = "test-bot-id"
    mock_bot.name = "test-bot"
    mock_bot.token = "test-token"
    mock_bot.status = "active"

    mock_result.fetchone.return_value = mock_bot
    mock_session.execute.return_value = mock_result

    # Test getting bot
    result = await registry.get_bot(mock_session, "test-bot-id")

    assert result is not None
    assert result["id"] == "test-bot-id"
    assert result["name"] == "test-bot"
    assert result["token"] == "test-token"
    assert result["status"] == "active"

@pytest.mark.asyncio
async def test_get_bot_not_found():
    """Test getting non-existent bot"""
    registry = BotRegistry()

    # Mock session with no results
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.fetchone.return_value = None
    mock_session.execute.return_value = mock_result

    result = await registry.get_bot(mock_session, "non-existent-id")

    assert result is None

@pytest.mark.asyncio
async def test_update_bot():
    """Test updating bot information"""
    registry = BotRegistry()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_bot = MagicMock()

    mock_bot.id = "test-bot-id"
    mock_bot.name = "updated-bot"
    mock_bot.token = "updated-token"
    mock_bot.status = "inactive"

    mock_result.fetchone.return_value = mock_bot
    mock_session.execute.return_value = mock_result

    # Test updating bot
    result = await registry.update_bot(
        mock_session,
        "test-bot-id",
        name="updated-bot",
        token="updated-token",
        status="inactive"
    )

    assert result is not None
    assert result["name"] == "updated-bot"
    assert result["token"] == "updated-token"
    assert result["status"] == "inactive"

    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_update_bot_no_changes():
    """Test updating bot with no actual changes"""
    registry = BotRegistry()

    # Mock get_bot method
    mock_session = AsyncMock()

    # When no updates are provided, should call get_bot
    with patch.object(registry, 'get_bot') as mock_get_bot:
        mock_get_bot.return_value = {"id": "test-id", "name": "test"}

        result = await registry.update_bot(mock_session, "test-id")

        mock_get_bot.assert_called_once_with(mock_session, "test-id")
        assert result == {"id": "test-id", "name": "test"}

@pytest.mark.asyncio
async def test_delete_bot():
    """Test deleting a bot"""
    registry = BotRegistry()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.rowcount = 1
    mock_session.execute.return_value = mock_result

    # Test deleting bot
    result = await registry.delete_bot(mock_session, "test-bot-id")

    assert result is True
    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_delete_bot_not_found():
    """Test deleting non-existent bot"""
    registry = BotRegistry()

    # Mock session with no affected rows
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.rowcount = 0
    mock_session.execute.return_value = mock_result

    result = await registry.delete_bot(mock_session, "non-existent-id")

    assert result is False

@pytest.mark.asyncio
async def test_list_bots():
    """Test listing all bots"""
    registry = BotRegistry()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = AsyncMock()

    # Create mock bots
    mock_bot1 = MagicMock()
    mock_bot1.id = "bot-1"
    mock_bot1.name = "Bot 1"
    mock_bot1.token = "token-1"
    mock_bot1.status = "active"

    mock_bot2 = MagicMock()
    mock_bot2.id = "bot-2"
    mock_bot2.name = "Bot 2"
    mock_bot2.token = "token-2"
    mock_bot2.status = "inactive"

    mock_result.fetchall.return_value = [mock_bot1, mock_bot2]
    mock_session.execute.return_value = mock_result

    # Test listing bots
    result = await registry.list_bots(mock_session)

    assert len(result) == 2
    assert result[0]["name"] == "Bot 1"
    assert result[1]["name"] == "Bot 2"

@pytest.mark.asyncio
async def test_list_bots_empty():
    """Test listing bots when none exist"""
    registry = BotRegistry()

    # Mock session with no results
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    result = await registry.list_bots(mock_session)

    assert result == []

@pytest.mark.asyncio
async def test_db_ok():
    """Test database health check"""
    registry = BotRegistry()

    # Mock successful database connection
    mock_session = AsyncMock()

    result = await registry.db_ok(mock_session)

    assert result is True
    mock_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_db_ok_failure():
    """Test database health check failure"""
    registry = BotRegistry()

    # Mock failed database connection
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Connection failed")

    result = await registry.db_ok(mock_session)

    assert result is False