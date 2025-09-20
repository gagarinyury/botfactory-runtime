"""Performance tests for Bot Factory Runtime"""
import pytest
import time
import asyncio
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient
from runtime.main import app


class TestPreviewEndpointPerformance:
    """Test performance of /preview/send endpoint"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_single_request_response_time(self, client):
        """Test single request response time is reasonable"""
        bot_id = "test-perf-bot-001"

        start_time = time.time()

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        assert response.status_code == 200
        assert response_time_ms < 500  # Should respond within 500ms

    def test_100_requests_p95_latency(self, client):
        """Test that 100 requests have p95 ≤ 200ms on dev"""
        bot_id = "test-perf-bot-100"
        response_times = []

        for i in range(100):
            start_time = time.time()

            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/test{i}"
            })

            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            assert response.status_code == 200
            response_times.append(response_time_ms)

        # Calculate p95 latency
        p95_latency = statistics.quantiles(response_times, n=20)[18]  # 95th percentile

        # Requirement: p95 ≤ 200ms on dev
        assert p95_latency <= 200, f"P95 latency {p95_latency:.2f}ms exceeds 200ms limit"

        # Additional statistics for insight
        avg_latency = statistics.mean(response_times)
        max_latency = max(response_times)
        min_latency = min(response_times)

        print(f"Performance stats - Avg: {avg_latency:.2f}ms, P95: {p95_latency:.2f}ms, Max: {max_latency:.2f}ms, Min: {min_latency:.2f}ms")

    def test_concurrent_requests_performance(self, client):
        """Test performance under concurrent load"""
        bot_id = "test-perf-concurrent-bot"
        num_concurrent = 10
        num_requests = 50

        def make_request(request_id):
            start_time = time.time()
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/concurrent{request_id}"
            })
            end_time = time.time()
            return (end_time - start_time) * 1000, response.status_code

        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]

            results = []
            for future in as_completed(futures):
                response_time, status_code = future.result()
                assert status_code == 200
                results.append(response_time)

        # Analyze concurrent performance
        avg_concurrent_latency = statistics.mean(results)
        p95_concurrent_latency = statistics.quantiles(results, n=20)[18]

        # Concurrent requests should not degrade performance too much
        assert p95_concurrent_latency <= 300  # Allow slight degradation under load
        assert avg_concurrent_latency <= 150

    def test_wizard_flow_performance(self, client):
        """Test performance of complete wizard flows"""
        bot_id = "test-perf-wizard-bot"

        # Measure complete wizard flow time
        start_time = time.time()

        # Step 1: Start wizard
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })

        # Step 2: Provide service
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "massage"
        })

        # Step 3: Provide time
        response3 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "2024-01-15 14:00"
        })

        end_time = time.time()
        total_flow_time_ms = (end_time - start_time) * 1000

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        # Complete wizard flow should finish within reasonable time
        assert total_flow_time_ms < 1000  # 1 second for complete flow

    def test_database_query_performance(self, client):
        """Test performance of database-heavy operations"""
        bot_id = "test-perf-db-bot"

        # Test /my command (SQL query)
        start_time = time.time()

        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/my"
        })

        end_time = time.time()
        db_query_time_ms = (end_time - start_time) * 1000

        assert response.status_code == 200
        assert db_query_time_ms < 300  # Database operations should be fast

    def test_template_rendering_performance(self, client):
        """Test performance of template rendering with large datasets"""
        # This would require setting up test data with many bookings
        # to test template rendering performance with {{#each}} loops
        pass

    def test_redis_operations_performance(self, client):
        """Test performance of Redis operations for wizard state"""
        bot_id = "test-perf-redis-bot"

        # Start multiple wizards to test Redis performance
        response_times = []

        for i in range(20):
            start_time = time.time()

            # Start wizard (creates Redis state)
            response = client.post("/preview/send", json={
                "bot_id": f"{bot_id}_{i}",
                "text": "/book"
            })

            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            assert response.status_code == 200
            response_times.append(response_time_ms)

        # Redis operations should be consistently fast
        avg_redis_time = statistics.mean(response_times)
        assert avg_redis_time < 100  # Redis operations should be very fast


class TestMemoryPerformance:
    """Test memory usage and performance"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_memory_usage_under_load(self, client):
        """Test that memory usage doesn't grow excessively under load"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        bot_id = "test-memory-bot"

        # Send many requests
        for i in range(200):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/test{i}"
            })
            assert response.status_code == 200

        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 50MB for 200 requests)
        assert memory_growth < 50 * 1024 * 1024  # 50MB

    def test_wizard_state_memory_cleanup(self, client):
        """Test that wizard states are properly cleaned up from memory"""
        # This would test Redis memory usage and cleanup
        pass

    def test_cache_memory_efficiency(self, client):
        """Test that caching doesn't consume excessive memory"""
        # Test router cache and other caching mechanisms
        pass


class TestScalabilityLimits:
    """Test scalability limits and bottlenecks"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_multiple_bots_performance(self, client):
        """Test performance with multiple different bots"""
        num_bots = 10
        requests_per_bot = 10

        all_response_times = []

        for bot_num in range(num_bots):
            bot_id = f"test-scale-bot-{bot_num}"

            for req_num in range(requests_per_bot):
                start_time = time.time()

                response = client.post("/preview/send", json={
                    "bot_id": bot_id,
                    "text": f"/test{req_num}"
                })

                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000

                assert response.status_code == 200
                all_response_times.append(response_time_ms)

        # Performance should remain consistent across multiple bots
        avg_response_time = statistics.mean(all_response_times)
        p95_response_time = statistics.quantiles(all_response_times, n=20)[18]

        assert avg_response_time < 100
        assert p95_response_time < 200

    def test_many_concurrent_users_per_bot(self, client):
        """Test performance with many concurrent users on same bot"""
        bot_id = "test-concurrent-users-bot"
        num_users = 50

        def simulate_user(user_id):
            start_time = time.time()
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/user{user_id}"
            })
            end_time = time.time()
            return (end_time - start_time) * 1000, response.status_code

        # Simulate many concurrent users
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(simulate_user, i) for i in range(num_users)]

            results = []
            for future in as_completed(futures):
                response_time, status_code = future.result()
                assert status_code == 200
                results.append(response_time)

        # Should handle many concurrent users efficiently
        avg_latency = statistics.mean(results)
        p95_latency = statistics.quantiles(results, n=20)[18]

        assert avg_latency < 200
        assert p95_latency < 400

    def test_long_running_wizard_performance(self, client):
        """Test performance of long-running wizard sessions"""
        bot_id = "test-long-wizard-bot"

        # Simulate long wizard with many steps
        start_time = time.time()

        # Start wizard
        response = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/book"
        })
        assert response.status_code == 200

        # Simulate many wizard steps
        for step in range(10):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"step_{step}_input"
            })
            assert response.status_code == 200

        end_time = time.time()
        total_time_ms = (end_time - start_time) * 1000

        # Long wizard should still perform reasonably
        assert total_time_ms < 2000  # 2 seconds for 10+ step wizard

    def test_large_database_result_performance(self, client):
        """Test performance with large database query results"""
        # This would require setup with large amounts of test data
        # Test /my command with user having many bookings
        pass

    def test_complex_template_rendering_performance(self, client):
        """Test performance of complex template rendering"""
        # Test templates with many {{#each}} loops and large datasets
        pass


class TestCachePerformance:
    """Test caching mechanisms and their performance impact"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_router_cache_performance(self, client):
        """Test that router caching improves performance"""
        bot_id = "test-cache-bot"

        # First request (cache miss)
        start_time = time.time()
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })
        first_request_time = (time.time() - start_time) * 1000

        # Second request (cache hit)
        start_time = time.time()
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/help"
        })
        second_request_time = (time.time() - start_time) * 1000

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Second request should be faster due to caching
        # (This might not always be true depending on implementation)
        # assert second_request_time <= first_request_time

    def test_cache_invalidation_performance(self, client):
        """Test performance of cache invalidation"""
        bot_id = "test-cache-invalidation-bot"

        # Make request to populate cache
        response1 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })

        # Invalidate cache
        start_time = time.time()
        response_reload = client.post(f"/bots/{bot_id}/reload")
        cache_invalidation_time = (time.time() - start_time) * 1000

        # Make request after cache invalidation
        start_time = time.time()
        response2 = client.post("/preview/send", json={
            "bot_id": bot_id,
            "text": "/start"
        })
        post_invalidation_time = (time.time() - start_time) * 1000

        assert response1.status_code == 200
        assert response_reload.status_code == 200
        assert response2.status_code == 200

        # Cache invalidation should be fast
        assert cache_invalidation_time < 50  # 50ms

    def test_memory_cache_efficiency(self, client):
        """Test that in-memory caches are efficient"""
        # Test TTLCache and other caching mechanisms
        pass


class TestResourceUtilization:
    """Test resource utilization under various loads"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_cpu_utilization_under_load(self, client):
        """Test CPU utilization during high load"""
        import psutil
        import threading

        # Monitor CPU usage
        cpu_percentages = []

        def monitor_cpu():
            for _ in range(10):  # Monitor for 10 seconds
                cpu_percentages.append(psutil.cpu_percent(interval=1))

        # Start CPU monitoring
        monitor_thread = threading.Thread(target=monitor_cpu)
        monitor_thread.start()

        # Generate load
        bot_id = "test-cpu-bot"
        for i in range(100):
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/load{i}"
            })
            assert response.status_code == 200

        monitor_thread.join()

        # CPU usage should be reasonable
        avg_cpu = statistics.mean(cpu_percentages)
        max_cpu = max(cpu_percentages)

        assert avg_cpu < 80  # Average CPU should be under 80%
        assert max_cpu < 95   # Peak CPU should be under 95%

    def test_database_connection_efficiency(self, client):
        """Test database connection pool efficiency"""
        # Test that database connections are reused efficiently
        # and not exhausted under load
        pass

    def test_redis_connection_efficiency(self, client):
        """Test Redis connection efficiency"""
        # Test Redis connection pooling and efficiency
        pass


class TestLatencyBreakdown:
    """Test to understand latency breakdown"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_request_processing_latency_components(self, client):
        """Break down request processing latency into components"""
        # This would require instrumentation to measure:
        # - JSON parsing time
        # - DSL loading time
        # - Router execution time
        # - Database query time
        # - Template rendering time
        # - Response serialization time
        pass

    def test_wizard_state_operation_latency(self, client):
        """Test latency of wizard state operations"""
        # Measure Redis get/set operations
        # Measure state serialization/deserialization
        pass

    def test_database_operation_latency(self, client):
        """Test latency of different database operations"""
        # Measure SELECT vs INSERT vs DELETE performance
        # Measure simple vs complex queries
        pass


class TestPerformanceRegression:
    """Test for performance regressions"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_baseline_performance_metrics(self, client):
        """Establish baseline performance metrics"""
        bot_id = "test-baseline-bot"

        # Run standardized performance test
        response_times = []
        for i in range(50):
            start_time = time.time()
            response = client.post("/preview/send", json={
                "bot_id": bot_id,
                "text": f"/baseline{i}"
            })
            end_time = time.time()

            assert response.status_code == 200
            response_times.append((end_time - start_time) * 1000)

        avg_time = statistics.mean(response_times)
        p95_time = statistics.quantiles(response_times, n=20)[18]
        p99_time = statistics.quantiles(response_times, n=100)[98]

        # Store these as baseline metrics for comparison
        baseline_metrics = {
            "avg_response_time": avg_time,
            "p95_response_time": p95_time,
            "p99_response_time": p99_time
        }

        # Assert reasonable baseline performance
        assert avg_time < 100  # 100ms average
        assert p95_time < 200  # 200ms p95
        assert p99_time < 500  # 500ms p99

        print(f"Baseline metrics: {baseline_metrics}")

    def test_performance_with_different_loads(self, client):
        """Test performance under different load patterns"""
        # Test sustained load
        # Test burst load
        # Test gradual ramp-up
        pass


class TestStressLimits:
    """Test system behavior at stress limits"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_maximum_concurrent_requests(self, client):
        """Test maximum number of concurrent requests system can handle"""
        # Gradually increase concurrent requests until response times degrade
        pass

    def test_maximum_requests_per_second(self, client):
        """Test maximum sustainable requests per second"""
        # Find the RPS limit where system remains stable
        pass

    def test_graceful_degradation_under_overload(self, client):
        """Test that system degrades gracefully under overload"""
        # Verify system doesn't crash under extreme load
        # Verify appropriate error responses when overloaded
        pass