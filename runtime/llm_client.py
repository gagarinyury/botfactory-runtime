"""LLM client for local 3B model with OpenAI-compatible API"""
import os
import hashlib
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Union, Type
from dataclasses import dataclass
from time import perf_counter
import structlog
import json
from .circuit_breaker import with_circuit_breaker, CircuitBreakerError
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger()


@dataclass
class LLMConfig:
    """LLM service configuration"""
    base_url: str = "http://llm:11434"
    model: str = "microsoft/Phi-3-mini-4k-instruct"
    timeout: int = 30
    max_retries: int = 3
    temperature: float = 0.2
    max_tokens: int = 256
    top_p: float = 0.9
    enabled: bool = True


@dataclass
class LLMResponse:
    """Standardized LLM response"""
    content: str
    usage: Dict[str, int]
    model: str
    cached: bool = False
    duration_ms: int = 0


class LLMClient:
    """Local LLM client with caching and error handling"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._session: Optional[aiohttp.ClientSession] = None

        # Load from environment
        self.config.base_url = os.getenv("LLM_BASE_URL", self.config.base_url)
        self.config.model = os.getenv("LLM_MODEL", self.config.model)
        self.config.enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
        self.config.timeout = int(os.getenv("LLM_TIMEOUT", str(self.config.timeout)))

    async def _with_circuit_breaker(self, bot_id: str, coro):
        """Wrapper to apply circuit breaker to LLM calls"""
        try:
            return await with_circuit_breaker(bot_id, coro)
        except CircuitBreakerError as e:
            logger.warning("llm_circuit_breaker_open",
                         bot_id=bot_id,
                         state=e.state.value)
            # Return fallback response
            return LLMResponse(
                content="⚠️ Service temporarily unavailable. Please try again later.",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                model=self.config.model,
                duration_ms=0,
                cached=False,
                error="circuit_breaker_open"
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _hash_prompt(self, system: str, user: str, **kwargs) -> str:
        """Create hash for caching"""
        content = f"{system}|{user}|{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    async def _get_from_cache(self, cache_key: str) -> Optional[LLMResponse]:
        """Get response from cache"""
        try:
            from .redis_client import redis_client
            cached = await redis_client.get(f"llm:cache:{cache_key}")
            if cached:
                data = json.loads(cached)
                response = LLMResponse(**data)
                response.cached = True
                logger.info("llm_cache_hit", cache_key=cache_key[:8])
                return response
        except Exception as e:
            logger.warning("llm_cache_get_error", error=str(e))
        return None

    async def _set_cache(self, cache_key: str, response: LLMResponse, ttl: int = 900):
        """Set response in cache (15 min default TTL)"""
        try:
            from .redis_client import redis_client
            # Don't cache the cached flag
            cache_data = {
                "content": response.content,
                "usage": response.usage,
                "model": response.model,
                "duration_ms": response.duration_ms
            }
            await redis_client.setex(
                f"llm:cache:{cache_key}",
                ttl,
                json.dumps(cache_data)
            )
            logger.info("llm_cache_set", cache_key=cache_key[:8], ttl=ttl)
        except Exception as e:
            logger.warning("llm_cache_set_error", error=str(e))

    async def complete(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        use_cache: bool = True,
        bot_id: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> LLMResponse:
        """
        Generate completion using chat format

        Args:
            system: System message/prompt
            user: User message/query
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            tools: Tool definitions for function calling
            use_cache: Whether to use caching
            bot_id: Bot ID for rate limiting
            user_id: User ID for rate limiting

        Returns:
            LLMResponse with generated content
        """
        if not self.config.enabled:
            raise RuntimeError("LLM service is disabled")

        # Security check: filter prompt for blacklisted content
        from .llm_security import llm_security

        # Check system prompt safety
        system_check = llm_security.check_prompt_safety(system, {"type": "system"})
        if not system_check["safe"]:
            logger.warning("llm_system_prompt_blocked",
                         reason=system_check["reason"],
                         risk_score=system_check["risk_score"])
            raise ValueError(f"System prompt blocked: {system_check['reason']}")

        # Check user prompt safety
        user_check = llm_security.check_prompt_safety(user, {"type": "user"})
        if not user_check["safe"]:
            logger.warning("llm_user_prompt_blocked",
                         reason=user_check["reason"],
                         risk_score=user_check["risk_score"])
            raise ValueError(f"User prompt blocked: {user_check['reason']}")

        # Check rate limits if bot_id and user_id provided
        if bot_id and user_id:
            await self._check_rate_limit(bot_id, user_id)

        start_time = perf_counter()

        # Build request parameters
        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

        # Check cache first
        cache_key = None
        if use_cache and not tools:  # Don't cache tool calls
            cache_key = self._hash_prompt(system, user, temperature=temp, max_tokens=max_tok)
            cached_response = await self._get_from_cache(cache_key)
            if cached_response:
                # Record cache hit metrics
                from .telemetry import llm_requests_total, llm_latency_ms, llm_cache_hits_total
                llm_requests_total.labels("chat_completion", "success").inc()
                llm_latency_ms.labels("chat_completion", "true").observe(cached_response.duration_ms)
                llm_cache_hits_total.labels(self.config.model).inc()
                return cached_response

        # Prepare messages
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        # Build request payload
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tok,
            "top_p": self.config.top_p,
            "stream": False
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Make request with retries
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                session = await self._get_session()
                url = f"{self.config.base_url}/v1/chat/completions"

                logger.info("llm_request",
                           attempt=attempt + 1,
                           system_len=len(system),
                           user_len=len(user),
                           model=self.config.model,
                           max_tokens=max_tok)

                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        duration_ms = int((perf_counter() - start_time) * 1000)

                        # Extract response
                        choice = data["choices"][0]
                        content = choice["message"]["content"]
                        usage = data.get("usage", {})

                        response = LLMResponse(
                            content=content,
                            usage=usage,
                            model=self.config.model,
                            duration_ms=duration_ms
                        )

                        # Cache successful response
                        if use_cache and cache_key and not tools:
                            await self._set_cache(cache_key, response)

                        # Record success metrics
                        from .telemetry import llm_requests_total, llm_latency_ms, llm_tokens_total
                        llm_requests_total.labels("chat_completion", "success").inc()
                        llm_latency_ms.labels("chat_completion", "false").observe(duration_ms)
                        llm_tokens_total.labels(self.config.model, "input").inc(usage.get("prompt_tokens", 0))
                        llm_tokens_total.labels(self.config.model, "output").inc(usage.get("completion_tokens", 0))

                        # Record token usage for budget tracking
                        if bot_id:
                            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                            await self._record_token_usage(bot_id, total_tokens)

                        logger.info("llm_success",
                                   duration_ms=duration_ms,
                                   input_tokens=usage.get("prompt_tokens", 0),
                                   output_tokens=usage.get("completion_tokens", 0))

                        return response
                    else:
                        error_text = await resp.text()
                        last_error = f"HTTP {resp.status}: {error_text}"
                        logger.warning("llm_http_error",
                                     status=resp.status,
                                     error=error_text,
                                     attempt=attempt + 1)

            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning("llm_timeout", attempt=attempt + 1)
            except Exception as e:
                last_error = str(e)
                logger.warning("llm_request_error", error=str(e), attempt=attempt + 1)

            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # All retries failed
        duration_ms = int((perf_counter() - start_time) * 1000)
        logger.error("llm_failed",
                    error=last_error,
                    duration_ms=duration_ms,
                    retries=self.config.max_retries)

        # Record metrics
        from .telemetry import llm_requests_total, llm_errors_total
        llm_requests_total.labels("chat_completion", "failed").inc()
        llm_errors_total.labels(self.config.model, "request_failed").inc()

        raise RuntimeError(f"LLM request failed after {self.config.max_retries} retries: {last_error}")

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> LLMResponse:
        """
        Generate text completion using completions format

        Args:
            prompt: Input prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            use_cache: Whether to use caching

        Returns:
            LLMResponse with generated content
        """
        if not self.config.enabled:
            raise RuntimeError("LLM service is disabled")

        start_time = perf_counter()

        # Build request parameters
        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

        # Check cache first
        cache_key = None
        if use_cache:
            cache_key = self._hash_prompt("", prompt, temperature=temp, max_tokens=max_tok)
            cached_response = await self._get_from_cache(cache_key)
            if cached_response:
                return cached_response

        # Build request payload
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "temperature": temp,
            "max_tokens": max_tok,
            "top_p": self.config.top_p,
            "stream": False
        }

        # Make request with retries
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                session = await self._get_session()
                url = f"{self.config.base_url}/v1/completions"

                logger.info("llm_generate",
                           attempt=attempt + 1,
                           prompt_len=len(prompt),
                           model=self.config.model,
                           max_tokens=max_tok)

                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        duration_ms = int((perf_counter() - start_time) * 1000)

                        # Extract response
                        choice = data["choices"][0]
                        content = choice["text"].strip()
                        usage = data.get("usage", {})

                        response = LLMResponse(
                            content=content,
                            usage=usage,
                            model=self.config.model,
                            duration_ms=duration_ms
                        )

                        # Cache successful response
                        if use_cache and cache_key:
                            await self._set_cache(cache_key, response)

                        # Record token usage for budget tracking
                        if bot_id:
                            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                            await self._record_token_usage(bot_id, total_tokens)

                        logger.info("llm_generate_success",
                                   duration_ms=duration_ms,
                                   input_tokens=usage.get("prompt_tokens", 0),
                                   output_tokens=usage.get("completion_tokens", 0))

                        return response
                    else:
                        error_text = await resp.text()
                        last_error = f"HTTP {resp.status}: {error_text}"
                        logger.warning("llm_http_error",
                                     status=resp.status,
                                     error=error_text,
                                     attempt=attempt + 1)

            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning("llm_timeout", attempt=attempt + 1)
            except Exception as e:
                last_error = str(e)
                logger.warning("llm_request_error", error=str(e), attempt=attempt + 1)

            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # All retries failed
        duration_ms = int((perf_counter() - start_time) * 1000)
        logger.error("llm_generate_failed",
                    error=last_error,
                    duration_ms=duration_ms,
                    retries=self.config.max_retries)

        # Record metrics
        from .telemetry import llm_requests_total, llm_errors_total
        llm_requests_total.labels("completion", "failed").inc()
        llm_errors_total.labels(self.config.model, "request_failed").inc()

        raise RuntimeError(f"LLM request failed after {self.config.max_retries} retries: {last_error}")

    async def _check_rate_limit(self, bot_id: str, user_id: int):
        """Check rate limits and budget limits for LLM requests"""
        try:
            from .redis_client import redis_client
            import time

            # 1. Rate limits: 10 requests per minute per user
            rate_limit_key = f"llm:ratelimit:{bot_id}:{user_id}"
            current_time = int(time.time())
            window_start = current_time - 60  # 1 minute window

            # Get current request count in window
            try:
                current_count = await redis_client.get(rate_limit_key)
                current_count = int(current_count) if current_count else 0
            except:
                current_count = 0

            if current_count >= 10:  # Max 10 requests per minute
                logger.warning("llm_rate_limit_exceeded",
                              bot_id=bot_id,
                              user_id=user_id,
                              current_count=current_count)

                from .telemetry import llm_errors_total, llm_budget_limits_hit_total
                llm_errors_total.labels(self.config.model, "rate_limit_exceeded").inc()
                llm_budget_limits_hit_total.labels(bot_id, "rate_limit").inc()

                raise RuntimeError("LLM rate limit exceeded. Please try again later.")

            # 2. Budget limits: Check daily token budget for bot
            daily_budget_limit = await self._get_bot_budget_limit(bot_id)
            if daily_budget_limit > 0:  # 0 means unlimited
                current_usage = await redis_client.get_daily_budget_usage(bot_id)
                if current_usage >= daily_budget_limit:
                    logger.warning("llm_budget_limit_exceeded",
                                  bot_id=bot_id,
                                  current_usage=current_usage,
                                  daily_limit=daily_budget_limit)
                    from .telemetry import llm_errors_total, llm_budget_limits_hit_total
                    llm_errors_total.labels(self.config.model, "budget_limit_exceeded").inc()
                    llm_budget_limits_hit_total.labels(bot_id, "daily_budget").inc()
                    raise RuntimeError("Daily LLM budget limit exceeded. Please try again tomorrow.")

            # Increment rate limit counter with expiration
            await redis_client.setex(rate_limit_key, 60, current_count + 1)

        except RuntimeError:
            raise  # Re-raise rate limit and budget errors
        except Exception as e:
            logger.warning("llm_limits_check_failed", error=str(e))
            # Don't block on limit check failures

    async def _get_bot_budget_limit(self, bot_id: str) -> int:
        """Get daily budget limit for bot from database"""
        try:
            from .main import async_session
            from sqlalchemy import text

            async with async_session() as session:
                result = await session.execute(
                    text("SELECT daily_budget_limit FROM bots WHERE id = :bot_id"),
                    {"bot_id": bot_id}
                )
                row = result.fetchone()
                return row[0] if row else 10000  # Default 10k tokens/day

        except Exception as e:
            logger.error("bot_budget_limit_get_failed", bot_id=bot_id, error=str(e))
            return 10000  # Fail safe with default limit

    async def _record_token_usage(self, bot_id: str, tokens_used: int):
        """Record token usage for budget tracking"""
        try:
            from .redis_client import redis_client
            new_total = await redis_client.increment_daily_budget_usage(bot_id, tokens_used)

            logger.debug("llm_tokens_recorded",
                        bot_id=bot_id,
                        tokens_used=tokens_used,
                        daily_total=new_total)

            # Update metrics
            from .telemetry import llm_tokens_total, llm_budget_usage_total
            llm_tokens_total.labels(bot_id, "completion").inc(tokens_used)
            llm_budget_usage_total.labels(bot_id).inc(tokens_used)

        except Exception as e:
            logger.error("token_usage_record_failed", bot_id=bot_id, tokens=tokens_used, error=str(e))

    async def complete_json(
        self,
        system: str,
        user: str,
        response_model: Type[BaseModel],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        use_cache: bool = True,
        bot_id: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> BaseModel:
        """
        Generate JSON completion with strict Pydantic validation

        Args:
            system: System message/prompt
            user: User message/query
            response_model: Pydantic model class for response validation
            temperature: Sampling temperature (lower for JSON tasks)
            max_tokens: Maximum tokens to generate
            max_retries: Number of validation retries
            use_cache: Whether to use caching
            bot_id: Bot ID for rate limiting
            user_id: User ID for rate limiting

        Returns:
            Validated Pydantic model instance
        """
        # Security check for JSON completion
        from .llm_security import llm_security

        # Check both prompts for safety
        system_check = llm_security.check_prompt_safety(system, {"type": "system", "mode": "json"})
        if not system_check["safe"]:
            logger.warning("llm_json_system_prompt_blocked",
                         reason=system_check["reason"],
                         risk_score=system_check["risk_score"])
            raise ValueError(f"JSON system prompt blocked: {system_check['reason']}")

        user_check = llm_security.check_prompt_safety(user, {"type": "user", "mode": "json"})
        if not user_check["safe"]:
            logger.warning("llm_json_user_prompt_blocked",
                         reason=user_check["reason"],
                         risk_score=user_check["risk_score"])
            raise ValueError(f"JSON user prompt blocked: {user_check['reason']}")

        # Ensure strict JSON-only prompt
        json_system = f"""{system}

CRITICAL: You MUST respond with valid JSON only. No explanations, no markdown, no extra text.
The JSON must match this exact schema:
{response_model.schema_json(indent=2)}

Respond with JSON object only:"""

        # Lower temperature for JSON tasks
        json_temperature = temperature if temperature is not None else 0.1
        json_max_tokens = max_tokens if max_tokens is not None else 300

        last_error = None

        for attempt in range(max_retries):
            try:
                # Get raw LLM response
                llm_response = await self.complete(
                    system=json_system,
                    user=user,
                    temperature=json_temperature,
                    max_tokens=json_max_tokens,
                    use_cache=use_cache and attempt == 0,  # Only cache first attempt
                    bot_id=bot_id,
                    user_id=user_id
                )

                # Clean and extract JSON from response
                json_text = self._extract_json_from_response(llm_response.content)

                # Security check for response content
                response_check = llm_security.check_response_safety(llm_response.content)
                if not response_check["safe"]:
                    logger.warning("llm_response_blocked",
                                 reason=response_check["reason"])
                    last_error = f"Response blocked: {response_check['reason']}"
                    continue

                # Validate with Pydantic
                validated_response = response_model.parse_raw(json_text)

                # Record success metrics
                from .telemetry import llm_json_requests_total, llm_json_validation_success_total
                llm_json_requests_total.labels(self.config.model, "success").inc()
                llm_json_validation_success_total.labels(self.config.model).inc()

                logger.info("llm_json_success",
                           attempt=attempt + 1,
                           model_type=response_model.__name__,
                           duration_ms=llm_response.duration_ms)

                return validated_response

            except ValidationError as e:
                last_error = f"Validation error: {e}"
                logger.warning("llm_json_validation_failed",
                             attempt=attempt + 1,
                             model_type=response_model.__name__,
                             error=str(e),
                             response_preview=llm_response.content[:200] if 'llm_response' in locals() else "N/A")

                # Record validation failure
                from .telemetry import llm_json_validation_failed_total
                llm_json_validation_failed_total.labels(self.config.model, "validation_error").inc()

            except json.JSONDecodeError as e:
                last_error = f"JSON decode error: {e}"
                logger.warning("llm_json_parse_failed",
                             attempt=attempt + 1,
                             error=str(e),
                             response_preview=llm_response.content[:200] if 'llm_response' in locals() else "N/A")

                # Record parse failure
                from .telemetry import llm_json_validation_failed_total
                llm_json_validation_failed_total.labels(self.config.model, "parse_error").inc()

            except Exception as e:
                last_error = f"LLM error: {e}"
                logger.warning("llm_json_request_failed",
                             attempt=attempt + 1,
                             error=str(e))

                # Don't retry on LLM failures - those are retried in complete()
                break

            # Add some randomness for retries
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 + (attempt * 0.3))

        # All retries failed
        from .telemetry import llm_json_requests_total
        llm_json_requests_total.labels(self.config.model, "failed").inc()

        logger.error("llm_json_failed",
                    model_type=response_model.__name__,
                    error=last_error,
                    retries=max_retries)

        raise RuntimeError(f"JSON completion failed after {max_retries} attempts: {last_error}")

    def _extract_json_from_response(self, response: str) -> str:
        """Extract clean JSON from LLM response"""
        import re

        # Remove markdown code blocks
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*$', '', response)

        # Find JSON object or array
        json_match = re.search(r'[\{\[].*[\}\]]', response, re.DOTALL)
        if json_match:
            return json_match.group(0).strip()

        # If no clear JSON found, try to clean the response
        cleaned = response.strip()

        # Remove common prefixes
        for prefix in ["Here's the JSON:", "JSON response:", "Response:"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()

        return cleaned

    async def health_check(self) -> bool:
        """Check if LLM service is healthy"""
        try:
            session = await self._get_session()
            url = f"{self.config.base_url}/health"

            async with session.get(url) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning("llm_health_check_failed", error=str(e))
            return False


# Global LLM client instance
llm_client = LLMClient()