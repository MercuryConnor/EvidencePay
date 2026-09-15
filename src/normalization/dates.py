"""Date normalization — normalize various date formats to ISO YYYY-MM-DD.

Supports:
- ISO: 2026-03-15
- Slash formats: 15/03/2026, 03/15/2026
- Dot formats: 15.03.2026
- Dash formats: 15-03-2026
- Textual dates: 15 Mar 2026, March 15, 2026, 15. März 2026
- Ambiguity detection: flags dates where DD/MM vs MM/DD cannot be determined
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

MONTH_NAMES = {
    "jan": 1, "january": 1, "januar": 1, "janvier": 1, "gennaio": 1,
    "feb": 2, "february": 2, "februar": 2, "fevrier": 2, "février": 2, "febbraio": 2,
    "mar": 3, "march": 3, "mär": 3, "märz": 3, "mars": 3, "marzo": 3,
    "apr": 4, "april": 4, "avril": 4, "aprile": 4,
    "may": 5, "mai": 5, "maggio": 5,
    "jun": 6, "june": 6, "juni": 6, "juin": 6, "giugno": 6,
    "jul": 7, "july": 7, "juli": 7, "juillet": 7, "luglio": 7,
    "aug": 8, "august": 8, "août": 8, "aout": 8, "agosto": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9, "settembre": 9,
    "oct": 10, "october": 10, "oktober": 10, "octobre": 10, "ottobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "dez": 12, "dezember": 12, "décembre": 12, "dicembre": 12,
}


def normalize_date(date_str: str, default_to_day_first: bool = True) -> Tuple[str, bool]:
    """Normalize date string to ISO YYYY-MM-DD format.

    Args:
        date_str: Raw date string from document.
        default_to_day_first: If True, ambiguous dates (e.g. 03/04/2026) default to DD/MM/YYYY.

    Returns:
        tuple: (normalized_date_iso, is_ambiguous)
        normalized_date_iso will be empty string if parsing fails.
    """
    if not date_str:
        return "", False

    cleaned = date_str.strip()
    if not cleaned:
        return "", False

    # Check ISO format directly: YYYY-MM-DD
    iso_match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", cleaned)
    if iso_match:
        y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        try:
            dt = datetime(y, m, d)
            return dt.strftime("%Y-%m-%d"), False
        except ValueError:
            return "", False

    # Check textual month patterns: e.g. "15 Mar 2026", "15. März 2026", "March 15, 2026"
    # Pattern: Day Month Year
    dmy_text = re.match(r"^(\d{1,2})[.\s/-]+([A-Za-zÀ-ÿ]+)[,\s/-]+(\d{4})$", cleaned)
    if dmy_text:
        d = int(dmy_text.group(1))
        m_str = dmy_text.group(2).lower()
        y = int(dmy_text.group(3))
        if m_str in MONTH_NAMES:
            m = MONTH_NAMES[m_str]
            try:
                dt = datetime(y, m, d)
                return dt.strftime("%Y-%m-%d"), False
            except ValueError:
                return "", False

    # Pattern: Month Day Year e.g. "March 15, 2026"
    mdy_text = re.match(r"^([A-Za-zÀ-ÿ]+)[.\s/-]+(\d{1,2})[,\s/-]+(\d{4})$", cleaned)
    if mdy_text:
        m_str = mdy_text.group(1).lower()
        d = int(mdy_text.group(2))
        y = int(mdy_text.group(3))
        if m_str in MONTH_NAMES:
            m = MONTH_NAMES[m_str]
            try:
                dt = datetime(y, m, d)
                return dt.strftime("%Y-%m-%d"), False
            except ValueError:
                return "", False

    # Pattern: numeric 2-digit day/month and 4-digit year: DD/MM/YYYY or MM/DD/YYYY
    num_match = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", cleaned)
    if num_match:
        p1, p2, raw_y = int(num_match.group(1)), int(num_match.group(2)), int(num_match.group(3))
        y = raw_y if raw_y >= 100 else (2000 + raw_y if raw_y < 70 else 1900 + raw_y)

        # Disambiguation:
        # If p1 > 12 and p2 <= 12 -> must be DD/MM/YYYY
        # If p2 > 12 and p1 <= 12 -> must be MM/DD/YYYY
        # If both <= 12 -> ambiguous!
        if p1 > 12 and p2 <= 12:
            try:
                dt = datetime(y, p2, p1)
                return dt.strftime("%Y-%m-%d"), False
            except ValueError:
                return "", False
        elif p2 > 12 and p1 <= 12:
            try:
                dt = datetime(y, p1, p2)
                return dt.strftime("%Y-%m-%d"), False
            except ValueError:
                return "", False
        elif p1 <= 12 and p2 <= 12:
            # Ambiguous!
            is_ambiguous = (p1 != p2)
            d, m = (p1, p2) if default_to_day_first else (p2, p1)
            try:
                dt = datetime(y, m, d)
                return dt.strftime("%Y-%m-%d"), is_ambiguous
            except ValueError:
                return "", False

    return "", False


def parse_date_safe(date_str: str) -> str:
    """Convenience wrapper returning YYYY-MM-DD or empty string."""
    iso_date, _ = normalize_date(date_str)
    return iso_date
