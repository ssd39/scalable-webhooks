import uuid
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from app.models.webhook import WebhookResponse
from app.services.redis_client import get_webhook_queue
from app.worker.tasks import process_webhook_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Accept a webhook event",
    description=(
        "Accepts any arbitrary JSON payload, assigns it a unique task ID, "
        "and enqueues it onto the Redis queue for async processing by the worker."
    ),
)
async def receive_webhook(request: Request) -> WebhookResponse:
    """
    POST /webhook

    Accepts any JSON body (no fixed schema), wraps it with a task_id,
    and pushes it to the Redis-backed RQ queue.
    """
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        )

    task_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {"task_id": task_id, **body}

    try:
        queue = get_webhook_queue()
        job = queue.enqueue(process_webhook_task, payload)
    except Exception as exc:
        logger.exception("Failed to enqueue webhook task: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to the task queue. Please try again later.",
        )

    logger.info("Webhook accepted – task_id=%s job_id=%s", task_id, job.id)

    return WebhookResponse(
        task_id=task_id,
        job_id=job.id,
        status="queued",
        message="Webhook received and task queued for processing.",
    )
