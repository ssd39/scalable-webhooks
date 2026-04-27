from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WebhookResponse(BaseModel):
    """Response returned after a webhook is accepted."""

    task_id: str = Field(..., description="Internal task UUID")
    job_id: str = Field(..., description="Redis Queue job ID")
    status: str = Field(..., description="Current task status")
    message: str = Field(..., description="Human-readable status message")
    queued_at: datetime = Field(default_factory=_now)


class TaskResult(BaseModel):
    """Result of a processed task."""

    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processed_at: datetime = Field(default_factory=_now)
