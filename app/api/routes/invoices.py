import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.invoice import Invoice
from app.schemas.job import InvoiceOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get(
    "",
    summary="List invoices",
    description="Returns a paginated list of all invoice records, optionally filtered by vendor or currency.",
)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    vendor_id: Optional[str] = Query(None, description="Filter by vendor ID"),
    currency: Optional[str] = Query(None, description="Filter by currency code, e.g. USD"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * page_size

    query = select(Invoice)
    count_query = select(func.count()).select_from(Invoice)

    if vendor_id:
        query = query.where(Invoice.vendor_id == vendor_id)
        count_query = count_query.where(Invoice.vendor_id == vendor_id)
    if currency:
        query = query.where(Invoice.currency == currency.upper())
        count_query = count_query.where(Invoice.currency == currency.upper())

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(query.order_by(Invoice.updated_at.desc()).offset(offset).limit(page_size))
    ).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [InvoiceOut.model_validate(r) for r in rows],
    }


@router.get(
    "/{vendor_id}/{invoice_id}",
    response_model=InvoiceOut,
    summary="Get invoice by vendor + invoice ID",
)
async def get_invoice(
    vendor_id: str,
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
) -> InvoiceOut:
    result = await db.execute(
        select(Invoice).where(
            Invoice.vendor_id == vendor_id,
            Invoice.invoice_id == invoice_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' for vendor '{vendor_id}' not found.",
        )
    return InvoiceOut.model_validate(invoice)
