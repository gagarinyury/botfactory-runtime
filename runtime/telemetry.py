from prometheus_client import Counter, Histogram, generate_latest, Gauge
from time import perf_counter
from fastapi import HTTPException

# Management API metrics
api_requests_total = Counter("api_requests_total", "Total management API requests", ["route", "code"])
dsl_validate_errors_total = Counter("dsl_validate_errors_total", "Total DSL validation errors")
bot_reload_total = Counter("bot_reload_total", "Total bot reloads", ["bot_id"])
bot_prepare_total = Counter("bot_prepare_total", "Total bot preparations", ["bot_id"])

# Prometheus metrics
updates = Counter("bot_updates_total", "Total bot updates", ["bot_id"])
lat = Histogram("dsl_handle_latency_ms", "DSL handle latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2,5))
webhook_lat = Histogram("webhook_latency_ms", "Webhook latency in milliseconds", buckets=(0.01,0.05,0.1,0.2,0.5,1,2))
errors = Counter("bot_errors_total", "Total bot errors", ["bot_id", "where", "code"])

# New metrics for wizards and actions
wizard_active_total = Gauge("wizard_active_total", "Total active wizards", ["bot_id"])
wizard_errors_total = Counter("wizard_errors_total", "Total wizard errors", ["bot_id", "flow_cmd"])
wizard_flows = Counter("wizard_flows_total", "Total wizard flows started", ["bot_id", "flow_cmd"])
wizard_steps = Counter("wizard_steps_total", "Total wizard steps completed", ["bot_id", "flow_cmd"])
wizard_steps_total = wizard_steps
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

# Pagination widget metrics
widget_pagination_renders_total = Counter("widget_pagination_renders_total", "Total pagination widget renders", ["bot_id"])
widget_pagination_selects_total = Counter("widget_pagination_selects_total", "Total pagination selections", ["bot_id"])

# Budget and rate limiting metrics
llm_budget_usage_total = Counter("llm_budget_usage_total", "Total LLM budget usage in tokens", ["bot_id"])
llm_budget_limits_hit_total = Counter("llm_budget_limits_hit_total", "Budget limits hit", ["bot_id", "limit_type"])

# LLM metrics
llm_requests_total = Counter("llm_requests_total", "Total LLM requests", ["type", "status"])
llm_latency_ms = Histogram("llm_latency_ms", "LLM request latency", ["type", "cached"], buckets=(10, 50, 100, 200, 500, 1000, 2000, 5000))
llm_errors_total = Counter("llm_errors_total", "Total LLM errors", ["model", "error_type"])
llm_tokens_total = Counter("llm_tokens_total", "Total LLM tokens", ["model", "type"])  # type: input, output
llm_cache_hits_total = Counter("llm_cache_hits_total", "Total LLM cache hits", ["model"])

# LLM JSON mode metrics
llm_json_requests_total = Counter("llm_json_requests_total", "Total LLM JSON requests", ["model", "status"])
llm_json_validation_success_total = Counter("llm_json_validation_success_total", "Successful JSON validations", ["model"])
llm_json_validation_failed_total = Counter("llm_json_validation_failed_total", "Failed JSON validations", ["model", "error_type"])

# Reply template metrics
reply_sent_total = Counter("reply_sent_total", "Total replies sent", ["bot_id"])
reply_failed_total = Counter("reply_failed_total", "Total reply failures", ["bot_id"])
reply_latency_ms = Histogram("reply_latency_ms", "Reply template rendering latency", ["bot_id"], buckets=(0.1,0.5,1,2,5,10,20,50))

# Broadcast system metrics
broadcast_total = Counter("broadcast_total", "Total broadcast campaigns created", ["bot_id", "audience"])
broadcast_sent_total = Counter("broadcast_sent_total", "Total broadcast messages sent", ["bot_id"])
broadcast_failed_total = Counter("broadcast_failed_total", "Total broadcast messages failed", ["bot_id"])
broadcast_duration_seconds = Histogram("broadcast_duration_seconds", "Broadcast campaign duration", ["bot_id"], buckets=(1,5,10,30,60,300,900,1800,3600))

# I18n metrics
i18n_renders_total = Counter("i18n_renders_total", "Total i18n renders", ["bot_id", "locale"])
i18n_key_miss_total = Counter("i18n_key_miss_total", "Total i18n key misses", ["bot_id", "locale"])
i18n_cache_hits_total = Counter("i18n_cache_hits_total", "Total i18n cache hits", ["bot_id", "locale"])
i18n_cache_misses_total = Counter("i18n_cache_misses_total", "Total i18n cache misses", ["bot_id", "locale"])

# Rate limit policy metrics
policy_ratelimit_hits_total = Counter("policy_ratelimit_hits_total", "Total rate limit hits", ["bot_id", "scope"])
policy_ratelimit_pass_total = Counter("policy_ratelimit_pass_total", "Total rate limit passes", ["bot_id", "scope"])

# Circuit breaker metrics
circuit_breaker_state_changes_total = Counter("circuit_breaker_state_changes_total", "Circuit breaker state changes", ["bot_id", "from_state", "to_state"])
circuit_breaker_open_duration_seconds = Histogram("circuit_breaker_open_duration_seconds", "Duration circuit breaker was open", ["bot_id"], buckets=(1, 5, 10, 30, 60, 300, 600))
llm_timeout_total = Counter("llm_timeout_total", "Total LLM timeouts", ["bot_id"])
llm_circuit_breaker_rejections_total = Counter("llm_circuit_breaker_rejections_total", "Total requests rejected by circuit breaker", ["bot_id"])

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
    import structlog
    logger = structlog.get_logger()

    logger.info("measured_webhook_start", bot_id=bot_id, fn_name=fn.__name__)

    t = perf_counter()
    try:
        result = await fn(*a, **kw)
        updates.labels(bot_id).inc()
        logger.info("measured_webhook_success", bot_id=bot_id, fn_name=fn.__name__)
        return result
    except HTTPException as e:
        errors.labels(bot_id, "webhook", str(e.status_code)).inc()
        logger.error("measured_webhook_http_error", bot_id=bot_id, fn_name=fn.__name__, error=str(e))
        raise
    except Exception as e:
        errors.labels(bot_id, "webhook", "500").inc()
        logger.error("measured_webhook_error", bot_id=bot_id, fn_name=fn.__name__, error=str(e))
        raise
    finally:
        duration = (perf_counter() - t) * 1000
        webhook_lat.observe(duration)
        logger.info("measured_webhook_complete", bot_id=bot_id, fn_name=fn.__name__, duration_ms=duration)