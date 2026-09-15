"""Number normalization — locale-aware decimal parsing.

Handles European (1.234,56), US (1,234.56), and mixed formats.
All output is dot-decimal as required by erp.py.
Uses Decimal for all financial calculations.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from src.models import AccountingIR

logger = logging.getLogger(__name__)

# Characters to strip from the beginning of a number string
_CURRENCY_CHARS = set("€$£¥₹₩₫₱₦₵₸₺₼₽฿RM RSRKR")


def parse_number(value: str | None) -> str:
    """Parse a locale-aware number string to dot-decimal format.

    Handles:
    - European format: 1.234,56 → 1234.56
    - US format: 1,234.56 → 1234.56
    - Plain: 1234.56 → 1234.56
    - Percentage: 19% → 19
    - Currency symbols: €1,234.56 → 1234.56
    - Negative: -1.234,56 → -1234.56
    - Parenthetical negatives: (1,234.56) → -1234.56

    Returns empty string for empty/None/unparseable input.
    """
    if value is None:
        return ""

    s = str(value).strip()
    if not s:
        return ""

    # Strip percentage sign
    s = s.replace("%", "").strip()

    # Handle parenthetical negatives: (1,234.56) → -1,234.56
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
        is_negative = True

    # Strip leading currency symbols and whitespace
    i = 0
    while i < len(s) and (s[i] in _CURRENCY_CHARS or s[i].isspace()):
        i += 1
    s = s[i:].strip()

    # Strip trailing currency codes (EUR, USD, etc.)
    s = re.sub(r'\s*[A-Z]{3}\s*$', '', s).strip()

    # Handle explicit negative sign (leading or trailing SAP/German format)
    if s.startswith("-") or s.startswith("−"):  # regular minus or en-dash minus
        s = s[1:].strip()
        is_negative = True
    elif s.endswith("-") or s.endswith("−"):  # trailing minus (German/SAP)
        s = s[:-1].strip()
        is_negative = True

    if not s:
        return ""

    # Determine format by analyzing dots and commas
    s = _normalize_separators(s)

    if not s:
        return ""

    # Validate it's a valid number
    try:
        d = Decimal(s)
        if is_negative:
            d = -d
        # Return normalized string representation
        return str(d)
    except InvalidOperation:
        logger.debug("Could not parse number: %s (original: %s)", s, value)
        return ""


def _normalize_separators(s: str) -> str:
    """Normalize thousand/decimal separators to produce a dot-decimal string.

    Logic:
    - If both . and , are present, the LAST one is the decimal separator
    - If only , is present and appears once with ≤2 digits after: decimal separator
    - If only . is present and appears once with ≤2 digits after: decimal separator
    - Multiple . → thousand separators (e.g., 1.234.567)
    - Multiple , → thousand separators (e.g., 1,234,567)
    """
    has_dot = '.' in s
    has_comma = ',' in s

    if has_dot and has_comma:
        # Both present — last one is decimal separator
        last_dot = s.rfind('.')
        last_comma = s.rfind(',')

        if last_comma > last_dot:
            # European: 1.234,56 → dots are thousands, comma is decimal
            s = s.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56 → commas are thousands, dot is decimal
            s = s.replace(',', '')

    elif has_comma and not has_dot:
        comma_count = s.count(',')
        parts_after_comma = s.split(',')[-1]

        if comma_count == 1 and len(parts_after_comma) <= 2:
            # Single comma with 1-2 digits after: decimal separator
            # e.g., 1234,56 → 1234.56
            s = s.replace(',', '.')
        elif comma_count == 1 and len(parts_after_comma) == 3:
            # Ambiguous: could be 1,234 (thousands) or rare decimal
            # Default to thousands separator (more common in financial docs)
            s = s.replace(',', '')
        else:
            # Multiple commas: thousand separators (1,234,567)
            s = s.replace(',', '')

    elif has_dot and not has_comma:
        dot_count = s.count('.')
        parts_after_dot = s.split('.')[-1]

        if dot_count == 1:
            # Single dot — keep as decimal (standard format)
            pass
        else:
            # Multiple dots: thousand separators (1.234.567)
            # But the last dot might be decimal if ≤2 digits follow
            if len(parts_after_dot) <= 2:
                # Last dot is decimal: 1.234.567,89 style but with dots only
                parts = s.rsplit('.', 1)
                s = parts[0].replace('.', '') + '.' + parts[1]
            else:
                s = s.replace('.', '')

    # Remove any remaining spaces (e.g., "1 234.56")
    s = s.replace(' ', '').replace('\u00a0', '').replace('\u202f', '')

    return s


def parse_decimal(value: str | None) -> Decimal:
    """Parse a value to Decimal via parse_number. Returns Decimal('0.00') if invalid."""
    num_str = parse_number(value)
    if not num_str:
        return Decimal("0.00")
    try:
        return Decimal(num_str)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def format_decimal(value: str, decimal_places: int = 2) -> str:
    """Format a dot-decimal string to a specific number of decimal places.

    Returns the formatted string, or the original if not parseable.
    """
    if not value:
        return value
    try:
        d = Decimal(value)
        quantize_str = '0.' + '0' * decimal_places
        return str(d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return value


def normalize_accounting_ir(ir: AccountingIR) -> AccountingIR:
    """Normalize all numeric fields in an AccountingIR to dot-decimal format.

    This is a non-destructive pass — it normalizes in-place and returns
    the same object.
    """
    # Header numeric fields
    ir.gross_total = parse_number(ir.gross_total) if ir.gross_total else ir.gross_total
    ir.subtotal = parse_number(ir.subtotal) if ir.subtotal else ir.subtotal
    ir.total_tax_amount = parse_number(ir.total_tax_amount) if ir.total_tax_amount else ir.total_tax_amount
    ir.discount_amount = parse_number(ir.discount_amount) if ir.discount_amount else ir.discount_amount
    ir.freight_charges = parse_number(ir.freight_charges) if ir.freight_charges else ir.freight_charges
    ir.insurance_charges = parse_number(ir.insurance_charges) if ir.insurance_charges else ir.insurance_charges
    ir.extra_charges = parse_number(ir.extra_charges) if ir.extra_charges else ir.extra_charges
    ir.excise_duties = parse_number(ir.excise_duties) if ir.excise_duties else ir.excise_duties

    # Header taxes
    for tax in ir.taxes:
        tax.tax_rate = parse_number(tax.tax_rate) if tax.tax_rate else tax.tax_rate
        tax.tax_amount = parse_number(tax.tax_amount) if tax.tax_amount else tax.tax_amount

    # Line items
    for line in ir.line_items:
        line.quantity = parse_number(line.quantity) if line.quantity else line.quantity
        line.unit_price = parse_number(line.unit_price) if line.unit_price else line.unit_price
        line.total = parse_number(line.total) if line.total else line.total
        line.discount = parse_number(line.discount) if line.discount else line.discount
        line.discount_percentage = parse_number(line.discount_percentage) if line.discount_percentage else line.discount_percentage
        line.tax_rate = parse_number(line.tax_rate) if line.tax_rate else line.tax_rate
        line.tax_amount = parse_number(line.tax_amount) if line.tax_amount else line.tax_amount

        # Unit price scaling sanity check (e.g., DU-05: total 771.66 for 100 PC, unit_price misassigned as total)
        q = float(parse_decimal(line.quantity)) if line.quantity else 1.0
        p = float(parse_decimal(line.unit_price)) if line.unit_price else 0.0
        tot = float(parse_decimal(line.total)) if line.total else 0.0
        if q > 1 and tot > 0 and abs(p - tot) < 0.01 and abs(q * p - tot) > 1.0:
            logger.info("Unit price equals line total for qty > 1; rescaling unit_price to %.4f", tot / q)
            line.unit_price = str(round(tot / q, 4))

        for tax in line.taxes:
            tax.tax_rate = parse_number(tax.tax_rate) if tax.tax_rate else tax.tax_rate
            tax.tax_amount = parse_number(tax.tax_amount) if tax.tax_amount else tax.tax_amount

    # Precision rounding adjustment: if sum of line bases is 1 or 2 cents off from stated subtotal due to truncated unit price
    sub = float(parse_decimal(ir.subtotal))
    if sub > 0 and ir.line_items:
        line_sum = 0.0
        for li in ir.line_items:
            q = float(parse_decimal(li.quantity)) if li.quantity else 1.0
            p_val = float(parse_decimal(li.unit_price)) if li.unit_price else 0.0
            disc = float(parse_decimal(li.discount)) if li.discount else 0.0
            line_sum += round(q * p_val - disc, 2)
        diff = round(sub - line_sum, 2)
        if abs(diff) in (0.01, 0.02):
            for li in ir.line_items:
                q = float(parse_decimal(li.quantity)) if li.quantity else 1.0
                if q > 1:
                    current_base = round(q * float(parse_decimal(li.unit_price)), 2)
                    target_base = current_base + diff
                    li.unit_price = str(round(target_base / q, 6))
                    logger.info("Adjusted line unit_price for rounding precision (diff=%.2f): %s", diff, li.unit_price)
                    break

    return ir


