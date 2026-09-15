"""Tests for Gemini model pool fallback, quota management, and schema purity."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

from src.extraction.model_manager import (
    DailyQuotaExhaustedError,
    GeminiModelManager,
    is_daily_quota_exhausted,
)
from src.extraction.extractor import (
    _call_google_model,
    _call_vision_llm,
    extract_payables_with_declined,
)
from src.models import (
    EvidencePacket,
    FileOutput,
    PageEvidence,
)
from src.output.writer import format_output_dict


class TestQuotaDetection:
    """Verify daily quota exhaustion is properly distinguished from transient 429s."""

    def test_daily_quota_patterns_detected(self):
        daily_errors = [
            "429 Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "Resource has been exhausted: GenerateRequestsPerDayPerModel for gemini-3.8-flash",
            "Error: generate_content_free_tier_requests per day exceeded",
            "DailyQuotaExceeded: Please wait until tomorrow",
            "Quota exceeded for quota metric 'Generate Content API requests per day'",
            "Rate limit error: 100 requests per day per model reached",
        ]
        for err in daily_errors:
            assert is_daily_quota_exhausted(Exception(err)), f"Should identify as daily quota: {err}"

    def test_transient_rate_limits_not_identified_as_daily_quota(self):
        transient_errors = [
            "429 Too Many Requests: Rate limit exceeded (15 requests per minute)",
            "429 ResourceExhausted: rate_limit_exceeded for TPM",
            "HTTP 429: Too many concurrent requests",
            "503 Service Unavailable",
            "500 Internal Server Error",
            "Connection reset by peer",
        ]
        for err in transient_errors:
            assert not is_daily_quota_exhausted(Exception(err)), f"Should NOT identify as daily quota: {err}"


class TestGeminiModelManager:
    """Verify model pool resolution, ordering, and exhaustion state tracking."""

    def test_env_pool_configuration(self):
        with patch.dict(os.environ, {
            "GEMINI_MODELS": "gemini-test-1, gemini-test-2, gemini-test-3",
            "LLM_MODEL": "gemini-test-2",
        }):
            manager = GeminiModelManager()
            models = manager.get_configured_models()
            assert models == ["gemini-test-1", "gemini-test-2", "gemini-test-3"]

            # Primary model should be first in get_models_to_try
            to_try = manager.get_models_to_try()
            assert to_try[0] == "gemini-test-2"
            assert "gemini-test-1" in to_try
            assert "gemini-test-3" in to_try

    def test_exhausted_models_filtered_out(self):
        manager = GeminiModelManager(
            model_pool=["model-a", "model-b", "model-c"],
            primary_model="model-a",
        )
        assert manager.get_models_to_try() == ["model-a", "model-b", "model-c"]

        manager.mark_exhausted("model-a", reason="Daily quota exceeded")
        assert "model-a" in manager.exhausted_models
        assert manager.fallback_count == 1
        assert manager.last_fallback_reason == "Daily quota exceeded"

        # Now model-a should be skipped
        available = manager.get_models_to_try()
        assert "model-a" not in available
        assert available == ["model-b", "model-c"]


class TestImmediateFailover:
    """Verify that daily quota exhaustion aborts retries immediately (1 attempt, not 3)."""

    def test_daily_quota_aborts_immediately_without_retrying(self):
        mock_client = MagicMock()
        daily_err = Exception("429 ResourceExhausted: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        mock_client.models.generate_content.side_effect = daily_err

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        with pytest.raises(DailyQuotaExhaustedError):
            _call_google_model(
                client=mock_client,
                model_name="gemini-3.8-flash",
                temperature=0.0,
                max_retries=3,
                page_images=["dummy_b64"],
                evidence=evidence,
            )

        # Crucial check: MUST have been called exactly ONCE, not 3 times!
        assert mock_client.models.generate_content.call_count == 1

    def test_transient_error_retries_with_backoff(self):
        mock_client = MagicMock()
        transient_err = Exception("429 Too Many Requests (15 requests per minute)")
        mock_client.models.generate_content.side_effect = transient_err

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        from src.extraction.model_manager import TemporaryModelUnavailableError
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(TemporaryModelUnavailableError, match="temporarily unavailable"):
                _call_google_model(
                    client=mock_client,
                    model_name="gemini-3.8-flash",
                    temperature=0.0,
                    max_retries=3,
                    page_images=["dummy_b64"],
                    evidence=evidence,
                )

        # Transient error should be retried max_retries (3) times
        assert mock_client.models.generate_content.call_count == 3
        assert mock_sleep.call_count == 2


class TestVisionLLMFallback:
    """Verify fallback from primary model to secondary model upon quota exhaustion."""

    def test_fallback_to_next_model(self):
        mock_client = MagicMock()
        daily_err = Exception("GenerateRequestsPerDayPerModel quota exceeded")

        success_response = MagicMock()
        success_response.text = json.dumps({"is_payable": True, "invoice_number": "FB-001"})

        def side_effect(model, contents, config):
            if model == "gemini-3.8-flash":
                raise daily_err
            elif model == "gemini-3.7-flash":
                return success_response
            raise ValueError(f"Unexpected model: {model}")

        mock_client.models.generate_content.side_effect = side_effect

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        from src.extraction.model_manager import gemini_manager
        gemini_manager.reset()

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "google",
            "GEMINI_MODELS": "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
            "LLM_MODEL": "gemini-3.8-flash",
        }):
            with patch("src.extraction.extractor._get_llm_client", return_value=(mock_client, "google")):
                result, model_used = _call_vision_llm(["dummy_b64"], evidence)

                assert result == {"is_payable": True, "invoice_number": "FB-001"}
                assert model_used == "gemini-3.7-flash"
                assert "gemini-3.8-flash" in gemini_manager.exhausted_models

                # Next document should skip gemini-3.8-flash immediately
                mock_client.models.generate_content.reset_mock()
                result2, model_used2 = _call_vision_llm(["dummy_b64"], evidence)
                assert model_used2 == "gemini-3.7-flash"
                # Check that 3.8 was NOT called at all for the second document
                called_models = [c.kwargs.get("model") for c in mock_client.models.generate_content.call_args_list]
                assert "gemini-3.8-flash" not in called_models


class TestOpenAIProviderIsolation:
    """Verify that OpenAI provider does NOT use the Gemini model pool."""

    def test_openai_uses_single_model(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({"is_payable": True})))]
        mock_client.chat.completions.create.return_value = mock_response

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "GEMINI_MODELS": "gemini-3.8-flash,gemini-3.7-flash",
        }):
            with patch("src.extraction.extractor._get_llm_client", return_value=(mock_client, "openai")):
                result, model_used = _call_vision_llm(["dummy_b64"], evidence)
                assert model_used == "gpt-4o"
                # Ensure gpt-4o was passed to OpenAI, not any gemini model
                mock_client.chat.completions.create.assert_called_once()
                assert mock_client.chat.completions.create.call_args.kwargs["model"] == "gpt-4o"


class TestCacheAndSchemaPurity:
    """Verify cache receives clean dict and FileOutput contains no execution metadata."""

    def test_file_output_contains_no_execution_metadata(self):
        output = FileOutput(file="test.pdf")
        dumped = format_output_dict(output)

        assert "file" in dumped
        assert "payables" in dumped
        assert "declined" in dumped

        # Ensure execution metadata is NOT leaked into FileOutput
        assert "fallback" not in dumped
        assert "fallback_reason" not in dumped
        assert "llm_model_used" not in dumped
        assert len(dumped.keys()) == 3


class TestResilienceLevelsAndAFCOptimization:
    """Verify 5-level resilience, 503 capacity handling, AFC disabling, and non-payable purity."""

    def test_afc_disabled_in_generate_content_config(self):
        """Verify automatic_function_calling is explicitly disabled to eliminate AFC warnings."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text='{"is_payable": true}')

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        _call_google_model(
            client=mock_client,
            model_name="gemini-3.8-flash",
            temperature=0.0,
            max_retries=1,
            page_images=["dummy_b64"],
            evidence=evidence,
        )

        mock_client.models.generate_content.assert_called_once()
        config_used = mock_client.models.generate_content.call_args.kwargs["config"]
        assert config_used.automatic_function_calling is not None
        assert config_used.automatic_function_calling.disable is True

    def test_level3_503_capacity_error_failover(self, caplog):
        """Verify 503 No capacity error triggers retries with backoff and fails over to 3.7."""
        mock_client = MagicMock()
        err_503 = Exception("Error: UNAVAILABLE (code 503): No capacity available for model gemini-3.8-flash on the server")
        success_response = MagicMock(text=json.dumps({"is_payable": True, "invoice_number": "INV-37"}))

        def side_effect(model, contents, config):
            if model == "gemini-3.8-flash":
                raise err_503
            elif model == "gemini-3.7-flash":
                return success_response
            raise ValueError(f"Unexpected model: {model}")

        mock_client.models.generate_content.side_effect = side_effect

        evidence = EvidencePacket(filename="test.pdf", file_hash="abc", total_pages=1, pages=[
            PageEvidence(page_number=1, width=100, height=100, is_blank=False, has_native_text=False)
        ])

        from src.extraction.model_manager import gemini_manager
        gemini_manager.reset()

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "google",
            "GEMINI_MODELS": "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
            "LLM_MODEL": "gemini-3.8-flash",
        }):
            with patch("src.extraction.extractor._get_llm_client", return_value=(mock_client, "google")):
                with patch("time.sleep"):  # skip actual sleep
                    import logging
                    with caplog.at_level(logging.INFO):
                        result, model_used = _call_vision_llm(["dummy_b64"], evidence)

                        assert result == {"is_payable": True, "invoice_number": "INV-37"}
                        assert model_used == "gemini-3.7-flash"

                        # Verify exact log sequence
                        log_text = caplog.text
                        assert "Attempting extraction with Gemini model: gemini-3.8-flash" in log_text
                        assert "gemini-3.8-flash returned 503 (attempt 1/3)" in log_text
                        assert "gemini-3.8-flash returned 503 (attempt 2/3)" in log_text
                        assert "gemini-3.8-flash returned 503 (attempt 3/3)" in log_text
                        assert "gemini-3.8-flash temporarily unavailable" in log_text
                        assert "Failing over to gemini-3.7-flash" in log_text
                        assert "Extraction successful with gemini-3.7-flash" in log_text

                        # Next document skips 3.8 immediately
                        caplog.clear()
                        result2, model_used2 = _call_vision_llm(["dummy_b64"], evidence)
                        assert model_used2 == "gemini-3.7-flash"
                        assert "gemini-3.8-flash temporarily unavailable; skipping" in caplog.text

    def test_level5_all_models_unavailable_raises_infra_error_not_declined(self):
        """Verify Level 5 raises InfrastructureError and does NOT mark document as declined non-payable."""
        from src.extraction.model_manager import AllModelsUnavailableError, InfrastructureError, gemini_manager
        from src.pipeline import process_single_pdf

        gemini_manager.reset()
        gemini_manager.mark_temporarily_unavailable("gemini-3.8-flash", "returned 503")
        gemini_manager.mark_temporarily_unavailable("gemini-3.7-flash", "returned 503")
        gemini_manager.mark_temporarily_unavailable("gemini-3.6-flash", "returned 503")

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "google",
            "GOOGLE_API_KEY": "test_key_123",
            "GEMINI_MODELS": "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
        }):
            from pathlib import Path
            dummy_pdf = Path("candidate_kit/candidate_kit/documents/INV-01.pdf")
            if not dummy_pdf.exists():
                pytest.skip("Test document not found")

            with patch("src.cache.extraction_cache.ExtractionCache.get", return_value=None):
                with patch("google.genai.Client"):
                    with pytest.raises(InfrastructureError):
                        process_single_pdf(dummy_pdf)
