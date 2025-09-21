"""Unit tests for I18n Manager"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.i18n_manager import I18nManager


class TestI18nManager:
    """Test I18n Manager functionality"""

    @pytest.fixture
    def manager(self):
        return I18nManager()

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        session = AsyncMock()
        return session

    def test_configure(self, manager):
        """Test configuration of i18n manager"""
        config = {
            "default_locale": "en",
            "supported": ["en", "fr", "de"]
        }

        manager.configure(config)

        assert manager.default_locale == "en"
        assert manager.supported_locales == ["en", "fr", "de"]

    def test_configure_defaults(self, manager):
        """Test configuration with defaults"""
        config = {}

        manager.configure(config)

        assert manager.default_locale == "ru"
        assert manager.supported_locales == ["ru", "en"]

    @pytest.mark.asyncio
    async def test_get_user_locale_user_strategy(self, manager, mock_session):
        """Test getting user locale with user strategy"""
        # Mock database result
        mock_result = MagicMock()
        mock_result.scalar.return_value = "en"
        mock_session.execute.return_value = mock_result

        locale = await manager.get_user_locale(
            mock_session, "test-bot", user_id=123, strategy="user"
        )

        assert locale == "en"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_locale_chat_strategy(self, manager, mock_session):
        """Test getting user locale with chat strategy"""
        # Mock database result
        mock_result = MagicMock()
        mock_result.scalar.return_value = "fr"
        mock_session.execute.return_value = mock_result

        manager.configure({"supported": ["ru", "en", "fr"]})

        locale = await manager.get_user_locale(
            mock_session, "test-bot", chat_id=456, strategy="chat"
        )

        assert locale == "fr"

    @pytest.mark.asyncio
    async def test_get_user_locale_fallback(self, manager, mock_session):
        """Test fallback to default locale"""
        # Mock no result
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        locale = await manager.get_user_locale(
            mock_session, "test-bot", user_id=123, strategy="user"
        )

        assert locale == manager.default_locale

    @pytest.mark.asyncio
    async def test_get_user_locale_unsupported(self, manager, mock_session):
        """Test fallback when locale is unsupported"""
        # Mock unsupported locale
        mock_result = MagicMock()
        mock_result.scalar.return_value = "unsupported"
        mock_session.execute.return_value = mock_result

        locale = await manager.get_user_locale(
            mock_session, "test-bot", user_id=123, strategy="user"
        )

        assert locale == manager.default_locale

    @pytest.mark.asyncio
    async def test_set_user_locale_user(self, manager, mock_session):
        """Test setting user locale"""
        manager.configure({"supported": ["ru", "en"]})

        success = await manager.set_user_locale(
            mock_session, "test-bot", "en", user_id=123
        )

        assert success is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_locale_unsupported(self, manager, mock_session):
        """Test setting unsupported locale"""
        success = await manager.set_user_locale(
            mock_session, "test-bot", "unsupported", user_id=123
        )

        assert success is False
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_user_locale_chat(self, manager, mock_session):
        """Test setting chat locale"""
        manager.configure({"supported": ["ru", "en"]})

        success = await manager.set_user_locale(
            mock_session, "test-bot", "en", chat_id=456
        )

        assert success is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_locale_invalid_params(self, manager, mock_session):
        """Test setting locale with invalid parameters"""
        success = await manager.set_user_locale(
            mock_session, "test-bot", "en"  # No user_id or chat_id
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_get_keys_from_db(self, manager, mock_session):
        """Test getting keys from database"""
        # Mock database result
        mock_rows = [
            MagicMock(key="greeting", value="Hello"),
            MagicMock(key="farewell", value="Goodbye")
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        keys = await manager.get_keys(mock_session, "test-bot", "en")

        assert keys == {"greeting": "Hello", "farewell": "Goodbye"}
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_keys_cached(self, manager, mock_session):
        """Test getting keys from cache"""
        # Pre-populate cache
        cache_key = "test-bot:en"
        manager.cache[cache_key] = {"greeting": "Hello"}

        with patch('runtime.i18n_manager.i18n_cache_hits_total') as mock_hits:
            mock_hits.labels.return_value.inc = MagicMock()

            keys = await manager.get_keys(mock_session, "test-bot", "en")

            assert keys == {"greeting": "Hello"}
            mock_session.execute.assert_not_called()
            mock_hits.labels.assert_called_with("test-bot", "en")

    @pytest.mark.asyncio
    async def test_translate_key_exists(self, manager, mock_session):
        """Test translating existing key"""
        # Pre-populate cache
        cache_key = "test-bot:en"
        manager.cache[cache_key] = {"greeting": "Hello {name}"}

        with patch('runtime.i18n_manager.i18n_renders_total') as mock_renders:
            mock_renders.labels.return_value.inc = MagicMock()

            result = await manager.translate(
                mock_session, "test-bot", "greeting", "en", name="John"
            )

            assert result == "Hello John"
            mock_renders.labels.assert_called_with("test-bot", "en")

    @pytest.mark.asyncio
    async def test_translate_key_missing(self, manager, mock_session):
        """Test translating missing key"""
        # Empty cache
        cache_key = "test-bot:en"
        manager.cache[cache_key] = {}

        # No fallback either
        fallback_key = "test-bot:ru"
        manager.cache[fallback_key] = {}

        with patch('runtime.i18n_manager.i18n_key_miss_total') as mock_miss:
            mock_miss.labels.return_value.inc = MagicMock()

            result = await manager.translate(
                mock_session, "test-bot", "missing", "en"
            )

            assert result == "[missing]"
            mock_miss.labels.assert_called_with("test-bot", "en")

    @pytest.mark.asyncio
    async def test_translate_fallback_to_default(self, manager, mock_session):
        """Test fallback to default locale"""
        # Key missing in requested locale
        cache_key = "test-bot:en"
        manager.cache[cache_key] = {}

        # Key exists in default locale
        fallback_key = "test-bot:ru"
        manager.cache[fallback_key] = {"greeting": "Привет"}

        result = await manager.translate(
            mock_session, "test-bot", "greeting", "en"
        )

        assert result == "Привет"

    def test_apply_placeholders(self, manager):
        """Test applying placeholders to template"""
        template = "Hello {name}, you have {count} messages"
        placeholders = {"name": "John", "count": 5}

        result = manager._apply_placeholders(template, placeholders)

        assert result == "Hello John, you have 5 messages"

    def test_apply_placeholders_partial(self, manager):
        """Test applying partial placeholders"""
        template = "Hello {name}, you have {count} messages"
        placeholders = {"name": "John"}

        result = manager._apply_placeholders(template, placeholders)

        assert result == "Hello John, you have {count} messages"

    @pytest.mark.asyncio
    async def test_bulk_set_keys(self, manager, mock_session):
        """Test bulk setting keys"""
        manager.configure({"supported": ["ru", "en"]})

        keys = {
            "greeting": "Hello",
            "farewell": "Goodbye"
        }

        success = await manager.bulk_set_keys(
            mock_session, "test-bot", "en", keys
        )

        assert success is True
        assert mock_session.execute.call_count == 2  # One per key
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_set_keys_unsupported_locale(self, manager, mock_session):
        """Test bulk setting keys with unsupported locale"""
        keys = {"greeting": "Hello"}

        success = await manager.bulk_set_keys(
            mock_session, "test-bot", "unsupported", keys
        )

        assert success is False
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_set_keys_invalidates_cache(self, manager, mock_session):
        """Test that bulk set keys invalidates cache"""
        manager.configure({"supported": ["ru", "en"]})

        # Pre-populate cache
        cache_key = "test-bot:en"
        manager.cache[cache_key] = {"old": "value"}

        keys = {"greeting": "Hello"}

        await manager.bulk_set_keys(mock_session, "test-bot", "en", keys)

        # Cache should be invalidated
        assert cache_key not in manager.cache

    def test_invalidate_cache_specific_locale(self, manager):
        """Test invalidating cache for specific locale"""
        # Populate cache
        manager.cache["test-bot:en"] = {"greeting": "Hello"}
        manager.cache["test-bot:ru"] = {"greeting": "Привет"}
        manager.cache["other-bot:en"] = {"greeting": "Hi"}

        manager.invalidate_cache("test-bot", "en")

        # Only test-bot:en should be removed
        assert "test-bot:en" not in manager.cache
        assert "test-bot:ru" in manager.cache
        assert "other-bot:en" in manager.cache

    def test_invalidate_cache_all_locales(self, manager):
        """Test invalidating cache for all locales of a bot"""
        # Populate cache
        manager.cache["test-bot:en"] = {"greeting": "Hello"}
        manager.cache["test-bot:ru"] = {"greeting": "Привет"}
        manager.cache["other-bot:en"] = {"greeting": "Hi"}

        manager.invalidate_cache("test-bot")

        # All test-bot entries should be removed
        assert "test-bot:en" not in manager.cache
        assert "test-bot:ru" not in manager.cache
        assert "other-bot:en" in manager.cache

    @pytest.mark.asyncio
    async def test_error_handling_get_user_locale(self, manager, mock_session):
        """Test error handling in get_user_locale"""
        mock_session.execute.side_effect = Exception("DB error")

        locale = await manager.get_user_locale(
            mock_session, "test-bot", user_id=123, strategy="user"
        )

        # Should fallback to default on error
        assert locale == manager.default_locale

    @pytest.mark.asyncio
    async def test_error_handling_set_user_locale(self, manager, mock_session):
        """Test error handling in set_user_locale"""
        mock_session.execute.side_effect = Exception("DB error")
        manager.configure({"supported": ["ru", "en"]})

        success = await manager.set_user_locale(
            mock_session, "test-bot", "en", user_id=123
        )

        assert success is False
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_get_keys(self, manager, mock_session):
        """Test error handling in get_keys"""
        mock_session.execute.side_effect = Exception("DB error")

        keys = await manager.get_keys(mock_session, "test-bot", "en")

        # Should return empty dict on error
        assert keys == {}

    @pytest.mark.asyncio
    async def test_error_handling_translate(self, manager, mock_session):
        """Test error handling in translate"""
        # Force an error in getting keys
        mock_session.execute.side_effect = Exception("DB error")

        result = await manager.translate(
            mock_session, "test-bot", "greeting", "en"
        )

        # Should return key in brackets on error
        assert result == "[greeting]"

    @pytest.mark.asyncio
    async def test_error_handling_bulk_set_keys(self, manager, mock_session):
        """Test error handling in bulk_set_keys"""
        mock_session.execute.side_effect = Exception("DB error")
        manager.configure({"supported": ["ru", "en"]})

        keys = {"greeting": "Hello"}

        success = await manager.bulk_set_keys(
            mock_session, "test-bot", "en", keys
        )

        assert success is False
        mock_session.rollback.assert_called_once()