"""Accounting charges logic — freight, insurance, extra charges, excise duties.

Semantics:
- Freight charges: Transport/shipping fees.
- Insurance charges: Transit/cargo insurance.
- Extra charges: Handling, packing, surcharges.
- Excise duties: Specific tariffs or luxury taxes.
- Other charges are added to gross total after discounted base and taxes.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from src.models.accounting import AccountingIR
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)


def total_charges(ir: AccountingIR) -> Decimal:
    """Calculate the sum of all header-level non-tax charges."""
    return (
        parse_decimal(ir.freight_charges)
        + parse_decimal(ir.insurance_charges)
        + parse_decimal(ir.extra_charges)
        + parse_decimal(ir.excise_duties)
    )
