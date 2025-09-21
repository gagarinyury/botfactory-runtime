"""Performance tests for LLM integration under load"""
import pytest
import asyncio
import time
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch
from runtime.llm_client import LLMClient, LLMConfig


class TestLLMLoadPerformance:
    """Load testing for LLM services"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for performance testing"""
        config = LLMConfig(
            base_url="http://mock-llm:11434",
            timeout=5,
            max_retries=2
        )
        return LLMClient(config)

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_llm_requests(self, mock_llm_client):
        """Test 10 concurrent LLM requests finish within reasonable time"""
        concurrent_requests = 10
        timeout_per_request = 300  # 300ms per request
        total_timeout = 2000  # 2 seconds total

        async def mock_llm_response(*args, **kwargs):
            # Simulate realistic LLM response time
            await asyncio.sleep(0.1)  # 100ms response time
            return {
                "content": "Test response from LLM",
                "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 100
            }

        with patch.object(mock_llm_client, '_make_request', side_effect=mock_llm_response):
            start_time = time.perf_counter()

            # Create concurrent tasks
            tasks = []
            for i in range(concurrent_requests):
                task = mock_llm_client.complete(
                    system="You are a helpful assistant",
                    user=f"Test message {i}",
                    use_cache=False  # Disable cache for load testing
                )
                tasks.append(task)

            # Execute all tasks concurrently
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            end_time = time.perf_counter()
            total_duration_ms = (end_time - start_time) * 1000

            # Verify performance requirements
            assert total_duration_ms < total_timeout, f"Total time {total_duration_ms}ms exceeded {total_timeout}ms"

            # Verify all requests succeeded
            successful_responses = [r for r in responses if not isinstance(r, Exception)]
            assert len(successful_responses) == concurrent_requests

            # Calculate performance metrics
            avg_response_time = total_duration_ms / concurrent_requests
            assert avg_response_time < timeout_per_request, f"Average response time {avg_response_time}ms exceeded {timeout_per_request}ms"

            print(f"Performance metrics:")
            print(f"  Total duration: {total_duration_ms:.1f}ms")
            print(f"  Average per request: {avg_response_time:.1f}ms")
            print(f"  Requests per second: {(concurrent_requests / total_duration_ms * 1000):.1f}")

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_sequential_llm_cache_performance(self, mock_llm_client):
        """Test that cache significantly improves response time"""
        cache_requests = 5
        max_cached_time = 50  # 50ms for cached responses

        system_prompt = "You are a helpful assistant"
        user_prompt = "What is the capital of France?"

        async def mock_llm_response(*args, **kwargs):
            # First request is slow, cached requests are fast
            await asyncio.sleep(0.2)  # 200ms for uncached
            return {
                "content": "Paris is the capital of France",
                "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 200
            }

        # Mock cache behavior
        cache_hit = {
            "content": "Paris is the capital of France",
            "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
            "model": "phi-3-mini",
            "cached": True,
            "duration_ms": 5
        }

        with patch.object(mock_llm_client, '_make_request', side_effect=mock_llm_response), \
             patch.object(mock_llm_client, '_get_from_cache') as mock_cache:

            # First request - cache miss
            mock_cache.return_value = None
            start_time = time.perf_counter()
            first_response = await mock_llm_client.complete(system_prompt, user_prompt)
            first_duration = (time.perf_counter() - start_time) * 1000

            # Subsequent requests - cache hits
            mock_cache.return_value = cache_hit

            cached_times = []
            for i in range(cache_requests):
                start_time = time.perf_counter()
                response = await mock_llm_client.complete(system_prompt, user_prompt)
                duration = (time.perf_counter() - start_time) * 1000
                cached_times.append(duration)

                assert response["cached"] is True
                assert duration < max_cached_time, f"Cached request {i} took {duration}ms, expected < {max_cached_time}ms"

            avg_cached_time = sum(cached_times) / len(cached_times)
            speedup_ratio = first_duration / avg_cached_time

            print(f"Cache performance metrics:")
            print(f"  First request (uncached): {first_duration:.1f}ms")
            print(f"  Average cached request: {avg_cached_time:.1f}ms")
            print(f"  Speedup ratio: {speedup_ratio:.1f}x")

            # Cache should provide at least 2x speedup
            assert speedup_ratio > 2.0, f"Cache speedup {speedup_ratio:.1f}x is too low"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_llm_json_validation_performance(self, mock_llm_client):
        """Test JSON validation doesn't add significant overhead"""
        from runtime.llm_models import ValidationResult

        validation_requests = 10
        max_validation_overhead = 50  # 50ms overhead for JSON validation

        async def mock_json_response(*args, **kwargs):
            await asyncio.sleep(0.1)
            return {
                "content": '{"valid": true, "reason": "Input is valid", "confidence": 0.95}',
                "usage": {"prompt_tokens": 25, "completion_tokens": 12, "total_tokens": 37},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 100
            }

        with patch.object(mock_llm_client, '_make_request', side_effect=mock_json_response):
            # Measure JSON completion performance
            json_times = []
            for i in range(validation_requests):
                start_time = time.perf_counter()

                result = await mock_llm_client.complete_json(
                    system="Validate the user input",
                    user=f"Test input {i}",
                    response_model=ValidationResult,
                    use_cache=False
                )

                duration = (time.perf_counter() - start_time) * 1000
                json_times.append(duration)

                # Verify parsed result
                assert result.valid is True
                assert isinstance(result.confidence, float)

            avg_json_time = sum(json_times) / len(json_times)

            # Compare with regular completion
            regular_times = []
            for i in range(validation_requests):
                start_time = time.perf_counter()

                response = await mock_llm_client.complete(
                    system="Respond to user",
                    user=f"Test input {i}",
                    use_cache=False
                )

                duration = (time.perf_counter() - start_time) * 1000
                regular_times.append(duration)

            avg_regular_time = sum(regular_times) / len(regular_times)
            validation_overhead = avg_json_time - avg_regular_time

            print(f"JSON validation performance:")
            print(f"  Regular completion: {avg_regular_time:.1f}ms")
            print(f"  JSON completion: {avg_json_time:.1f}ms")
            print(f"  Validation overhead: {validation_overhead:.1f}ms")

            assert validation_overhead < max_validation_overhead, \
                f"JSON validation overhead {validation_overhead:.1f}ms exceeds {max_validation_overhead}ms"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_llm_error_recovery_performance(self, mock_llm_client):
        """Test that error recovery doesn't significantly degrade performance"""
        error_recovery_requests = 5
        max_recovery_time = 1000  # 1 second for error recovery

        call_count = 0

        async def mock_failing_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count <= 2:  # First 2 calls fail
                raise asyncio.TimeoutError("Simulated timeout")
            else:  # Third call succeeds
                await asyncio.sleep(0.1)
                return {
                    "content": "Recovery successful",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "model": "phi-3-mini",
                    "cached": False,
                    "duration_ms": 100
                }

        with patch.object(mock_llm_client, '_make_request', side_effect=mock_failing_response):
            recovery_times = []

            for i in range(error_recovery_requests):
                call_count = 0  # Reset for each test
                start_time = time.perf_counter()

                try:
                    response = await mock_llm_client.complete(
                        system="Test system",
                        user=f"Test recovery {i}",
                        use_cache=False
                    )
                    duration = (time.perf_counter() - start_time) * 1000
                    recovery_times.append(duration)

                    assert response["content"] == "Recovery successful"
                    assert duration < max_recovery_time, f"Recovery took {duration}ms, expected < {max_recovery_time}ms"

                except Exception as e:
                    pytest.fail(f"Error recovery failed: {e}")

            avg_recovery_time = sum(recovery_times) / len(recovery_times)

            print(f"Error recovery performance:")
            print(f"  Average recovery time: {avg_recovery_time:.1f}ms")
            print(f"  Max recovery time: {max(recovery_times):.1f}ms")

            # Recovery should complete within reasonable time even with retries
            assert avg_recovery_time < max_recovery_time

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_usage_stability(self, mock_llm_client):
        """Test that memory usage remains stable under load"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        async def mock_response(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {
                "content": "Test response " * 100,  # Larger response
                "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 10
            }

        with patch.object(mock_llm_client, '_make_request', side_effect=mock_response):
            # Run many requests to test memory stability
            for batch in range(10):  # 10 batches
                tasks = []
                for i in range(20):  # 20 requests per batch
                    task = mock_llm_client.complete(
                        system="System prompt",
                        user=f"Batch {batch} request {i}",
                        use_cache=False
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

                # Check memory usage
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = current_memory - initial_memory

                # Memory should not increase by more than 50MB
                assert memory_increase < 50, f"Memory increased by {memory_increase:.1f}MB after batch {batch}"

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_increase = final_memory - initial_memory

        print(f"Memory usage:")
        print(f"  Initial: {initial_memory:.1f}MB")
        print(f"  Final: {final_memory:.1f}MB")
        print(f"  Increase: {total_increase:.1f}MB")

        # Total memory increase should be reasonable
        assert total_increase < 100, f"Total memory increase {total_increase:.1f}MB is too high"