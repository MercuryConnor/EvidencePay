"""ERP Validator — wrapper around the supplied erp_book() oracle.

Calls the sealed erp.py and compares the result against the document's
stated gross. Returns structured diagnostics, never modifies erp.py.
"""

from __future__ import annotations

import json
import logging
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# Add candidate_kit to sys.path so we can import erp
_CANDIDATE_KIT = Path(__file__).resolve().parent.parent / "candidate_kit" / "candidate_kit"
if str(_CANDIDATE_KIT) not in sys.path:
    sys.path.insert(0, str(_CANDIDATE_KIT))

from erp import erp_book  # noqa: E402

from src.models import AutodraftPayable, ERPResult

logger = logging.getLogger(__name__)


def round2(x: float) -> float:
    """Mirror erp.py's rounding: 2dp, ROUND_HALF_UP."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_payable(payable: AutodraftPayable) -> ERPResult:
    """Run erp_book() on a payable and compare against its stated gross_total.

    Returns an ERPResult with the comparison details.
    Does NOT modify the payable — purely diagnostic.
    """
    payable_dict = json.loads(payable.model_dump_json())

    try:
        erp_result = erp_book(payable_dict)
    except Exception as e:
        logger.error("erp_book() raised an exception: %s", e)
        return ERPResult(
            will_book_gross=0.0,
            currency=payable.currency,
            expected_gross=_parse_gross(payable.gross_total),
            matches=False,
            delta=_parse_gross(payable.gross_total),
        )

    booked_gross = erp_result.get("will_book_gross", 0.0)
    booked_currency = erp_result.get("currency", "")
    expected_gross = _parse_gross(payable.gross_total)

    delta = round2(booked_gross - expected_gross)
    matches = abs(delta) < 0.005  # within half a cent = match

    if matches:
        logger.info(
            "[MATCH] ERP MATCH: %s %s (expected %s %s)",
            booked_gross, booked_currency, expected_gross, payable.currency
        )
    else:
        logger.warning(
            "[MISMATCH] ERP MISMATCH: booked=%s expected=%s delta=%s (%s)",
            booked_gross, expected_gross, delta, payable.currency
        )

    return ERPResult(
        will_book_gross=booked_gross,
        currency=booked_currency,
        expected_gross=expected_gross,
        matches=matches,
        delta=delta,
    )


def validate_payable_dict(payable_dict: dict) -> ERPResult:
    """Run erp_book() on a raw payable dict. Convenience for testing."""
    try:
        erp_result = erp_book(payable_dict)
    except Exception as e:
        logger.error("erp_book() raised an exception: %s", e)
        return ERPResult(matches=False)

    booked_gross = erp_result.get("will_book_gross", 0.0)
    booked_currency = erp_result.get("currency", "")
    expected_gross = _parse_gross(payable_dict.get("gross_total", "0"))

    delta = round2(booked_gross - expected_gross)
    matches = abs(delta) < 0.005

    return ERPResult(
        will_book_gross=booked_gross,
        currency=booked_currency,
        expected_gross=expected_gross,
        matches=matches,
        delta=delta,
    )


def _parse_gross(value: Any) -> float:
    """Parse a gross total string to float. Handles empty/None gracefully."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0
