"""Unit tests for DSL parser and new flow functionality"""
import pytest
from pydantic import ValidationError
from runtime.schemas import BotSpec, Flow, FlowStep, FlowStepValidation, Intent, SqlQueryAction, SqlExecAction, ReplyTemplateAction


class TestBotSpecParser:
    """Test BotSpec parsing and validation"""

    def test_parse_basic_spec_with_intents(self):
        """Test parsing basic spec with intents only"""
        spec_data = {
            "intents": [
                {"cmd": "/start", "reply": "Привет!"},
                {"cmd": "/help", "reply": "Помощь"}
            ]
        }

        bot_spec = BotSpec(**spec_data)

        assert bot_spec.intents is not None
        assert len(bot_spec.intents) == 2
        assert bot_spec.intents[0].cmd == "/start"
        assert bot_spec.intents[0].reply == "Привет!"
        assert bot_spec.flows is None
        assert bot_spec.use is None

    def test_parse_spec_with_use_components(self):
        """Test parsing spec with 'use' components"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"],
            "intents": [{"cmd": "/start", "reply": "Start"}]
        }

        bot_spec = BotSpec(**spec_data)

        assert bot_spec.use is not None
        assert len(bot_spec.use) == 3
        assert "flow.wizard.v1" in bot_spec.use
        assert "action.sql_exec.v1" in bot_spec.use
        assert "action.sql_query.v1" in bot_spec.use

    def test_parse_spec_with_flows(self):
        """Test parsing spec with flows section"""
        spec_data = {
            "use": ["flow.wizard.v1"],
            "flows": [
                {
                    "entry_cmd": "/book",
                    "steps": [
                        {"ask": "Какая услуга?", "var": "service"},
                        {"ask": "Когда?", "var": "time", "validate": {"regex": "^\\d{2}:\\d{2}$", "msg": "Формат HH:MM"}}
                    ]
                }
            ]
        }

        bot_spec = BotSpec(**spec_data)

        assert bot_spec.flows is not None
        assert len(bot_spec.flows) == 1

        flow = bot_spec.flows[0]
        assert flow.entry_cmd == "/book"
        assert flow.steps is not None
        assert len(flow.steps) == 2

        # Test first step
        step1 = flow.steps[0]
        assert step1.ask == "Какая услуга?"
        assert step1.var == "service"
        assert step1.validate is None

        # Test second step with validation
        step2 = flow.steps[1]
        assert step2.ask == "Когда?"
        assert step2.var == "time"
        assert step2.validate is not None
        assert step2.validate.regex == "^\\d{2}:\\d{2}$"
        assert step2.validate.msg == "Формат HH:MM"

    def test_parse_flow_with_actions(self):
        """Test parsing flow with action handlers"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1"],
            "flows": [
                {
                    "entry_cmd": "/book",
                    "on_enter": [
                        {"action.sql_query.v1": {"sql": "SELECT * FROM services", "result_var": "services"}}
                    ],
                    "on_complete": [
                        {"action.sql_exec.v1": {"sql": "INSERT INTO bookings(service) VALUES(:service)"}},
                        {"action.reply_template.v1": {"text": "Забронировано: {{service}}"}}
                    ]
                }
            ]
        }

        bot_spec = BotSpec(**spec_data)

        assert bot_spec.flows is not None
        flow = bot_spec.flows[0]

        assert flow.on_enter is not None
        assert len(flow.on_enter) == 1
        assert "action.sql_query.v1" in flow.on_enter[0]

        assert flow.on_complete is not None
        assert len(flow.on_complete) == 2
        assert "action.sql_exec.v1" in flow.on_complete[0]
        assert "action.reply_template.v1" in flow.on_complete[1]

    def test_empty_spec(self):
        """Test parsing empty spec"""
        spec_data = {}

        bot_spec = BotSpec(**spec_data)

        assert bot_spec.use is None
        assert bot_spec.intents is None
        assert bot_spec.flows is None

    def test_spec_with_all_sections(self):
        """Test parsing complete spec with all sections"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"],
            "intents": [
                {"cmd": "/start", "reply": "Добро пожаловать!"}
            ],
            "flows": [
                {
                    "entry_cmd": "/book",
                    "steps": [
                        {"ask": "Услуга?", "var": "service", "validate": {"regex": "^(massage|spa)$", "msg": "Выберите: massage или spa"}}
                    ],
                    "on_complete": [
                        {"action.sql_exec.v1": {"sql": "INSERT INTO bookings(service) VALUES(:service)"}}
                    ]
                }
            ]
        }

        bot_spec = BotSpec(**spec_data)

        # All sections should be parsed
        assert bot_spec.use is not None
        assert len(bot_spec.use) == 3
        assert bot_spec.intents is not None
        assert len(bot_spec.intents) == 1
        assert bot_spec.flows is not None
        assert len(bot_spec.flows) == 1


class TestFlowStepValidation:
    """Test FlowStep validation parsing"""

    def test_flow_step_without_validation(self):
        """Test parsing flow step without validation"""
        step_data = {"ask": "Введите имя", "var": "name"}

        step = FlowStep(**step_data)

        assert step.ask == "Введите имя"
        assert step.var == "name"
        assert step.validate is None

    def test_flow_step_with_validation(self):
        """Test parsing flow step with regex validation"""
        step_data = {
            "ask": "Введите email",
            "var": "email",
            "validate": {
                "regex": "^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}$",
                "msg": "Неправильный формат email"
            }
        }

        step = FlowStep(**step_data)

        assert step.ask == "Введите email"
        assert step.var == "email"
        assert step.validate is not None
        assert step.validate.regex == "^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}$"
        assert step.validate.msg == "Неправильный формат email"

    def test_invalid_flow_step_missing_fields(self):
        """Test that missing required fields raise validation error"""
        with pytest.raises(ValidationError):
            FlowStep(ask="Вопрос")  # missing 'var'

        with pytest.raises(ValidationError):
            FlowStep(var="variable")  # missing 'ask'

    def test_invalid_validation_missing_fields(self):
        """Test that validation requires both regex and msg"""
        step_data = {
            "ask": "Вопрос",
            "var": "answer",
            "validate": {"regex": "\\d+"}  # missing 'msg'
        }

        with pytest.raises(ValidationError):
            FlowStep(**step_data)


class TestActionParsing:
    """Test action parsing and validation"""

    def test_sql_query_action(self):
        """Test SqlQueryAction parsing"""
        action_data = {
            "sql": "SELECT * FROM users WHERE bot_id=:bot_id",
            "result_var": "users"
        }

        action = SqlQueryAction(**action_data)

        assert action.sql == "SELECT * FROM users WHERE bot_id=:bot_id"
        assert action.result_var == "users"

    def test_sql_exec_action(self):
        """Test SqlExecAction parsing"""
        action_data = {
            "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES(:bot_id, :user_id, :service)"
        }

        action = SqlExecAction(**action_data)

        assert action.sql == "INSERT INTO bookings(bot_id, user_id, service) VALUES(:bot_id, :user_id, :service)"

    def test_reply_template_action(self):
        """Test ReplyTemplateAction parsing"""
        action_data = {
            "text": "Ваши брони:\\n{{#each bookings}}{{service}} - {{time}}\\n{{/each}}",
            "empty_text": "У вас нет броней"
        }

        action = ReplyTemplateAction(**action_data)

        assert action.text == "Ваши брони:\\n{{#each bookings}}{{service}} - {{time}}\\n{{/each}}"
        assert action.empty_text == "У вас нет броней"

    def test_reply_template_action_without_empty_text(self):
        """Test ReplyTemplateAction without empty_text"""
        action_data = {
            "text": "Результат: {{result}}"
        }

        action = ReplyTemplateAction(**action_data)

        assert action.text == "Результат: {{result}}"
        assert action.empty_text is None

    def test_invalid_actions_missing_required_fields(self):
        """Test that actions require their mandatory fields"""
        # SqlQueryAction missing result_var
        with pytest.raises(ValidationError):
            SqlQueryAction(sql="SELECT 1")

        # SqlQueryAction missing sql
        with pytest.raises(ValidationError):
            SqlQueryAction(result_var="result")

        # SqlExecAction missing sql
        with pytest.raises(ValidationError):
            SqlExecAction()

        # ReplyTemplateAction missing text
        with pytest.raises(ValidationError):
            ReplyTemplateAction(empty_text="Empty")


class TestComplexFlowParsing:
    """Test parsing complex realistic flow specifications"""

    def test_booking_flow_spec(self):
        """Test parsing realistic booking flow spec"""
        spec_data = {
            "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"],
            "flows": [
                {
                    "entry_cmd": "/book",
                    "steps": [
                        {
                            "ask": "Какая услуга?",
                            "var": "service",
                            "validate": {
                                "regex": "^(massage|spa|consultation)$",
                                "msg": "Выберите: massage, spa, consultation"
                            }
                        },
                        {
                            "ask": "Когда удобно? (YYYY-MM-DD HH:MM)",
                            "var": "slot",
                            "validate": {
                                "regex": "^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$",
                                "msg": "Формат: 2024-01-15 14:00"
                            }
                        }
                    ],
                    "on_complete": [
                        {
                            "action.sql_exec.v1": {
                                "sql": "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"
                            }
                        },
                        {
                            "action.reply_template.v1": {
                                "text": "Забронировано: {{service}} на {{slot}}"
                            }
                        }
                    ]
                },
                {
                    "entry_cmd": "/my",
                    "on_enter": [
                        {
                            "action.sql_query.v1": {
                                "sql": "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5",
                                "result_var": "bookings"
                            }
                        },
                        {
                            "action.reply_template.v1": {
                                "text": "Ваши брони:\\n{{#each bookings}}{{service}} - {{slot}}\\n{{/each}}",
                                "empty_text": "У вас нет активных броней"
                            }
                        }
                    ]
                }
            ]
        }

        bot_spec = BotSpec(**spec_data)

        # Verify overall structure
        assert len(bot_spec.flows) == 2
        assert len(bot_spec.use) == 3

        # Verify booking flow
        book_flow = bot_spec.flows[0]
        assert book_flow.entry_cmd == "/book"
        assert len(book_flow.steps) == 2
        assert len(book_flow.on_complete) == 2

        # Verify my flow (no steps, only on_enter)
        my_flow = bot_spec.flows[1]
        assert my_flow.entry_cmd == "/my"
        assert my_flow.steps is None
        assert len(my_flow.on_enter) == 2

    def test_multiple_flows_different_patterns(self):
        """Test parsing multiple flows with different step patterns"""
        spec_data = {
            "flows": [
                {
                    "entry_cmd": "/simple",
                    "on_enter": [
                        {"action.reply_template.v1": {"text": "Simple response"}}
                    ]
                },
                {
                    "entry_cmd": "/wizard",
                    "steps": [
                        {"ask": "Question 1", "var": "var1"},
                        {"ask": "Question 2", "var": "var2", "validate": {"regex": "yes|no", "msg": "Answer yes or no"}}
                    ],
                    "on_step": [
                        {"action.reply_template.v1": {"text": "Step processed"}}
                    ],
                    "on_complete": [
                        {"action.reply_template.v1": {"text": "Wizard complete: {{var1}}, {{var2}}"}}
                    ]
                },
                {
                    "entry_cmd": "/immediate",
                    "on_enter": [
                        {"action.sql_query.v1": {"sql": "SELECT count(*) as cnt FROM stats", "result_var": "stats"}},
                        {"action.reply_template.v1": {"text": "Count: {{stats.cnt}}"}}
                    ]
                }
            ]
        }

        bot_spec = BotSpec(**spec_data)

        assert len(bot_spec.flows) == 3

        # Simple flow
        simple_flow = bot_spec.flows[0]
        assert simple_flow.entry_cmd == "/simple"
        assert simple_flow.steps is None
        assert simple_flow.on_enter is not None

        # Wizard flow
        wizard_flow = bot_spec.flows[1]
        assert wizard_flow.entry_cmd == "/wizard"
        assert len(wizard_flow.steps) == 2
        assert wizard_flow.on_step is not None
        assert wizard_flow.on_complete is not None

        # Immediate flow
        immediate_flow = bot_spec.flows[2]
        assert immediate_flow.entry_cmd == "/immediate"
        assert immediate_flow.steps is None
        assert len(immediate_flow.on_enter) == 2