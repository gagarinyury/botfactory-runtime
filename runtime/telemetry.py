from prometheus_client import Counter, Histogram, generate_latest
from time import perf_counter
from fastapi import HTTPException

# Prometheus metrics
updates = Counter("bot_updates_total", "Total bot updates", ["bot_id"])
lat = Histogram("dsl_handle_latency_ms", "DSL handle latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2,5))
webhook_lat = Histogram("webhook_latency_ms", "Webhook latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2))
errors = Counter("bot_errors_total", "Total bot errors", ["bot_id", "where", "code"])

# New metrics for wizards and actions
wizard_flows = Counter("wizard_flows_total", "Total wizard flows started", ["bot_id", "flow_cmd"])
wizard_steps = Counter("wizard_steps_total", "Total wizard steps completed", ["bot_id", "flow_cmd"])
wizard_completions = Counter("wizard_completions_total", "Total wizard completions", ["bot_id", "flow_cmd"])
sql_actions = Counter("sql_actions_total", "Total SQL actions executed", ["bot_id", "action_type"])
bot_sql_exec_total = Counter("bot_sql_exec_total", "Total SQL exec actions", ["bot_id"])
bot_sql_query_total = Counter("bot_sql_query_total", "Total SQL query actions", ["bot_id"])
sql_action_latency = Histogram("sql_action_latency_ms", "SQL action latency in milliseconds", buckets=(0.1,0.5,1,2,5,10,20,50))
dsl_action_latency_ms = Histogram("dsl_action_latency_ms", "DSL action latency by type", ["action"], buckets=(0.1,0.5,1,2,5,10,20,50))
template_renders = Counter("template_renders_total", "Total template renders", ["bot_id"])

# Calendar widget metrics
widget_calendar_renders_total = Counter("widget_calendar_renders_total", "Total calendar widget renders", ["bot_id"])
widget_calendar_picks_total = Counter("widget_calendar_picks_total", "Total calendar picks", ["bot_id", "mode"])

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
    """Measure with error tracking and latency for webhook"""
    t = perf_counter()
    try:
        result = await fn(*a, **kw)
        updates.labels(bot_id).inc()
        return result
    except HTTPException as e:
        errors.labels(bot_id, "webhook", str(e.status_code)).inc()
        raise
    except Exception as e:
        errors.labels(bot_id, "webhook", "500").inc()
        raise
    finally:
        webhook_lat.observe((perf_counter() - t) * 1000)