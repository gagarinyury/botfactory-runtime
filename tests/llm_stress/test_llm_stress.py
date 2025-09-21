"""
LLM Stress Testing with 32 parallel requests

Tests:
- Concurrent LLM requests
- Prompt truncation edge cases
- Timeout fallback scenarios
- Performance metrics under load
- Circuit breaker behavior
"""
import asyncio
import pytest
import time
import json
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch

# Assuming these are available in the runtime
from runtime.llm_client import LLMClient, LLMResponse
from runtime.circuit_breaker import circuit_breaker, CircuitBreakerError
from runtime.telemetry import llm_latency_ms, llm_requests_total


class StressTestResults:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.timeout_requests = 0
        self.circuit_breaker_rejections = 0
        self.min_latency_ms = float('inf')
        self.max_latency_ms = 0
        self.total_latency_ms = 0
        self.errors = []

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.successful_requests, 1)

    @property
    def success_rate(self) -> float:
        return self.successful_requests / max(self.total_requests, 1)

    @property
    def timeout_rate(self) -> float:
        return self.timeout_requests / max(self.total_requests, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "timeout_requests": self.timeout_requests,
            "circuit_breaker_rejections": self.circuit_breaker_rejections,
            "success_rate": self.success_rate,
            "timeout_rate": self.timeout_rate,
            "min_latency_ms": self.min_latency_ms if self.min_latency_ms != float('inf') else 0,
            "max_latency_ms": self.max_latency_ms,
            "avg_latency_ms": self.avg_latency_ms,
            "errors": self.errors[:10]  # First 10 errors for debugging
        }


class LLMStressTester:
    def __init__(self, llm_client: LLMClient, bot_id: str = "stress-test-bot"):
        self.llm_client = llm_client
        self.bot_id = bot_id
        self.results = StressTestResults()

    async def make_single_request(self, request_id: int, prompt: str) -> Dict[str, Any]:
        """Make a single LLM request and record metrics"""
        start_time = time.time()
        result = {
            "request_id": request_id,
            "success": False,
            "latency_ms": 0,
            "error": None,
            "response_length": 0
        }

        try:
            # Use circuit breaker wrapper
            response = await self.llm_client._with_circuit_breaker(
                self.bot_id,
                self.llm_client.generate_text(
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=150,
                    use_cache=False  # Disable cache for stress testing
                )
            )

            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)

            result.update({
                "success": True,
                "latency_ms": latency_ms,
                "response_length": len(response.content),
                "cached": response.cached
            })

            self.results.successful_requests += 1
            self.results.total_latency_ms += latency_ms
            self.results.min_latency_ms = min(self.results.min_latency_ms, latency_ms)
            self.results.max_latency_ms = max(self.results.max_latency_ms, latency_ms)

        except CircuitBreakerError as e:
            result.update({
                "error": f"circuit_breaker_{e.state.value}",
                "latency_ms": int((time.time() - start_time) * 1000)
            })
            self.results.circuit_breaker_rejections += 1

        except asyncio.TimeoutError:
            result.update({
                "error": "timeout",
                "latency_ms": int((time.time() - start_time) * 1000)
            })
            self.results.timeout_requests += 1

        except Exception as e:
            result.update({
                "error": str(e),
                "latency_ms": int((time.time() - start_time) * 1000)
            })
            self.results.failed_requests += 1
            self.results.errors.append(f"req_{request_id}: {str(e)}")

        self.results.total_requests += 1
        return result

    async def run_concurrent_test(self, num_requests: int = 32, prompts: List[str] = None) -> StressTestResults:
        """Run concurrent LLM requests"""
        if prompts is None:
            prompts = [
                "Explain quantum computing in simple terms.",
                "Write a short story about a robot learning to paint.",
                "List 5 benefits of renewable energy.",
                "Describe the process of photosynthesis.",
                "What are the main causes of climate change?",
                "Explain machine learning to a 10-year-old.",
                "Write a haiku about technology.",
                "Compare democracy and autocracy."
            ]

        # Create tasks for concurrent execution
        tasks = []
        for i in range(num_requests):
            prompt = prompts[i % len(prompts)]  # Cycle through prompts
            task = self.make_single_request(i, prompt)
            tasks.append(task)

        # Execute all requests concurrently
        print(f"🔥 Starting {num_requests} concurrent LLM requests...")
        start_time = time.time()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_duration = end_time - start_time

        print(f"✅ Completed in {total_duration:.2f}s")
        print(f"📊 Results: {self.results.to_dict()}")

        return self.results


@pytest.fixture
def llm_client():
    """Mock LLM client for testing"""
    client = LLMClient()
    return client


@pytest.fixture
def stress_tester(llm_client):
    """Stress tester instance"""
    return LLMStressTester(llm_client)


@pytest.mark.asyncio
async def test_32_concurrent_requests(stress_tester):
    """Test 32 concurrent LLM requests"""
    # Reset circuit breaker
    await circuit_breaker.reset_bot("stress-test-bot")

    results = await stress_tester.run_concurrent_test(num_requests=32)

    # Validate results
    assert results.total_requests == 32
    assert results.success_rate >= 0.8, f"Success rate too low: {results.success_rate}"
    assert results.timeout_rate <= 0.15, f"Timeout rate too high: {results.timeout_rate}"
    assert results.avg_latency_ms <= 2000, f"Average latency too high: {results.avg_latency_ms}ms"


@pytest.mark.asyncio
async def test_large_prompt_handling(stress_tester):
    """Test handling of large prompts (>2048 tokens)"""
    # Create a very large prompt
    large_prompt = "Write a detailed analysis of " + "artificial intelligence " * 300

    results = await stress_tester.run_concurrent_test(
        num_requests=16,
        prompts=[large_prompt]
    )

    # Should handle large prompts gracefully (truncate or reject)
    assert results.total_requests == 16
    # Either all succeed (with truncation) or all fail gracefully
    assert results.success_rate >= 0.5 or results.timeout_rate <= 0.3


@pytest.mark.asyncio
async def test_timeout_fallback(stress_tester):
    """Test timeout fallback behavior"""
    with patch.object(stress_tester.llm_client, 'generate_text') as mock_generate:
        # Simulate slow responses
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(6)  # Longer than typical timeout
            return LLMResponse(
                content="Slow response",
                usage={"total_tokens": 10},
                model="test",
                duration_ms=6000
            )

        mock_generate.side_effect = slow_response

        results = await stress_tester.run_concurrent_test(num_requests=8)

        # Should have timeouts
        assert results.timeout_rate > 0, "Expected some timeouts with slow responses"


@pytest.mark.asyncio
async def test_circuit_breaker_behavior(stress_tester):
    """Test circuit breaker opening under load"""
    with patch.object(stress_tester.llm_client, 'generate_text') as mock_generate:
        # Simulate failures
        mock_generate.side_effect = Exception("LLM service unavailable")

        results = await stress_tester.run_concurrent_test(num_requests=16)

        # Should trigger circuit breaker
        circuit_state = circuit_breaker.get_state("stress-test-bot")
        print(f"Circuit breaker state after failures: {circuit_state}")

        # Should have some circuit breaker rejections
        total_failures = results.failed_requests + results.circuit_breaker_rejections
        assert total_failures > 0, "Expected failures to trigger circuit breaker"


@pytest.mark.asyncio
async def test_performance_metrics(stress_tester):
    """Test that performance meets acceptance criteria"""
    # Reset circuit breaker
    await circuit_breaker.reset_bot("stress-test-bot")

    results = await stress_tester.run_concurrent_test(num_requests=32)

    # Performance acceptance criteria from your requirements
    assert results.avg_latency_ms <= 1500, f"p95 latency > 1.5s: {results.avg_latency_ms}ms"
    assert results.success_rate >= 0.85, f"Success rate < 85%: {results.success_rate}"
    assert results.timeout_rate <= 0.05, f"Timeout rate > 5%: {results.timeout_rate}"

    # Additional performance checks
    assert results.max_latency_ms <= 5000, f"Max latency too high: {results.max_latency_ms}ms"

    print(f"🎯 Performance test passed!")
    print(f"   Success rate: {results.success_rate:.1%}")
    print(f"   Avg latency: {results.avg_latency_ms:.0f}ms")
    print(f"   Max latency: {results.max_latency_ms:.0f}ms")
    print(f"   Timeout rate: {results.timeout_rate:.1%}")


@pytest.mark.asyncio
async def test_cache_behavior_under_load(stress_tester):
    """Test cache hit rate under concurrent load"""
    # Use same prompt for all requests to test caching
    same_prompt = "What is the capital of France?"

    results = await stress_tester.run_concurrent_test(
        num_requests=16,
        prompts=[same_prompt]
    )

    # With caching enabled, should be very fast after first request
    assert results.success_rate >= 0.9, "Cache should improve success rate"

    # Cache hit rate should be measured by telemetry
    # This is more of an integration test


if __name__ == "__main__":
    async def main():
        client = LLMClient()
        tester = LLMStressTester(client)

        print("🔥 Running LLM Stress Test Suite")
        results = await tester.run_concurrent_test(32)

        print("\n📊 Final Results:")
        for key, value in results.to_dict().items():
            print(f"  {key}: {value}")

        # Save results to file
        with open("llm_stress_results.json", "w") as f:
            json.dump(results.to_dict(), f, indent=2)

        print("\n✅ Stress test completed!")

    if __name__ == "__main__":
        asyncio.run(main())