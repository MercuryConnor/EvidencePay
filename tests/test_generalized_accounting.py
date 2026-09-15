"""Regression tests for generalized accounting patterns.

Tests:
1. Unit price inference when missing on explicit line total and quantity.
2. Implicit quantity defaulting to 1 for flat service charges with explicit total.
3. Header tax synthesis from total_tax_amount when individual taxes were omitted.
4. Discount deduplication when header discount duplicates line-level discount percentage/amounts.
5. Freight deduplication when freight is already present as an explicit line item.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from src.models.accounting import AccountingIR, LineItemIR, TaxIR
from src.accounting.reconstruction import reconstruct_autodraft
from src.accounting.taxes import reconcile_taxes_placement
from src.accounting.discounts import reconcile_discount_placement
from src.erp_validator import validate_payable


class TestUnitPriceInference:
    """Test unit price inference when line totals are explicit."""

    def test_infer_unit_price_single_item(self):
        """When quantity is 1 and unit_price is empty, unit_price = total."""
        ir = AccountingIR(
            gross_total="44.99",
            subtotal="44.99",
            line_items=[
                LineItemIR(description="Bananas", quantity="1", unit_price="", total="44.99")
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert len(payable.line_items) == 1
        assert payable.line_items[0].unit_price == "44.99"
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 44.99

    def test_infer_unit_price_multiple_items(self):
        """When quantity is 2 and total is 77.98, unit_price = 38.99."""
        ir = AccountingIR(
            gross_total="77.98",
            subtotal="77.98",
            line_items=[
                LineItemIR(description="Yoghurt", quantity="2", unit_price="", total="77.98")
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert payable.line_items[0].unit_price == "38.99"
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 77.98

    def test_flat_service_fee_implicit_quantity(self):
        """When quantity is empty on a flat service fee line, default quantity=1, unit_price=total."""
        ir = AccountingIR(
            gross_total="53.40",
            subtotal="53.40",
            line_items=[
                LineItemIR(description="Tarnekulud", quantity="", unit_price="", total="53.40")
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert payable.line_items[0].quantity == "1"
        assert payable.line_items[0].unit_price == "53.40"
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 53.40

    def test_preserve_existing_unit_price(self):
        """Explicit unit_price must not be overwritten."""
        ir = AccountingIR(
            gross_total="100.00",
            subtotal="100.00",
            line_items=[
                LineItemIR(description="Widgets", quantity="10", unit_price="10.00", total="100.00")
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert payable.line_items[0].unit_price == "10.00"
        res = validate_payable(payable)
        assert res.matches


class TestHeaderTaxSynthesis:
    """Test synthesizing header tax from total_tax_amount when individual TaxIR entries are omitted."""

    def test_synthesize_tax_when_taxes_empty_and_math_reconciles(self):
        """When ir.taxes is empty but total_tax_amount reconciles subtotal to gross, populate header tax."""
        ir = AccountingIR(
            gross_total="83.21",
            subtotal="67.10",
            total_tax_amount="16.11",
            taxes=[],
            line_items=[
                LineItemIR(description="Service", quantity="1", unit_price="67.10", total="67.10")
            ],
        )
        reconciled = reconcile_taxes_placement(ir)
        assert len(reconciled.taxes) == 1
        assert reconciled.taxes[0].tax_amount == "16.11"
        payable = reconstruct_autodraft(reconciled)
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 83.21


class TestDiscountDeduplication:
    """Test discount deduplication when header discount duplicates line-level discounts."""

    def test_clear_header_discount_when_line_percentage_matches(self):
        """When line discount percentage yields 424.61 and header discount is 424.61, clear header discount."""
        ir = AccountingIR(
            gross_total="407.95",
            subtotal="407.95",
            discount_amount="424.61",
            line_items=[
                LineItemIR(
                    description="Coffee",
                    quantity="24.0",
                    unit_price="34.69",
                    total="407.95",
                    discount_percentage="51.00",
                )
            ],
        )
        reconciled = reconcile_discount_placement(ir)
        # Header discount should be cleared because line 1 already discounts by 51%
        assert float(reconciled.discount_amount or 0) == 0.0
        payable = reconstruct_autodraft(reconciled)
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 407.95


class TestFreightDeduplication:
    """Test freight deduplication when freight is both an explicit line item and header charge."""

    def test_clear_header_freight_when_line_freight_exists(self):
        """When a line item has 'transport' and total 50.00, and freight_charges is 50.00, header freight is cleared."""
        ir = AccountingIR(
            gross_total="150.00",
            subtotal="150.00",
            freight_charges="50.00",
            line_items=[
                LineItemIR(description="Rental", quantity="1", unit_price="100.00", total="100.00"),
                LineItemIR(description="Transport fee", quantity="1", unit_price="50.00", total="50.00"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        # Header freight should not cause ERP to book 200.00
        res = validate_payable(payable)
        assert res.will_book_gross == 150.00
        assert res.matches


class TestTaxInclusivePricing:
    """Test tax-inclusive invoice detection and deduplication."""

    def test_tax_inclusive_clears_duplicate_taxes(self):
        """When stated_gross matches net_base before taxes, header tax is informational and cleared."""
        ir = AccountingIR(
            gross_total="1683.98",
            subtotal="1633.98",
            freight_charges="50.00",
            taxes=[TaxIR(tax_type="VAT", tax_amount="169.83")],
            line_items=[
                LineItemIR(description="Groceries", quantity="1", unit_price="1633.98", total="1633.98")
            ],
        )
        reconciled = reconcile_taxes_placement(ir)
        assert len(reconciled.taxes) == 0
        payable = reconstruct_autodraft(reconciled)
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 1683.98


class TestHeaderDiscountReconciliation:
    """Test header discount economic evaluation against stated gross."""

    def test_header_discount_retained_when_matching_stated_gross(self):
        """When applying header discount matches stated gross, line discounts are cleared."""
        ir = AccountingIR(
            gross_total="535.79",
            subtotal="868.51",
            discount_amount="432.91",
            taxes=[TaxIR(tax_type="IVA", tax_rate="23", tax_amount="100.19")],
            line_items=[
                LineItemIR(description="Product A", quantity="24", unit_price="34.69", discount_percentage="51.00"),
                LineItemIR(description="Desconto em Valor", total="-8.30"),
                LineItemIR(description="Product B", quantity="1", unit_price="35.95"),
            ],
        )
        reconciled = reconcile_discount_placement(ir)
        assert reconciled.discount_amount == "432.91"
        assert reconciled.line_items[0].discount_percentage == ""
        # Discount-only line removed
        assert len(reconciled.line_items) == 2
        payable = reconstruct_autodraft(reconciled)
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 535.79


class TestRobustLLMParsing:
    """Test _parse_llm_response handling of standard JSON aliases."""

    def test_parse_llm_response_with_aliases(self):
        """Parse LLM output using total_amount, subtotal_amount, line tax_rate, and float header_taxes."""
        from src.extraction.extractor import _parse_llm_response
        from src.models.evidence import EvidencePacket

        raw_data = {
            "invoice_number": "INV-TEST-001",
            "currency": "EUR",
            "total_amount": 26.47,
            "subtotal_amount": 21.70,
            "tax_amount": 4.77,
            "header_taxes": 0.0,
            "line_items": [
                {
                    "description": "Transport",
                    "quantity": 1.0,
                    "unit_price": 18.87,
                    "tax_rate": "22.00%",
                    "tax_amount": 4.15,
                },
                {
                    "description": "Fuel surcharge",
                    "quantity": 1.0,
                    "unit_price": 2.83,
                    "tax_rate": "22.00%",
                    "tax_amount": 0.62,
                },
            ],
        }
        ev = EvidencePacket(filename="INV-TEST.pdf", total_pages=1)
        candidates, declined = _parse_llm_response(raw_data, ev)
        assert len(candidates) == 1
        ir = candidates[0]
        assert ir.gross_total == "26.47"
        assert ir.subtotal == "21.7"
        assert len(ir.line_items) == 2
        assert ir.line_items[0].taxes[0].tax_rate == "22.00%"
        assert ir.line_items[0].taxes[0].tax_amount == "4.15"


class TestBundleHierarchy:
    """Test bundle parent-child duplicate item deduplication."""

    def test_prune_bundle_components_matching_parent(self):
        """When a parent bundle is followed by components summing to the parent total, prune components."""
        ir = AccountingIR(
            gross_total="124.00",
            subtotal="100.00",
            taxes=[TaxIR(tax_type="VAT", tax_rate="24.0", tax_amount="24.00")],
            line_items=[
                LineItemIR(description="Speaker Set Bundle", quantity="1", unit_price="100.00", total="100.00"),
                LineItemIR(description="Satellite Speaker", quantity="2", unit_price="35.00", total="70.00"),
                LineItemIR(description="Subwoofer", quantity="1", unit_price="30.00", total="30.00"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert len(payable.line_items) == 1
        assert payable.line_items[0].description == "Speaker Set Bundle"
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 124.00

    def test_preserve_independent_line_items(self):
        """When line items do not form a parent-child bundle, preserve all lines."""
        ir = AccountingIR(
            gross_total="248.00",
            subtotal="200.00",
            taxes=[TaxIR(tax_type="VAT", tax_rate="24.0", tax_amount="48.00")],
            line_items=[
                LineItemIR(description="Widget A", quantity="1", unit_price="100.00", total="100.00"),
                LineItemIR(description="Widget B", quantity="1", unit_price="100.00", total="100.00"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        assert len(payable.line_items) == 2
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 248.00


class TestOperationalMeasurements:
    """Test operational measurement vs billable quantity reconciliation."""

    def test_operational_weight_reconstruction(self):
        """When consignment manifest weights in quantity inflate line bases, reconstruct from authoritative summary."""
        ir = AccountingIR(
            gross_total="248.00",
            subtotal="200.00",
            taxes=[TaxIR(tax_type="VAT", tax_rate="24.0", tax_amount="48.00")],
            line_items=[
                LineItemIR(description="Shipment 1", quantity="25.0", unit_price="60.00", total="80.00"),
                LineItemIR(description="Shipment 2", quantity="40.0", unit_price="80.00", total="120.00"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        # Quantity normalized from operational weight (25kg, 40kg) to 1
        assert payable.line_items[0].quantity == "1"
        assert payable.line_items[1].quantity == "1"
        # Extra charges assigned difference to subtotal
        assert payable.extra_charges == "60.00"
        res = validate_payable(payable)
        assert res.matches
        assert res.will_book_gross == 248.00


class TestDiagnosticTaxonomy:
    """Test diagnostic root cause categorization."""

    def test_compound_tax_diagnosis(self):
        from src.validation.diagnostics import diagnose_mismatch
        from src.models.enums import DiagnosticCategory

        ir = AccountingIR(
            gross_total="1012.14",
            subtotal="835.27",
            excise_duties="88.33",
            line_items=[
                LineItemIR(description="Cerveja com IEC", quantity="10", unit_price="20.00", total="200.00")
            ],
        )
        diags = diagnose_mismatch(ir, 1324.53, "1012.14")
        assert diags[0].category == DiagnosticCategory.COMPOUND_TAX

    def test_non_linear_formula_diagnosis(self):
        from src.validation.diagnostics import diagnose_mismatch
        from src.models.enums import DiagnosticCategory

        ir = AccountingIR(
            gross_total="2487.73",
            line_items=[
                LineItemIR(description="Cooling System CCH-042 Connected Ton PM", quantity="3.5", unit_price="63.93", total="61.73")
            ],
        )
        diags = diagnose_mismatch(ir, 2507.75, "2487.73")
        assert diags[0].category == DiagnosticCategory.NON_LINEAR_BILLING_FORMULA


