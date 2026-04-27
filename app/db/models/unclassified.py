import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UnclassifiedEvent(Base):
    """Stores raw payloads that the LLM could not classify as Shipment or Invoice."""

    __tablename__ = "unclassified_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Full raw payload stored as JSONB – no schema enforced
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    job = relationship("Job", foreign_keys=[job_id], lazy="select")

    def __repr__(self) -> str:
        return f"<UnclassifiedEvent id={self.id} job_id={self.job_id}>"
