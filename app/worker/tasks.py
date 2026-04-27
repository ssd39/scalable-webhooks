"""
Task functions executed by the RQ worker.

Each function here is enqueued onto the Redis queue by the /webhook endpoint
and picked up by the worker process (app/worker/listener.py).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def process_webhook_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core task handler invoked by the RQ worker for every incoming webhook.

    Args:
        payload: The raw JSON body received at /webhook, augmented with a
                 ``task_id`` field injected by the route handler.

    Returns:
        A dict describing the outcome, stored as the RQ job result.
    """
    task_id = payload.get("task_id", "unknown")
    logger.info("[task:%s] Starting – payload keys: %s", task_id, list(payload.keys()))

    # ------------------------------------------------------------------
    # TODO: Replace with your real business logic, e.g.:
    #   • Persist the event to PostgreSQL via SQLAlchemy
    #   • Call a third-party API
    #   • Trigger downstream services
    # ------------------------------------------------------------------

    result: Dict[str, Any] = {
        "task_id": task_id,
        "status": "completed",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "received_keys": list(payload.keys()),
    }

    logger.info("[task:%s] Completed successfully – result: %s", task_id, result)
    return result
