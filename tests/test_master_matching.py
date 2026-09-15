"""Unit tests for master data matching (supplier, buyer, tax, terms, po)."""

import pytest
from src.master_data import (
    ensure_loaded,
    match_buyer,
    match_payment_term,
    match_po,
    match_supplier,
    match_tax_code,
    parse_buyer_codes,
)
from src.models.enums import MatchConfidence, MatchMethod


@pytest.fixture(autouse=True)
def load_data():
    ensure_loaded()


class TestSupplierMatching:
    """Test supplier identity resolution."""

    def test_vat_exact_match(self):
        ev = match_supplier(vat_id="DE209177122")
        assert ev.matched_id == "2845695"
        assert ev.match_method == MatchMethod.VAT_ID_EXACT
        assert ev.confidence == MatchConfidence.HIGH

    def test_iban_match(self):
        # Using known IBAN from master data
        from src.master_data import loader
        first_supplier = next(s for s in loader.suppliers if s.get("bank_iban"))
        iban = first_supplier["bank_iban"]
        expected_id = first_supplier["supplier_id"]

        ev = match_supplier(iban=iban)
        assert ev.matched_id == expected_id
        assert ev.match_method == MatchMethod.IBAN_EXACT

    def test_name_exact_match(self):
        from src.master_data import loader
        s = loader.suppliers[0]
        ev = match_supplier(name=s["name"])
        assert ev.matched_id == s["supplier_id"]

    def test_unknown_supplier(self):
        ev = match_supplier(name="Completely Nonexistent Supplier XYZ 999", vat_id="XX999999999")
        assert ev.matched_id == ""
        assert ev.confidence == MatchConfidence.NONE


class TestTaxMatching:
    """Test tax code resolution."""

    def test_tax_rate_matching(self):
        ev = match_tax_code(country="DE", rate=19.0)
        assert ev.matched_id != ""
        assert ev.confidence == MatchConfidence.HIGH

    def test_tax_reduced_rate(self):
        ev = match_tax_code(country="DE", rate=7.0)
        assert ev.matched_id != ""

    def test_unknown_country_tax(self):
        ev = match_tax_code(country="ZZ", rate=50.0)
        assert ev.matched_id == ""


class TestPOMatching:
    """Test purchase order resolution."""

    def test_exact_po_match(self):
        from src.master_data import loader
        if loader.po_master:
            po = loader.po_master[0]
            po_num = po.get("po_number")
            ev = match_po(po_num)
            assert ev.matched_id == po_num
            assert ev.confidence == MatchConfidence.HIGH

    def test_nonexistent_po(self):
        ev = match_po("NONEXISTENT-PO-9999")
        assert ev.matched_id == ""
        assert ev.confidence == MatchConfidence.NONE


class TestTermsMatching:
    """Test payment terms matching."""

    def test_explicit_text_terms(self):
        ev = match_payment_term(text="Net 30")
        assert ev.matched_id != ""

    def test_date_diff_terms(self):
        ev = match_payment_term(invoice_date="2026-03-01", due_date="2026-03-31")
        assert ev.matched_id != ""
