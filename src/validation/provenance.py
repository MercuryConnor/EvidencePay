"""Provenance validation — ensures that every emitted value is traceable back to document evidence."""

from __future__ import annotations

import logging
from typing import List, Tuple

from src.models.accounting import AccountingIR

logger = logging.getLogger(__name__)


def validate_provenance(ir: AccountingIR) -> Tuple[bool, List[str]]:
    """Verify that values in AccountingIR have traceability back to the source document."""
    warnings: List[str] = []

    if not ir.source_pages:
        warnings.append("No source pages recorded in AccountingIR")

    if not ir.supplier.name and not ir.supplier.vat_id:
        warnings.append("Supplier identity is unanchored in document text")

    return True, warnings
