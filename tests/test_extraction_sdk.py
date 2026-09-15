"""Tests for modern google-genai SDK migration."""

import os
import pytest
from unittest.mock import patch, MagicMock

from google import genai
from google.genai import types
from src.extraction.llm import GoogleExtractor, get_extractor
from src.extraction.extractor import _get_llm_client


class TestGoogleGenAISDK:
    """Test suite for the modern google.genai SDK migration."""

    def test_sdk_import(self):
        """Verify google.genai can be imported."""
        assert hasattr(genai, "Client")
        assert hasattr(types, "Part")
        assert hasattr(types, "GenerateContentConfig")

    def test_google_extractor_initialization(self):
        """Verify GoogleExtractor initializes Client with api_key."""
        extractor = GoogleExtractor(api_key="test_key_123", model="gemini-3.6-flash")
        assert extractor.model == "gemini-3.6-flash"
        assert extractor.client is not None

    def test_google_extractor_missing_key_raises(self):
        """Verify GoogleExtractor raises ValueError if no key is found."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY is not set"):
                GoogleExtractor(api_key=None)

    def test_get_llm_client_factory(self):
        """Verify _get_llm_client creates genai.Client for google provider."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "google", "GOOGLE_API_KEY": "test_key_456"}):
            client, provider = _get_llm_client()
            assert provider == "google"
            assert isinstance(client, genai.Client)

    def test_image_part_creation(self):
        """Verify types.Part.from_bytes constructs valid binary image part."""
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        part = types.Part.from_bytes(data=fake_png, mime_type="image/png")
        assert part is not None
