"""Accounting tax logic — line vs header placement, withholding, zero-rate, compound taxes.

Accounting rules:
- Line vs Header: If line items specify explicit rates/amounts per line, they must be preserved at line level.
- If only a global tax summary exists at the header, taxes belong at the header level.
- Withholding taxes: Represented as negative tax amounts (reducing the gross payable).
- Zero-rate / Reverse charge: rate="0", explicit code from tax master.
- Compound taxes / Multiple rates: Multiple entries preserved in line.taxes or header taxes[].
"""

from __future__ import annotations

import logging
from typing import List

from src.models.accounting import AccountingIR, LineItemIR, TaxIR
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)


def is_withholding_tax(tax: TaxIR) -> bool:
    """Check if tax is a withholding tax (either name contains withholding/retención or negative amount)."""
    name = (tax.tax_name or "").lower()
    tax_type = (tax.tax_type or "").lower()
    if (
        "withholding" in name
        or "retención" in name
        or "retencion" in name
        or "ภาษีหัก" in name
        or "wht" in name
        or "withholding" in tax_type
        or "wht" in tax_type
    ):
        return True
    amt = parse_decimal(tax.tax_amount)
    return amt < 0


def reconcile_taxes_placement(ir: AccountingIR) -> AccountingIR:
    """Ensure taxes are placed at the correct accounting level.

    If line items have individual taxes and header taxes is a duplicate summary of line taxes,
    avoid double-counting in ERP. Also ensures withholding taxes are appropriately handled.
    """
    from src.accounting.charges import total_charges

    stated_gross = float(parse_decimal(ir.gross_total))
    subtotal = float(parse_decimal(ir.subtotal))
    charges = float(total_charges(ir))
    disc = float(parse_decimal(ir.discount_amount)) if ir.discount_amount else 0.0
    line_sum = sum(float(parse_decimal(li.total or li.unit_price or "0")) for li in ir.line_items)
    effective_subtotal = line_sum if line_sum > 0 and (subtotal == 0 or abs(line_sum - subtotal) <= 0.50) else subtotal
    net_base = effective_subtotal + charges - disc

    # Statutory tax rate reconciliation: align tax_amount to statutory tax if it matches stated gross
    if stated_gross > 0 and net_base > 0:
        for t in ir.taxes:
            rate = float(parse_decimal(t.tax_rate)) if t.tax_rate else 0.0
            if rate > 0:
                statutory_tax = round(net_base * rate / 100.0, 2)
                if abs((net_base + statutory_tax) - stated_gross) <= 0.01:
                    amt = float(parse_decimal(t.tax_amount)) if t.tax_amount else 0.0
                    if abs(amt - statutory_tax) > 0.01:
                        logger.info(
                            "Statutory tax rate (%.2f%%) on net base (%.2f) yields %.2f, "
                            "reconciling exactly with stated gross (%.2f). Aligning tax amount.",
                            rate, net_base, statutory_tax, stated_gross,
                        )
                        t.tax_amount = f"{statutory_tax:.2f}"

    # Check if withholding tax is informational (gross matches net_base + standard taxes)
    # or should be deducted as a negative tax (gross matches net_base + taxes - withholding)
    has_wht = any(is_withholding_tax(t) for t in ir.taxes)
    if has_wht and stated_gross > 0 and net_base > 0:
        non_wht_sum = sum(
            float(parse_decimal(t.tax_amount))
            for t in ir.taxes
            if not is_withholding_tax(t)
        )
        if abs((net_base + non_wht_sum) - stated_gross) < 0.05:
            logger.info("Stated gross matches standard taxes without withholding; dropping informational withholding tax")
            ir.taxes = [t for t in ir.taxes if not is_withholding_tax(t)]
        else:
            # Enforce negative amounts on withholding taxes so ERP reduces the gross payable
            for t in ir.taxes:
                if is_withholding_tax(t):
                    amt = parse_decimal(t.tax_amount)
                    if amt > 0:
                        t.tax_amount = f"-{amt}"
                    t.is_withholding = True
    else:
        # Enforce negative amounts on any remaining withholding taxes
        for t in ir.taxes:
            if is_withholding_tax(t):
                amt = parse_decimal(t.tax_amount)
                if amt > 0:
                    t.tax_amount = f"-{amt}"
                t.is_withholding = True

    for li in ir.line_items:
        for t in li.taxes:
            if is_withholding_tax(t):
                amt = parse_decimal(t.tax_amount)
                if amt > 0:
                    t.tax_amount = f"-{amt}"
                t.is_withholding = True


    has_line_taxes = any(bool(li.taxes) or bool(li.tax_rate) for li in ir.line_items)
    has_header_taxes = bool(ir.taxes)

    # Check if document is tax-inclusive: stated gross matches net_base before taxes
    if stated_gross > 0 and abs(net_base - stated_gross) <= 0.05:
        if has_header_taxes or has_line_taxes:
            logger.info(
                "Stated gross (%.2f) matches net base (%.2f); prices are tax-inclusive. "
                "Clearing duplicate taxes to prevent double counting in ERP.",
                stated_gross, net_base
            )
            ir.taxes = []
            for li in ir.line_items:
                li.taxes = []
                li.tax_rate = ""
                li.tax_amount = ""
            return ir

    # If no line or header taxes exist, but total_tax_amount was extracted and reconciles
    if not has_line_taxes and not has_header_taxes and ir.total_tax_amount:
        tax_amt = float(parse_decimal(ir.total_tax_amount))
        if tax_amt > 0:
            # Check if adding total_tax_amount to net_base reconciles with stated gross
            if stated_gross == 0 or abs((net_base + tax_amt) - stated_gross) <= 0.05 or abs((subtotal + tax_amt) - stated_gross) <= 0.05:
                logger.info("Synthesizing header tax from total_tax_amount (%.2f) to reconcile with stated gross", tax_amt)
                ir.taxes.append(TaxIR(
                    tax_type="TAX",
                    tax_name="VAT / Sales Tax",
                    tax_amount=str(parse_decimal(ir.total_tax_amount)),
                ))
                has_header_taxes = True



    if has_line_taxes and has_header_taxes:
        # Compute line tax sum, deriving amounts from rates if tax_amount is not populated
        line_tax_sum = 0.0
        for li in ir.line_items:
            q = float(parse_decimal(li.quantity)) if li.quantity else 1.0
            p = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
            disc = float(parse_decimal(li.discount)) if li.discount else 0.0
            base = max(0.0, q * p - disc)

            for t in li.taxes:
                amt = float(parse_decimal(t.tax_amount))
                rate = float(parse_decimal(t.tax_rate))
                if amt != 0:
                    line_tax_sum += amt
                elif rate > 0:
                    line_tax_sum += round(base * rate / 100.0, 2)

            if not li.taxes and li.tax_rate:
                rate = float(parse_decimal(li.tax_rate))
                if rate > 0:
                    line_tax_sum += round(base * rate / 100.0, 2)

        header_tax_sum = sum(float(parse_decimal(t.tax_amount)) for t in ir.taxes)
        if header_tax_sum == 0:
            sub = float(parse_decimal(ir.subtotal))
            for t in ir.taxes:
                rate = float(parse_decimal(t.tax_rate))
                if rate > 0 and sub > 0:
                    header_tax_sum += round(sub * rate / 100.0, 2)

        # Economic reconciliation: evaluate whether both or single placement matches stated gross
        stated_gross = float(parse_decimal(ir.gross_total))
        subtotal = float(parse_decimal(ir.subtotal))
        header_disc = float(parse_decimal(ir.discount_amount)) if ir.discount_amount else 0.0
        net_base = subtotal + charges - header_disc

        if stated_gross > 0 and (line_tax_sum > 0 or header_tax_sum > 0):
            diff_header = abs((net_base + header_tax_sum) - stated_gross)
            diff_line = abs((net_base + line_tax_sum) - stated_gross)
            diff_both = abs((net_base + line_tax_sum + header_tax_sum) - stated_gross)

            # If applying both taxes creates a substantial mismatch, but either single option reconciles
            if diff_both > 0.05 and (diff_header <= 0.05 or diff_line <= 0.05 or abs(line_tax_sum - header_tax_sum) < 0.05):
                if diff_header < diff_line and diff_header <= 0.05:
                    logger.info(
                        "Header taxes (%.2f) match stated gross better than line taxes (%.2f); "
                        "clearing line taxes to avoid double counting",
                        header_tax_sum, line_tax_sum,
                    )
                    for li in ir.line_items:
                        li.taxes = []
                        li.tax_rate = ""
                        li.tax_amount = ""
                    return ir
                elif diff_line < diff_header and diff_line <= 0.05:
                    logger.info(
                        "Line taxes (%.2f) match stated gross better than header taxes (%.2f); "
                        "clearing header taxes to avoid double counting",
                        line_tax_sum, header_tax_sum,
                    )
                    ir.taxes = []
                    return ir
                else:
                    # Equal reconciliation (e.g. diff_header == diff_line):
                    # If header tax has explicit amount and line tax was only rate-derived,
                    # prefer header taxes for precision; otherwise clear duplicate header taxes
                    has_explicit_header_amt = any(float(parse_decimal(t.tax_amount)) > 0 for t in ir.taxes)
                    has_explicit_line_amt = any(any(float(parse_decimal(t.tax_amount)) > 0 for t in li.taxes) for li in ir.line_items)

                    if has_explicit_header_amt and not has_explicit_line_amt:
                        logger.info("Retaining explicit header tax amount; clearing line tax rates to prevent double counting")
                        for li in ir.line_items:
                            li.taxes = []
                            li.tax_rate = ""
                            li.tax_amount = ""
                        return ir
                    else:
                        logger.info("Retaining line-level taxes; clearing duplicate header tax summary")
                        ir.taxes = []
                        return ir

        # Fallback duplicate check if stated gross was not available
        if abs(line_tax_sum - header_tax_sum) < 0.05 and (line_tax_sum > 0 or header_tax_sum > 0):
            logger.info("Header taxes duplicate line taxes; clearing header taxes to avoid double counting")
            ir.taxes = []

    return ir
