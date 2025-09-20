from prometheus_client import Counter, Histogram, generate_latest
from time import perf_counter
from fastapi import HTTPException

# Prometheus metrics
updates = Counter("bot_updates_total", "Total bot updates", ["bot_id"])
lat = Histogram("dsl_handle_latency_ms", "DSL handle latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2,5))
errors = Counter("bot_errors_total", "Total bot errors", ["bot_id", "where", "code"])

async def measure(bot_id, fn, *a, **kw):
    """Measure function execution time and record metrics"""
    t = perf_counter()
    res = await fn(*a, **kw)
    updates.labels(bot_id).inc()
    lat.observe((perf_counter() - t) * 1000)
    return res

async def measured_preview(bot_id, fn, *a, **kw):
    """Measure with error tracking for preview"""
    try:
        return await measure(bot_id, fn, *a, **kw)
    except HTTPException as e:
        errors.labels(bot_id, "preview", str(e.status_code)).inc()
        raise
    except Exception as e:
        errors.labels(bot_id, "preview", "500").inc()
        raise

async def measured_webhook(bot_id, fn, *a, **kw):
    """Measure with error tracking for webhook"""
    try:
        return await measure(bot_id, fn, *a, **kw)
    except HTTPException as e:
        errors.labels(bot_id, "webhook", str(e.status_code)).inc()
        raise
    except Exception as e:
        errors.labels(bot_id, "webhook", "500").inc()
        raise