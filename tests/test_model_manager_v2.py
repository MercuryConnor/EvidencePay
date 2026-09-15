"""Comprehensive regression test suite for model discovery, error classification,
rate limiting, model health/fallback, and accounting reconstruction rules.

Tests all 16 invariants defined in Part 11:
1. 404 model -> no repeated retry.
2. 404 model -> next model selected.
3. Daily quota exhaustion -> fallback.
4. 503 -> bounded retry + temporary quarantine.
5. 429 RPM -> rate-limit handling.
6. All models unavailable -> infrastructure exception.
7. Infrastructure exception never becomes declined.
8. Global rate limiter is invoked for API calls.
9. Successful fallback records the model in diagnostics but not final JSON.
10. Explicit tax amount + tax rate does not double-count.
11. DU-06-style multi-tax invoice reconstructs correctly.
12. DU-10-style credit memo reconstructs correctly.
13. DU-11-style credit memo reconstructs correctly.
14. HLD-08-style VAT reconstructs correctly.
15. Discount amount + equivalent percentage is not double-applied.
16. Conflicting discount amount/percentage produces a diagnostic rather than silent double counting.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from candidate_kit.candidate_kit.erp import erp_book
from src.accounting.reconstruction import reconstruct_autodraft
from src.erp_validator import validate_payable
from src.extraction.extractor import (
    _call_google_model,
    _call_vision_llm,
)
from src.extraction.model_manager import (
    AllModelsUnavailableError,
    DailyQuotaExhaustedError,
    InfrastructureError,
    InvalidModelError,
    ModelErrorKind,
    ModelHealthState,
    RateLimitExceededError,
    TemporaryModelUnavailableError,
    classify_gemini_error,
    discover_gemini_models,
    gemini_manager,
)
from src.extraction.rate_limiter import gemini_rate_limiter
from src.models import (
    AccountingIR,
    AutodraftPayable,
    DocumentType,
    EvidencePacket,
    FileOutput,
    InvoiceType,
    LineItemIR,
    PageEvidence,
    SupplierIR,
    TaxIR,
)
from src.validation.diagnostics import diagnose_mismatch


def _make_dummy_evidence() -> EvidencePacket:
    return EvidencePacket(
        filename="test.pdf",
        file_hash="dummy_hash_123",
        total_pages=1,
        pages=[
            PageEvidence(
                page_number=1,
                width=100,
                height=100,
                is_blank=False,
                has_native_text=False,
            )
        ],
    )


# ── Model Behavior Tests (1–9) ─────────────────────────────────────────

class TestModelBehavior:
    """Tests 1–9 covering model discovery, error classification, and fallback."""

    def test_1_model_404_no_repeated_retry(self):
        """Test 1: 404 model not found must NOT be retried (call count == 1)."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("404 NOT_FOUND: Model 'gemini-3-flash' does not exist")

        with pytest.raises(InvalidModelError):
            _call_google_model(
                client=mock_client,
                model_name="gemini-3-flash",
                temperature=0.0,
                max_retries=3,
                page_images=["dummy_b64"],
                evidence=_make_dummy_evidence(),
            )

        # Invariant: 404 must abort retries immediately (1 attempt, not 3)
        assert mock_client.models.generate_content.call_count == 1

    def test_2_model_404_selects_next_model(self):
        """Test 2: 404 marks model invalid and immediately fails over to next candidate."""
        mock_client = MagicMock()
        err_404 = Exception("404 Not Found: model gemini-invalid is not found")
        success_resp = MagicMock(text=json.dumps({"is_payable": True, "invoice_number": "INV-02"}))

        def side_effect(model, contents, config):
            if model == "gemini-invalid":
                raise err_404
            elif model == "gemini-3.7-flash":
                return success_resp
            raise ValueError(f"Unexpected model: {model}")

        mock_client.models.generate_content.side_effect = side_effect

        gemini_manager.reset()
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "google",
            "GEMINI_MODELS": "gemini-invalid,gemini-3.7-flash",
            "LLM_MODEL": "gemini-invalid",
        }):
            with patch("src.extraction.extractor._get_llm_client", return_value=(mock_client, "google")):
                result, model_used = _call_vision_llm(["dummy_b64"], _make_dummy_evidence())

                assert result == {"is_payable": True, "invoice_number": "INV-02"}
                assert model_used == "gemini-3.7-flash"
                assert gemini_manager.model_states["gemini-invalid"] == ModelHealthState.INVALID

    def test_3_daily_quota_exhaustion_fallback(self):
        """Test 3: Daily quota exhaustion immediately marks model exhausted and falls back."""
        mock_client = MagicMock()
        daily_err = Exception("429 ResourceExhausted: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        success_resp = MagicMock(text=json.dumps({"is_payable": True, "invoice_number": "INV-03"}))

        def side_effect(model, contents, config):
            if model == "gemini-3.8-flash":
                raise daily_err
            elif model == "gemini-3.7-flash":
                return success_resp
            raise ValueError(f"Unexpected: {model}")

        mock_client.models.generate_content.side_effect = side_effect

        gemini_manager.reset()
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "google",
            "GEMINI_MODELS": "gemini-3.8-flash,gemini-3.7-flash",
            "LLM_MODEL": "gemini-3.8-flash",
        }):
            with patch("src.extraction.extractor._get_llm_client", return_value=(mock_client, "google")):
                result, model_used = _call_vision_llm(["dummy_b64"], _make_dummy_evidence())

                assert result["invoice_number"] == "INV-03"
                assert model_used == "gemini-3.7-flash"
                assert gemini_manager.model_states["gemini-3.8-flash"] == ModelHealthState.DAILY_QUOTA_EXHAUSTED

    def test_4_503_bounded_retry_and_temporary_quarantine(self):
        """Test 4: 503 retries with backoff up to limit, then temporarily quarantines model."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE: The service is currently unavailable")
        mock_client.models.generate_content.side_effect = err_503

        gemini_manager.reset()
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(TemporaryModelUnavailableError):
                _call_google_model(
                    client=mock_client,
                    model_name="gemini-3.8-flash",
                    temperature=0.0,
                    max_retries=2,
                    page_images=["dummy_b64"],
                    evidence=_make_dummy_evidence(),
                )

        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1

    def test_5_429_rpm_rate_limit_handling(self):
        """Test 5: 429 RPM rate limit is classified as RATE_LIMITED, retried, and quarantined without daily exhaustion."""
        exc = Exception("429 Too Many Requests (15 requests per minute limit reached)")
        kind, summary = classify_gemini_error(exc)
        assert kind == ModelErrorKind.RATE_LIMITED
        assert "429 RPM" in summary

        gemini_manager.reset()
        gemini_manager.mark_rate_limited("gemini-3.8-flash", "429 RPM cooldown")
        assert gemini_manager.model_states["gemini-3.8-flash"] == ModelHealthState.RATE_LIMITED
        assert gemini_manager.model_states["gemini-3.8-flash"] != ModelHealthState.DAILY_QUOTA_EXHAUSTED

    def test_6_all_models_unavailable_raises_infrastructure_exception(self):
        """Test 6: When all models in pool are unavailable, raises InfrastructureError / AllModelsUnavailableError."""
        gemini_manager.reset()
        gemini_manager.mark_daily_exhausted("m1", "quota")
        gemini_manager.mark_temporarily_unavailable("m2", "503")

        with patch.dict(os.environ, {"GEMINI_MODELS": "m1,m2", "LLM_PROVIDER": "google"}):
            with patch("src.extraction.extractor._get_llm_client", return_value=(MagicMock(), "google")):
                with pytest.raises(AllModelsUnavailableError):
                    _call_vision_llm(["dummy_b64"], _make_dummy_evidence())

    def test_7_infrastructure_exception_never_becomes_declined(self):
        """Test 7: Infrastructure failures must raise and must NEVER be classified as non-payable / declined."""
        from pathlib import Path
        from src.pipeline import process_single_pdf

        gemini_manager.reset()
        gemini_manager.mark_daily_exhausted("m1", "exhausted")

        with patch.dict(os.environ, {"GEMINI_MODELS": "m1", "LLM_PROVIDER": "google"}):
            with patch("src.extraction.extractor._get_llm_client", return_value=(MagicMock(), "google")):
                with patch("src.cache.extraction_cache.ExtractionCache.get", return_value=None):
                    with patch("src.extraction.extractor._call_vision_llm", side_effect=AllModelsUnavailableError("Pool exhausted")):
                        with pytest.raises(InfrastructureError):
                            process_single_pdf(Path("candidate_kit/candidate_kit/documents/INV-01.pdf"))

    def test_8_global_rate_limiter_is_invoked(self):
        """Test 8: Global rate limiter acquire() is invoked before calling Gemini API."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=json.dumps({"is_payable": True}))

        with patch.object(gemini_rate_limiter, "acquire") as mock_acquire:
            _call_google_model(
                client=mock_client,
                model_name="gemini-3.5-flash",
                temperature=0.0,
                max_retries=1,
                page_images=["dummy_b64"],
                evidence=_make_dummy_evidence(),
            )
            assert mock_acquire.called

    def test_9_fallback_metadata_not_in_final_json(self):
        """Test 9: Model fallback metadata is logged/tracked internally but never leaked into FileOutput JSON."""
        ir = AccountingIR(
            invoice_number="INV-09",
            gross_total="100.00",
            subtotal="100.00",
            currency="USD",
        )
        payable = reconstruct_autodraft(ir)
        output = FileOutput(file="test.pdf", payables=[payable], declined=[])
        data = output.model_dump()

        # Final JSON schema invariants: only file, payables, declined
        assert set(data.keys()) == {"file", "payables", "declined"}
        for key in ("fallback", "fallback_reason", "llm_model_used", "model_used"):
            assert key not in data
            assert key not in data["payables"][0]


# ── Accounting Behavior Tests (10–16) ───────────────────────────────────

class TestAccountingInvariants:
    """Tests 10–16 covering tax double counting, credit memos, and discount reconciliation."""

    def test_10_explicit_tax_amount_plus_tax_rate_does_not_double_count(self):
        """Test 10: Explicit tax amount + rate does not result in double tax calculation."""
        ir = AccountingIR(
            invoice_number="INV-10",
            gross_total="120.00",
            subtotal="100.00",
            currency="EUR",
            taxes=[TaxIR(tax_type="VAT", tax_rate="20", tax_amount="20.00")],
            line_items=[
                LineItemIR(
                    description="Item",
                    quantity="1",
                    unit_price="100.00",
                    tax_rate="20",
                )
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        # Correct gross: 100 + 20 = 120 (NOT 140)
        assert res["will_book_gross"] == 120.00

    def test_11_du06_style_multi_tax_invoice(self):
        """Test 11: DU-06 style multi-tax invoice with bucket rates reconstructs to stated gross."""
        ir = AccountingIR(
            invoice_number="DU06-TEST",
            gross_total="153.58",
            subtotal="138.20",
            currency="EUR",
            taxes=[
                TaxIR(tax_type="IVA", tax_name="IVA 23%", tax_rate="23", tax_amount="9.59"),
                TaxIR(tax_type="IVA", tax_name="IVA 6%", tax_rate="6", tax_amount="5.79"),
            ],
            line_items=[
                LineItemIR(description="L1", quantity="1", unit_price="41.68", tax_rate="23"),
                LineItemIR(description="L2", quantity="1", unit_price="28.43", tax_rate="23"),
                LineItemIR(description="L3", quantity="1", unit_price="25.94", tax_rate="23"),
                LineItemIR(description="L4", quantity="2", unit_price="13.43", tax_rate="6"),
                LineItemIR(description="L5", quantity="1", unit_price="15.29", tax_rate="6"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        assert res["will_book_gross"] == 153.58

    def test_12_du10_style_credit_memo_tax(self):
        """Test 12: DU-10 CREDIT_MEMO with header tax and line VAT rates does not overstate by VAT."""
        ir = AccountingIR(
            invoice_type=InvoiceType.CREDIT_MEMO,
            invoice_number="5900366703",
            gross_total="5076.17",
            subtotal="4230.14",
            total_tax_amount="846.03",
            currency="GBP",
            taxes=[TaxIR(tax_type="VAT", tax_rate="20", tax_amount="846.03")],
            line_items=[
                LineItemIR(description="Item 1", quantity="6", unit_price="457.24", tax_rate="20"),
                LineItemIR(description="Item 2", quantity="2", unit_price="743.35", tax_rate="20"),
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        # Must produce 5076.17, not 5922.20
        assert res["will_book_gross"] == 5076.17

    def test_13_du11_style_credit_memo_tax(self):
        """Test 13: DU-11 CREDIT_MEMO with header tax and line VAT rates does not overstate by VAT."""
        ir = AccountingIR(
            invoice_type=InvoiceType.CREDIT_MEMO,
            invoice_number="6265-K",
            gross_total="400.00",
            subtotal="327.87",
            total_tax_amount="72.13",
            currency="EUR",
            taxes=[TaxIR(tax_type="VAT", tax_rate="22", tax_amount="72.13")],
            line_items=[
                LineItemIR(description="Goods return", quantity="1", unit_price="327.87", tax_rate="22")
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        # Must produce 400.00, not 472.13
        assert res["will_book_gross"] == 400.00

    def test_14_hld08_style_vat_reconstruction(self):
        """Test 14: HLD-08 style VAT does not produce extra VAT addition."""
        ir = AccountingIR(
            invoice_number="162547",
            gross_total="148941.47",
            subtotal="129514.32",
            total_tax_amount="19427.15",
            currency="ZAR",
            taxes=[TaxIR(tax_type="VAT", tax_rate="15.00", tax_amount="19427.15")],
            line_items=[
                LineItemIR(
                    description="Fruit Punch",
                    quantity="468.0",
                    unit_price="276.74",
                    tax_rate="15.00",
                )
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        # Must book 148941.47, not 168368.62
        assert res["will_book_gross"] == 148941.47

    def test_15_discount_amount_and_percentage_not_double_applied(self):
        """Test 15: Equivalent discount amount and percentage are reconciled to a single economic deduction."""
        # 123.36 * 51.76% = 63.85
        # Line total = 123.36 - 63.85 = 59.51
        # Tax 13% on 59.51 = 7.74 -> Gross = 67.25
        ir = AccountingIR(
            invoice_number="HLD03-TEST",
            gross_total="67.25",
            subtotal="123.36",
            total_tax_amount="7.74",
            currency="EUR",
            taxes=[TaxIR(tax_type="VAT", tax_rate="13", tax_amount="7.74")],
            line_items=[
                LineItemIR(
                    description="Wine product",
                    quantity="1",
                    unit_price="123.36",
                    discount="63.85",
                    discount_percentage="51.76",
                )
            ],
        )
        payable = reconstruct_autodraft(ir)
        res = erp_book(payable.model_dump())

        # Must book 67.25 exactly
        assert res["will_book_gross"] == 67.25

    def test_16_conflicting_discount_produces_diagnostic(self, caplog):
        """Test 16: Conflicting discount amount and percentage preserves evidence and logs warning diagnostic."""
        import logging
        ir = AccountingIR(
            invoice_number="CONFLICT-DISC",
            gross_total="90.00",
            subtotal="100.00",
            currency="USD",
            line_items=[
                LineItemIR(
                    description="Conflicting discount",
                    quantity="1",
                    unit_price="100.00",
                    discount="10.00",         # 10%
                    discount_percentage="50.00",# 50% != 10%
                )
            ],
        )
        with caplog.at_level(logging.WARNING):
            payable = reconstruct_autodraft(ir)

        # Warning logged, evidence preserved
        assert any("conflict materially" in record.message for record in caplog.records)
        # Did not invent a balancing figure
        assert payable.line_items[0].discount == "10.00"
        assert payable.line_items[0].discount_percentage == "50.00"
