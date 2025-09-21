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


def mask_user_text(text: str, max_length: int = 100) -> str:
    """
    Mask user text for logging while preserving length information

    Args:
        text: User input text to mask
        max_length: Maximum length to show before truncating

    Returns:
        Masked text with hash and length info
    """
    if not text:
        return ""

    import hashlib

    # Create hash of the text for debugging
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:8]

    # Get length info
    length = len(text)

    # Truncate if too long
    if length > max_length:
        preview = text[:max_length] + "..."
        length_info = f"[len={length}, truncated]"
    else:
        preview = text
        length_info = f"[len={length}]"

    # Replace text content with asterisks but keep structure
    masked_preview = ""
    for char in preview:
        if char.isspace():
            masked_preview += char
        elif char in ".,!?;:":
            masked_preview += char
        else:
            masked_preview += "*"

    return f"{masked_preview} {length_info} hash:{text_hash}"


def mask_user_input_in_logs(data):
    """Mask user input text in log data while preserving system fields"""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            # Fields that contain user input
            if k.lower() in ('text', 'message', 'content', 'user_input', 'query', 'prompt'):
                if isinstance(v, str):
                    masked[k] = mask_user_text(v)
                else:
                    masked[k] = v
            # Recursively mask nested dicts
            elif isinstance(v, dict):
                masked[k] = mask_user_input_in_logs(v)
            elif isinstance(v, list):
                masked[k] = [mask_user_input_in_logs(item) if isinstance(item, dict) else item for item in v]
            else:
                masked[k] = v
        return masked
    return data