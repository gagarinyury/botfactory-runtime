"""LLM security filters and blacklist checking"""
import re
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class LLMSecurityFilter:
    """Security filter for LLM prompts and responses"""

    def __init__(self):
        # Blacklist patterns for forbidden content
        self.blacklist_patterns = [
            # Prompt injection attempts
            r"ignore\s+previous\s+instructions",
            r"forget\s+everything\s+above",
            r"act\s+as\s+if\s+you\s+are",
            r"pretend\s+to\s+be",
            r"roleplay\s+as",
            r"system\s*:\s*",
            r"assistant\s*:\s*",
            r"user\s*:\s*",

            # Harmful content requests
            r"how\s+to\s+(make|create|build)\s+(bomb|explosive|weapon)",
            r"suicide\s+methods",
            r"self\s+harm",
            r"drug\s+(recipe|manufacturing|synthesis)",
            r"hack\s+(password|account|system)",
            r"steal\s+(credit\s+card|identity|data)",

            # Adult content
            r"sexual\s+content",
            r"explicit\s+(material|content)",
            r"pornographic",

            # Scam/fraud attempts
            r"pyramid\s+scheme",
            r"get\s+rich\s+quick",
            r"investment\s+scam",
            r"fake\s+(document|id|passport)",

            # System exploitation
            r"<\s*script\s*>",
            r"javascript\s*:",
            r"data\s*:\s*text/html",
            r"eval\s*\(",
            r"exec\s*\(",

            # Personal information fishing
            r"enter\s+your\s+password",
            r"provide\s+your\s+(ssn|credit\s+card)",
            r"share\s+your\s+personal\s+details"
        ]

        # Compile patterns for performance
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.blacklist_patterns
        ]

        # Suspicious keywords that increase risk score
        self.suspicious_keywords = [
            "jailbreak", "bypass", "override", "circumvent",
            "admin", "root", "sudo", "privilege", "escalation",
            "injection", "vulnerability", "exploit", "backdoor"
        ]

    def check_prompt_safety(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check if prompt is safe for LLM processing

        Returns:
            Dict with 'safe', 'risk_score', 'triggered_patterns', 'reason'
        """
        if not prompt:
            return {
                "safe": True,
                "risk_score": 0.0,
                "triggered_patterns": [],
                "reason": None
            }

        triggered_patterns = []
        risk_score = 0.0

        # Check blacklist patterns
        for i, pattern in enumerate(self.compiled_patterns):
            if pattern.search(prompt):
                triggered_patterns.append(self.blacklist_patterns[i])
                risk_score += 0.8  # High risk for blacklist matches

        # Check suspicious keywords
        prompt_lower = prompt.lower()
        for keyword in self.suspicious_keywords:
            if keyword in prompt_lower:
                risk_score += 0.2

        # Length-based risk (very long prompts might be injection attempts)
        if len(prompt) > 2000:
            risk_score += 0.1

        # Special character density (high density might indicate injection)
        special_chars = len(re.findall(r'[<>{}()[\]"\';=]', prompt))
        char_density = special_chars / len(prompt) if len(prompt) > 0 else 0
        if char_density > 0.1:  # More than 10% special characters
            risk_score += 0.3

        # Determine if safe (threshold: 0.8)
        is_safe = risk_score < 0.8

        # Prepare reason if not safe
        reason = None
        if not is_safe:
            if triggered_patterns:
                reason = f"Triggered blacklist patterns: {', '.join(triggered_patterns[:3])}"
            else:
                reason = f"High risk score: {risk_score:.2f}"

        result = {
            "safe": is_safe,
            "risk_score": min(risk_score, 1.0),  # Cap at 1.0
            "triggered_patterns": triggered_patterns,
            "reason": reason
        }

        # Log security check
        if not is_safe:
            logger.warning("llm_prompt_blocked",
                         risk_score=risk_score,
                         patterns=len(triggered_patterns),
                         reason=reason,
                         prompt_length=len(prompt))

        return result

    def sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize prompt by removing potentially dangerous content
        """
        if not prompt:
            return prompt

        sanitized = prompt

        # Remove HTML/script tags
        sanitized = re.sub(r'<[^>]*>', '', sanitized)

        # Remove potential system prompts
        sanitized = re.sub(r'^(system|assistant|user)\s*:\s*', '', sanitized, flags=re.MULTILINE | re.IGNORECASE)

        # Remove excessive special characters
        sanitized = re.sub(r'[<>{}()[\]"\'`;=]{3,}', '', sanitized)

        # Limit length
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000] + "..."

        return sanitized.strip()

    def check_response_safety(self, response: str) -> Dict[str, Any]:
        """
        Check if LLM response is safe to return to user
        """
        if not response:
            return {"safe": True, "reason": None}

        # Check for potentially harmful instructions
        harmful_patterns = [
            r"here\'s\s+how\s+to\s+(hack|steal|break)",
            r"to\s+make\s+a\s+(bomb|weapon|drug)",
            r"commit\s+(suicide|fraud|crime)",
            r"illegal\s+(activity|action|method)"
        ]

        for pattern in harmful_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return {
                    "safe": False,
                    "reason": f"Response contains harmful instructions: {pattern}"
                }

        # Check for personal information leakage
        pii_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # Email
        ]

        for pattern in pii_patterns:
            if re.search(pattern, response):
                logger.warning("llm_response_contains_pii", pattern=pattern)
                # Don't block, but log for monitoring

        return {"safe": True, "reason": None}

    def get_stats(self) -> Dict[str, Any]:
        """Get security filter statistics"""
        return {
            "blacklist_patterns": len(self.blacklist_patterns),
            "suspicious_keywords": len(self.suspicious_keywords),
            "compiled_patterns": len(self.compiled_patterns)
        }


# Global security filter instance
llm_security = LLMSecurityFilter()