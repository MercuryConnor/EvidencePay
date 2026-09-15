"""Layout and table structure extraction using pdfplumber / PyMuPDF."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def extract_tables_from_page(pdf_path: Path, page_number: int) -> List[List[List[Optional[str]]]]:
    """Extract table structures from a page using pdfplumber if available.

    Returns a list of tables, each table being a 2D list of cells.
    """
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            if 1 <= page_number <= len(pdf.pages):
                page = pdf.pages[page_number - 1]
                tables = page.extract_tables()
                return tables or []
        return []
    except Exception as e:
        logger.debug("pdfplumber table extraction unavailable or failed: %s", e)
        return []
