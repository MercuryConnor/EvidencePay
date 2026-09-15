"""Native PDF text extraction with bounding boxes and spatial coordinates.

Extracts text blocks, spans, and lines with exact coordinate bboxes for provenance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

import pymupdf

from src.models.evidence import BoundingBox, EvidenceValue

logger = logging.getLogger(__name__)


def extract_page_text_blocks(pdf_path: Path, page_number: int) -> List[dict]:
    """Extract text blocks with coordinates from a specific page.

    Returns a list of block dicts with text and bbox (x0, y0, x1, y1).
    """
    doc = pymupdf.open(str(pdf_path))
    try:
        page = doc[page_number - 1]
        # "blocks": (x0, y0, x1, y1, text, block_no, block_type)
        blocks = page.get_text("blocks")
        results = []
        for b in blocks:
            if len(b) >= 5 and b[6] == 0:  # text block
                results.append({
                    "bbox": BoundingBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3], page=page_number),
                    "text": b[4].strip(),
                    "block_no": b[5],
                })
        return results
    finally:
        doc.close()


def find_text_coordinate(
    pdf_path: Path,
    target_substring: str,
    page_number: Optional[int] = None,
) -> Optional[EvidenceValue]:
    """Search for a target text snippet in a PDF and return an EvidenceValue with its bbox.

    If page_number is not given, searches all pages.
    """
    if not target_substring:
        return None

    target = target_substring.strip().lower()
    doc = pymupdf.open(str(pdf_path))
    try:
        pages_to_search = [page_number] if page_number else range(1, len(doc) + 1)
        for p_num in pages_to_search:
            page = doc[p_num - 1]
            rects = page.search_for(target_substring)
            if rects:
                r = rects[0]
                return EvidenceValue(
                    value=target_substring,
                    normalized_value=target_substring,
                    page=p_num,
                    source_text=target_substring,
                    bbox=BoundingBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1, page=p_num),
                    confidence=1.0,
                    extraction_method="pdf_text",
                )
        return None
    finally:
        doc.close()
