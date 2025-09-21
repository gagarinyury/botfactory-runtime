"""Integration tests for pagination widget in real flow scenarios"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from runtime.dsl_engine import handle, handle_callback


class TestPaginationWidgetFlowsIntegration:
    """Test pagination widget in wizard and flow scenarios"""

    @pytest.mark.asyncio
    async def test_pagination_widget_sql_source_in_wizard(self):
        """Test pagination widget with SQL source in wizard flow"""
        # Test spec with pagination widget
        spec_data = {
            "use": ["flow.wizard.v1", "widget.pagination.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/services",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.pagination.v1",
                                    "params": {
                                        "source": {
                                            "type": "sql",
                                            "sql": "SELECT id, title FROM services WHERE bot_id=:bot_id ORDER BY id LIMIT :limit OFFSET :offset"
                                        },
                                        "page_size": 3,
                                        "item_template": "• {{title}}",
                                        "select_callback": "/pick_service",
                                        "id_field": "id",
                                        "title": "Выберите услугу:",
                                        "empty_text": "Нет услуг"
                                    }
                                },
                                "var": "service_id"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Выбрана услуга: {{service_id}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            # Mock load_spec
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock pagination widget render
            with patch('runtime.pagination_widget.pagination_widget.render_pagination') as mock_render:
                mock_render.return_value = {
                    "type": "reply",
                    "text": "Выберите услугу:\nСтраница 1 из 2\nЭлементов: 3",
                    "keyboard": [
                        [{"text": "• Массаж", "callback_data": "pg:sel:test-bot:999999:1"}],
                        [{"text": "• Маникюр", "callback_data": "pg:sel:test-bot:999999:2"}],
                        [{"text": "• Стрижка", "callback_data": "pg:sel:test-bot:999999:3"}],
                        [
                            {"text": "1/2", "callback_data": "pg:ignore"},
                            {"text": "Далее »", "callback_data": "pg:next:test-bot:999999:1"}
                        ]
                    ],
                    "success": True
                }

                # Start wizard with /services command
                response = await handle("test-bot", "/services")
                assert "Выберите услугу:" in str(response)

            # Test item selection
            with patch('runtime.pagination_widget.pagination_widget.handle_callback') as mock_callback, \
                 patch('runtime.actions.ActionExecutor._execute_reply_template') as mock_reply:

                mock_callback.return_value = {
                    "type": "synthetic_input",
                    "selected_id": "2"
                }

                mock_reply.return_value = {
                    "success": True,
                    "type": "reply",
                    "text": "Выбрана услуга: 2"
                }

                # Simulate service selection
                callback_response = await handle_callback("test-bot", 999999, "pg:sel:test-bot:999999:2")
                assert "Выбрана услуга: 2" in str(callback_response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_pagination_widget_ctx_source_in_wizard(self):
        """Test pagination widget with context source in wizard flow"""
        spec_data = {
            "use": ["flow.wizard.v1", "widget.pagination.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/choose",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.pagination.v1",
                                    "params": {
                                        "source": {
                                            "type": "ctx",
                                            "ctx_var": "options"
                                        },
                                        "page_size": 2,
                                        "item_template": "{{name}} - {{price}}₽",
                                        "select_callback": "/pick",
                                        "id_field": "id",
                                        "title": "Выберите опцию:"
                                    }
                                },
                                "var": "selected_option"
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Mock pagination widget with context data
            with patch('runtime.pagination_widget.pagination_widget.render_pagination') as mock_render:
                mock_render.return_value = {
                    "type": "reply",
                    "text": "Выберите опцию:\nСтраница 1 из 2\nЭлементов: 2 (всего: 3)",
                    "keyboard": [
                        [{"text": "Опция А - 100₽", "callback_data": "pg:sel:test-bot:999999:opt_a"}],
                        [{"text": "Опция Б - 200₽", "callback_data": "pg:sel:test-bot:999999:opt_b"}],
                        [
                            {"text": "1/2", "callback_data": "pg:ignore"},
                            {"text": "Далее »", "callback_data": "pg:next:test-bot:999999:1"}
                        ]
                    ],
                    "success": True
                }

                response = await handle("test-bot", "/choose")
                assert "Выберите опцию:" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_pagination_navigation_callbacks(self):
        """Test pagination navigation callbacks"""
        # Mock wizard state
        wizard_state = {
            "format": "v1",
            "step": 0,
            "vars": {},
            "ttl_sec": 86400
        }

        with patch('runtime.redis_client.redis_client.get_wizard_state') as mock_get_state:
            mock_get_state.return_value = wizard_state

            # Test navigation callback
            with patch('runtime.pagination_widget.pagination_widget.handle_callback') as mock_callback:
                mock_callback.return_value = {
                    "type": "navigation",
                    "action": "pg:next",
                    "page": 1,
                    "bot_id": "test-bot",
                    "user_id": 999999
                }

                response = await handle_callback("test-bot", 999999, "pg:next:test-bot:999999:1")

                assert response is not None
                mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_ignore_callbacks(self):
        """Test pagination ignore callbacks"""
        wizard_state = {
            "format": "v1",
            "step": 0,
            "vars": {},
            "ttl_sec": 86400
        }

        with patch('runtime.redis_client.redis_client.get_wizard_state') as mock_get_state:
            mock_get_state.return_value = wizard_state

            # Test ignore callback
            with patch('runtime.pagination_widget.pagination_widget.handle_callback') as mock_callback:
                mock_callback.return_value = None

                response = await handle_callback("test-bot", 999999, "pg:ignore")

                assert response is None
                mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_widget_error_handling(self):
        """Test pagination widget error handling"""
        # Test invalid callback format
        with patch('runtime.pagination_widget.pagination_widget.handle_callback') as mock_callback:
            mock_callback.return_value = {"error": "Ошибка обработки выбора"}

            response = await handle_callback("test-bot", 999999, "pg:sel:invalid:format")

            assert response["error"] == "Ошибка обработки выбора"

    @pytest.mark.asyncio
    async def test_pagination_empty_results(self):
        """Test pagination widget with empty results"""
        spec_data = {
            "use": ["flow.wizard.v1", "widget.pagination.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/empty",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.pagination.v1",
                                    "params": {
                                        "source": {
                                            "type": "ctx",
                                            "ctx_var": "empty_list"
                                        },
                                        "item_template": "{{title}}",
                                        "select_callback": "/select",
                                        "id_field": "id",
                                        "title": "Список:",
                                        "empty_text": "Список пуст"
                                    }
                                },
                                "var": "selection"
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            with patch('runtime.pagination_widget.pagination_widget.render_pagination') as mock_render:
                mock_render.return_value = {
                    "type": "reply",
                    "text": "Список пуст",
                    "keyboard": [],
                    "success": True
                }

                response = await handle("test-bot", "/empty")
                assert "Список пуст" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_pagination_with_extra_keyboard(self):
        """Test pagination widget with extra keyboard buttons"""
        spec_data = {
            "use": ["flow.wizard.v1", "widget.pagination.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/browse",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.pagination.v1",
                                    "params": {
                                        "source": {
                                            "type": "ctx",
                                            "ctx_var": "items"
                                        },
                                        "page_size": 3,
                                        "item_template": "{{title}}",
                                        "select_callback": "/select",
                                        "id_field": "id",
                                        "title": "Выберите:",
                                        "extra_keyboard": [
                                            {"text": "🔙 Назад в меню", "callback_data": "/menu"},
                                            {"text": "❌ Отмена", "callback_data": "/cancel"}
                                        ]
                                    }
                                },
                                "var": "item_id"
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            with patch('runtime.pagination_widget.pagination_widget.render_pagination') as mock_render:
                mock_render.return_value = {
                    "type": "reply",
                    "text": "Выберите:\nЭлементов: 2",
                    "keyboard": [
                        [{"text": "Item 1", "callback_data": "pg:sel:test-bot:999999:1"}],
                        [{"text": "Item 2", "callback_data": "pg:sel:test-bot:999999:2"}],
                        [{"text": "🔙 Назад в меню", "callback_data": "/menu"}],
                        [{"text": "❌ Отмена", "callback_data": "/cancel"}]
                    ],
                    "success": True
                }

                response = await handle("test-bot", "/browse")
                assert "Выберите:" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_pagination_multi_step_wizard(self):
        """Test pagination widget in multi-step wizard"""
        spec_data = {
            "use": ["flow.wizard.v1", "widget.pagination.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/multi",
                    "params": {
                        "steps": [
                            {
                                "widget": {
                                    "type": "widget.pagination.v1",
                                    "params": {
                                        "source": {
                                            "type": "ctx",
                                            "ctx_var": "categories"
                                        },
                                        "item_template": "{{name}}",
                                        "select_callback": "/pick_category",
                                        "id_field": "id",
                                        "title": "Выберите категорию:"
                                    }
                                },
                                "var": "category_id"
                            },
                            {
                                "ask": "Введите название:",
                                "var": "name"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "Создано: {{name}} в категории {{category_id}}"
                                }
                            }
                        ]
                    }
                }
            ]
        }

        original_load_spec = None
        try:
            from runtime import dsl_engine as dsl
            original_load_spec = dsl.load_spec
            dsl.load_spec = AsyncMock(return_value=spec_data)

            # Start wizard
            with patch('runtime.pagination_widget.pagination_widget.render_pagination') as mock_render:
                mock_render.return_value = {
                    "type": "reply",
                    "text": "Выберите категорию:",
                    "keyboard": [
                        [{"text": "Категория 1", "callback_data": "pg:sel:test-bot:999999:cat1"}]
                    ],
                    "success": True
                }

                response = await handle("test-bot", "/multi")
                assert "Выберите категорию:" in str(response)

            # Select category and move to next step
            with patch('runtime.pagination_widget.pagination_widget.handle_callback') as mock_callback:
                mock_callback.return_value = {
                    "type": "synthetic_input",
                    "selected_id": "cat1"
                }

                # This should advance to the next step (name input)
                callback_response = await handle_callback("test-bot", 999999, "pg:sel:test-bot:999999:cat1")
                assert "Введите название:" in str(callback_response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec