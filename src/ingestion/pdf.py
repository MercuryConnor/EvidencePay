"""PDF Ingestion — load PDFs, extract text, render pages to images.

Uses PyMuPDF (fitz) for both text extraction and page rendering.
Preserves page boundaries, spatial information, and page numbering.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

import pymupdf  # PyMuPDF
from PIL import Image

from src.models.evidence import EvidencePacket, PageEvidence
from src.models.enums import PageRole

logger = logging.getLogger(__name__)

# DPI for rendering pages to images for vision models
RENDER_DPI = 200
# Minimum text length to consider a page as having native text
MIN_TEXT_LENGTH = 20


def ingest_pdf(pdf_path: Path) -> EvidencePacket:
    """Ingest a PDF and build an EvidencePacket with per-page evidence.

    For each page:
    - Extracts native text (if available)
    - Detects if page is image-only
    - Renders page to an image for vision model processing
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    packet = EvidencePacket(
        filename=pdf_path.name,
        total_pages=len(doc),
    )

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1

        # Extract native text
        native_text = page.get_text("text").strip()
        has_native = len(native_text) >= MIN_TEXT_LENGTH

        # Detect if page is image-only (has images but no meaningful text)
        image_list = page.get_images(full=True)
        is_image_only = not has_native and len(image_list) > 0

        # Get page dimensions
        rect = page.rect
        width = rect.width
        height = rect.height

        page_evidence = PageEvidence(
            page_number=page_num,
            native_text=native_text if has_native else "",
            has_native_text=has_native,
            is_image_only=is_image_only,
            width=width,
            height=height,
            role=PageRole.UNKNOWN,
        )

        packet.pages.append(page_evidence)

        logger.debug(
            "  Page %d: native_text=%s, image_only=%s, text_len=%d",
            page_num, has_native, is_image_only, len(native_text)
        )

    doc.close()
    logger.info(
        "Ingested %s: %d pages (%d with native text, %d image-only)",
        pdf_path.name,
        packet.total_pages,
        sum(1 for p in packet.pages if p.has_native_text),
        sum(1 for p in packet.pages if p.is_image_only),
    )

    return packet


def render_page_to_image(pdf_path: Path, page_number: int, dpi: int = RENDER_DPI) -> Image.Image:
    """Render a single page to a PIL Image.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number.
        dpi: Resolution for rendering.

    Returns:
        PIL Image of the rendered page.
    """
    doc = pymupdf.open(str(pdf_path))
    page = doc[page_number - 1]

    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)

    img = Image.open(io.BytesIO(pixmap.tobytes("png")))
    doc.close()

    return img


def render_page_to_base64(pdf_path: Path, page_number: int, dpi: int = RENDER_DPI) -> str:
    """Render a page to a base64-encoded PNG string for LLM API calls.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number.
        dpi: Resolution for rendering.

    Returns:
        Base64-encoded PNG string.
    """
    img = render_page_to_image(pdf_path, page_number, dpi)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def render_all_pages_to_base64(pdf_path: Path, dpi: int = RENDER_DPI) -> list[str]:
    """Render all pages of a PDF to base64-encoded PNG strings.

    Returns a list of base64 strings, one per page.
    """
    doc = pymupdf.open(str(pdf_path))
    results = []

    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pixmap = page.get_pixmap(matrix=matrix)
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        results.append(base64.b64encode(buffer.read()).decode("utf-8"))

    doc.close()
    return results


def get_page_text(pdf_path: Path, page_number: int) -> str:
    """Extract native text from a specific page.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number.

    Returns:
        Extracted text string.
    """
    doc = pymupdf.open(str(pdf_path))
    page = doc[page_number - 1]
    text = page.get_text("text").strip()
    doc.close()
    return text

