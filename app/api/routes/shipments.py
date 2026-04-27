import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.shipment import Shipment
from app.schemas.job import ShipmentOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.get(
    "",
    summary="List shipments",
    description="Returns a paginated list of all shipment records, optionally filtered by vendor or status.",
)
async def list_shipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    vendor_id: Optional[str] = Query(None, description="Filter by vendor ID"),
    status: Optional[str] = Query(None, description="Filter by status: TRANSIT | DELIVERED | EXCEPTION"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * page_size

    query = select(Shipment)
    count_query = select(func.count()).select_from(Shipment)

    if vendor_id:
        query = query.where(Shipment.vendor_id == vendor_id)
        count_query = count_query.where(Shipment.vendor_id == vendor_id)
    if status:
        query = query.where(Shipment.status == status.upper())
        count_query = count_query.where(Shipment.status == status.upper())

    total = (await db.execute(count_query)).scalar_one()
    rows = (await db.execute(query.order_by(Shipment.updated_at.desc()).offset(offset).limit(page_size))).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ShipmentOut.model_validate(r) for r in rows],
    }


@router.get(
    "/{tracking_number}",
    response_model=ShipmentOut,
    summary="Get shipment by tracking number",
)
async def get_shipment(
    tracking_number: str,
    db: AsyncSession = Depends(get_db),
) -> ShipmentOut:
    result = await db.execute(
        select(Shipment).where(Shipment.tracking_number == tracking_number)
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment with tracking number '{tracking_number}' not found.",
        )
    return ShipmentOut.model_validate(shipment)
