"""Regression tests for evaluator semantics.

Verifies:
1. Genuine non-payable (e.g. delivery_note, reminder, form) is not classified as an ERP failure.
2. Payable ERP mismatch is classified as PAYABLE_RECONCILIATION_FAILURE, never as a genuine non-payable.
3. Accepted payable match contributes to accepted ERP match rate.
4. Rejected payable reconstruction failure contributes to overall candidate reconciliation rate.
5. Denominators are explicit (e.g. 28/28 accepted vs 28/37 overall candidates).
6. Financial summary for accepted payables only includes accepted payables, excluding failed candidates.
"""

from __future__ import annotations

import json
import pytest
from decimal import Decimal
from pathlib import Path

from scripts.evaluate import evaluate_outputs, _map_to_canonical_category


@pytest.fixture
def mock_output_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with synthetic output JSON files for evaluation testing."""
    # 1. Accepted payable: valid invoice matching ERP
    p1 = {
        "file": "INV-VALID.pdf",
        "payables": [
            {
                "invoice_number": "INV-100",
                "invoice_type": "INVOICE",
                "currency": "EUR",
                "gross_total": "100.00",
                "supplier": {"name": "Vendor A"},
                "buyer": {"company_code": "US01"},
                "payment_term_id": "NET30",
                "line_items": [
                    {
                        "description": "Item 1",
                        "quantity": "1",
                        "unit_price": "100.00",
                        "total": "100.00",
                    }
                ],
            }
        ],
        "declined": [],
    }
    with open(tmp_path / "INV-VALID.json", "w", encoding="utf-8") as f:
        json.dump(p1, f)

    # 2. Genuine non-payable: delivery note
    p2 = {
        "file": "DN-01.pdf",
        "payables": [],
        "declined": [
            {
                "doc_type": "delivery_note",
                "reason": "Document is a delivery note with shipping details and no payment request",
            }
        ],
    }
    with open(tmp_path / "DN-01.json", "w", encoding="utf-8") as f:
        json.dump(p2, f)

    # 3. Genuine non-payable: payment reminder
    p3 = {
        "file": "REM-01.pdf",
        "payables": [],
        "declined": [
            {
                "doc_type": "reminder",
                "reason": "Payment reminder (Mahnung), not an invoice or credit memo",
            }
        ],
    }
    with open(tmp_path / "REM-01.json", "w", encoding="utf-8") as f:
        json.dump(p3, f)

    # 4. Payable candidate whose accounting reconstruction failed (ERP mismatch)
    p4 = {
        "file": "INV-FAIL.pdf",
        "payables": [],
        "declined": [
            {
                "doc_type": "invoice",
                "reason": (
                    "PAYABLE_RECONCILIATION_FAILURE: inv=INV-999, curr=EUR, stated=500.00, "
                    "erp=350.00, delta=-150.00, category=UNIT_PRICE: "
                    "Line items missing explicit unit price; ERP books zero line base."
                ),
            }
        ],
    }
    with open(tmp_path / "INV-FAIL.json", "w", encoding="utf-8") as f:
        json.dump(p4, f)

    return tmp_path


def test_genuine_non_payable_is_not_erp_failure(mock_output_dir: Path):
    """Genuine non-payable documents must not be counted as ERP failures."""
    stats = evaluate_outputs(mock_output_dir)

    cl = stats["classification"]
    assert cl["genuine_non_payables"] == 2
    assert cl["payable_reconstruction_failures"] == 1

    # Check that genuine non-payables are listed under genuine_non_payables, not exceptions/erp_mismatches
    non_pay_files = [g["file"] for g in stats["genuine_non_payables"]]
    assert "DN-01.pdf" in non_pay_files
    assert "REM-01.pdf" in non_pay_files
    assert "INV-FAIL.pdf" not in non_pay_files


def test_payable_erp_mismatch_is_not_classified_as_non_payable(mock_output_dir: Path):
    """An invoice that failed reconciliation must be classified as PAYABLE_RECONCILIATION_FAILURE."""
    stats = evaluate_outputs(mock_output_dir)

    cl = stats["classification"]
    assert cl["payable_reconstruction_failures"] == 1

    failures = stats["payable_reconstruction_failures"]
    assert len(failures) == 1
    fail = failures[0]
    assert fail["file"] == "INV-FAIL.pdf"
    assert fail["invoice_number"] == "INV-999"
    assert fail["currency"] == "EUR"
    assert fail["stated_gross"] == 500.00
    assert fail["erp_gross"] == 350.00
    assert fail["delta"] == -150.00
    assert fail["diagnostic_category"] == "UNIT_PRICE"


def test_explicit_denominators_and_rates(mock_output_dir: Path):
    """Reconciliation metrics must have explicit, distinct denominators for accepted vs candidates."""
    stats = evaluate_outputs(mock_output_dir)

    rec = stats["reconciliation"]
    cl = stats["classification"]

    # Payable candidates = 1 accepted + 1 failed = 2
    assert cl["payable_candidates"] == 2
    assert rec["overall_payable_candidates"] == 2

    # Accepted payables = 1
    assert rec["accepted_payables"] == 1
    assert rec["erp_exact_matches_accepted"] == 1
    assert rec["erp_mismatches_accepted"] == 0
    assert rec["accepted_match_rate"] == 100.0
    assert "1/1 (100.0%)" in rec["accepted_match_rate_str"]

    # Overall candidates = 2, exact matches = 1, failures = 1 -> 50.0%
    assert rec["overall_exact_matches"] == 1
    assert rec["overall_reconstruction_failures"] == 1
    assert rec["overall_reconciliation_rate"] == 50.0
    assert "1/2 (50.0%)" in rec["overall_reconciliation_rate_str"]


def test_financial_summary_separation(mock_output_dir: Path):
    """Financial summary for accepted payables must exclude failed reconstruction amounts."""
    stats = evaluate_outputs(mock_output_dir)

    fin_acc = stats["financials_accepted"]
    fin_fail = stats["financials_failures"]

    # Accepted payables has only INV-VALID (100.00 EUR)
    assert "EUR" in fin_acc
    assert fin_acc["EUR"]["invoices"] == 100.00
    assert fin_acc["EUR"]["net_due"] == 100.00
    assert fin_acc["EUR"]["count"] == 1

    # Reconstruction failures has INV-FAIL (500.00 EUR) separately
    assert "EUR" in fin_fail
    assert fin_fail["EUR"]["invoices"] == 500.00
    assert fin_fail["EUR"]["count"] == 1


def test_canonical_category_mapping():
    """Diagnostics must map to one of the 8 canonical categories."""
    assert _map_to_canonical_category("UNIT_PRICE") == "UNIT_PRICE"
    assert _map_to_canonical_category("TAX_PLACEMENT_MISMATCH") == "TAX_DOUBLE_COUNTING"
    assert _map_to_canonical_category("HEADER_DISCOUNT_MISMATCH") == "DISCOUNT_DOUBLE_COUNTING"
    assert _map_to_canonical_category("CHARGE_PLACEMENT") == "CHARGE_PLACEMENT"
    assert _map_to_canonical_category("ROUNDING_MISMATCH") == "ROUNDING"
    assert _map_to_canonical_category("CURRENT_VS_HISTORICAL_AMOUNT") == "CURRENT_VS_HISTORICAL"
    assert _map_to_canonical_category("COMPOUND_TAX") == "COMPOUND_TAX"
    assert _map_to_canonical_category("UNRECOGNIZED_ISSUE") == "OTHER"
