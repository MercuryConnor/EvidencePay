"""Document classification — determines document type and payable status.

Classifies documents based on multiple signals:
- Page content analysis
- Document structure
- Accounting intent indicators
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.models import DocumentType, EvidencePacket, PageRole

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of document classification."""
    document_type: str = "unknown"
    is_non_payable: bool = False
    decline_reason: str = ""
    payable_pages: list[int] = field(default_factory=list)
    non_payable_pages: list[int] = field(default_factory=list)
    num_payable_candidates: int = 1  # expected number of payables in the PDF


# Keywords indicating payable documents
_PAYABLE_KEYWORDS = [
    "invoice", "rechnung", "factura", "fatura", "facture", "invois",
    "tax invoice", "credit note", "credit memo", "gutschrift",
    "nota de crédito", "nota de credito",
]

# Keywords indicating NON-payable documents
_NON_PAYABLE_KEYWORDS = [
    "estimate", "quote", "quotation", "proposal", "proforma",
    "delivery note", "packing slip", "shipping",
    "reminder", "dunning", "mahnung", "payment reminder",
    "statement of account", "account statement",
    "receipt", "acknowledgment",
]


def classify_document(evidence: EvidencePacket) -> ClassificationResult:
    """Classify a document packet based on its content.

    Uses page-level text analysis and structural signals.
    This is a first-pass heuristic — the LLM extraction step
    will refine the classification.
    """
    result = ClassificationResult()
    result.payable_pages = list(range(1, evidence.total_pages + 1))

    # Gather all text from the document for classification
    all_text = ""
    for page in evidence.pages:
        if page.has_native_text:
            all_text += page.native_text.lower() + " "

    if not all_text.strip():
        # No native text — likely scanned images, need LLM vision
        # Don't classify as non-payable yet, let extraction handle it
        result.document_type = "unknown"
        logger.info("No native text found — classification deferred to LLM")
        return result

    # Check for non-payable indicators
    for keyword in _NON_PAYABLE_KEYWORDS:
        if keyword in all_text:
            # Check if payable keywords also present (e.g., "invoice" in a statement)
            has_payable = any(pk in all_text for pk in _PAYABLE_KEYWORDS)
            if not has_payable:
                result.is_non_payable = True
                result.document_type = _classify_non_payable_type(all_text)
                result.decline_reason = f"Document classified as non-payable: {result.document_type}"
                logger.info("Classified as non-payable: %s", result.document_type)
                return result

    # Check for payable indicators
    for keyword in _PAYABLE_KEYWORDS:
        if keyword in all_text:
            if "credit" in keyword:
                result.document_type = "credit_memo"
            else:
                result.document_type = "invoice"
            break

    if result.document_type == "unknown":
        # No clear indicators — let LLM decide
        logger.info("Ambiguous classification — deferred to LLM extraction")

    return result


def _classify_non_payable_type(text: str) -> str:
    """Determine the specific non-payable type."""
    if any(kw in text for kw in ["estimate", "quote", "quotation", "proposal", "proforma"]):
        return "estimate"
    if any(kw in text for kw in ["delivery note", "packing slip", "shipping"]):
        return "delivery_note"
    if any(kw in text for kw in ["reminder", "dunning", "mahnung", "payment reminder"]):
        return "reminder"
    if any(kw in text for kw in ["statement", "account statement"]):
        return "statement"
    return "non_payable"
