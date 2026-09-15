"""Deterministic mismatch diagnostics — diagnose discrepancies between ERP calculation and stated totals.

Categories:
- TAX_PLACEMENT_MISMATCH
- LINE_DISCOUNT_MISMATCH
- HEADER_DISCOUNT_MISMATCH
- CHARGE_MISSING
- CHARGE_DOUBLE_COUNTED
- CURRENT_VS_HISTORICAL_AMOUNT
- ROUNDING_MISMATCH
- LINE_STRUCTURE_MISMATCH
- CREDIT_MEMO_SEMANTICS
- MASTER_DATA_MISMATCH
- UNSUPPORTED_STRUCTURE
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from src.models.accounting import AccountingIR
from src.models.diagnostics import MismatchDiagnostic
from src.models.enums import DiagnosticCategory
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)


def diagnose_mismatch(
    ir: AccountingIR,
    erp_gross: float,
    stated_gross_str: str,
) -> List[MismatchDiagnostic]:
    """Analyze a numerical discrepancy between ERP gross and stated gross.

    Returns a list of plausible MismatchDiagnostics explaining the delta.
    """
    diagnostics: List[MismatchDiagnostic] = []
    stated_gross = float(parse_decimal(stated_gross_str))
    delta = round(erp_gross - stated_gross, 2)
    abs_delta = abs(delta)

    if abs_delta < 0.01:
        return diagnostics

    logger.debug("Diagnosing discrepancy: erp=%.2f, stated=%.2f, delta=%.2f", erp_gross, stated_gross, delta)

    # 1. Rounding mismatch check: difference <= 0.05
    if abs_delta <= 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.ROUNDING_MISMATCH,
            description=f"Minor cent rounding difference ({delta:+.2f}). Possible per-line vs sum rounding.",
            suspect_field="line_items.unit_price",
            suggested_action="Verify exact decimal precision on line item unit prices.",
        ))

    # 2. Root cause check: Compound tax (e.g. excise duty legally compounded into VAT base)
    notes_text = getattr(ir, "notes", "") + " " + getattr(ir, "payment_terms_text", "")
    has_compound_tax = (
        bool(ir.excise_duties)
        or any(any(w in li.description.lower() for w in ("iec", "excise", "depósito sdr", "deposito sdr")) for li in ir.line_items)
        or any("iec" in (t.tax_name or "").lower() or "imposto" in (t.tax_name or "").lower() for t in ir.taxes)
        or any(w in notes_text.lower() for w in ("iec", "imposto especial", "depósito", "deposito", "dec. lei"))
    )
    if has_compound_tax and abs_delta > 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.COMPOUND_TAX,
            description=f"Excise duty (IEC) legally compounded into VAT taxable base prior to IVA calculation; linear ERP schema cannot represent compound tax base without synthesis (delta {delta:+.2f}).",
            suspect_field="taxes",
            suggested_action="Compound excise duty structure requires pre-tax base adjustments not supported in linear ERP line schema.",
        ))
        return diagnostics

    # 3. Root cause check: Non-linear billing formulas (e.g. utility lease amortization / demand factors)
    has_non_linear_formula = any(
        any(w in li.description.lower() for w in ("connected ton", "cch-", "wcms", "btu", "per lease", "demand at", "sm #"))
        for li in ir.line_items
    ) or any(w in notes_text.lower() for w in ("reimbursement", "utilities reimbursement", "lease annual fee"))
    if has_non_linear_formula and abs_delta > 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.NON_LINEAR_BILLING_FORMULA,
            description=f"Billing amount determined by non-linear formula (e.g. connected tons * annual fee / 12 months * factor); linear ERP schema cannot represent without fabricating artificial unit price (delta {delta:+.2f}).",
            suspect_field="line_items.unit_price",
            suggested_action="Non-linear formula requires monthly lease amortization unsupported in linear quantity * unit_price ERP schema.",
        ))
        return diagnostics

    # 4. Root cause check: Operational measurements (e.g. manifest shipment weight in kg extracted as quantity)
    raw_qty_sum = sum(float(parse_decimal(li.quantity or "1")) * float(parse_decimal(li.unit_price or "0")) for li in ir.line_items)
    sub = float(parse_decimal(ir.subtotal))
    if sub > 0 and raw_qty_sum > sub * 1.5 and abs_delta > 50:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.OPERATIONAL_MEASUREMENT_VS_BILLABLE_AMOUNT,
            description=f"Operational measurements (e.g. shipment weight in kg) extracted as line quantities, inflating line bases (delta {delta:+.2f}).",
            suspect_field="line_items.quantity",
            suggested_action="Distinguish operational metrics (weight/volume) from billable flat consignment charges.",
        ))
        return diagnostics

    # 5. Root cause check: Bundle hierarchy duplicate extraction
    has_bundle = any(
        any(w in li.description.lower() for w in ("komplekt", "bundle", "set", "package"))
        for li in ir.line_items
    )
    if has_bundle and abs_delta > 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.BUNDLE_HIERARCHY,
            description=f"Priced bundle package conflicts with extracted component rows (delta {delta:+.2f}).",
            suspect_field="line_items",
            suggested_action="Prune component rows whose monetary extension is blank or already included in bundle price.",
        ))
        return diagnostics

    # 6. Tax placement mismatch: check if delta matches tax amount or header taxes
    header_tax_sum = float(sum(parse_decimal(t.tax_amount) for t in ir.taxes))
    line_tax_sum = float(sum(sum(parse_decimal(t.tax_amount) for t in li.taxes) for li in ir.line_items))

    if header_tax_sum > 0 and abs(abs_delta - header_tax_sum) < 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.TAX_PLACEMENT_MISMATCH,
            description=f"Delta ({delta:+.2f}) closely matches header tax sum ({header_tax_sum:.2f}). Tax may be double-counted or duplicated across line/header.",
            suspect_field="header_taxes",
            suggested_action="Check if taxes are already included in line totals or if header tax was duplicated.",
        ))

    if line_tax_sum > 0 and abs(abs_delta - line_tax_sum) < 0.05:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.TAX_PLACEMENT_MISMATCH,
            description=f"Delta ({delta:+.2f}) closely matches line tax sum ({line_tax_sum:.2f}).",
            suspect_field="line_items.taxes",
            suggested_action="Check if prices were tax-inclusive or tax was double applied.",
        ))

    # 3. Discount mismatch check
    header_discount = float(parse_decimal(ir.discount_amount))
    line_disc_sum = sum(float(parse_decimal(li.discount)) for li in ir.line_items if li.discount)
    has_disc_pct = any(bool(li.discount_percentage) for li in ir.line_items)
    if header_discount > 0:
        if abs(abs_delta - header_discount) < 0.05:
            diagnostics.append(MismatchDiagnostic(
                category=DiagnosticCategory.HEADER_DISCOUNT_MISMATCH,
                description=f"Delta ({delta:+.2f}) matches discount amount ({header_discount:.2f}). Discount sign or deduction issue.",
                suspect_field="discount_amount",
                suggested_action="Verify if discount was already subtracted from subtotal on invoice.",
            ))
        elif has_disc_pct or line_disc_sum > 0 or header_discount > 50:
            diagnostics.append(MismatchDiagnostic(
                category=DiagnosticCategory.DISCOUNT_DOUBLE_COUNTING,
                description=f"Header commercial discount ({header_discount:.2f}) unapplied or conflicting with line discount structure (delta {delta:+.2f}).",
                suspect_field="discount_amount",
                suggested_action="Reconcile header discount vs line-level discounts or net prices.",
            ))

    # 4. Missing or zero unit price on lines with non-zero total, or quantity-unit price mismatch
    lines_missing_price = [
        li for li in ir.line_items
        if (not li.unit_price or float(parse_decimal(li.unit_price)) == 0.0)
        and float(parse_decimal(li.total)) > 0
    ]
    has_qty_price_mismatch = any(
        abs(float(parse_decimal(li.quantity or "1")) * float(parse_decimal(li.unit_price or "0")) - float(parse_decimal(li.total or "0"))) > 1.0
        and float(parse_decimal(li.total or "0")) > 0
        for li in ir.line_items
    )
    if lines_missing_price:
        missing_total = sum(float(parse_decimal(li.total)) for li in lines_missing_price)
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.UNIT_PRICE,
            description=f"Line items missing explicit unit price (sum={missing_total:.2f}); ERP books zero line base.",
            suspect_field="line_items.unit_price",
            suggested_action="Infer unit price from line total divided by quantity or check price column alignment.",
        ))
    elif has_qty_price_mismatch and abs_delta > 50:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.UNIT_PRICE,
            description=f"Column alignment or quantity-unit price rate mismatch (delta {delta:+.2f}).",
            suspect_field="line_items.unit_price",
            suggested_action="Verify column alignment between unit price, quantity, and line total.",
        ))

    # 5. Charges check: freight, insurance, extra, excise
    from src.accounting.charges import total_charges
    charges = float(total_charges(ir))
    if charges > 0:
        if abs(abs_delta - charges) < 0.05:
            diagnostics.append(MismatchDiagnostic(
                category=DiagnosticCategory.CHARGE_PLACEMENT,
                description=f"Delta ({delta:+.2f}) matches charge sum ({charges:.2f}). Charge placement issue.",
                suspect_field="charges",
                suggested_action="Verify whether charges are already an item line or separate header charge.",
            ))
        elif abs_delta > 0.05 and not diagnostics:
            diagnostics.append(MismatchDiagnostic(
                category=DiagnosticCategory.CHARGE_PLACEMENT,
                description=f"Header charges ({charges:.2f}) conflict with line item reconciliation (delta {delta:+.2f}).",
                suspect_field="charges",
                suggested_action="Verify charge deduction vs line base.",
            ))

    # 6. Line discount percentage vs amount conflict
    for li in ir.line_items:
        if li.discount and li.discount_percentage:
            amt = float(parse_decimal(li.discount))
            pct = float(parse_decimal(li.discount_percentage))
            q = float(parse_decimal(li.quantity)) if li.quantity else 1.0
            p = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
            sub = q * p
            if sub > 0 and amt > 0 and pct > 0:
                expected_amt = sub * pct / 100.0
                if abs(amt - expected_amt) > 0.05:
                    diagnostics.append(MismatchDiagnostic(
                        category=DiagnosticCategory.DISCOUNT_MISMATCH,
                        description=f"Line discount amount ({amt:.2f}) and percentage ({pct:.2f}%) conflict on line '{li.description[:25]}'.",
                        suspect_field="line_items.discount",
                        suggested_action="Reconcile explicit discount amount vs percentage.",
                    ))
                    break

    # 7. Sub-cent meter rate precision / unit price truncation rounding
    if abs_delta <= 10.0 and not diagnostics:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.ROUNDING,
            description=f"Net-of-tax rounding/precision discrepancy ({delta:+.2f}).",
            suspect_field="line_items.unit_price",
            suggested_action="Verify exact decimal precision and rounding rules.",
        ))
    elif abs_delta <= 25.0 and any(len((li.unit_price or "").split(".")[-1]) > 4 for li in ir.line_items):
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.ROUNDING,
            description=f"Sub-cent meter rate precision rounding discrepancy ({delta:+.2f}).",
            suspect_field="line_items.unit_price",
            suggested_action="Verify meter rate / decimal precision interpretation.",
        ))

    # Default fallback diagnostic if no specific pattern matched
    if not diagnostics:
        diagnostics.append(MismatchDiagnostic(
            category=DiagnosticCategory.LINE_STRUCTURE_MISMATCH,
            description=f"Unexplained delta of {delta:+.2f} between ERP gross ({erp_gross:.2f}) and document gross ({stated_gross:.2f}).",
            suspect_field="line_items",
            suggested_action="Re-verify line item quantities, unit prices, and discounts.",
        ))

    return diagnostics
