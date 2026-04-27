import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.invoice import Invoice
from app.db.models.job import Job
from app.db.models.shipment import Shipment
from app.db.models.unclassified import UnclassifiedEvent
from app.schemas.job import (
    InvoiceOut,
    JobDetailOut,
    JobListResponse,
    JobOut,
    ShipmentOut,
    UnclassifiedEventOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ---------------------------------------------------------------------------
# List all jobs (paginated + filterable by status / classification)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=JobListResponse,
    summary="List all jobs",
    description="Returns a paginated list of all webhook jobs tracked in the system.",
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    classification: Optional[str] = Query(None, description="Filter by classification type"),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    offset = (page - 1) * page_size

    query = select(Job)
    count_query = select(func.count()).select_from(Job)

    if status:
        query = query.where(Job.status == status.upper())
        count_query = count_query.where(Job.status == status.upper())

    if classification:
        query = query.where(Job.classification == classification.upper())
        count_query = count_query.where(Job.classification == classification.upper())

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Job.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[JobOut.model_validate(j) for j in jobs],
    )


# ---------------------------------------------------------------------------
# Get a single job by task_id (with resolved entity detail)
# ---------------------------------------------------------------------------


@router.get(
    "/{task_id}",
    response_model=JobDetailOut,
    summary="Get job detail",
    description=(
        "Returns a single job by its task_id, including the resolved entity "
        "(shipment, invoice, or unclassified event) if processing has completed."
    ),
)
async def get_job(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    result = await db.execute(select(Job).where(Job.task_id == task_id))
    job: Job | None = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with task_id '{task_id}' not found.",
        )

    detail = JobDetailOut.model_validate(job)

    # Attach resolved entity based on classification
    if job.classification == "SHIPMENT":
        shipment_result = await db.execute(
            select(Shipment).where(Shipment.job_id == job.id)
        )
        shipment = shipment_result.scalar_one_or_none()
        if shipment:
            detail.shipment = ShipmentOut.model_validate(shipment)

    elif job.classification == "INVOICE":
        invoice_result = await db.execute(
            select(Invoice).where(Invoice.job_id == job.id)
        )
        invoice = invoice_result.scalar_one_or_none()
        if invoice:
            detail.invoice = InvoiceOut.model_validate(invoice)

    elif job.classification == "UNCLASSIFIED":
        unclassified_result = await db.execute(
            select(UnclassifiedEvent).where(UnclassifiedEvent.job_id == job.id)
        )
        unclassified = unclassified_result.scalar_one_or_none()
        if unclassified:
            detail.unclassified = UnclassifiedEventOut.model_validate(unclassified)

    return detail
