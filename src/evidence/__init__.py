"""Evidence extraction and rendering package."""

from src.evidence.layout import extract_tables_from_page
from src.evidence.ocr import extract_ocr_text
from src.evidence.renderer import (
    RENDER_DPI,
    render_all_pages_to_base64,
    render_page_to_base64,
    render_page_to_image,
)
from src.evidence.text import extract_page_text_blocks, find_text_coordinate

__all__ = [
    "extract_page_text_blocks",
    "find_text_coordinate",
    "render_page_to_image",
    "render_page_to_base64",
    "render_all_pages_to_base64",
    "extract_ocr_text",
    "extract_tables_from_page",
    "RENDER_DPI",
]
