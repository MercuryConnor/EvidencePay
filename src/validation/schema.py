"""Schema validation — validates autodraft JSON structure against AUTODRAFT_SCHEMA.md."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from src.models.autodraft import AutodraftPayable

logger = logging.getLogger(__name__)

REQUIRED_PAYABLE_FIELDS = [
    "invoice_number",
    "invoice_date",
    "invoice_type",
    "currency",
    "supplier",
    "buyer",
    "gross_total",
]

REQUIRED_SUPPLIER_FIELDS = [
    "name",
    "supplier_id",
]

REQUIRED_BUYER_FIELDS = [
    "company_code",
    "business_unit_code",
    "location_code",
]


def validate_schema(payable: AutodraftPayable | dict) -> Tuple[bool, List[str]]:
    """Validate a payable object or dict against the autodraft schema.

    Returns:
        tuple: (is_valid, list_of_validation_errors)
    """
    errors: List[str] = []
    data = payable.model_dump() if isinstance(payable, AutodraftPayable) else payable

    for req in REQUIRED_PAYABLE_FIELDS:
        val = data.get(req)
        if val is None or val == "":
            errors.append(f"Missing required payable field: {req}")

    # Supplier
    supplier = data.get("supplier")
    if not isinstance(supplier, dict):
        errors.append("Field 'supplier' must be an object")
    else:
        for req in REQUIRED_SUPPLIER_FIELDS:
            if not supplier.get(req):
                errors.append(f"Missing required supplier field: {req}")

    # Buyer
    buyer = data.get("buyer")
    if not isinstance(buyer, dict):
        errors.append("Field 'buyer' must be an object")
    else:
        for req in REQUIRED_BUYER_FIELDS:
            if not buyer.get(req):
                errors.append(f"Missing required buyer field: {req}")

    # Line items
    line_items = data.get("line_items", [])
    if not isinstance(line_items, list):
        errors.append("Field 'line_items' must be a list")
    else:
        for idx, li in enumerate(line_items):
            if not isinstance(li, dict):
                errors.append(f"Line item {idx} must be an object")
                continue
            if not li.get("quantity") and not li.get("total"):
                errors.append(f"Line item {idx} missing quantity and total")

    return len(errors) == 0, errors
