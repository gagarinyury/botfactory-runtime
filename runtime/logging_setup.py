import logging
import structlog

logging.basicConfig(level=logging.INFO, format="%(message)s")
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()  # читаемо в docker logs
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
)

# Base logger with app context
log = structlog.get_logger().bind(app="botfactory")

def bind_ctx(bot_id=None, spec_version=None, trace_id=None, **kwargs):
    """Bind context to logger with required fields"""
    context = {}
    if bot_id:
        context["bot_id"] = bot_id
    if spec_version:
        context["spec_version"] = spec_version
    if trace_id:
        context["trace_id"] = trace_id
    context.update(kwargs)
    return log.bind(**context)

def mask_sensitive_data(data):
    """Mask sensitive data like tokens in logs"""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if k.lower() in ('token', 'authorization', 'password', 'secret'):
                masked[k] = "***masked***"
            elif isinstance(v, dict):
                masked[k] = mask_sensitive_data(v)
            elif isinstance(v, list):
                masked[k] = [mask_sensitive_data(item) if isinstance(item, dict) else item for item in v]
            else:
                masked[k] = v
        return masked
    return data