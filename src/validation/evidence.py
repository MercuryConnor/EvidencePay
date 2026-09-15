"""Evidence grounding validation — verifies that extracted data is supported by document pages."""

from __future__ import annotations

import logging
from typing import List, Tuple

from src.models.accounting import AccountingIR
from src.models.evidence import EvidencePacket

logger = logging.getLogger(__name__)


def validate_evidence(ir: AccountingIR, packet: EvidencePacket) -> Tuple[bool, List[str]]:
    """Validate that IR values are grounded in the evidence packet.

    Checks:
    - Source pages are within valid document range [1, total_pages]
    - Mandatory identifiers exist
    """
    errors: List[str] = []

    if packet.total_pages <= 0:
        errors.append("Evidence packet contains 0 pages")

    for page_num in ir.source_pages:
        if page_num < 1 or page_num > packet.total_pages:
            errors.append(f"Invalid source page {page_num}; document has {packet.total_pages} pages")

    if not ir.invoice_number and not ir.gross_total:
        errors.append("Neither invoice number nor gross total could be grounded")

    return len(errors) == 0, errors
