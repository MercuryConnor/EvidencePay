"""Unit tests for document and page-role classification."""

import pytest
from src.classification.document import classify_document
from src.classification.page import classify_page_role
from src.models.enums import PageRole
from src.models.evidence import EvidencePacket, PageEvidence


class TestPageRoleClassification:
    """Test classification of individual page accounting roles."""

    def test_invoice_header(self):
        page = PageEvidence(
            page_number=1,
            native_text="INVOICE NO: INV-100\nDate: 2026-03-01\nBill To: Acme Corp\nDescription: Consulting Qty: 1 Unit Price: 100",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.INVOICE_HEADER

    def test_credit_note_page(self):
        page = PageEvidence(
            page_number=1,
            native_text="GUTSCHRIFT / CREDIT NOTE\nCredit Memo #: CM-501\nOriginal Invoice: INV-100",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.CREDIT_NOTE

    def test_delivery_note_page(self):
        page = PageEvidence(
            page_number=1,
            native_text="DELIVERY NOTE / PACKING SLIP\nGoods received confirmation\nItems shipped: 5",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.DELIVERY_SHIPPING

    def test_reminder_page(self):
        page = PageEvidence(
            page_number=1,
            native_text="PAYMENT REMINDER / 2. MAHNUNG\nPlease settle overdue amount of EUR 500",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.REMINDER_DUNNING

    def test_statement_page(self):
        page = PageEvidence(
            page_number=1,
            native_text="STATEMENT OF ACCOUNT\nTransactions summary for March 2026",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.STATEMENT_HISTORY

    def test_duplicate_page(self):
        page = PageEvidence(
            page_number=2,
            native_text="INVOICE COPY / DUPLICATE\nCustomer copy - do not pay",
            has_native_text=True,
        )
        role = classify_page_role(page)
        assert role == PageRole.DUPLICATE_COPY


class TestDocumentClassification:
    """Test packet-level document classification."""

    def test_payable_invoice(self):
        packet = EvidencePacket(filename="invoice.pdf", total_pages=1)
        packet.pages.append(PageEvidence(
            page_number=1,
            native_text="TAX INVOICE\nSupplier: ACME Ltd\nInvoice: INV-01\nGross Total: EUR 100.00",
            has_native_text=True,
        ))
        result = classify_document(packet)
        assert result.document_type == "invoice"
        assert not result.is_non_payable

    def test_non_payable_estimate(self):
        packet = EvidencePacket(filename="quote.pdf", total_pages=1)
        packet.pages.append(PageEvidence(
            page_number=1,
            native_text="COST ESTIMATE / PROPOSAL / QUOTATION\nEstimated cost for project\nValid for 30 days",
            has_native_text=True,
        ))
        result = classify_document(packet)
        assert result.is_non_payable
        assert result.document_type == "estimate"
        assert "estimate" in result.decline_reason.lower()
