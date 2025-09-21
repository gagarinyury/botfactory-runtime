"""Unit tests for pagination widget"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from runtime.pagination_widget import PaginationWidget


class TestPaginationWidget:
    """Test pagination widget functionality"""

    @pytest.fixture
    def widget(self):
        return PaginationWidget()

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        session = AsyncMock()
        return session

    def test_render_template_basic(self, widget):
        """Test basic template rendering"""
        template = "• {{title}} - {{id}}"
        context = {"title": "Test Item", "id": 123}

        result = widget._render_template(template, context)
        assert result == "• Test Item - 123"

    def test_render_template_missing_vars(self, widget):
        """Test template rendering with missing variables"""
        template = "• {{title}} - {{missing}}"
        context = {"title": "Test Item"}

        result = widget._render_template(template, context)
        assert result == "• Test Item - {{missing}}"

    def test_build_pagination_keyboard_empty(self, widget):
        """Test keyboard building with empty items"""
        items = []
        keyboard = widget._build_pagination_keyboard(
            items, "test-bot", 123, 0, 5, 0,
            "{{title}}", "/select", "id", []
        )

        assert keyboard == []

    def test_build_pagination_keyboard_single_page(self, widget):
        """Test keyboard building with single page"""
        items = [
            {"id": 1, "title": "Item 1"},
            {"id": 2, "title": "Item 2"}
        ]

        keyboard = widget._build_pagination_keyboard(
            items, "test-bot", 123, 0, 5, 2,
            "{{title}}", "/select", "id", []
        )

        # Should have 2 item rows, no navigation
        assert len(keyboard) == 2
        assert keyboard[0][0]["text"] == "Item 1"
        assert keyboard[0][0]["callback_data"] == "pg:sel:test-bot:123:1"
        assert keyboard[1][0]["text"] == "Item 2"
        assert keyboard[1][0]["callback_data"] == "pg:sel:test-bot:123:2"

    def test_build_pagination_keyboard_multiple_pages(self, widget):
        """Test keyboard building with multiple pages"""
        items = [{"id": i, "title": f"Item {i}"} for i in range(1, 6)]

        keyboard = widget._build_pagination_keyboard(
            items, "test-bot", 123, 0, 5, 10,  # total 10 items, page size 5
            "{{title}}", "/select", "id", []
        )

        # Should have 5 item rows + 1 navigation row
        assert len(keyboard) == 6

        # Check navigation row (last row)
        nav_row = keyboard[-1]
        assert len(nav_row) == 2  # Page indicator + Next button
        assert "1/2" in nav_row[0]["text"]
        assert "Далее »" in nav_row[1]["text"]
        assert nav_row[1]["callback_data"] == "pg:next:test-bot:123:1"

    def test_build_pagination_keyboard_middle_page(self, widget):
        """Test keyboard building for middle page"""
        items = [{"id": i, "title": f"Item {i}"} for i in range(6, 11)]

        keyboard = widget._build_pagination_keyboard(
            items, "test-bot", 123, 1, 5, 15,  # page 1 of 3
            "{{title}}", "/select", "id", []
        )

        # Check navigation row
        nav_row = keyboard[-1]
        assert len(nav_row) == 3  # Prev + Page indicator + Next
        assert "« Назад" in nav_row[0]["text"]
        assert nav_row[0]["callback_data"] == "pg:prev:test-bot:123:0"
        assert "2/3" in nav_row[1]["text"]
        assert "Далее »" in nav_row[2]["text"]
        assert nav_row[2]["callback_data"] == "pg:next:test-bot:123:2"

    def test_build_pagination_keyboard_with_extra_buttons(self, widget):
        """Test keyboard building with extra buttons"""
        items = [{"id": 1, "title": "Item 1"}]
        extra_keyboard = [
            {"text": "Назад в меню", "callback_data": "/menu"}
        ]

        keyboard = widget._build_pagination_keyboard(
            items, "test-bot", 123, 0, 5, 1,
            "{{title}}", "/select", "id", extra_keyboard
        )

        # Should have 1 item row + 1 extra button row
        assert len(keyboard) == 2
        assert keyboard[1][0]["text"] == "Назад в меню"
        assert keyboard[1][0]["callback_data"] == "/menu"

    def test_build_message_text_empty(self, widget):
        """Test message text building for empty list"""
        text = widget._build_message_text("Список:", [], "{{title}}", 0, 5, 0)
        assert text == "Список:"

    def test_build_message_text_single_page(self, widget):
        """Test message text building for single page"""
        items = [{"id": 1, "title": "Item 1"}]
        text = widget._build_message_text("Список:", items, "{{title}}", 0, 5, 1)

        assert "Список:" in text
        assert "Элементов: 1" in text
        assert "Страница" not in text  # Single page, no page info

    def test_build_message_text_multiple_pages(self, widget):
        """Test message text building for multiple pages"""
        items = [{"id": i, "title": f"Item {i}"} for i in range(1, 6)]
        text = widget._build_message_text("Список:", items, "{{title}}", 0, 5, 10)

        assert "Список:" in text
        assert "Страница 1 из 2" in text
        assert "Элементов: 5" in text
        assert "(всего: 10)" in text

    @pytest.mark.asyncio
    async def test_get_ctx_data(self, widget):
        """Test getting data from context"""
        context_vars = {
            "items": [
                {"id": 1, "title": "Item 1"},
                {"id": 2, "title": "Item 2"},
                {"id": 3, "title": "Item 3"}
            ]
        }

        # Get first page
        items, total = await widget._get_ctx_data("items", 2, 0, context_vars)
        assert len(items) == 2
        assert total == 3
        assert items[0]["id"] == 1
        assert items[1]["id"] == 2

        # Get second page
        items, total = await widget._get_ctx_data("items", 2, 1, context_vars)
        assert len(items) == 1
        assert total == 3
        assert items[0]["id"] == 3

    @pytest.mark.asyncio
    async def test_get_ctx_data_missing_var(self, widget):
        """Test getting data from missing context variable"""
        context_vars = {}

        items, total = await widget._get_ctx_data("missing", 2, 0, context_vars)
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_ctx_data_invalid_type(self, widget):
        """Test getting data from non-list context variable"""
        context_vars = {"items": "not a list"}

        with pytest.raises(ValueError, match="must be a list"):
            await widget._get_ctx_data("items", 2, 0, context_vars)

    @pytest.mark.asyncio
    async def test_handle_selection_callback(self, widget, mock_session):
        """Test handling selection callback"""
        with patch('runtime.pagination_widget.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await widget._handle_selection("pg:sel:test-bot:123:item-id", mock_logger)

            assert result["type"] == "synthetic_input"
            assert result["selected_id"] == "item-id"
            mock_logger.log_event.assert_called_once_with("pagination_select", {"item_id": "item-id"})

    @pytest.mark.asyncio
    async def test_handle_selection_invalid_format(self, widget, mock_session):
        """Test handling invalid selection callback"""
        with patch('runtime.pagination_widget.create_events_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger

            result = await widget._handle_selection("pg:sel:invalid", mock_logger)

            assert result["error"] == "Invalid selection callback"

    @pytest.mark.asyncio
    async def test_handle_navigation_callback(self, widget):
        """Test handling navigation callback"""
        result = await widget._handle_navigation("pg:next:test-bot:123:2")

        assert result["type"] == "navigation"
        assert result["action"] == "pg:next"
        assert result["page"] == 2
        assert result["bot_id"] == "test-bot"
        assert result["user_id"] == 123

    @pytest.mark.asyncio
    async def test_handle_navigation_invalid_format(self, widget):
        """Test handling invalid navigation callback"""
        result = await widget._handle_navigation("pg:next:invalid")

        assert result["error"] == "Invalid navigation callback"

    @pytest.mark.asyncio
    async def test_render_pagination_sql_source(self, widget, mock_session):
        """Test rendering pagination with SQL source"""
        params = {
            "source": {
                "type": "sql",
                "sql": "SELECT id, title FROM items WHERE bot_id=:bot_id ORDER BY id LIMIT :limit OFFSET :offset"
            },
            "page_size": 3,
            "item_template": "• {{title}}",
            "select_callback": "/select",
            "id_field": "id",
            "title": "Items:"
        }

        # Mock SQL execution
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            {"id": 1, "title": "Item 1"},
            {"id": 2, "title": "Item 2"}
        ]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_session.execute.side_effect = [mock_result, mock_count_result]

        result = await widget.render_pagination("test-bot", 123, params, mock_session)

        assert result["success"] is True
        assert result["type"] == "reply"
        assert "Items:" in result["text"]
        assert len(result["keyboard"]) == 3  # 2 items + navigation

    @pytest.mark.asyncio
    async def test_render_pagination_ctx_source(self, widget, mock_session):
        """Test rendering pagination with context source"""
        params = {
            "source": {
                "type": "ctx",
                "ctx_var": "items"
            },
            "page_size": 2,
            "item_template": "• {{title}}",
            "select_callback": "/select",
            "id_field": "id",
            "title": "Items:"
        }

        context_vars = {
            "items": [
                {"id": 1, "title": "Item 1"},
                {"id": 2, "title": "Item 2"},
                {"id": 3, "title": "Item 3"}
            ]
        }

        result = await widget.render_pagination("test-bot", 123, params, mock_session, context_vars)

        assert result["success"] is True
        assert result["type"] == "reply"
        assert "Items:" in result["text"]
        assert len(result["keyboard"]) == 3  # 2 items + navigation

    @pytest.mark.asyncio
    async def test_render_pagination_empty_data(self, widget, mock_session):
        """Test rendering pagination with empty data"""
        params = {
            "source": {
                "type": "ctx",
                "ctx_var": "items"
            },
            "item_template": "• {{title}}",
            "select_callback": "/select",
            "id_field": "id",
            "title": "Items:",
            "empty_text": "Нет элементов"
        }

        context_vars = {"items": []}

        result = await widget.render_pagination("test-bot", 123, params, mock_session, context_vars)

        assert result["success"] is True
        assert result["text"] == "Нет элементов"
        assert result["keyboard"] == []

    @pytest.mark.asyncio
    async def test_render_pagination_page_size_limit(self, widget, mock_session):
        """Test pagination respects page size limit"""
        params = {
            "source": {
                "type": "ctx",
                "ctx_var": "items"
            },
            "page_size": 100,  # Exceeds max_page_size
            "item_template": "• {{title}}",
            "select_callback": "/select",
            "id_field": "id"
        }

        context_vars = {"items": [{"id": i, "title": f"Item {i}"} for i in range(100)]}

        result = await widget.render_pagination("test-bot", 123, params, mock_session, context_vars)

        # Should be limited to max_page_size (50)
        assert len(result["keyboard"]) <= 52  # 50 items + navigation + extra buttons