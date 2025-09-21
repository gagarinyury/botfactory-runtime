#!/usr/bin/env python3
"""
LLM Stress Test - 32 параллельно + длинный ввод
Критерии:
- p95 ≤ 1.5s
- error_rate ≤ 3%
- cache_hit ≥ 30%
"""
import asyncio
import aiohttp
import time
import statistics
import json
from typing import List, Dict

class LLMStressResults:
    def __init__(self):
        self.requests = []
        self.errors = []
        self.start_time = None
        self.end_time = None

    def add_request(self, duration_ms: float, success: bool, cached: bool = False, error: str = None):
        self.requests.append({
            'duration_ms': duration_ms,
            'success': success,
            'cached': cached,
            'error': error
        })
        if not success and error:
            self.errors.append(error)

    @property
    def total_requests(self) -> int:
        return len(self.requests)

    @property
    def successful_requests(self) -> int:
        return sum(1 for r in self.requests if r['success'])

    @property
    def failed_requests(self) -> int:
        return self.total_requests - self.successful_requests

    @property
    def error_rate(self) -> float:
        return self.failed_requests / max(self.total_requests, 1)

    @property
    def cache_hit_rate(self) -> float:
        cache_hits = sum(1 for r in self.requests if r['success'] and r['cached'])
        return cache_hits / max(self.successful_requests, 1)

    @property
    def latencies_ms(self) -> List[float]:
        return [r['duration_ms'] for r in self.requests if r['success']]

    @property
    def p95_latency_ms(self) -> float:
        latencies = self.latencies_ms
        return statistics.quantiles(latencies, n=20)[18] if latencies else 0  # 95th percentile

    @property
    def avg_latency_ms(self) -> float:
        latencies = self.latencies_ms
        return statistics.mean(latencies) if latencies else 0

    @property
    def max_latency_ms(self) -> float:
        latencies = self.latencies_ms
        return max(latencies) if latencies else 0

    def to_dict(self) -> Dict:
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'error_rate': self.error_rate,
            'cache_hit_rate': self.cache_hit_rate,
            'p95_latency_ms': self.p95_latency_ms,
            'avg_latency_ms': self.avg_latency_ms,
            'max_latency_ms': self.max_latency_ms,
            'total_duration_s': (self.end_time - self.start_time) if self.end_time and self.start_time else 0,
            'errors': self.errors[:5]  # First 5 errors for debugging
        }

async def make_llm_request(session: aiohttp.ClientSession, request_id: int, prompt: str) -> Dict:
    """Make single LLM request"""
    start_time = time.time()

    payload = {
        "bot_id": "test-llm-stress",
        "text": prompt
    }

    try:
        async with session.post(
            "http://localhost:8000/preview/send",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            duration_ms = (time.time() - start_time) * 1000

            if response.status == 200:
                data = await response.json()
                # Check if response indicates cached result
                cached = 'кэш' in data.get('bot_reply', '').lower() or duration_ms < 100
                return {
                    'request_id': request_id,
                    'duration_ms': duration_ms,
                    'success': True,
                    'cached': cached,
                    'status': response.status,
                    'response_length': len(data.get('bot_reply', ''))
                }
            else:
                return {
                    'request_id': request_id,
                    'duration_ms': duration_ms,
                    'success': False,
                    'cached': False,
                    'status': response.status,
                    'error': f"HTTP {response.status}"
                }

    except asyncio.TimeoutError:
        duration_ms = (time.time() - start_time) * 1000
        return {
            'request_id': request_id,
            'duration_ms': duration_ms,
            'success': False,
            'cached': False,
            'error': "timeout"
        }
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return {
            'request_id': request_id,
            'duration_ms': duration_ms,
            'success': False,
            'cached': False,
            'error': str(e)
        }

async def run_concurrent_llm_test(concurrency: int = 32) -> LLMStressResults:
    """Run concurrent LLM stress test"""

    # Test prompts (including long input)
    prompts = [
        "Объясни квантовые вычисления простыми словами",
        "Напиши короткий рассказ о роботе, который учится рисовать",
        "Перечисли 5 преимуществ возобновляемой энергии",
        "Опиши процесс фотосинтеза детально",
        # Long input test
        "Проведи подробный анализ следующей ситуации: " +
        "искусственный интеллект в современном мире становится всё более важным. " * 50,
        "Что такое машинное обучение? Объясни подробно",
        "Напиши хайку о технологиях",
        "Сравни демократию и автократию"
    ]

    results = LLMStressResults()
    results.start_time = time.time()

    print(f"🔥 Starting LLM stress test with {concurrency} concurrent requests...")

    # Create HTTP session
    connector = aiohttp.TCPConnector(limit=concurrency + 10)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Create tasks
        tasks = []
        for i in range(concurrency):
            prompt = prompts[i % len(prompts)]
            task = make_llm_request(session, i, prompt)
            tasks.append(task)

        # Execute all requests concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for response in responses:
            if isinstance(response, Exception):
                results.add_request(0, False, False, str(response))
            else:
                results.add_request(
                    response['duration_ms'],
                    response['success'],
                    response.get('cached', False),
                    response.get('error')
                )

    results.end_time = time.time()
    return results

async def main():
    print("🚀 LLM Stress Test Suite")
    print("Критерии: p95 ≤ 1.5s, error_rate ≤ 3%, cache_hit ≥ 30%")
    print()

    # Run 32 concurrent requests
    results = await run_concurrent_llm_test(32)

    print("📊 Результаты:")
    stats = results.to_dict()

    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    print()
    print("🎯 Проверка критериев:")

    # Check criteria
    p95_ok = stats['p95_latency_ms'] <= 1500
    error_rate_ok = stats['error_rate'] <= 0.03
    cache_hit_ok = stats['cache_hit_rate'] >= 0.30

    print(f"  p95 latency ≤ 1.5s: {stats['p95_latency_ms']:.0f}ms {'✅' if p95_ok else '❌'}")
    print(f"  error rate ≤ 3%: {stats['error_rate']:.1%} {'✅' if error_rate_ok else '❌'}")
    print(f"  cache hit ≥ 30%: {stats['cache_hit_rate']:.1%} {'✅' if cache_hit_ok else '❌'}")

    # Overall result
    all_criteria_met = p95_ok and error_rate_ok and cache_hit_ok

    if all_criteria_met:
        print("\n✅ PASS - Все критерии LLM стресс тестирования выполнены")
    else:
        print("\n❌ FAIL - Некоторые критерии не выполнены")

    # Save results
    with open("artifacts/llm_stress_results.json", "w") as f:
        json.dump({
            **stats,
            'criteria_met': all_criteria_met,
            'p95_criterion': p95_ok,
            'error_rate_criterion': error_rate_ok,
            'cache_hit_criterion': cache_hit_ok
        }, f, indent=2)

    print(f"\n💾 Результаты сохранены в artifacts/llm_stress_results.json")

    return all_criteria_met

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)