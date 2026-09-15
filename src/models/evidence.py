"""Evidence models — provenance-tracked extraction values.

Every material field in the accounting pipeline must be traceable back to
a specific page, region, and extraction method. This module defines those
data structures.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import ExtractionMethod, PageRole


# ── Spatial ─────────────────────────────────────

class BoundingBox(BaseModel):
    """Axis-aligned bounding box for a value on a page (PDF points)."""
    x0: float
    y0: float
    x1: float
    y1: float


# ── Field-level provenance ──────────────────────

class EvidenceValue(BaseModel):
    """A single extracted value with full provenance chain.

    Every material accounting field (amounts, rates, identifiers) should
    carry one of these so that later validation can answer:
    "Where did this number come from?"
    """
    value: str = ""                             # raw value as seen on document
    normalized_value: str = ""                  # after locale normalisation
    page: int = 0                               # 1-indexed source page
    source_text: str = ""                       # surrounding text context
    bbox: Optional[BoundingBox] = None          # location on page
    confidence: float = 0.0                     # extraction confidence [0,1]
    extraction_method: ExtractionMethod = ExtractionMethod.VISION_LLM

    def is_empty(self) -> bool:
        return not self.value.strip() and not self.normalized_value.strip()

    def is_grounded(self) -> bool:
        """Does this value have sufficient evidence to be trusted?"""
        return bool(self.value.strip()) and self.page > 0


# ── Page-level evidence ─────────────────────────

class PageEvidence(BaseModel):
    """Evidence collected from a single PDF page."""
    page_number: int                            # 1-indexed
    native_text: str = ""                       # raw PDF text extraction
    ocr_text: str = ""                          # OCR output (if image-only)
    has_native_text: bool = False               # len(native_text) >= threshold
    is_image_only: bool = False                 # has images but no native text
    image_path: Optional[str] = None            # path to rendered image
    width: float = 0.0                          # page width (points)
    height: float = 0.0                         # page height (points)
    role: PageRole = PageRole.UNKNOWN           # classified page role


# ── Document-level evidence packet ──────────────

class EvidencePacket(BaseModel):
    """All evidence collected from a single PDF file.

    This is the input to classification and extraction stages.
    """
    filename: str
    total_pages: int = 0
    pages: list[PageEvidence] = Field(default_factory=list)

    def text_pages(self) -> list[PageEvidence]:
        """Pages with native PDF text."""
        return [p for p in self.pages if p.has_native_text]

    def image_pages(self) -> list[PageEvidence]:
        """Pages that are image-only (need OCR/vision)."""
        return [p for p in self.pages if p.is_image_only]

    def all_text(self) -> str:
        """Concatenated text from all pages (native + OCR)."""
        parts = []
        for p in self.pages:
            text = p.native_text or p.ocr_text
            if text:
                parts.append(text)
        return "\n\n".join(parts)
