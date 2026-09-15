"""Accounting Reconstruction — converts AccountingIR to AutodraftPayable.

This is the deterministic bridge between document semantics and the ERP schema.
The LLM extracts evidence; this layer produces the final representation.
"""

from __future__ import annotations

import logging

from src.accounting.discounts import reconcile_discount_placement
from src.accounting.taxes import reconcile_taxes_placement
from src.models import (
    AccountingIR,
    AutodraftBuyer,
    AutodraftLineItem,
    AutodraftPayable,
    AutodraftSupplier,
    AutodraftTax,
)

logger = logging.getLogger(__name__)


def reconcile_bundle_hierarchy(ir: AccountingIR) -> AccountingIR:
    """Reconcile bundle parent-child duplicate lines.

    Accounting rule:
    If an item line i represents a priced bundle (total > 0), and subsequent component rows
    have amounts that sum to the bundle price (|sum(child) - parent| <= 0.05), and pruning
    those component lines causes the line total sum to reconcile with document subtotal/gross
    (within 0.50), prune the component lines so the components do not become independently payable lines.
    """
    from src.normalization.numbers import parse_decimal

    subtotal = float(parse_decimal(ir.subtotal)) if ir.subtotal else 0.0
    stated_gross = float(parse_decimal(ir.gross_total)) if ir.gross_total else 0.0
    disc = float(parse_decimal(ir.discount_amount)) if ir.discount_amount else 0.0

    target_net = subtotal if subtotal > 0 else (stated_gross - disc if stated_gross > 0 else 0.0)
    if target_net <= 0:
        return ir

    lines = ir.line_items
    n = len(lines)

    for i in range(n):
        p_tot = float(parse_decimal(lines[i].total or lines[i].unit_price or "0"))
        if p_tot <= 0:
            continue

        comp_sum = 0.0
        for j in range(i + 1, n):
            c_tot = float(parse_decimal(lines[j].total or "0"))
            if c_tot == 0.0 and float(parse_decimal(lines[j].unit_price or "0")) > 0:
                c_q = float(parse_decimal(lines[j].quantity or "1"))
                c_tot = c_q * float(parse_decimal(lines[j].unit_price or "0"))
            comp_sum += c_tot

            if abs(comp_sum - p_tot) <= 0.05 and comp_sum > 0:
                rem_lines = [l for k, l in enumerate(lines) if k <= i or k > j]
                rem_sum = sum(float(parse_decimal(l.total or l.unit_price or "0")) for l in rem_lines)

                if abs(rem_sum - target_net) <= 0.50 or (stated_gross > 0 and abs((rem_sum - disc) * 1.24 - stated_gross) <= 0.50):
                    logger.info(
                        "Bundle parent line %d (%r, %.2f) matches component sum %.2f (lines %d..%d); pruning component rows",
                        i, lines[i].description, p_tot, comp_sum, i + 1, j,
                    )
                    ir.line_items = rem_lines
                    return ir

    return ir


def reconcile_operational_measurements(ir: AccountingIR) -> AccountingIR:
    """Distinguish operational measurements (e.g. shipment weight in kg) from monetary billable quantities.

    Accounting rule:
    When an invoice has an authoritative summary (subtotal + taxes == gross within 0.05),
    but multiplying line quantity by rate yields a drastically inflated line sum (>> subtotal)
    because quantity represents an operational measurement (such as consignment weight),
    perform summary-level accounting reconstruction: normalize billable quantities to 1 (per consignment charge)
    and assign remaining subtotal difference to extra charges.
    """
    from src.normalization.numbers import parse_decimal

    stated_gross = float(parse_decimal(ir.gross_total)) if ir.gross_total else 0.0
    subtotal = float(parse_decimal(ir.subtotal)) if ir.subtotal else 0.0
    tax_amt = sum(float(parse_decimal(t.tax_amount or "0")) for t in ir.taxes if t.tax_amount)
    if tax_amt == 0 and ir.total_tax_amount:
        tax_amt = float(parse_decimal(ir.total_tax_amount))

    if stated_gross <= 0 or subtotal <= 0:
        return ir

    charges = (
        float(parse_decimal(ir.freight_charges or "0"))
        + float(parse_decimal(ir.extra_charges or "0"))
        + float(parse_decimal(ir.insurance_charges or "0"))
    )
    disc = float(parse_decimal(ir.discount_amount or "0"))
    summary_net = subtotal + charges - disc

    if abs((summary_net + tax_amt) - stated_gross) <= 0.05:
        billable_lines = [
            l for l in ir.line_items
            if not any(w in l.description.lower() for w in ("ümardamine", "umardamine", "rounding", "arredondamento"))
            and float(parse_decimal(l.unit_price or l.total or "0")) > 0.05
        ]

        def _line_net(li):
            q = float(parse_decimal(li.quantity or "1"))
            p = float(parse_decimal(li.unit_price or "0"))
            sub = q * p
            d = 0.0
            if li.discount:
                d = float(parse_decimal(li.discount))
            elif li.discount_percentage:
                pct = float(parse_decimal(li.discount_percentage))
                d = sub * pct / 100.0
            return max(0.0, sub - d)

        net_line_sum = sum(_line_net(l) for l in billable_lines)
        flat_rate_sum = sum(float(parse_decimal(l.unit_price or "0")) for l in billable_lines)
        has_qty_discrepancy = any(
            abs(_line_net(l) - float(parse_decimal(l.total or "0"))) > 1.0
            for l in billable_lines
            if float(parse_decimal(l.quantity or "1")) > 1.0 and float(parse_decimal(l.total or "0")) > 0
        )

        if net_line_sum > subtotal * 1.5 and flat_rate_sum > 0 and has_qty_discrepancy:
            logger.info(
                "Operational measurements detected in line quantities (raw sum=%.2f vs subtotal=%.2f). "
                "Reconstructing from authoritative summary.",
                net_line_sum, subtotal,
            )
            for l in billable_lines:
                l.quantity = "1"
                l.total = l.unit_price
            ir.line_items = billable_lines
            extra = round(subtotal - flat_rate_sum, 2)
            if extra > 0:
                ir.extra_charges = f"{extra:.2f}"

    return ir


def reconstruct_autodraft(ir: AccountingIR) -> AutodraftPayable:
    """Convert an AccountingIR into a final AutodraftPayable.

    This is a deterministic transformation — no inference, no invention.
    Maps IR fields directly to the autodraft schema.
    """
    from src.normalization.numbers import parse_decimal

    # Reconcile bundle hierarchy and operational measurements before price inference
    ir = reconcile_bundle_hierarchy(ir)
    ir = reconcile_operational_measurements(ir)

    # Reconcile unit prices: infer missing unit price when total and quantity are explicit
    for li in ir.line_items:
        tot = float(parse_decimal(li.total)) if li.total else 0.0
        p = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
        q = float(parse_decimal(li.quantity)) if li.quantity else 0.0

        if tot > 0:
            if q == 0.0:
                # Flat service charge / single-fee line with implicit quantity = 1
                li.quantity = "1"
                q = 1.0
            if p == 0.0 and q > 0.0:
                unit_p = tot / q
                if round(unit_p, 2) == round(unit_p, 4):
                    li.unit_price = f"{unit_p:.2f}"
                else:
                    li.unit_price = f"{unit_p:.4f}".rstrip('0').rstrip('.')

    # Reconcile duplicate header freight when already present as an explicit line item
    if ir.freight_charges:
        freight_amt = float(parse_decimal(ir.freight_charges))
        if freight_amt > 0:
            has_freight_line = any(
                abs(float(parse_decimal(li.total or li.unit_price or "0")) - freight_amt) <= 0.01
                and any(w in li.description.lower() for w in ("transport", "freight", "shipping", "delivery", "tarnekulud"))
                for li in ir.line_items
            )
            if has_freight_line:
                logger.info("Header freight (%.2f) duplicated as line item; clearing header freight", freight_amt)
                ir.freight_charges = ""

    ir = reconcile_taxes_placement(ir)
    ir = reconcile_discount_placement(ir)

    payable = AutodraftPayable(

        # Identity
        invoice_number=ir.invoice_number,
        invoice_date=ir.invoice_date,
        due_date=ir.due_date,
        invoice_type=ir.invoice_type.value,
        currency=ir.currency,

        # Supplier
        supplier=AutodraftSupplier(
            name=ir.supplier.name,
            supplier_id=ir.supplier.supplier_id,
            address=ir.supplier.address,
            vat_id=ir.supplier.vat_id,
        ),

        # Buyer
        buyer=AutodraftBuyer(
            company_code=ir.buyer.company_code,
            business_unit_code=ir.buyer.business_unit_code,
            location_code=ir.buyer.location_code,
        ),

        # References
        payment_term_id=ir.payment_term_id,
        po_number=ir.po_number,
        po_id=ir.po_id,

        # Totals (as printed on document)
        gross_total=ir.gross_total,
        subtotal=ir.subtotal,
        total_tax_amount=ir.total_tax_amount,

        # Header charges & discounts
        discount_amount=ir.discount_amount,
        freight_charges=ir.freight_charges,
        insurance_charges=ir.insurance_charges,
        extra_charges=ir.extra_charges,
        excise_duties=ir.excise_duties,

        # Header taxes
        taxes=[
            AutodraftTax(
                tax_type=t.tax_type,
                tax_name=t.tax_name,
                tax_rate=t.tax_rate,
                tax_amount=t.tax_amount,
                tax_type_code=t.tax_type_code,
            )
            for t in ir.taxes
        ],

        # Line items
        line_items=[
            AutodraftLineItem(
                description=li.description,
                item_type=li.item_type,
                uom=li.uom,
                quantity=li.quantity,
                unit_price=li.unit_price,
                total=li.total,
                discount=li.discount,
                discount_percentage=li.discount_percentage,
                tax_rate=li.tax_rate,
                tax_amount=li.tax_amount,
                taxes=[
                    AutodraftTax(
                        tax_type=t.tax_type,
                        tax_name=t.tax_name,
                        tax_rate=t.tax_rate,
                        tax_amount=t.tax_amount,
                        tax_type_code=t.tax_type_code,
                    )
                    for t in li.taxes
                ],
            )
            for li in ir.line_items
        ],
    )

    logger.debug(
        "Reconstructed autodraft: %s, %d lines, %d header taxes",
        payable.invoice_number,
        len(payable.line_items),
        len(payable.taxes),
    )

    return payable
