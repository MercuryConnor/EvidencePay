"""Unit tests for the three-layer validation system and mismatch diagnostics."""

import pytest
from src.models import (
    AccountingIR,
    AutodraftBuyer,
    AutodraftLineItem,
    AutodraftPayable,
    AutodraftSupplier,
    AutodraftTax,
    EvidencePacket,
    InvoiceType,
    LineItemIR,
    SupplierIR,
    TaxIR,
)
from src.models.enums import DiagnosticCategory
from src.validation.accounting import validate_accounting_structure
from src.validation.diagnostics import diagnose_mismatch
from src.validation.evidence import validate_evidence
from src.validation.schema import validate_schema


class TestSchemaValidation:
    """Test schema compliance against AUTODRAFT_SCHEMA.md."""

    def test_valid_schema(self):
        payable = AutodraftPayable(
            invoice_number="INV-001",
            invoice_date="2026-03-01",
            invoice_type="INVOICE",
            currency="EUR",
            gross_total="100.00",
            supplier=AutodraftSupplier(name="Supplier", supplier_id="100"),
            buyer=AutodraftBuyer(company_code="C1", business_unit_code="B1", location_code="L1"),
            line_items=[AutodraftLineItem(description="Item", quantity="1", total="100.00")],
        )
        is_valid, errors = validate_schema(payable)
        assert is_valid
        assert len(errors) == 0

    def test_missing_required_field(self):
        payable = AutodraftPayable(
            invoice_number="",  # missing!
            invoice_date="2026-03-01",
            currency="EUR",
            gross_total="100.00",
            supplier=AutodraftSupplier(name="Supplier", supplier_id="100"),
            buyer=AutodraftBuyer(company_code="C1", business_unit_code="B1", location_code="L1"),
        )
        is_valid, errors = validate_schema(payable)
        assert not is_valid
        assert any("invoice_number" in e for e in errors)


class TestEvidenceValidation:
    """Test evidence grounding validation."""

    def test_valid_evidence_pages(self):
        packet = EvidencePacket(filename="doc.pdf", total_pages=3)
        ir = AccountingIR(invoice_number="INV-1", gross_total="100.00", source_pages=[1, 2])
        is_valid, errors = validate_evidence(ir, packet)
        assert is_valid

    def test_out_of_bounds_page(self):
        packet = EvidencePacket(filename="doc.pdf", total_pages=2)
        ir = AccountingIR(invoice_number="INV-1", gross_total="100.00", source_pages=[1, 5])
        is_valid, errors = validate_evidence(ir, packet)
        assert not is_valid
        assert any("5" in e for e in errors)


class TestMismatchDiagnostics:
    """Test diagnostic categorizer."""

    def test_rounding_mismatch(self):
        ir = AccountingIR(invoice_number="INV-1", gross_total="100.00")
        diags = diagnose_mismatch(ir, erp_gross=100.02, stated_gross_str="100.00")
        assert len(diags) > 0
        assert diags[0].category == DiagnosticCategory.ROUNDING_MISMATCH

    def test_header_tax_double_counted(self):
        ir = AccountingIR(
            invoice_number="INV-TAX",
            gross_total="100.00",
            taxes=[TaxIR(tax_type="VAT", tax_amount="19.00")],
        )
        diags = diagnose_mismatch(ir, erp_gross=119.00, stated_gross_str="100.00")
        assert any(d.category == DiagnosticCategory.TAX_PLACEMENT_MISMATCH for d in diags)

    def test_discount_mismatch(self):
        ir = AccountingIR(
            invoice_number="INV-DISC",
            gross_total="100.00",
            discount_amount="20.00",
        )
        diags = diagnose_mismatch(ir, erp_gross=80.00, stated_gross_str="100.00")
        assert any(d.category == DiagnosticCategory.HEADER_DISCOUNT_MISMATCH for d in diags)
