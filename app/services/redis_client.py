import redis
from rq import Queue

from app.config import settings

# Synchronous Redis connection used by RQ
_redis_conn: redis.Redis | None = None


def get_redis_connection() -> redis.Redis:
    """Return a singleton synchronous Redis connection."""
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=False,
        )
    return _redis_conn


def get_webhook_queue() -> Queue:
    """Return the RQ Queue for webhook tasks."""
    conn = get_redis_connection()
    return Queue(settings.WEBHOOK_QUEUE_NAME, connection=conn)


def ping_redis() -> bool:
    """Check Redis connectivity. Returns True if reachable."""
    try:
        return get_redis_connection().ping()
    except redis.exceptions.ConnectionError:
        return False
