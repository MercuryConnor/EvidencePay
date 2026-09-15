"""Currency normalization — maps currency symbols and names to ISO 4217 codes.

Handles symbols: €, $, £, ¥, ₹, CHF, etc.
Validates against known currencies.
"""

from __future__ import annotations

import re
from typing import Optional

CURRENCY_MAP = {
    "€": "EUR",
    "EUR": "EUR",
    "EURO": "EUR",
    "$": "USD",
    "USD": "USD",
    "US DOLLAR": "USD",
    "£": "GBP",
    "GBP": "GBP",
    "POUND": "GBP",
    "¥": "JPY",
    "JPY": "JPY",
    "YEN": "JPY",
    "₹": "INR",
    "INR": "INR",
    "RUPEE": "INR",
    "CHF": "CHF",
    "CAD": "CAD",
    "AUD": "AUD",
    "SEK": "SEK",
    "NOK": "NOK",
    "DKK": "DKK",
    "PLN": "PLN",
    "SGD": "SGD",
    "HKD": "HKD",
    "NZD": "NZD",
    "ZAR": "ZAR",
    "AED": "AED",
    "SAR": "SAR",
    "GHS": "GHS",
    "GH₵": "GHS",
    "GH\u20b5": "GHS",
    "KES": "KES",
    "THB": "THB",
}


def normalize_currency(currency_str: str) -> str:
    """Normalize a raw currency string or symbol to ISO 4217 3-letter code.

    Args:
        currency_str: Currency symbol or code (e.g. "€", "EUR", "USD", "$")

    Returns:
        3-letter ISO currency code, or original uppercase string if not mapped.
    """
    if not currency_str:
        return ""

    cleaned = currency_str.strip().upper()
    if cleaned in CURRENCY_MAP:
        return CURRENCY_MAP[cleaned]

    # Search for embedded symbol
    for sym, code in CURRENCY_MAP.items():
        if sym in currency_str:
            return code

    # Fallback to uppercase 3-letter code if valid format
    if re.match(r"^[A-Z]{3}$", cleaned):
        return cleaned

    return cleaned
