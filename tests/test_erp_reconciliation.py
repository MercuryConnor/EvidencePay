"""Unit tests for ERP reconciliation using original sealed erp_book()."""

import json
from pathlib import Path
import pytest

from erp import erp_book
from src.erp_validator import validate_payable_dict
from src.models import AutodraftPayable, AutodraftLineItem, AutodraftSupplier, AutodraftBuyer, AutodraftTax


class TestERPReconciliation:
    """Test ERP oracle behavior and reconciliation contracts."""

    def test_sample_autodraft_reconciliation(self):
        sample_file = Path("candidate_kit/candidate_kit/sample_autodraft.json")
        with open(sample_file, "r", encoding="utf-8") as f:
            sample_data = json.load(f)

        erp_res = erp_book(sample_data)
        assert abs(erp_res["will_book_gross"] - 438.00) < 0.01

        val_res = validate_payable_dict(sample_data)
        assert val_res.matches
        assert val_res.delta == 0.0

    def test_per_line_rounding_behavior(self):
        # Two lines: qty 3 @ 10.333 -> round2(31.00) vs single total
        payable = {
            "gross_total": "62.00",
            "currency": "EUR",
            "supplier": {"name": "Test", "supplier_id": "1"},
            "buyer": {"company_code": "C", "business_unit_code": "B", "location_code": "L"},
            "line_items": [
                {"quantity": "3", "unit_price": "10.333", "total": "31.00"},
                {"quantity": "3", "unit_price": "10.333", "total": "31.00"},
            ],
            "taxes": [],
        }
        res = erp_book(payable)
        assert res["will_book_gross"] == 62.00

    def test_erp_mismatch_detection(self):
        # Gross total stated is 500.00, but lines sum to 100.00
        payable = {
            "gross_total": "500.00",
            "currency": "EUR",
            "supplier": {"name": "Test", "supplier_id": "1"},
            "buyer": {"company_code": "C", "business_unit_code": "B", "location_code": "L"},
            "line_items": [
                {"quantity": "1", "unit_price": "100.00", "total": "100.00"},
            ],
            "taxes": [],
        }
        val = validate_payable_dict(payable)
        assert not val.matches
        assert abs(val.delta - (-400.00)) < 0.01
