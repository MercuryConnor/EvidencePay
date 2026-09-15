"""Master data resolution — resolve all master codes for an AccountingIR.

Uses the individual matchers (supplier, buyer, tax, terms, po)
and populates the AccountingIR with resolved IDs.
Returns the list of MatchEvidence for audit logging.
"""

from __future__ import annotations

import logging

from src.master_data.buyer import match_buyer, parse_buyer_codes
from src.master_data.loader import ensure_loaded
from src.master_data.po import match_po
from src.master_data.supplier import match_supplier
from src.master_data.tax import match_tax_code
from src.master_data.terms import match_payment_term
from src.models.accounting import AccountingIR
from src.models.diagnostics import MatchEvidence

logger = logging.getLogger(__name__)


def resolve_master_data(ir: AccountingIR) -> tuple[AccountingIR, list[MatchEvidence]]:
    """Resolve all master data codes for an AccountingIR.

    Returns (updated_ir, list_of_match_evidence) for audit logging.
    """
    ensure_loaded()
    matches: list[MatchEvidence] = []

    # ── Supplier ──
    if not ir.supplier.supplier_id:
        supplier_match = match_supplier(
            name=ir.supplier.name,
            vat_id=ir.supplier.vat_id,
            address=ir.supplier.address,
            iban=ir.supplier.iban,
        )
        ir.supplier.supplier_id = supplier_match.matched_id
        matches.append(supplier_match)
        logger.debug("Supplier: %s (%s)", supplier_match.matched_id, supplier_match.match_method.value)

    # ── Buyer ──
    if not ir.buyer.company_code:
        buyer_match = match_buyer(
            entity_name=ir.buyer.raw_name,
            address=ir.buyer.raw_address,
            country=ir.buyer.country or _infer_country(ir),
        )
        codes = parse_buyer_codes(buyer_match)
        ir.buyer.company_code = codes["company_code"]
        ir.buyer.business_unit_code = codes["business_unit_code"]
        ir.buyer.location_code = codes["location_code"]
        matches.append(buyer_match)

    # ── Payment term ──
    if not ir.payment_term_id:
        term_match = match_payment_term(
            text=ir.payment_terms_text,
            invoice_date=ir.invoice_date,
            due_date=ir.due_date,
        )
        ir.payment_term_id = term_match.matched_id
        matches.append(term_match)

    # ── PO ──
    if ir.po_number and not ir.po_id:
        po_match = match_po(ir.po_number)
        ir.po_id = po_match.matched_id
        matches.append(po_match)

    # ── Header taxes ──
    country = _infer_country(ir)
    for tax in ir.taxes:
        if not tax.tax_type_code:
            tax_match = match_tax_code(
                country=country,
                tax_type=tax.tax_type,
                rate=tax.tax_rate,
                tax_name=tax.tax_name,
            )
            tax.tax_type_code = tax_match.matched_id
            matches.append(tax_match)

    # ── Line-level taxes ──
    for line in ir.line_items:
        for tax in line.taxes:
            if not tax.tax_type_code:
                tax_match = match_tax_code(
                    country=country,
                    tax_type=tax.tax_type,
                    rate=tax.tax_rate,
                    tax_name=tax.tax_name,
                )
                tax.tax_type_code = tax_match.matched_id
                matches.append(tax_match)

    return ir, matches


def _infer_country(ir: AccountingIR) -> str:
    """Infer the country from supplier VAT ID or buyer info."""
    vat = ir.supplier.vat_id
    if vat:
        prefix = vat[:2].upper()
        if prefix.isalpha():
            return prefix

    if ir.buyer.country:
        return ir.buyer.country.upper()

    address = ir.supplier.address
    if address:
        parts = address.split(",")
        if parts:
            last = parts[-1].strip().upper()
            if len(last) == 2 and last.isalpha():
                return last

    return ""
