"""Circuit breaker implementation for LLM requests per bot"""
import time
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
import asyncio
import structlog

logger = structlog.get_logger()


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5        # Failures before opening
    timeout_threshold: float = 5.0    # Timeout threshold in seconds
    recovery_timeout: int = 30        # Seconds before attempting recovery
    success_threshold: int = 2        # Successes needed to close from half-open


class CircuitBreakerStats:
    def __init__(self):
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.state = CircuitState.CLOSED
        self.half_open_attempts = 0

    def reset(self):
        """Reset stats when circuit closes"""
        self.failure_count = 0
        self.success_count = 0
        self.half_open_attempts = 0


class CircuitBreaker:
    """Circuit breaker for LLM requests with per-bot isolation"""

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._bot_stats: Dict[str, CircuitBreakerStats] = {}
        self._lock = asyncio.Lock()

    def _get_stats(self, bot_id: str) -> CircuitBreakerStats:
        """Get or create stats for bot"""
        if bot_id not in self._bot_stats:
            self._bot_stats[bot_id] = CircuitBreakerStats()
        return self._bot_stats[bot_id]

    async def can_proceed(self, bot_id: str) -> bool:
        """Check if request can proceed for this bot"""
        async with self._lock:
            stats = self._get_stats(bot_id)
            now = time.time()

            if stats.state == CircuitState.CLOSED:
                return True

            elif stats.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if now - stats.last_failure_time >= self.config.recovery_timeout:
                    stats.state = CircuitState.HALF_OPEN
                    stats.half_open_attempts = 0
                    logger.info("circuit_breaker_half_open", bot_id=bot_id)
                    return True
                return False

            elif stats.state == CircuitState.HALF_OPEN:
                # Allow limited requests to test recovery
                return stats.half_open_attempts < self.config.success_threshold

    async def record_success(self, bot_id: str, duration_ms: int):
        """Record successful request"""
        async with self._lock:
            stats = self._get_stats(bot_id)

            if stats.state == CircuitState.HALF_OPEN:
                stats.success_count += 1
                stats.half_open_attempts += 1

                if stats.success_count >= self.config.success_threshold:
                    stats.state = CircuitState.CLOSED
                    stats.reset()
                    logger.info("circuit_breaker_closed", bot_id=bot_id)

            elif stats.state == CircuitState.CLOSED:
                # Reset failure count on success
                stats.failure_count = 0

            # Record metrics
            from .telemetry import llm_requests_total
            llm_requests_total.labels(type="llm", status="success").inc()

    async def record_failure(self, bot_id: str, error_type: str = "unknown"):
        """Record failed request"""
        async with self._lock:
            stats = self._get_stats(bot_id)
            stats.failure_count += 1
            stats.last_failure_time = time.time()

            if stats.state == CircuitState.HALF_OPEN:
                # Failed during recovery, back to open
                stats.state = CircuitState.OPEN
                logger.warning("circuit_breaker_failed_recovery", bot_id=bot_id)

            elif stats.state == CircuitState.CLOSED:
                if stats.failure_count >= self.config.failure_threshold:
                    stats.state = CircuitState.OPEN
                    logger.error("circuit_breaker_opened",
                               bot_id=bot_id,
                               failure_count=stats.failure_count)

            # Record metrics
            from .telemetry import llm_requests_total, llm_errors_total
            llm_requests_total.labels(type="llm", status="failure").inc()
            llm_errors_total.labels(model="unknown", error_type=error_type).inc()

    async def record_timeout(self, bot_id: str, duration_ms: int):
        """Record timeout (special case of failure)"""
        if duration_ms > self.config.timeout_threshold * 1000:
            await self.record_failure(bot_id, "timeout")
            logger.warning("llm_timeout_detected",
                         bot_id=bot_id,
                         duration_ms=duration_ms,
                         threshold_ms=self.config.timeout_threshold * 1000)

    def get_state(self, bot_id: str) -> CircuitState:
        """Get current circuit state for bot"""
        stats = self._get_stats(bot_id)
        return stats.state

    def get_stats_dict(self, bot_id: str) -> Dict:
        """Get stats as dictionary for monitoring"""
        stats = self._get_stats(bot_id)
        return {
            "state": stats.state.value,
            "failure_count": stats.failure_count,
            "success_count": stats.success_count,
            "last_failure_time": stats.last_failure_time,
            "half_open_attempts": stats.half_open_attempts
        }

    async def reset_bot(self, bot_id: str):
        """Reset circuit breaker for specific bot (admin operation)"""
        async with self._lock:
            if bot_id in self._bot_stats:
                self._bot_stats[bot_id].state = CircuitState.CLOSED
                self._bot_stats[bot_id].reset()
                logger.info("circuit_breaker_reset", bot_id=bot_id)


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    def __init__(self, bot_id: str, state: CircuitState):
        self.bot_id = bot_id
        self.state = state
        super().__init__(f"Circuit breaker {state.value} for bot {bot_id}")


# Global circuit breaker instance
circuit_breaker = CircuitBreaker()


async def with_circuit_breaker(bot_id: str, coro):
    """
    Decorator-like function to wrap coroutines with circuit breaker

    Usage:
        result = await with_circuit_breaker("bot123", llm_client.generate_text("hello"))
    """
    if not await circuit_breaker.can_proceed(bot_id):
        state = circuit_breaker.get_state(bot_id)
        raise CircuitBreakerError(bot_id, state)

    start_time = time.time()
    try:
        result = await coro
        duration_ms = int((time.time() - start_time) * 1000)
        await circuit_breaker.record_success(bot_id, duration_ms)
        return result

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        await circuit_breaker.record_timeout(bot_id, duration_ms)
        raise

    except Exception as e:
        await circuit_breaker.record_failure(bot_id, type(e).__name__)
        raise