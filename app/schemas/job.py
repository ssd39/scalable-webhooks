from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobOut(BaseModel):
    """Public representation of a Job record."""

    id: str
    task_id: str
    rq_job_id: Optional[str] = None
    status: str
    attempts: int
    max_attempts: int
    classification: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    total: int
    page: int
    page_size: int
    items: List[JobOut]


class ShipmentOut(BaseModel):
    id: str
    job_id: Optional[str] = None
    vendor_id: str
    tracking_number: str
    status: str
    event_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: str
    job_id: Optional[str] = None
    vendor_id: str
    invoice_id: str
    amount: float
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UnclassifiedEventOut(BaseModel):
    id: str
    job_id: Optional[str] = None
    payload: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobDetailOut(JobOut):
    """Job with its resolved record (shipment / invoice / unclassified)."""

    shipment: Optional[ShipmentOut] = None
    invoice: Optional[InvoiceOut] = None
    unclassified: Optional[UnclassifiedEventOut] = None
