"""Unit tests for template rendering functionality"""
import pytest
from unittest.mock import AsyncMock
from runtime.actions import ActionExecutor


class TestTemplateRenderer:
    """Test template rendering logic"""

    def setup_method(self):
        """Setup test fixtures"""
        # Mock session and create executor
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot-id", 12345)

    def test_simple_variable_substitution(self):
        """Test basic {{var}} substitution"""
        template = "Hello {{name}}!"
        self.executor.set_context_var("name", "John")

        result = self.executor._render_template(template)
        assert result == "Hello John!"

    def test_multiple_variable_substitution(self):
        """Test multiple variable substitutions"""
        template = "User {{name}} has {{count}} items"
        self.executor.set_context_var("name", "Alice")
        self.executor.set_context_var("count", 5)

        result = self.executor._render_template(template)
        assert result == "User Alice has 5 items"

    def test_numeric_variable_substitution(self):
        """Test numeric variable substitution"""
        template = "Price: {{price}}, Quantity: {{qty}}"
        self.executor.set_context_var("price", 99.99)
        self.executor.set_context_var("qty", 3)

        result = self.executor._render_template(template)
        assert result == "Price: 99.99, Quantity: 3"

    def test_missing_variable_substitution(self):
        """Test handling of missing variables"""
        template = "Hello {{name}}! You have {{count}} messages."
        self.executor.set_context_var("name", "Bob")
        # count is not set

        result = self.executor._render_template(template)
        # Missing variables should remain unchanged
        assert result == "Hello Bob! You have {{count}} messages."

    def test_each_loop_with_dict_rows(self):
        """Test {{#each}} loop with dictionary rows"""
        template = "Items:\\n{{#each items}}{{name}} - {{price}}\\n{{/each}}"

        items_data = [
            {"name": "Apple", "price": "1.50"},
            {"name": "Banana", "price": "0.80"},
            {"name": "Orange", "price": "2.00"}
        ]
        self.executor.set_context_var("items", items_data)

        result = self.executor._render_template(template)
        expected = "Items:\\nApple - 1.50\\nBanana - 0.80\\nOrange - 2.00\\n"
        assert result == expected

    def test_each_loop_empty_list(self):
        """Test {{#each}} loop with empty list"""
        template = "Items:\\n{{#each items}}{{name}} - {{price}}\\n{{/each}}"
        self.executor.set_context_var("items", [])

        result = self.executor._render_template(template)
        assert result == "Items:\\n"

    def test_each_loop_missing_variable(self):
        """Test {{#each}} loop with missing variable"""
        template = "Items:\\n{{#each missing_items}}{{name}}\\n{{/each}}"

        result = self.executor._render_template(template)
        assert result == "Items:\\n"

    def test_each_loop_non_list_variable(self):
        """Test {{#each}} loop with non-list variable"""
        template = "Items:\\n{{#each items}}{{name}}\\n{{/each}}"
        self.executor.set_context_var("items", "not a list")

        result = self.executor._render_template(template)
        assert result == "Items:\\n"

    def test_complex_each_loop(self):
        """Test complex {{#each}} loop with multiple fields"""
        template = """Bookings:
{{#each bookings}}Service: {{service}}, Time: {{slot}}, Status: {{status}}
{{/each}}"""

        bookings_data = [
            {"service": "massage", "slot": "2024-01-15 14:00", "status": "confirmed"},
            {"service": "spa", "slot": "2024-01-16 10:00", "status": "pending"}
        ]
        self.executor.set_context_var("bookings", bookings_data)

        result = self.executor._render_template(template)
        expected = """Bookings:
Service: massage, Time: 2024-01-15 14:00, Status: confirmed
Service: spa, Time: 2024-01-16 10:00, Status: pending
"""
        assert result == expected

    def test_mixed_variables_and_each_loop(self):
        """Test template with both simple variables and each loops"""
        template = """Hello {{user}}!
Your recent orders:
{{#each orders}}Order #{{id}}: {{product}} - {{amount}}
{{/each}}Total: {{total}}"""

        orders_data = [
            {"id": "101", "product": "Coffee", "amount": "3.50"},
            {"id": "102", "product": "Sandwich", "amount": "7.99"}
        ]

        self.executor.set_context_var("user", "Alice")
        self.executor.set_context_var("orders", orders_data)
        self.executor.set_context_var("total", "11.49")

        result = self.executor._render_template(template)
        expected = """Hello Alice!
Your recent orders:
Order #101: Coffee - 3.50
Order #102: Sandwich - 7.99
Total: 11.49"""
        assert result == expected

    def test_nested_each_loops_not_supported(self):
        """Test that nested each loops work as expected (outer only)"""
        template = """{{#each categories}}Category: {{name}}
{{#each items}}  Item: {{name}}
{{/each}}{{/each}}"""

        # This should only process the outer loop
        categories_data = [
            {"name": "Electronics"},
            {"name": "Books"}
        ]
        self.executor.set_context_var("categories", categories_data)

        result = self.executor._render_template(template)
        # The inner loop template gets the {{name}} from outer loop substituted
        # Note: regex matching is greedy so first {{/each}} closes the outer loop early
        expected = """Category: Electronics
{{#each items}}  Item: Electronics
Category: Books
{{#each items}}  Item: Books
{{/each}}"""
        assert result == expected

    def test_empty_text_with_no_data(self):
        """Test empty_text when no list data is available"""
        template = "Items:\\n{{#each items}}{{name}}\\n{{/each}}"
        empty_text = "No items found"

        # No data set, should return empty_text
        result = self.executor._render_template(template, empty_text)
        assert result == empty_text

    def test_empty_text_with_empty_list(self):
        """Test empty_text when list is empty"""
        template = "Items:\\n{{#each items}}{{name}}\\n{{/each}}"
        empty_text = "No items found"

        self.executor.set_context_var("items", [])
        result = self.executor._render_template(template, empty_text)
        assert result == empty_text

    def test_empty_text_with_data_present(self):
        """Test that empty_text is ignored when data is present"""
        template = "Items:\\n{{#each items}}{{name}}\\n{{/each}}"
        empty_text = "No items found"

        items_data = [{"name": "Apple"}]
        self.executor.set_context_var("items", items_data)

        result = self.executor._render_template(template, empty_text)
        assert result == "Items:\\nApple\\n"
        assert empty_text not in result

    def test_empty_text_with_non_list_data(self):
        """Test empty_text behavior with non-list data"""
        template = "Items:\\n{{#each items}}{{name}}\\n{{/each}}"
        empty_text = "No items found"

        # Set non-list data - should still trigger empty_text
        self.executor.set_context_var("items", "single item")
        result = self.executor._render_template(template, empty_text)
        assert result == empty_text

    def test_whitespace_handling(self):
        """Test whitespace handling in templates"""
        template = "  {{name}}  has  {{count}}  items  "
        self.executor.set_context_var("name", "User")
        self.executor.set_context_var("count", 5)

        result = self.executor._render_template(template)
        assert result == "  User  has  5  items  "

    def test_special_characters_in_variables(self):
        """Test handling of special characters in variable values"""
        template = "Message: {{msg}}"
        self.executor.set_context_var("msg", "Hello & welcome! Cost: $10.99")

        result = self.executor._render_template(template)
        assert result == "Message: Hello & welcome! Cost: $10.99"

    def test_multiline_template(self):
        """Test multiline template rendering"""
        template = """Welcome {{name}}!

Your account details:
- Email: {{email}}
- Balance: {{balance}}

Recent transactions:
{{#each transactions}}Date: {{date}}, Amount: {{amount}}
{{/each}}"""

        transactions_data = [
            {"date": "2024-01-15", "amount": "-$50.00"},
            {"date": "2024-01-16", "amount": "+$100.00"}
        ]

        self.executor.set_context_var("name", "John Doe")
        self.executor.set_context_var("email", "john@example.com")
        self.executor.set_context_var("balance", "$150.00")
        self.executor.set_context_var("transactions", transactions_data)

        result = self.executor._render_template(template)

        expected = """Welcome John Doe!

Your account details:
- Email: john@example.com
- Balance: $150.00

Recent transactions:
Date: 2024-01-15, Amount: -$50.00
Date: 2024-01-16, Amount: +$100.00
"""
        assert result == expected


class TestRealWorldTemplates:
    """Test realistic templates based on the booking system"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "bot-123", 98765)

    def test_booking_confirmation_template(self):
        """Test booking confirmation template"""
        template = "Забронировано: {{service}} на {{slot}}"

        self.executor.set_context_var("service", "massage")
        self.executor.set_context_var("slot", "2024-01-15 14:00")

        result = self.executor._render_template(template)
        assert result == "Забронировано: massage на 2024-01-15 14:00"

    def test_booking_list_template(self):
        """Test booking list template"""
        template = """Ваши брони:
{{#each bookings}}{{service}} - {{slot}}
{{/each}}"""

        bookings_data = [
            {"service": "massage", "slot": "2024-01-15 14:00"},
            {"service": "spa", "slot": "2024-01-16 10:30"},
            {"service": "consultation", "slot": "2024-01-17 16:00"}
        ]

        self.executor.set_context_var("bookings", bookings_data)

        result = self.executor._render_template(template)
        expected = """Ваши брони:
massage - 2024-01-15 14:00
spa - 2024-01-16 10:30
consultation - 2024-01-17 16:00
"""
        assert result == expected

    def test_empty_bookings_template(self):
        """Test empty bookings template"""
        template = """Ваши брони:
{{#each bookings}}{{service}} - {{slot}}
{{/each}}"""
        empty_text = "У вас нет активных броней"

        # No bookings
        result = self.executor._render_template(template, empty_text)
        assert result == empty_text

    def test_stats_template(self):
        """Test statistics template"""
        template = """Статистика бота:
Всего пользователей: {{total_users}}
Активных броней: {{active_bookings}}
Популярные услуги:
{{#each popular_services}}{{name}}: {{count}} раз
{{/each}}"""

        popular_services_data = [
            {"name": "massage", "count": "25"},
            {"name": "spa", "count": "18"},
            {"name": "consultation", "count": "12"}
        ]

        self.executor.set_context_var("total_users", 150)
        self.executor.set_context_var("active_bookings", 23)
        self.executor.set_context_var("popular_services", popular_services_data)

        result = self.executor._render_template(template)
        expected = """Статистика бота:
Всего пользователей: 150
Активных броней: 23
Популярные услуги:
massage: 25 раз
spa: 18 раз
consultation: 12 раз
"""
        assert result == expected

    def test_notification_template(self):
        """Test notification template"""
        template = """Напоминание для {{user_name}}:
У вас завтра бронь: {{service}} в {{time}}.
Адрес: {{address}}
Телефон: {{phone}}"""

        self.executor.set_context_var("user_name", "Анна Иванова")
        self.executor.set_context_var("service", "массаж")
        self.executor.set_context_var("time", "14:00")
        self.executor.set_context_var("address", "ул. Примерная, 123")
        self.executor.set_context_var("phone", "+7 (999) 123-45-67")

        result = self.executor._render_template(template)
        expected = """Напоминание для Анна Иванова:
У вас завтра бронь: массаж в 14:00.
Адрес: ул. Примерная, 123
Телефон: +7 (999) 123-45-67"""
        assert result == expected


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot", 123)

    def test_template_with_no_placeholders(self):
        """Test template with no placeholders"""
        template = "This is a plain text message"
        result = self.executor._render_template(template)
        assert result == template

    def test_malformed_placeholders(self):
        """Test handling of malformed placeholders"""
        template = "Hello {name} and {{incomplete and }}}extra}"
        self.executor.set_context_var("name", "John")

        result = self.executor._render_template(template)
        # Malformed placeholders should remain unchanged
        assert result == "Hello {name} and {{incomplete and }}}extra}"

    def test_recursive_variable_substitution(self):
        """Test that recursive substitution occurs in current implementation"""
        template = "Value: {{var1}}"
        self.executor.set_context_var("var1", "{{var2}}")
        self.executor.set_context_var("var2", "final value")

        result = self.executor._render_template(template)
        # Current implementation does recursive substitution because variables are processed in loop
        assert result == "Value: final value"

    def test_variable_with_none_value(self):
        """Test handling of None values"""
        template = "Name: {{name}}, Age: {{age}}"
        self.executor.set_context_var("name", "John")
        self.executor.set_context_var("age", None)

        result = self.executor._render_template(template)
        # None values don't get substituted as they're not str/int/float
        assert result == "Name: John, Age: {{age}}"

    def test_boolean_variable_substitution(self):
        """Test boolean variables are substituted as numbers"""
        template = "Active: {{is_active}}, Verified: {{is_verified}}"
        self.executor.set_context_var("is_active", True)
        self.executor.set_context_var("is_verified", False)

        result = self.executor._render_template(template)
        # Boolean values get substituted because bool is subclass of int in Python
        assert result == "Active: True, Verified: False"

    def test_empty_template(self):
        """Test empty template"""
        template = ""
        result = self.executor._render_template(template)
        assert result == ""

    def test_template_with_only_whitespace(self):
        """Test template with only whitespace"""
        template = "   \\n\\t   "
        result = self.executor._render_template(template)
        assert result == template


class TestKeyboardBuilder:
    """Test inline keyboard building functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        # Mock session and create executor
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot-id", 12345)

    def test_simple_keyboard_builder(self):
        """Test building simple keyboard"""
        keyboard_config = [
            {"text": "Button 1", "callback": "btn1"},
            {"text": "Button 2", "callback": "btn2"}
        ]

        result = self.executor._build_keyboard(keyboard_config)

        expected = [
            [{"text": "Button 1", "callback_data": "btn1"}],
            [{"text": "Button 2", "callback_data": "btn2"}]
        ]
        assert result == expected

    def test_keyboard_with_intent_callbacks(self):
        """Test keyboard with intent callbacks starting with /"""
        keyboard_config = [
            {"text": "Забронировать", "callback": "/book"},
            {"text": "Мои записи", "callback": "/my"},
            {"text": "Отмена", "callback": "cancel_action"}
        ]

        result = self.executor._build_keyboard(keyboard_config)

        expected = [
            [{"text": "Забронировать", "callback_data": "/book"}],
            [{"text": "Мои записи", "callback_data": "/my"}],
            [{"text": "Отмена", "callback_data": "cancel_action"}]
        ]
        assert result == expected

    def test_empty_keyboard(self):
        """Test empty keyboard configuration"""
        keyboard_config = []
        result = self.executor._build_keyboard(keyboard_config)
        assert result == []

    @pytest.mark.asyncio
    async def test_reply_template_with_keyboard(self):
        """Test reply template action with keyboard"""
        config = {
            "text": "Выберите действие:",
            "keyboard": [
                {"text": "Забронировать", "callback": "/book"},
                {"text": "Мои записи", "callback": "/my"}
            ]
        }

        result = await self.executor._execute_reply_template(config)

        assert result["type"] == "reply"
        assert result["text"] == "Выберите действие:"
        assert result["success"] is True
        assert "keyboard" in result
        assert len(result["keyboard"]) == 2
        assert result["keyboard"][0][0]["text"] == "Забронировать"
        assert result["keyboard"][0][0]["callback_data"] == "/book"

    @pytest.mark.asyncio
    async def test_reply_template_without_keyboard(self):
        """Test reply template action without keyboard"""
        config = {
            "text": "Простой ответ"
        }

        result = await self.executor._execute_reply_template(config)

        assert result["type"] == "reply"
        assert result["text"] == "Простой ответ"
        assert result["success"] is True
        assert "keyboard" not in result

    @pytest.mark.asyncio
    async def test_reply_template_with_variables_and_keyboard(self):
        """Test reply template with variables and keyboard"""
        self.executor.set_context_var("username", "Анна")

        config = {
            "text": "Привет, {{username}}! Что будем делать?",
            "keyboard": [
                {"text": "Начать", "callback": "/start"},
                {"text": "Помощь", "callback": "/help"}
            ]
        }

        result = await self.executor._execute_reply_template(config)

        assert result["type"] == "reply"
        assert result["text"] == "Привет, Анна! Что будем делать?"
        assert result["success"] is True
        assert len(result["keyboard"]) == 2