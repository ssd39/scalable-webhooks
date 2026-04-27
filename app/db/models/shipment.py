import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ShipmentStatus(str, enum.Enum):
    TRANSIT = "TRANSIT"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # FK to the job that created / last updated this record
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    vendor_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    tracking_number: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(
        Enum(ShipmentStatus, name="shipment_status"),
        nullable=False,
    )
    # The event timestamp from the payload (used for duplicate-newer check)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    job = relationship("Job", foreign_keys=[job_id], lazy="select")

    def __repr__(self) -> str:
        return f"<Shipment tracking={self.tracking_number} status={self.status}>"
