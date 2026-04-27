#!/usr/bin/env python3
"""
test_gen.py – LLM-powered webhook payload generator.

Uses Anthropic Claude (via LangChain, same config as the app) to generate
realistic, varied JSON payloads and prints them to stdout.

Usage:
    python test_gen.py                  # random type
    python test_gen.py --shipment       # shipment only
    python test_gen.py --invoice        # invoice only
    python test_gen.py --unclassified   # unclassified only
    python test_gen.py --shipment --count 3   # 3 shipment payloads
"""

import argparse
import json
import random
import sys
import os
from typing import Any, Dict, List

try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import BaseModel, Field
except ImportError as e:
    print(f"Missing dependency: {e}\nRun: pip install -r requirements.txt")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
from app.config import settings


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class GeneratedPayload(BaseModel):
    """Structured response from the LLM for each generated test payload."""

    payload: Dict[str, Any] = Field(
        ...,
        description=(
            "A realistic JSON payload of the requested type. "
            "Vary field names (e.g. vendorId / vendor_id / VendorId), "
            "add extra noise fields, use realistic values."
        ),
    )
    hint: str = Field(..., description="One-line description of what was generated")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a test-data generator for a webhook processing system.

Generate a single, realistic JSON payload of the type requested by the user.

Types:
1. SHIPMENT – must include: vendorId, trackingNumber, status (TRANSIT | DELIVERED | EXCEPTION),
   timestamp (ISO 8601). Optionally add carrier, origin, destination, weight, etc.
   Randomly vary field naming style: vendorId / vendor_id / VendorId / VENDOR_ID.

2. INVOICE – must include: vendorId, invoiceId, amount (float), currency (ISO 4217).
   Optionally add description, dueDate, lineItems, taxRate, etc.
   Randomly vary naming style.

3. UNCLASSIFIED – a payload that does NOT match either schema above.
   Be creative: user signup, IoT sensor reading, order event, heartbeat ping,
   log entry, analytics event, etc.

Rules:
- Use diverse, realistic values on every call (do not repeat the same vendor IDs, etc.).
- Never include a `task_id` field.
- `payload` must be a flat or lightly nested JSON object.
"""


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_payload(payload_type: str) -> GeneratedPayload:
    """Call the LLM and return a structured GeneratedPayload."""
    llm = ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=1.0,
        max_tokens=512,
    )
    structured_llm = llm.with_structured_output(GeneratedPayload)

    result: GeneratedPayload = structured_llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Generate a {payload_type.upper()} payload."),
    ])
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate random webhook test payloads using Claude (LangChain + Anthropic).",
    )
    parser.add_argument("--shipment", action="store_true", help="Generate shipment payload(s)")
    parser.add_argument("--invoice", action="store_true", help="Generate invoice payload(s)")
    parser.add_argument("--unclassified", action="store_true", help="Generate unclassified payload(s)")
    parser.add_argument("--count", type=int, default=1, metavar="N", help="How many payloads to generate (default: 1)")

    args = parser.parse_args()

    requested: List[str] = []
    if args.shipment:
        requested.append("shipment")
    if args.invoice:
        requested.append("invoice")
    if args.unclassified:
        requested.append("unclassified")

    all_types = ["shipment", "invoice", "unclassified"]

    for i in range(args.count):
        payload_type = random.choice(requested) if requested else random.choice(all_types)

        print(f"\n── [{i + 1}/{args.count}] Generating {payload_type.upper()} via LLM …")

        try:
            generated = generate_payload(payload_type)
        except Exception as exc:
            print(f"  ✗ LLM error: {exc}")
            sys.exit(1)

        print(f"  Hint    : {generated.hint}")
        print(f"  Payload :\n{json.dumps(generated.payload, indent=4)}")

    print(f"\n✓ Generated {args.count} payload(s).")


if __name__ == "__main__":
    main()
