from prometheus_client import Counter, Histogram, generate_latest
from time import perf_counter

# Prometheus metrics
updates = Counter("bot_updates_total", "Total bot updates", ["bot_id"])
lat = Histogram("dsl_handle_latency_ms", "DSL handle latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2,5))

async def measure(bot_id, fn, *a, **kw):
    """Measure function execution time and record metrics"""
    t = perf_counter()
    res = await fn(*a, **kw)
    updates.labels(bot_id).inc()
    lat.observe((perf_counter() - t) * 1000)
    return res