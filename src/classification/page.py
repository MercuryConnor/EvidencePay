"""Page-role classification — classifies individual pages by their accounting role.

Roles:
- INVOICE_HEADER: contains supplier/buyer info, date, invoice number
- INVOICE_LINES: line items table
- TAX_SUMMARY: tax breakdown table / VAT summary
- CREDIT_NOTE: credit note / memo header or body
- PAYMENT_REMITTANCE: bank details, payment slip, tear-off remittance advice
- STATEMENT_HISTORY: historical transaction statement / aging summary
- DELIVERY_SHIPPING: delivery receipt, bill of lading, dispatch advice
- ESTIMATE_QUOTE: pro forma, cost estimate, quote
- REMINDER_DUNNING: payment reminder, overdue notice
- DUPLICATE_COPY: duplicate/copy watermark or identical content
"""

from __future__ import annotations

import logging
from typing import List

from src.models.enums import PageRole
from src.models.evidence import PageEvidence

logger = logging.getLogger(__name__)


def classify_page_role(page: PageEvidence) -> PageRole:
    """Determine the functional accounting role of an individual page.

    Uses textual cues, headers, and structural keywords.
    """
    if not page.has_native_text or not page.native_text:
        return PageRole.UNKNOWN

    text = page.native_text.lower()

    # Duplicate / copy detection
    if any(w in text for w in ["duplicate", "customer copy", "client copy", "copia"]):
        return PageRole.DUPLICATE_COPY

    # Non-payable cues
    if any(w in text for w in ["delivery note", "lieferschein", "packing slip", "bon de livraison"]):
        return PageRole.DELIVERY_SHIPPING

    if any(w in text for w in ["proforma", "pro-forma", "quotation", "kostenvoranschlag", "devis"]):
        return PageRole.ESTIMATE_QUOTE

    if any(w in text for w in ["mahnung", "payment reminder", "overdue notice", "rappel"]):
        return PageRole.REMINDER_DUNNING

    if any(w in text for w in ["statement of account", "kontoauszug", "relevé de compte", "account summary"]):
        return PageRole.STATEMENT_HISTORY

    # Credit note
    if any(w in text for w in ["credit note", "credit memo", "gutschrift", "avoir", "nota de credito"]):
        return PageRole.CREDIT_NOTE

    # Tax summary
    if any(w in text for w in ["tax breakdown", "vat summary", "steuersatz", "steueraufschlüsselung", "tva sommaire"]):
        return PageRole.TAX_SUMMARY

    # Payment / remittance
    if any(w in text for w in ["remittance slip", "zahlungsanweisung", "bulletin de versement", "payment slip"]):
        return PageRole.PAYMENT_REMITTANCE

    # Invoice lines vs header
    has_header_info = any(w in text for w in ["invoice no", "rechnungs-nr", "bill to", "invoice date", "rechnungsdatum"])
    has_line_table = any(w in text for w in ["description", "qty", "quantity", "unit price", "amount", "gesamtpreis", "pos."])

    if has_header_info and has_line_table:
        return PageRole.INVOICE_HEADER  # First/main invoice page
    elif has_header_info:
        return PageRole.INVOICE_HEADER
    elif has_line_table:
        return PageRole.INVOICE_LINES

    return PageRole.UNKNOWN


def classify_pages_in_packet(pages: List[PageEvidence]) -> List[PageEvidence]:
    """Classify all pages in an evidence packet in place and return them."""
    for page in pages:
        page.role = classify_page_role(page)
    return pages
