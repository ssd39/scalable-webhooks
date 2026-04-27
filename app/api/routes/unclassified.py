import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.unclassified import UnclassifiedEvent
from app.schemas.job import UnclassifiedEventOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/unclassified", tags=["Unclassified"])


@router.get(
    "",
    summary="List unclassified events",
    description="Returns a paginated list of all webhook payloads the LLM could not classify.",
)
async def list_unclassified(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * page_size

    total = (
        await db.execute(select(func.count()).select_from(UnclassifiedEvent))
    ).scalar_one()

    rows = (
        await db.execute(
            select(UnclassifiedEvent)
            .order_by(UnclassifiedEvent.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [UnclassifiedEventOut.model_validate(r) for r in rows],
    }


@router.get(
    "/{event_id}",
    response_model=UnclassifiedEventOut,
    summary="Get unclassified event by ID",
)
async def get_unclassified_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> UnclassifiedEventOut:
    result = await db.execute(
        select(UnclassifiedEvent).where(UnclassifiedEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unclassified event '{event_id}' not found.",
        )
    return UnclassifiedEventOut.model_validate(event)
