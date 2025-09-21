"""LLM prompt templates for NLU tasks"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
import re


@dataclass
class PromptTemplate:
    """Template for LLM prompts"""
    system: str
    user_template: str
    temperature: float = 0.2
    max_tokens: int = 256
    response_format: str = "text"  # "text" or "json"


class LLMPrompts:
    """Collection of prompt templates for different NLU tasks"""

    # Text improvement and reformulation
    IMPROVE_TEXT = PromptTemplate(
        system="""Ты помощник для улучшения текстов ботов. Твоя задача - сделать текст более дружелюбным, понятным и полезным для пользователя.

Правила:
- Сохраняй основной смысл
- Делай текст более живым и человечным
- Используй эмодзи умеренно
- Избегай канцеляризмов
- Отвечай только улучшенным текстом, без объяснений""",
        user_template="Улучши этот текст: {text}",
        temperature=0.3,
        max_tokens=200
    )

    # Smart validation for wizard inputs
    VALIDATE_INPUT = PromptTemplate(
        system="""Ты валидатор ввода для ботов. Проверь, соответствует ли ввод пользователя ожиданиям.

Отвечай только JSON:
{
  "valid": true/false,
  "reason": "объяснение при invalid",
  "suggestion": "предложение исправления при invalid"
}""",
        user_template="Ожидание: {expectation}\nВвод пользователя: {input}",
        temperature=0.1,
        max_tokens=150,
        response_format="json"
    )

    # Generate menu suggestions
    GENERATE_MENU = PromptTemplate(
        system="""Ты генератор меню для ботов. Создай список опций меню на основе контекста.

Отвечай только JSON массивом:
[
  {"text": "Название опции", "description": "Краткое описание"},
  ...
]

Максимум 5 опций. Используй понятные названия и эмодзи.""",
        user_template="Контекст: {context}\nТема: {topic}",
        temperature=0.4,
        max_tokens=300,
        response_format="json"
    )

    # Intent classification
    CLASSIFY_INTENT = PromptTemplate(
        system="""Ты классификатор намерений пользователя. Определи, что хочет пользователь.

Доступные интенты: {intents}

Отвечай только JSON:
{
  "intent": "название_интента",
  "confidence": 0.95,
  "entities": {"entity_name": "value"}
}""",
        user_template="Сообщение пользователя: {message}",
        temperature=0.1,
        max_tokens=100,
        response_format="json"
    )

    # Generate contextual responses
    CONTEXTUAL_RESPONSE = PromptTemplate(
        system="""Ты умный ассистент бота. Сгенерируй подходящий ответ на основе контекста диалога.

Правила:
- Учитывай историю диалога
- Будь полезным и дружелюбным
- Используй информацию из контекста
- Отвечай кратко и по делу""",
        user_template="""Контекст: {context}
История: {history}
Текущее сообщение: {message}

Ответь пользователю:""",
        temperature=0.4,
        max_tokens=200
    )

    # Smart template variable extraction
    EXTRACT_VARIABLES = PromptTemplate(
        system="""Ты извлекатель переменных из текста. Найди в тексте значения указанных переменных.

Отвечай только JSON:
{
  "variable1": "значение1",
  "variable2": "значение2",
  "confidence": 0.95
}

Если переменная не найдена, используй null.""",
        user_template="Переменные: {variables}\nТекст: {text}",
        temperature=0.1,
        max_tokens=150,
        response_format="json"
    )

    # Generate FAQ answers
    FAQ_ANSWER = PromptTemplate(
        system="""Ты помощник для ответов на частые вопросы. Сгенерируй полезный ответ на основе базы знаний.

Правила:
- Используй только информацию из базы знаний
- Если информации нет, честно скажи об этом
- Будь конкретным и полезным
- Предложи альтернативы если возможно""",
        user_template="""База знаний: {knowledge_base}
Вопрос пользователя: {question}

Ответ:""",
        temperature=0.3,
        max_tokens=250
    )

    # Smart error messages
    GENERATE_ERROR_MESSAGE = PromptTemplate(
        system="""Ты генератор дружелюбных сообщений об ошибках. Преврати техническую ошибку в понятное пользователю сообщение.

Правила:
- Объясни простыми словами что произошло
- Предложи что делать дальше
- Будь сочувствующим, но не извиняйся слишком много
- Используй позитивный тон""",
        user_template="Техническая ошибка: {error}\nКонтекст: {context}",
        temperature=0.3,
        max_tokens=150
    )

    @classmethod
    def get_template(cls, template_name: str) -> Optional[PromptTemplate]:
        """Get prompt template by name"""
        return getattr(cls, template_name.upper(), None)

    @classmethod
    def list_templates(cls) -> List[str]:
        """List all available template names"""
        templates = []
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and attr_name.isupper():
                attr = getattr(cls, attr_name)
                if isinstance(attr, PromptTemplate):
                    templates.append(attr_name.lower())
        return templates

    @classmethod
    def format_prompt(cls, template: PromptTemplate, **kwargs) -> tuple[str, str]:
        """Format prompt template with variables"""
        try:
            system = template.system.format(**kwargs)
            user = template.user_template.format(**kwargs)
            return system, user
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")

    @classmethod
    def parse_json_response(cls, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        try:
            # Clean response - remove markdown, extra text
            cleaned = response.strip()

            # Find JSON in response
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)

            # Handle array responses
            if cleaned.startswith('['):
                return {"items": json.loads(cleaned)}

            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")

    @classmethod
    def validate_response_format(cls, response: str, expected_format: str) -> bool:
        """Validate response format"""
        if expected_format == "text":
            return len(response.strip()) > 0
        elif expected_format == "json":
            try:
                cls.parse_json_response(response)
                return True
            except ValueError:
                return False
        return False


# Predefined prompt configurations for common bot tasks
class BotPromptConfigs:
    """Ready-to-use prompt configurations for bot scenarios"""

    @staticmethod
    def improve_bot_message(original_text: str, llm_style: str = "neutral") -> Dict[str, Any]:
        """Improve bot message text with specified style"""

        # Style-specific system prompts
        style_prompts = {
            "short": """Ты помощник для улучшения текстов ботов. Твоя задача - сделать текст более кратким и ёмким.

Правила:
- Сохраняй основной смысл
- Убирай лишние слова
- Делай текст максимально коротким
- Используй эмодзи очень умеренно
- Отвечай только улучшенным текстом, без объяснений""",

            "neutral": """Ты помощник для улучшения текстов ботов. Твоя задача - сделать текст более дружелюбным, понятным и полезным для пользователя.

Правила:
- Сохраняй основной смысл
- Делай текст более живым и человечным
- Используй эмодзи умеренно
- Избегай канцеляризмов
- Отвечай только улучшенным текстом, без объяснений""",

            "detailed": """Ты помощник для улучшения текстов ботов. Твоя задача - сделать текст более подробным и информативным.

Правила:
- Сохраняй основной смысл
- Добавляй полезные детали и контекст
- Делай текст более живым и человечным
- Используй эмодзи для улучшения восприятия
- Отвечай только улучшенным текстом, без объяснений"""
        }

        # Max tokens by style
        style_max_tokens = {
            "short": 100,
            "neutral": 200,
            "detailed": 300
        }

        system_prompt = style_prompts.get(llm_style, style_prompts["neutral"])
        max_tokens = style_max_tokens.get(llm_style, 200)

        return {
            "system": system_prompt,
            "user": f"Улучши этот текст: {original_text}",
            "temperature": 0.3,
            "max_tokens": max_tokens
        }

    @staticmethod
    def smart_validate_input(user_input: str, expectation: str) -> Dict[str, Any]:
        """Validate user input with AI"""
        template = LLMPrompts.VALIDATE_INPUT
        system, user = LLMPrompts.format_prompt(
            template,
            input=user_input,
            expectation=expectation
        )

        return {
            "system": system,
            "user": user,
            "temperature": template.temperature,
            "max_tokens": template.max_tokens
        }

    @staticmethod
    def generate_dynamic_menu(context: str, topic: str) -> Dict[str, Any]:
        """Generate menu options based on context"""
        template = LLMPrompts.GENERATE_MENU
        system, user = LLMPrompts.format_prompt(
            template,
            context=context,
            topic=topic
        )

        return {
            "system": system,
            "user": user,
            "temperature": template.temperature,
            "max_tokens": template.max_tokens
        }

    @staticmethod
    def classify_user_intent(message: str, available_intents: List[str]) -> Dict[str, Any]:
        """Classify user intent"""
        template = LLMPrompts.CLASSIFY_INTENT
        intents_str = ", ".join(available_intents)
        system, user = LLMPrompts.format_prompt(
            template,
            message=message,
            intents=intents_str
        )

        return {
            "system": system,
            "user": user,
            "temperature": template.temperature,
            "max_tokens": template.max_tokens
        }

    @staticmethod
    def generate_contextual_reply(message: str, context: Dict[str, Any], history: List[str] = None) -> Dict[str, Any]:
        """Generate smart contextual response"""
        template = LLMPrompts.CONTEXTUAL_RESPONSE
        history_str = "\n".join(history[-3:]) if history else "Нет истории"
        context_str = json.dumps(context, ensure_ascii=False, indent=2)

        system, user = LLMPrompts.format_prompt(
            template,
            message=message,
            context=context_str,
            history=history_str
        )

        return {
            "system": system,
            "user": user,
            "temperature": template.temperature,
            "max_tokens": template.max_tokens
        }