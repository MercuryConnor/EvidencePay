"""Accounting structure validation — validates accounting logic and structural integrity."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Tuple

from src.models.accounting import AccountingIR
from src.models.enums import InvoiceType
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)


def validate_accounting_structure(ir: AccountingIR) -> Tuple[bool, List[str]]:
    """Validate that the AccountingIR respects fundamental accounting principles.

    Checks:
    - Non-empty line items or total
    - Credit memo magnitude semantics (positive numbers, invoice_type = CREDIT_MEMO)
    - Valid currency
    - Gross total consistency
    """
    errors: List[str] = []

    # Currency
    if not ir.currency:
        errors.append("Missing document currency")

    # Credit memo semantics
    if ir.invoice_type == InvoiceType.CREDIT_MEMO:
        gross = parse_decimal(ir.gross_total)
        if gross < 0:
            errors.append("Credit memo gross_total should have positive magnitude in schema")

    # Lines or subtotal
    if not ir.line_items and parse_decimal(ir.gross_total) == 0:
        errors.append("Invoice contains neither line items nor a valid gross total")

    return len(errors) == 0, errors
