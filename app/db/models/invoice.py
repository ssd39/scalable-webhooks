import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        # Duplicate key: same vendor + invoice combination
        UniqueConstraint("vendor_id", "invoice_id", name="uq_invoices_vendor_invoice"),
    )

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
    invoice_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    job = relationship("Job", foreign_keys=[job_id], lazy="select")

    def __repr__(self) -> str:
        return f"<Invoice vendor={self.vendor_id} invoice_id={self.invoice_id} amount={self.amount}>"
