"""Accounting discount logic — line vs header discounts.

Semantics:
- Line discount: Applies only to the specific line item base.
- If percentage is given, ERP computes base = round2(sub_total - sub_total * disc_pct / 100).
- If amount is given, ERP computes base = round2((price - disc_amt / abs(qty)) * qty).
- Header discount: Reduces net_base before header tax calculation.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from src.models.accounting import AccountingIR
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)


def compute_net_discount(ir: AccountingIR) -> Decimal:
    """Compute total discount across lines and header."""
    total_disc = Decimal("0.00")
    for li in ir.line_items:
        if li.discount:
            total_disc += parse_decimal(li.discount)
    if ir.discount_amount:
        total_disc += parse_decimal(ir.discount_amount)
    return total_disc


def reconcile_discount_placement(ir: AccountingIR) -> AccountingIR:
    """Ensure discounts are not double-counted between line items and header,
    or within line items between discount amount and discount percentage.

    If discount amount and percentage mathematically reconcile within tolerance (0.05),
    treat them as two representations of the same discount: retain the explicit discount
    amount and clear discount_percentage to prevent double deduction.
    If they conflict materially, preserve evidence and surface a diagnostic warning.
    """
    # 1. Line-level reconciliation: amount vs percentage
    for li in ir.line_items:
        if li.discount and li.discount_percentage:
            amt = float(parse_decimal(li.discount))
            pct = float(parse_decimal(li.discount_percentage))
            qty = float(parse_decimal(li.quantity)) if li.quantity else 1.0
            price = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
            sub_total = qty * price
            if sub_total > 0 and amt > 0 and pct > 0:
                expected_amt = sub_total * pct / 100.0
                if abs(amt - expected_amt) <= 0.05:
                    logger.info(
                        "Line discount amount (%.2f) and percentage (%.2f%%) reconcile; "
                        "retaining single economic discount amount",
                        amt, pct,
                    )
                    li.discount_percentage = ""
                else:
                    logger.warning(
                        "Line discount amount (%.2f) and percentage (%.2f%%) conflict materially "
                        "(expected %.2f); preserving document evidence",
                        amt, pct, expected_amt,
                    )

    # 2. Header vs line items reconciliation
    from src.accounting.charges import total_charges
    charges = float(total_charges(ir))

    line_disc_sum = 0.0
    gross_line_sum = 0.0
    net_line_sum = 0.0

    for li in ir.line_items:
        # Check if line is a discount-only row (e.g. negative total or discount description)
        tot = float(parse_decimal(li.total)) if li.total else 0.0
        desc = li.description.lower()
        is_disc_line = tot < 0 or any(w in desc for w in ("desconto", "discount", "rabatt", "rebate"))

        if is_disc_line:
            continue

        q = float(parse_decimal(li.quantity)) if li.quantity else 1.0
        p = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
        sub_total = q * p
        gross_line_sum += sub_total

        disc = 0.0
        if li.discount:
            disc = float(parse_decimal(li.discount))
        elif li.discount_percentage:
            pct = float(parse_decimal(li.discount_percentage))
            if sub_total > 0 and pct > 0:
                disc = round(sub_total * pct / 100.0, 2)

        line_disc_sum += disc
        net_line_sum += max(0.0, sub_total - disc)

    header_disc = float(parse_decimal(ir.discount_amount)) if ir.discount_amount else 0.0

    # Derive tax amount for comparison
    tax_amt = 0.0
    if ir.taxes:
        tax_amt = sum(float(parse_decimal(t.tax_amount)) for t in ir.taxes if t.tax_amount)
    elif ir.total_tax_amount:
        tax_amt = float(parse_decimal(ir.total_tax_amount))

    if header_disc > 0 or line_disc_sum > 0:
        stated_gross = float(parse_decimal(ir.gross_total))
        if stated_gross > 0 and header_disc > 0:
            diff_header = abs((gross_line_sum - header_disc + tax_amt + charges) - stated_gross)
            diff_line = abs((net_line_sum + tax_amt + charges) - stated_gross)

            if diff_header <= 0.05 and diff_line > 0.05:
                logger.info(
                    "Header discount (%.2f) reconciles with stated gross better than line discounts (%.2f); "
                    "retaining header discount and clearing line discounts",
                    header_disc, line_disc_sum,
                )
                for li in ir.line_items:
                    li.discount = ""
                    li.discount_percentage = ""
                ir.line_items = [
                    li for li in ir.line_items
                    if not (float(parse_decimal(li.total or "0")) < 0 or any(w in li.description.lower() for w in ("desconto", "discount", "rabatt", "rebate")))
                ]
                return ir
            elif diff_line <= 0.05 and diff_header > 0.05:
                logger.info(
                    "Line discounts (%.2f) reconcile with stated gross better than header discount (%.2f); "
                    "clearing header discount to avoid double counting",
                    line_disc_sum, header_disc,
                )
                ir.discount_amount = ""
                return ir

        # Direct duplicate check: if line discounts sum to header discount, clear header discount
        if line_disc_sum > 0 and header_disc > 0:
            if abs(line_disc_sum - header_disc) <= 0.05:
                logger.info(
                    "Header discount (%.2f) duplicates line discounts (%.2f); "
                    "clearing header discount to avoid double counting",
                    header_disc, line_disc_sum,
                )
                ir.discount_amount = ""
    return ir

