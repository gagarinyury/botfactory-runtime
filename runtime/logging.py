import structlog
import uuid

log = structlog.get_logger()

def with_trace(ctx=None):
    return (ctx or str(uuid.uuid4()))