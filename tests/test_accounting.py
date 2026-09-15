"""Unit tests for deterministic accounting reconstruction and calculations."""

from decimal import Decimal
import pytest

from src.accounting.charges import total_charges
from src.accounting.discounts import compute_net_discount
from src.accounting.reconstruction import reconstruct_autodraft
from src.accounting.taxes import is_withholding_tax, reconcile_taxes_placement
from src.erp_validator import validate_payable
from src.models import (
    AccountingIR,
    InvoiceType,
    LineItemIR,
    SupplierIR,
    BuyerIR,
    TaxIR,
)


class TestAccountingReconstruction:
    """Test suite for deterministic conversion from AccountingIR to AutodraftPayable."""

    def test_basic_reconstruction(self):
        ir = AccountingIR(
            invoice_number="INV-2026-001",
            invoice_date="2026-03-01",
            due_date="2026-03-31",
            currency="EUR",
            gross_total="119.00",
            subtotal="100.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            taxes=[
                TaxIR(tax_type="VAT", tax_rate="19", tax_amount="19.00", tax_type_code="V19"),
            ],
            line_items=[
                LineItemIR(description="Widget A", quantity="1", unit_price="100.00", total="100.00"),
            ],
        )

        payable = reconstruct_autodraft(ir)
        assert payable.invoice_number == "INV-2026-001"
        assert payable.gross_total == "119.00"
        assert payable.supplier.supplier_id == "1001"
        assert len(payable.line_items) == 1
        assert len(payable.taxes) == 1

        # Check ERP validation
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 119.00) < 0.01

    def test_line_level_tax_reconstruction(self):
        ir = AccountingIR(
            invoice_number="INV-LINE-TAX",
            currency="EUR",
            gross_total="238.00",
            subtotal="200.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(
                    description="Item 1",
                    quantity="2",
                    unit_price="100.00",
                    total="200.00",
                    taxes=[TaxIR(tax_type="VAT", tax_rate="19", tax_amount="38.00", tax_type_code="V19", is_line_level=True)],
                )
            ],
        )
        payable = reconstruct_autodraft(ir)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 238.00) < 0.01

    def test_line_discount_computation(self):
        ir = AccountingIR(
            invoice_number="INV-DISC",
            currency="EUR",
            gross_total="90.00",
            subtotal="100.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(
                    description="Discounted Item",
                    quantity="1",
                    unit_price="100.00",
                    discount_percentage="10",
                    total="90.00",
                )
            ],
        )
        payable = reconstruct_autodraft(ir)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 90.00) < 0.01

    def test_withholding_tax_reduction(self):
        # Tax with negative amount reduces the gross
        tax = TaxIR(tax_type="WHT", tax_name="Withholding Tax", tax_amount="-10.00")
        assert is_withholding_tax(tax)

        ir = AccountingIR(
            invoice_number="INV-WHT",
            currency="EUR",
            gross_total="90.00",
            subtotal="100.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            taxes=[tax],
            line_items=[
                LineItemIR(description="Service", quantity="1", unit_price="100.00", total="100.00")
            ],
        )
        payable = reconstruct_autodraft(ir)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 90.00) < 0.01

    def test_charges_addition(self):
        ir = AccountingIR(
            invoice_number="INV-CHARGES",
            currency="EUR",
            gross_total="125.00",
            subtotal="100.00",
            freight_charges="15.00",
            extra_charges="10.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(description="Hardware", quantity="1", unit_price="100.00", total="100.00")
            ],
        )
        assert total_charges(ir) == Decimal("25.00")
        payable = reconstruct_autodraft(ir)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 125.00) < 0.01

    def test_credit_memo_positive_magnitude(self):
        ir = AccountingIR(
            invoice_number="CM-001",
            invoice_type=InvoiceType.CREDIT_MEMO,
            currency="EUR",
            gross_total="50.00",
            subtotal="50.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(description="Returned item", quantity="1", unit_price="50.00", total="50.00")
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert payable.invoice_type == "CREDIT_MEMO"
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 50.00) < 0.01

    def test_reconcile_taxes_duplicate_header(self):
        """Test that header taxes duplicating line taxes are cleared to prevent double counting."""
        ir = AccountingIR(
            invoice_number="INV-TAX-DUP",
            currency="EUR",
            gross_total="119.00",
            subtotal="100.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            taxes=[
                TaxIR(tax_type="VAT", tax_rate="19", tax_amount="19.00", tax_type_code="V19"),
            ],
            line_items=[
                LineItemIR(
                    description="Item",
                    quantity="1",
                    unit_price="100.00",
                    total="100.00",
                    taxes=[TaxIR(tax_type="VAT", tax_rate="19", tax_amount="19.00", tax_type_code="V19")],
                )
            ],

        )
        reconciled = reconcile_taxes_placement(ir)
        # Header taxes should be cleared
        assert len(reconciled.taxes) == 0
        payable = reconstruct_autodraft(reconciled)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 119.00) < 0.01

    def test_reconcile_discount_duplicate_header(self):
        """Test that header discount matching sum of line discounts is cleared."""
        from src.accounting.discounts import reconcile_discount_placement
        ir = AccountingIR(
            invoice_number="INV-DISC-DUP",
            currency="EUR",
            gross_total="90.00",
            subtotal="100.00",
            discount_amount="10.00",
            supplier=SupplierIR(name="Supplier GmbH", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(
                    description="Item",
                    quantity="1",
                    unit_price="100.00",
                    total="100.00",
                    discount="10.00",
                )
            ],
        )
        reconciled = reconcile_discount_placement(ir)
        assert reconciled.discount_amount == ""
        payable = reconstruct_autodraft(reconciled)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 90.00) < 0.01

    def test_unit_price_scale_normalization(self):
        """Test unit price scale correction when unit price was extracted as line total for qty > 1 (DU-05 pattern)."""
        from src.normalization.numbers import normalize_accounting_ir
        ir = AccountingIR(
            invoice_number="INV-SCALE",
            currency="SGD",
            gross_total="771.66",
            subtotal="771.66",
            supplier=SupplierIR(name="Supplier Pte", supplier_id="1001"),
            buyer=BuyerIR(company_code="COMP1", business_unit_code="BU1", location_code="LOC1"),
            line_items=[
                LineItemIR(
                    description="Batch items",
                    quantity="100",
                    unit_price="771.66",
                    total="771.66",
                )
            ],
        )
        normalized = normalize_accounting_ir(ir)
        assert normalized.line_items[0].unit_price == "7.7166"
        payable = reconstruct_autodraft(normalized)
        erp_res = validate_payable(payable)
        assert erp_res.matches
        assert abs(erp_res.will_book_gross - 771.66) < 0.01

    def test_pass_aware_cache_keys(self, tmp_path):
        """Test that pass_type and focus create distinct cache keys."""
        from src.cache.extraction_cache import compute_cache_key
        dummy_file = tmp_path / "test.pdf"
        dummy_file.write_bytes(b"%PDF-dummy")

        key_initial = compute_cache_key(dummy_file, pass_type="initial")
        key_recheck1 = compute_cache_key(dummy_file, pass_type="recheck_1", focus="tax issue")
        key_recheck2 = compute_cache_key(dummy_file, pass_type="recheck_2", focus="discount issue")

        assert key_initial != key_recheck1
        assert key_recheck1 != key_recheck2
        assert "recheck_1" in key_recheck1
        assert "recheck_2" in key_recheck2

