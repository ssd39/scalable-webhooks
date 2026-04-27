"""
RQ task: classify webhook payload via LLM and persist to PostgreSQL.

Flow per execution:
  1. Increment attempt counter on the Job record, set status → PROCESSING.
  2. On RETRY attempts (attempts > 1) sleep RETRY_DELAY seconds before
     re-processing, giving transient errors (network, LLM rate-limit) time
     to resolve. First attempt runs immediately.
  3. Call the LLM to classify the payload.
  4. Persist the result to the appropriate table (shipments / invoices /
     unclassified_events) with duplicate-update logic.
  5. Mark the Job as COMPLETED.

On any exception:
  - If attempts < MAX_ATTEMPTS  → set status RETRYING, re-raise so RQ retries.
  - If attempts >= MAX_ATTEMPTS → set status FAILED, return error dict (RQ
    records this as a successful job result so it won't retry further).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

from dateutil import parser as dateutil_parser

from app.config import settings
from app.db.database import SyncSessionLocal
from app.db.models.invoice import Invoice
from app.db.models.job import Job, JobStatus
from app.db.models.shipment import Shipment, ShipmentStatus
from app.db.models.unclassified import UnclassifiedEvent
from app.services.llm import classify_payload

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAY = 10  # seconds – applied only on retry attempts (attempt > 1)


# ---------------------------------------------------------------------------
# Handlers per classification type
# ---------------------------------------------------------------------------


def _handle_shipment(db, job: Job, data: Dict[str, Any]) -> None:
    """Upsert a Shipment record. Update only if the incoming event is newer."""
    tracking_number = data["tracking_number"]
    incoming_ts: datetime = dateutil_parser.isoparse(data["timestamp"])
    if incoming_ts.tzinfo is None:
        incoming_ts = incoming_ts.replace(tzinfo=timezone.utc)

    existing: Shipment | None = (
        db.query(Shipment).filter(Shipment.tracking_number == tracking_number).first()
    )

    if existing is None:
        shipment = Shipment(
            job_id=job.id,
            vendor_id=data["vendor_id"],
            tracking_number=tracking_number,
            status=ShipmentStatus(data["status"]),
            event_timestamp=incoming_ts,
        )
        db.add(shipment)
        logger.info("[task:%s] Shipment %s created.", job.task_id, tracking_number)
    else:
        if incoming_ts > existing.event_timestamp:
            existing.job_id = job.id
            existing.vendor_id = data["vendor_id"]
            existing.status = ShipmentStatus(data["status"])
            existing.event_timestamp = incoming_ts
            logger.info(
                "[task:%s] Shipment %s updated (newer event).", job.task_id, tracking_number
            )
        else:
            logger.info(
                "[task:%s] Shipment %s duplicate ignored (not newer).",
                job.task_id, tracking_number,
            )


def _handle_invoice(db, job: Job, data: Dict[str, Any]) -> None:
    """Upsert an Invoice record. Update only if the incoming job is newer."""
    vendor_id = data["vendor_id"]
    invoice_id = data["invoice_id"]

    existing: Invoice | None = (
        db.query(Invoice)
        .filter(Invoice.vendor_id == vendor_id, Invoice.invoice_id == invoice_id)
        .first()
    )

    if existing is None:
        invoice = Invoice(
            job_id=job.id,
            vendor_id=vendor_id,
            invoice_id=invoice_id,
            amount=data["amount"],
            currency=data["currency"],
        )
        db.add(invoice)
        logger.info("[task:%s] Invoice %s/%s created.", job.task_id, vendor_id, invoice_id)
    else:
        if job.created_at > existing.updated_at:
            existing.job_id = job.id
            existing.amount = data["amount"]
            existing.currency = data["currency"]
            logger.info(
                "[task:%s] Invoice %s/%s updated (newer job).", job.task_id, vendor_id, invoice_id
            )
        else:
            logger.info(
                "[task:%s] Invoice %s/%s duplicate ignored (not newer).",
                job.task_id, vendor_id, invoice_id,
            )


def _handle_unclassified(db, job: Job, data: Dict[str, Any]) -> None:
    """Always insert an UnclassifiedEvent — no duplicate logic needed."""
    event = UnclassifiedEvent(job_id=job.id, payload=data)
    db.add(event)
    logger.info("[task:%s] Stored as UnclassifiedEvent.", job.task_id)


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


def process_webhook_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry-point called by the RQ worker.

    ``payload`` is the raw webhook JSON body with an injected ``task_id`` key.
    """
    task_id = payload.get("task_id", "unknown")
    db = SyncSessionLocal()

    try:
        # ── 1. Load job & increment attempt ───────────────────────────────
        job: Job | None = db.query(Job).filter(Job.task_id == task_id).first()
        if job is None:
            logger.error("[task:%s] Job record not found – cannot process.", task_id)
            return {"error": "Job not found", "task_id": task_id}

        job.attempts += 1
        job.status = JobStatus.PROCESSING
        db.commit()

        # ── 2. Delay only on retry attempts ───────────────────────────────
        if job.attempts > 1:
            logger.info(
                "[task:%s] Retry attempt %d/%d – waiting %ds before re-processing …",
                task_id, job.attempts, MAX_ATTEMPTS, RETRY_DELAY,
            )
            time.sleep(RETRY_DELAY)
        else:
            logger.info("[task:%s] First attempt – processing immediately.", task_id)

        # ── 3. Strip internal task_id before sending to LLM ───────────────
        clean_payload = {k: v for k, v in payload.items() if k != "task_id"}

        # ── 4. LLM classification ──────────────────────────────────────────
        classification = classify_payload(clean_payload)
        job.classification = classification["type"]
        db.commit()

        # ── 5. Persist to appropriate table ───────────────────────────────
        if classification["type"] == "SHIPMENT":
            _handle_shipment(db, job, classification["data"])
        elif classification["type"] == "INVOICE":
            _handle_invoice(db, job, classification["data"])
        elif classification["type"] == "UNCLASSIFIED":
            _handle_unclassified(db, job, classification["data"])

        # ── 6. Mark completed ──────────────────────────────────────────────
        job.status = JobStatus.COMPLETED
        job.error_message = None
        db.commit()

        logger.info("[task:%s] Completed (type=%s).", task_id, classification["type"])
        return {
            "task_id": task_id,
            "status": "completed",
            "classification": classification["type"],
        }

    except Exception as exc:
        logger.exception("[task:%s] Error on attempt %d: %s", task_id, job.attempts if job else "?", exc)

        if job:
            job.error_message = str(exc)

            if job.attempts >= MAX_ATTEMPTS:
                # All retries exhausted – mark as permanently failed
                job.status = JobStatus.FAILED
                db.commit()
                logger.error("[task:%s] Max attempts (%d) reached – job FAILED.", task_id, MAX_ATTEMPTS)
                # Return (not raise) so RQ marks job as success and stops retrying
                return {"task_id": task_id, "status": "failed", "error": str(exc)}
            else:
                job.status = JobStatus.RETRYING
                db.commit()

        # Re-raise so RQ's Retry(max=4) mechanism re-queues the job
        raise

    finally:
        db.close()
