"""
LLM-based payload classifier using LangChain + Anthropic.

Uses LangChain's ``with_structured_output`` to enforce a typed Pydantic
response from Claude, then maps it to one of three classification types:

  SHIPMENT   → vendorId, trackingNumber, status, timestamp
  INVOICE    → vendorId, invoiceId, amount, currency
  UNCLASSIFIED → raw payload stored as-is, no further extraction
"""

import json
import logging
from typing import Any, Dict, Literal, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured-output schemas
# ---------------------------------------------------------------------------


class ShipmentData(BaseModel):
    vendor_id: str = Field(..., description="Vendor identifier")
    tracking_number: str = Field(..., description="Shipment tracking number")
    status: Literal["TRANSIT", "DELIVERED", "EXCEPTION"] = Field(
        ..., description="Current shipment status"
    )
    timestamp: str = Field(..., description="ISO 8601 event timestamp")


class InvoiceData(BaseModel):
    vendor_id: str = Field(..., description="Vendor identifier")
    invoice_id: str = Field(..., description="Unique invoice identifier")
    amount: float = Field(..., description="Invoice amount")
    currency: str = Field(..., description="ISO 4217 currency code, e.g. USD")


class ClassificationResult(BaseModel):
    """Structured output returned by the LLM for every webhook payload."""

    type: Literal["SHIPMENT", "INVOICE", "UNCLASSIFIED"] = Field(
        ...,
        description=(
            "SHIPMENT if the payload is a shipment update, "
            "INVOICE if it is an invoice, "
            "UNCLASSIFIED otherwise."
        ),
    )
    shipment: Optional[ShipmentData] = Field(
        None, description="Populated when type == SHIPMENT"
    )
    invoice: Optional[InvoiceData] = Field(
        None, description="Populated when type == INVOICE"
    )
    reason: str = Field(..., description="One-sentence explanation of the classification")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a data classifier for a logistics and finance platform.

Analyse the JSON payload provided by the user and classify it into exactly one of:

1. SHIPMENT – a shipment/tracking update.
   Required fields (case-insensitive match allowed): vendorId, trackingNumber,
   status (TRANSIT | DELIVERED | EXCEPTION), timestamp (ISO 8601).
   → populate the `shipment` field with normalised values.

2. INVOICE – a financial invoice.
   Required fields: vendorId, invoiceId, amount (number), currency (ISO 4217).
   → populate the `invoice` field with normalised values.

3. UNCLASSIFIED – does not match either schema above.
   → leave `shipment` and `invoice` as null.

Always fill the `reason` field with a brief explanation.
"""


# ---------------------------------------------------------------------------
# Public classify function
# ---------------------------------------------------------------------------


def classify_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify ``raw_payload`` using Anthropic Claude via LangChain structured output.

    Returns a plain dict::

        {
            "type": "SHIPMENT" | "INVOICE" | "UNCLASSIFIED",
            "data": { ... extracted + normalised fields ... },
            "reason": "..."
        }

    Raises on LLM or parsing errors (the caller is responsible for retrying).
    """
    llm = ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0,
        max_tokens=1024,
    )

    structured_llm = llm.with_structured_output(ClassificationResult)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(raw_payload, default=str)),
    ]

    logger.debug("Sending payload to Anthropic for classification.")
    result: ClassificationResult = structured_llm.invoke(messages)

    logger.info(
        "LLM classification → type=%s reason=%s", result.type, result.reason
    )

    if result.type == "SHIPMENT":
        if not result.shipment:
            raise ValueError(
                f"LLM classified as SHIPMENT but `shipment` field is missing. "
                f"Reason: {result.reason}"
            )
        data: Dict[str, Any] = result.shipment.model_dump()

    elif result.type == "INVOICE":
        if not result.invoice:
            raise ValueError(
                f"LLM classified as INVOICE but `invoice` field is missing. "
                f"Reason: {result.reason}"
            )
        data = result.invoice.model_dump()

    elif result.type == "UNCLASSIFIED":
        # Preserve the original payload so the caller can store it verbatim
        data = raw_payload

    else:
        # Should never happen given the Literal type constraint, but guard anyway.
        raise ValueError(
            f"Unexpected classification type {result.type!r} returned by LLM."
        )

    return {
        "type": result.type,
        "data": data,
        "reason": result.reason,
    }
