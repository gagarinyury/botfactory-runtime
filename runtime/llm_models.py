"""Pydantic models for LLM JSON responses"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Model for input validation responses"""
    valid: bool = Field(..., description="Whether the input is valid")
    reason: Optional[str] = Field(None, description="Explanation if invalid")
    suggestion: Optional[str] = Field(None, description="Suggested correction if invalid")
    confidence: float = Field(0.95, ge=0.0, le=1.0, description="Confidence score")


class MenuOption(BaseModel):
    """Model for generated menu options"""
    text: str = Field(..., description="Menu option text")
    description: str = Field(..., description="Brief description")
    emoji: Optional[str] = Field(None, description="Optional emoji")


class MenuResponse(BaseModel):
    """Model for menu generation responses"""
    options: List[MenuOption] = Field(..., max_items=5, description="Generated menu options")
    title: Optional[str] = Field(None, description="Suggested menu title")


class IntentClassification(BaseModel):
    """Model for intent classification responses"""
    intent: str = Field(..., description="Detected intent name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")


class ExtractedVariables(BaseModel):
    """Model for variable extraction responses"""
    variables: Dict[str, Optional[str]] = Field(..., description="Extracted variable values")
    confidence: float = Field(0.95, ge=0.0, le=1.0, description="Overall confidence")


class ErrorMessage(BaseModel):
    """Model for friendly error message generation"""
    message: str = Field(..., description="User-friendly error message")
    suggestion: Optional[str] = Field(None, description="What user should do next")
    severity: str = Field("error", description="Error severity: error, warning, info")


class SmartResponse(BaseModel):
    """Model for contextual response generation"""
    text: str = Field(..., description="Generated response text")
    follow_up_suggestions: List[str] = Field(default_factory=list, max_items=3, description="Follow-up suggestions")
    confidence: float = Field(0.9, ge=0.0, le=1.0, description="Response confidence")


# Example usage functions for each model

class LLMModels:
    """Helper class with examples for each model"""

    @staticmethod
    async def validate_user_input(user_input: str, expectation: str) -> ValidationResult:
        """Validate user input using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import BotPromptConfigs

        prompt_config = BotPromptConfigs.smart_validate_input(user_input, expectation)

        return await llm_client.complete_json(
            system=prompt_config["system"],
            user=prompt_config["user"],
            response_model=ValidationResult,
            temperature=0.1,
            max_tokens=150
        )

    @staticmethod
    async def generate_menu(context: str, topic: str) -> MenuResponse:
        """Generate menu options using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import BotPromptConfigs

        prompt_config = BotPromptConfigs.generate_dynamic_menu(context, topic)

        return await llm_client.complete_json(
            system=prompt_config["system"],
            user=prompt_config["user"],
            response_model=MenuResponse,
            temperature=0.4,
            max_tokens=300
        )

    @staticmethod
    async def classify_intent(message: str, available_intents: List[str]) -> IntentClassification:
        """Classify user intent using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import BotPromptConfigs

        prompt_config = BotPromptConfigs.classify_user_intent(message, available_intents)

        return await llm_client.complete_json(
            system=prompt_config["system"],
            user=prompt_config["user"],
            response_model=IntentClassification,
            temperature=0.1,
            max_tokens=100
        )

    @staticmethod
    async def extract_variables(text: str, variables: List[str]) -> ExtractedVariables:
        """Extract variables from text using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import LLMPrompts

        template = LLMPrompts.EXTRACT_VARIABLES
        system, user = LLMPrompts.format_prompt(
            template,
            text=text,
            variables=", ".join(variables)
        )

        return await llm_client.complete_json(
            system=system,
            user=user,
            response_model=ExtractedVariables,
            temperature=0.1,
            max_tokens=150
        )

    @staticmethod
    async def generate_error_message(error: str, context: str) -> ErrorMessage:
        """Generate friendly error message using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import LLMPrompts

        template = LLMPrompts.GENERATE_ERROR_MESSAGE
        system, user = LLMPrompts.format_prompt(
            template,
            error=error,
            context=context
        )

        return await llm_client.complete_json(
            system=system,
            user=user,
            response_model=ErrorMessage,
            temperature=0.3,
            max_tokens=150
        )

    @staticmethod
    async def generate_smart_response(message: str, context: Dict[str, Any], history: List[str] = None) -> SmartResponse:
        """Generate contextual response using LLM JSON mode"""
        from .llm_client import llm_client
        from .llm_prompts import BotPromptConfigs

        prompt_config = BotPromptConfigs.generate_contextual_reply(message, context, history)

        # Modify system prompt for JSON output
        json_system = f"""{prompt_config["system"]}

Respond with JSON containing:
- text: your response message
- follow_up_suggestions: array of 1-3 follow-up questions/actions
- confidence: your confidence score (0.0-1.0)"""

        return await llm_client.complete_json(
            system=json_system,
            user=prompt_config["user"],
            response_model=SmartResponse,
            temperature=0.4,
            max_tokens=250
        )