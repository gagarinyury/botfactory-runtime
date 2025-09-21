"""Integration tests for enhanced action.reply_template.v1 in flows"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from runtime.dsl_engine import handle


class TestReplyTemplateEnhancedFlows:
    """Test enhanced reply template in real flow scenarios"""

    @pytest.mark.asyncio
    async def test_reply_template_with_multi_row_keyboard_in_wizard(self):
        """Test reply template with multi-row keyboard in wizard"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/menu",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "🏠 <b>Главное меню</b>\n\nВыберите действие:",
                                    "parse_mode": "HTML",
                                    "keyboard": [
                                        [
                                            {"text": "📅 Бронирование", "callback": "/book"},
                                            {"text": "📋 Мои записи", "callback": "/my"}
                                        ],
                                        [
                                            {"text": "⚙️ Настройки", "callback": "/settings"},
                                            {"text": "❓ Помощь", "callback": "/help"}
                                        ],
                                        {"text": "🚪 Выход", "callback": "/exit"}
                                    ]
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

            with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
                 patch('runtime.actions.reply_sent_total') as mock_sent, \
                 patch('runtime.actions.reply_latency_ms') as mock_latency:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger
                mock_sent_labels = MagicMock()
                mock_sent.labels.return_value = mock_sent_labels
                mock_latency_labels = MagicMock()
                mock_latency.labels.return_value = mock_latency_labels

                response = await handle("test-bot", "/menu")

                # Should return structured response with keyboard
                assert "Главное меню" in str(response)

                # Check that metrics were recorded
                mock_sent.labels.assert_called_with("test-bot")
                mock_sent_labels.inc.assert_called()

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_with_i18n_in_flow(self):
        """Test reply template with i18n keys in flow"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/greet",
                    "params": {
                        "steps": [
                            {
                                "ask": "Как вас зовут?",
                                "var": "username"
                            }
                        ],
                        "on_complete": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "t:greeting {name={{username}}}",
                                    "parse_mode": "MarkdownV2"
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

            with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
                 patch('runtime.i18n_manager.i18n_manager.translate') as mock_translate:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger
                mock_translate.return_value = "Привет, Alice!"

                # Start wizard
                response1 = await handle("test-bot", "/greet")
                assert "Как вас зовут?" in str(response1)

                # Complete wizard with name
                response2 = await handle("test-bot", "Alice")
                assert "Привет, Alice!" in str(response2)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_with_each_loop_in_flow(self):
        """Test reply template with {{#each}} loops in flow"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_query.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/orders",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.sql_query.v1",
                                "params": {
                                    "sql": "SELECT id, product_name, price FROM orders WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5",
                                    "result_var": "user_orders"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "📦 *Ваши заказы:*\n\n{{#each user_orders}}• {{product_name}} — {{price}}₽\n{{/each}}",
                                    "empty_text": "📦 *Заказы не найдены*\n\nВы еще не делали заказов\\.",
                                    "parse_mode": "MarkdownV2",
                                    "keyboard": [
                                        [
                                            {"text": "🛒 Новый заказ", "callback": "/shop"},
                                            {"text": "🔙 Назад", "callback": "/menu"}
                                        ]
                                    ]
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

            # Mock SQL query results
            with patch('runtime.actions.ActionExecutor._execute_sql_query') as mock_sql, \
                 patch('runtime.actions.create_events_logger') as mock_logger_factory:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger

                # Test with orders
                mock_sql.return_value = {
                    "success": True,
                    "rows": 2
                }

                # Mock the context to have orders
                with patch.object(ActionExecutor, 'set_context_var') as mock_set_var:
                    orders = [
                        {"id": 1, "product_name": "Товар 1", "price": 1000},
                        {"id": 2, "product_name": "Товар 2", "price": 2000}
                    ]

                    response = await handle("test-bot", "/orders")
                    assert "Ваши заказы:" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_error_handling_in_flow(self):
        """Test reply template error handling in flow context"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/broken",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "{{unclosed_template"  # Malformed template
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

            with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
                 patch('runtime.actions.reply_failed_total') as mock_failed:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger
                mock_failed_labels = MagicMock()
                mock_failed.labels.return_value = mock_failed_labels

                response = await handle("test-bot", "/broken")

                # Should return fallback error message
                assert "[template error]" in str(response)

                # Should record failure metric
                mock_failed.labels.assert_called_with("test-bot")
                mock_failed_labels.inc.assert_called()

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_empty_text_fallback_in_flow(self):
        """Test reply template empty_text fallback in flow"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_query.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/empty_list",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.sql_query.v1",
                                "params": {
                                    "sql": "SELECT * FROM items WHERE bot_id=:bot_id AND visible=true",
                                    "result_var": "items"
                                }
                            },
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "📋 Список элементов:\n{{#each items}}• {{name}}\n{{/each}}",
                                    "empty_text": "📭 Список пуст\n\nЭлементы отсутствуют."
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

            with patch('runtime.actions.ActionExecutor._execute_sql_query') as mock_sql, \
                 patch('runtime.actions.create_events_logger') as mock_logger_factory:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger

                # Mock empty SQL result
                mock_sql.return_value = {
                    "success": True,
                    "rows": 0
                }

                # Mock empty context
                with patch.object(ActionExecutor, 'set_context_var'):
                    response = await handle("test-bot", "/empty_list")
                    assert "Список пуст" in str(response)

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_complex_keyboard_layout(self):
        """Test reply template with complex keyboard layout"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/calculator",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "🧮 *Калькулятор*\n\nВыберите операцию:",
                                    "parse_mode": "MarkdownV2",
                                    "keyboard": [
                                        [
                                            {"text": "7", "callback": "num:7"},
                                            {"text": "8", "callback": "num:8"},
                                            {"text": "9", "callback": "num:9"},
                                            {"text": "÷", "callback": "op:div"}
                                        ],
                                        [
                                            {"text": "4", "callback": "num:4"},
                                            {"text": "5", "callback": "num:5"},
                                            {"text": "6", "callback": "num:6"},
                                            {"text": "×", "callback": "op:mul"}
                                        ],
                                        [
                                            {"text": "1", "callback": "num:1"},
                                            {"text": "2", "callback": "num:2"},
                                            {"text": "3", "callback": "num:3"},
                                            {"text": "+", "callback": "op:add"}
                                        ],
                                        [
                                            {"text": "0", "callback": "num:0"},
                                            {"text": ".", "callback": "num:dot"},
                                            {"text": "=", "callback": "op:equals"},
                                            {"text": "-", "callback": "op:sub"}
                                        ],
                                        {"text": "🗑️ Очистить", "callback": "clear"},
                                        {"text": "🔙 Назад", "callback": "/menu"}
                                    ]
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

            with patch('runtime.actions.create_events_logger') as mock_logger_factory:
                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger

                response = await handle("test-bot", "/calculator")

                # Should contain calculator text
                assert "Калькулятор" in str(response)

                # Check that event was logged with correct keyboard count
                mock_logger.log_event.assert_called()
                event_args = mock_logger.log_event.call_args[0]
                event_data = event_args[1]
                assert event_data["keyboard_buttons"] == 6  # 6 rows/buttons in config

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec

    @pytest.mark.asyncio
    async def test_reply_template_metrics_and_events_logging(self):
        """Test comprehensive metrics and events logging"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.reply_template.v1"],
            "flows": [
                {
                    "type": "flow.wizard.v1",
                    "entry_cmd": "/metrics_test",
                    "params": {
                        "on_enter": [
                            {
                                "type": "action.reply_template.v1",
                                "params": {
                                    "text": "📊 Test metrics logging",
                                    "parse_mode": "HTML",
                                    "keyboard": [
                                        {"text": "✅ OK", "callback": "ok"}
                                    ]
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

            with patch('runtime.actions.create_events_logger') as mock_logger_factory, \
                 patch('runtime.actions.reply_sent_total') as mock_sent, \
                 patch('runtime.actions.reply_latency_ms') as mock_latency:

                mock_logger = AsyncMock()
                mock_logger_factory.return_value = mock_logger
                mock_sent_labels = MagicMock()
                mock_sent.labels.return_value = mock_sent_labels
                mock_latency_labels = MagicMock()
                mock_latency.labels.return_value = mock_latency_labels

                response = await handle("test-bot", "/metrics_test")

                # Verify metrics were recorded
                mock_sent.labels.assert_called_with("test-bot")
                mock_sent_labels.inc.assert_called()
                mock_latency.labels.assert_called_with("test-bot")
                mock_latency_labels.observe.assert_called()

                # Verify event was logged
                mock_logger.log_event.assert_called_with("reply_render", {
                    "template_hash": mock_logger.log_event.call_args[0][1]["template_hash"],
                    "rendered_length": len("📊 Test metrics logging"),
                    "keyboard_buttons": 1,
                    "parse_mode": "HTML",
                    "duration_ms": mock_logger.log_event.call_args[0][1]["duration_ms"]
                })

        finally:
            if original_load_spec:
                dsl.load_spec = original_load_spec