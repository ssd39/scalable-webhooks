import uuid
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from rq import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.job import Job, JobStatus
from app.models.webhook import WebhookResponse
from app.services.redis_client import get_webhook_queue
from app.worker.tasks import MAX_ATTEMPTS, process_webhook_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Accept a webhook event",
    description=(
        "Accepts any arbitrary JSON payload, assigns it a unique task ID, "
        "persists a Job record, and enqueues it for async LLM classification "
        "and persistence."
    ),
)
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """
    POST /webhook

    Body: any valid JSON object (no fixed schema).

    Returns 202 Accepted immediately. The payload is classified by the LLM
    worker and saved to the appropriate table (shipments / invoices /
    unclassified_events) asynchronously.
    """
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        )

    task_id = str(uuid.uuid4())

    # ── 1. Persist Job record BEFORE enqueue ─────────────────────────────
    job = Job(
        task_id=task_id,
        raw_payload=body,
        status=JobStatus.PENDING,
        max_attempts=MAX_ATTEMPTS,
    )
    db.add(job)
    await db.flush()  # populate job.id without full commit
    job_db_id = job.id

    # ── 2. Enqueue task with payload (task_id injected) ───────────────────
    payload: Dict[str, Any] = {"task_id": task_id, **body}

    try:
        queue = get_webhook_queue()
        rq_job = queue.enqueue(
            process_webhook_task,
            payload,
            retry=Retry(max=MAX_ATTEMPTS - 1),  # 1 initial + (MAX-1) retries
            job_timeout=300,
            result_ttl=86400,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue webhook task: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to the task queue. Please try again later.",
        )

    # ── 3. Store the RQ job ID on the job record ──────────────────────────
    job.rq_job_id = rq_job.id
    # db.commit() is handled automatically by the get_db dependency

    logger.info(
        "Webhook accepted – task_id=%s rq_job_id=%s", task_id, rq_job.id
    )

    return WebhookResponse(
        task_id=task_id,
        job_id=rq_job.id,
        status="queued",
        message="Webhook received and task queued for async processing.",
    )
