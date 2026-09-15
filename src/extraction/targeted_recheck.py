"""Targeted re-extraction — bounded re-examination of specific document areas.

When ERP validation fails, this module diagnoses the likely mismatch area
and re-extracts only the targeted evidence. Max 3 total passes.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from src.models import AccountingIR, EvidencePacket, ERPResult

logger = logging.getLogger(__name__)


RECHECK_PROMPT_TEMPLATE = """You previously extracted data from this document, but the ERP validation shows a mismatch.

Previous extraction produced:
- Stated gross total: {gross_total}
- ERP computed gross: {erp_gross}
- Delta: {delta}

The ERP computes gross as:
  gross = sum(line_bases) - header_discount + line_taxes + header_taxes + other_charges

Where line_base = round2(qty * unit_price - discount) per line.

Please re-examine the document carefully and focus on:
{focus_areas}

Common issues to check:
1. Are all line items captured? (look for continuation pages)
2. Are quantities and unit prices correct? (check for locale number formats)
3. Are taxes placed correctly — line-level vs header-level?
4. Are there any discounts, freight, insurance, or extra charges?
5. Is the unit_price NET (tax-exclusive)? If prices include tax, extract the net price.
6. Are there multiple tax rates?
7. Is this actually a credit memo (negative amounts)?

Return the COMPLETE corrected extraction in the same JSON format as before.
Focus on accuracy — do not invent values to force a match."""


def targeted_recheck(
    evidence: EvidencePacket,
    candidate: AccountingIR,
    erp_result: ERPResult,
    pass_number: int,
) -> Optional[AccountingIR]:
    """Perform a targeted recheck or deterministic correction based on the ERP mismatch.

    1. Attempts deterministic accounting reconciliation (taxes, discounts, scale) first.
    2. If still mismatched, invokes LLM with diagnostic focus and pass-aware cache key.
    Returns an updated AccountingIR, or None if no changes are warranted.
    """
    if pass_number > 3:
        logger.warning("Max passes exceeded, not performing recheck")
        return None

    # Step A: Deterministic Recovery Phase
    from src.accounting.taxes import reconcile_taxes_placement
    from src.accounting.discounts import reconcile_discount_placement
    from src.normalization.numbers import normalize_accounting_ir
    from src.master_data.resolver import resolve_master_data
    from src.accounting.reconstruction import reconstruct_autodraft
    from src.erp_validator import validate_payable

    corrected_candidate = normalize_accounting_ir(candidate)
    corrected_candidate, _ = resolve_master_data(corrected_candidate)
    corrected_candidate = reconcile_taxes_placement(corrected_candidate)
    corrected_candidate = reconcile_discount_placement(corrected_candidate)

    # Test if deterministic reconciliation fixed the mismatch
    trial_draft = reconstruct_autodraft(corrected_candidate)
    trial_erp = validate_payable(trial_draft)
    if trial_erp.matches:
        logger.info("Deterministic reconciliation resolved ERP mismatch (delta=%.2f -> 0.00)", erp_result.delta)
        return corrected_candidate

    # Step B: Targeted LLM Recheck Phase
    focus_areas = _diagnose_mismatch(candidate, erp_result)

    if not focus_areas:
        logger.info("No specific diagnosis — cannot target recheck")
        return None

    logger.info("Recheck pass %d focus: %s", pass_number, focus_areas)

    prompt = RECHECK_PROMPT_TEMPLATE.format(
        gross_total=candidate.gross_total or str(erp_result.expected_gross),
        erp_gross=str(erp_result.will_book_gross),
        delta=f"{erp_result.delta:.2f}",
        focus_areas=focus_areas,
    )

    try:
        from src.extraction.extractor import extract_payables

        pass_type = f"targeted_recheck_{pass_number - 1}"
        candidates = extract_payables(
            evidence,
            prompt=prompt,
            pass_type=pass_type,
            focus=focus_areas,
        )

        if candidates:
            return candidates[0]
    except Exception as e:
        logger.warning("Targeted recheck failed: %s", e)

    return None



def _diagnose_mismatch(candidate: AccountingIR, erp_result: ERPResult) -> str:
    """Diagnose the likely cause of an ERP mismatch.

    Returns a description of the focus areas for re-extraction.
    """
    delta = erp_result.delta
    if abs(delta) < 0.01:
        return ""

    focus_areas = []

    # Large delta — likely missing lines or wrong amounts
    if abs(delta) > 100:
        focus_areas.append("- Large delta suggests missing line items or significantly wrong amounts")
        focus_areas.append("- Check if all pages were included")
        focus_areas.append("- Verify the gross total is the CURRENT amount due, not a historical balance")

    # Delta matches a common tax rate application
    stated_gross = erp_result.expected_gross
    if stated_gross > 0:
        ratio = abs(delta) / stated_gross
        if 0.04 < ratio < 0.26:
            focus_areas.append(f"- Delta/gross ratio ({ratio:.2%}) suggests a tax issue")
            focus_areas.append("- Check if unit_price is NET vs gross (tax-inclusive)")
            focus_areas.append("- Check if a tax is missing or double-counted")

    # Small delta — likely rounding or minor field error
    if abs(delta) < 1:
        focus_areas.append("- Small delta suggests rounding issue or minor quantity/price error")
        focus_areas.append("- Verify exact quantities and unit prices")
        focus_areas.append("- Check discount amounts")

    if not focus_areas:
        focus_areas.append(f"- ERP delta of {delta:.2f} — review all numeric fields")

    return "\n".join(focus_areas)
