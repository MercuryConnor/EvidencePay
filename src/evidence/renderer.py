"""Page rendering utilities for vision models and preview."""

from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image

from src.ingestion.pdf import (
    RENDER_DPI,
    render_all_pages_to_base64,
    render_page_to_base64,
    render_page_to_image,
)

__all__ = [
    "RENDER_DPI",
    "render_page_to_image",
    "render_page_to_base64",
    "render_all_pages_to_base64",
]
