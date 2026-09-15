"""OCR fallback for image-only or scanned pages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from src.ingestion.pdf import render_page_to_image

logger = logging.getLogger(__name__)


def extract_ocr_text(pdf_path: Path, page_number: int) -> str:
    """Attempt OCR extraction on a page using pytesseract if available.

    Falls back gracefully if tesseract is not installed or configured.
    """
    try:
        import pytesseract
        img = render_page_to_image(pdf_path, page_number)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        logger.debug("pytesseract OCR not available or failed on %s p.%d: %s", pdf_path.name, page_number, e)
        return ""
