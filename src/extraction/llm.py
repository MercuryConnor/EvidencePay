"""LLM provider abstraction — Protocol and implementations for vision-capable models.

Supports:
- OpenAIExtractor (GPT-4o)
- GoogleExtractor (Gemini)
- MockExtractor (Deterministic offline tests)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from src.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
    PROMPT_VERSION,
)
from src.models.evidence import EvidencePacket

logger = logging.getLogger(__name__)


@runtime_checkable
class DocumentExtractor(Protocol):
    """Protocol for LLM vision-based document extraction."""

    def extract(self, packet: EvidencePacket) -> str:
        """Extract structured accounting facts from document pages.

        Returns raw JSON string response.
        """
        ...


class MockExtractor:
    """Deterministic extractor for offline testing and unit tests."""

    def __init__(self, canned_response: Optional[Dict[str, Any]] = None):
        self.canned_response = canned_response or {
            "is_payable": True,
            "document_type": "invoice",
            "invoice_number": "MOCK-1001",
            "invoice_date": "2026-03-01",
            "due_date": "2026-03-31",
            "invoice_type": "INVOICE",
            "currency": "EUR",
            "supplier_name": "ACME Supplies GmbH",
            "supplier_vat_id": "DE209177122",
            "gross_total": "119.00",
            "subtotal": "100.00",
            "total_tax_amount": "19.00",
            "header_taxes": [
                {
                    "tax_type": "VAT",
                    "tax_name": "Standard VAT",
                    "tax_rate": "19",
                    "tax_amount": "19.00",
                }
            ],
            "line_items": [
                {
                    "description": "Consulting Services",
                    "item_type": "SERVICE",
                    "quantity": "1",
                    "unit_price": "100.00",
                    "total": "100.00",
                }
            ],
        }

    def extract(self, packet: EvidencePacket) -> str:
        logger.debug("MockExtractor returning canned response for %s", packet.filename)
        return json.dumps(self.canned_response)


class OpenAIExtractor:
    """OpenAI GPT-4o vision extractor."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        from openai import OpenAI
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def extract(self, packet: EvidencePacket) -> str:
        from src.evidence.renderer import render_all_pages_to_base64

        # Render all pages
        b64_pages = render_all_pages_to_base64(packet.pdf_path)
        content: List[Dict[str, Any]] = [{"type": "text", "text": EXTRACTION_USER_PROMPT}]

        for b64 in b64_pages:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
            })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return response.choices[0].message.content or "{}"


class GoogleExtractor:
    """Google Gemini vision extractor using modern google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.6-flash"):
        from google import genai
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model

    def extract(self, packet: EvidencePacket) -> str:
        import io
        from google.genai import types
        from src.evidence.renderer import render_page_to_image

        contents: List[Any] = [EXTRACTION_SYSTEM_PROMPT + "\n\n" + EXTRACTION_USER_PROMPT]
        for page_num in range(1, packet.total_pages + 1):
            img = render_page_to_image(packet.pdf_path, page_num)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            contents.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"))

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        return response.text or "{}"


def get_extractor() -> DocumentExtractor:
    """Factory function returning the configured DocumentExtractor."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        return OpenAIExtractor()
    elif provider in ("google", "gemini"):
        return GoogleExtractor()
    elif provider == "mock":
        return MockExtractor()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
