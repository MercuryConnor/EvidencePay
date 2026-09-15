"""LLM-based semantic extraction — extracts structured data from document images.

Uses a vision-capable LLM (GPT-4o / Gemini) to interpret page images and
produce structured accounting candidates. The LLM extracts what it sees;
the accounting layer validates and reconstructs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


from src.models import (
    AccountingIR,
    DocumentType,
    EvidencePacket,
    InvoiceType,
    LineItemIR,
    SupplierIR,
    BuyerIR,
    TaxIR,
)

logger = logging.getLogger(__name__)

from src.extraction.model_manager import (
    AllModelsUnavailableError,
    DailyQuotaExhaustedError,
    GeminiModelManager,
    InfrastructureError,
    InvalidModelError,
    ModelErrorKind,
    ModelHealthState,
    RateLimitExceededError,
    TemporaryModelUnavailableError,
    classify_gemini_error,
    gemini_manager,
    is_daily_quota_exhausted,
)
from src.extraction.rate_limiter import gemini_rate_limiter

# Exposed for backwards compatibility and external inspection
MODEL_POOL = gemini_manager.get_configured_models()
exhausted_models = gemini_manager.exhausted_models


def _get_llm_client():
    """Get the configured LLM client."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise InfrastructureError("OPENAI_API_KEY is not set.")
        return OpenAI(api_key=api_key), provider
    elif provider in ("google", "gemini"):
        from google import genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise InfrastructureError("GOOGLE_API_KEY is not set.")
        client = genai.Client(api_key=api_key)
        return client, provider
    elif provider in ("mock", "test"):
        from src.extraction.llm import MockExtractor
        return MockExtractor(), "mock"
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")



# The extraction prompt — instructs the LLM to extract ONLY what it sees
EXTRACTION_PROMPT = """You are a document analysis system. Your task is to extract structured data from this document image for an accounting system.

CRITICAL RULES:
1. Extract ONLY values that are VISIBLE on the document. Never invent, calculate, or infer values.
2. All numbers must be in dot-decimal format (e.g., 1234.56, not 1.234,56).
3. Dates must be in YYYY-MM-DD format.
4. unit_price must be NET (tax-exclusive). If prices appear tax-inclusive, note this.
5. Place taxes where the document places them — if a tax appears per line, put it on the line; if once at the header, put it at the header level.
6. For credit memos/credit notes, set invoice_type to "CREDIT_MEMO" and use positive magnitudes.
7. If this is NOT a payable (e.g., delivery note, estimate, reminder, statement), set is_payable to false and explain why.

Respond with a JSON object matching this exact structure:

```json
{
  "is_payable": true,
  "document_type": "invoice",
  "non_payable_reason": "",

  "invoice_number": "",
  "invoice_date": "",
  "due_date": "",
  "invoice_type": "INVOICE",
  "currency": "",

  "supplier_name": "",
  "supplier_address": "",
  "supplier_vat_id": "",
  "supplier_iban": "",

  "buyer_name": "",
  "buyer_address": "",

  "payment_terms_text": "",
  "po_number": "",

  "gross_total": "",
  "subtotal": "",
  "total_tax_amount": "",

  "discount_amount": "",
  "freight_charges": "",
  "insurance_charges": "",
  "extra_charges": "",
  "excise_duties": "",

  "header_taxes": [
    {
      "tax_type": "",
      "tax_name": "",
      "tax_rate": "",
      "tax_amount": ""
    }
  ],

  "line_items": [
    {
      "description": "",
      "item_type": "SERVICE",
      "uom": "",
      "quantity": "",
      "unit_price": "",
      "total": "",
      "discount": "",
      "discount_percentage": "",
      "line_taxes": [
        {
          "tax_type": "",
          "tax_name": "",
          "tax_rate": "",
          "tax_amount": ""
        }
      ]
    }
  ],

  "notes": ""
}
```

Important:
- "item_type" is one of: GOODS, SERVICE, FREIGHT, TAX
- "invoice_type" is one of: INVOICE, CREDIT_MEMO
- Leave fields as empty strings "" if not visible on the document
- Do NOT calculate missing values — if you can't see it, leave it empty
- Convert all numbers from the document's locale format to dot-decimal (e.g., "1.234,56" → "1234.56")
- If the document is in a non-English language, still extract the values and translate field labels

Analyze the document image and extract the data:"""


def extract_payables_with_declined(
    evidence: EvidencePacket,
    classification_result=None,
    prompt: Optional[str] = None,
    pass_type: str = "initial",
    focus: str = "",
) -> tuple[list[AccountingIR], list]:
    """Extract payable candidates and/or declined entries from a document using vision LLM.

    Returns (candidates, declined_entries).
    """
    from src.ingestion.pdf import render_all_pages_to_base64
    from src.models.autodraft import DeclinedDocument

    pdf_path = _resolve_pdf_path(evidence.filename)
    if not pdf_path:
        logger.error("Cannot find PDF: %s", evidence.filename)
        return [], []

    # Check cache first with pass_type and focus context
    from src.cache.extraction_cache import ExtractionCache
    cache = ExtractionCache()
    cached = cache.get(pdf_path, pass_type=pass_type, focus=focus)
    if cached:
        logger.info("Using cached extraction for %s [%s]", evidence.filename, pass_type)
        return _parse_llm_response(cached, evidence)

    # Render all pages to images
    page_images = render_all_pages_to_base64(pdf_path)

    # Call LLM with all page images
    try:
        raw_result, model_used = _call_vision_llm(page_images, evidence, prompt=prompt)
    except InfrastructureError:
        # Re-raise infrastructure failures immediately — do not swallow and mask as empty extraction!
        raise
    except Exception as e:
        logger.error("LLM extraction failed for %s: %s", evidence.filename, e)
        return [], []

    if raw_result is None:
        return [], []

    # Store in cache with pass_type and focus context
    cache.put(pdf_path, raw_result, pass_type=pass_type, focus=focus)

    # Parse LLM response into AccountingIR
    return _parse_llm_response(raw_result, evidence)


def extract_payables(
    evidence: EvidencePacket,
    classification_result=None,
    prompt: Optional[str] = None,
    pass_type: str = "initial",
    focus: str = "",
) -> list[AccountingIR]:
    """Extract payable candidates from a document using vision LLM."""
    candidates, _ = extract_payables_with_declined(
        evidence,
        classification_result,
        prompt=prompt,
        pass_type=pass_type,
        focus=focus,
    )
    return candidates


def _resolve_pdf_path(filename: str) -> Optional[Path]:
    """Find the PDF file in the documents directory."""
    candidates = [
        Path("candidate_kit/candidate_kit/documents") / filename,
        Path("documents") / filename,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _call_vision_llm(
    page_images: list[str],
    evidence: EvidencePacket,
    prompt: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """Call the vision LLM with page images using provider-specific model fallback.

    Returns a tuple of (parsed JSON response, model_name_used) or (None, None) on failure.
    """
    client, provider = _get_llm_client()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

    if provider == "mock":
        # Mock extractor does not depend on model name
        return json.loads(client.extract(evidence)), "mock"

    if provider == "openai":
        # OpenAI uses its own configured model (does NOT use Gemini pool)
        openai_model = os.getenv("LLM_MODEL", "gpt-4o")
        result = _call_openai(client, openai_model, temperature, max_retries, page_images, evidence, prompt=prompt)
        return result, openai_model


    if provider in ("google", "gemini"):
        # Initialize runtime discovery if not yet done
        if gemini_manager._discovered_pool is None:
            gemini_manager.initialize_discovery(client)

        all_models = gemini_manager.get_all_ordered_models()
        available_models = [m for m in all_models if gemini_manager.is_available(m)[0]]
        if not available_models and gemini_manager.temporarily_unavailable_models:
            logger.info(
                "All remaining models were temporarily quarantined (%s). Re-enabling for retry.",
                gemini_manager.temporarily_unavailable_models,
            )
            for m in list(gemini_manager.temporarily_unavailable_models):
                gemini_manager.model_states[m] = ModelHealthState.HEALTHY
            available_models = [m for m in all_models if gemini_manager.is_available(m)[0]]

        if not available_models:
            logger.error("All Gemini models in pool are unavailable or exhausted.")
            raise AllModelsUnavailableError(
                f"All Gemini models in pool ({all_models}) are unavailable or exhausted."
            )

        for i, model_name in enumerate(all_models):
            is_avail, reason = gemini_manager.get_model_status(model_name)
            if not is_avail:
                if "temporarily unavailable" in reason.lower() or "503" in reason:
                    logger.info("%s temporarily unavailable; skipping", model_name)
                elif "daily quota" in reason.lower():
                    logger.info("%s daily quota exhausted; skipping", model_name)
                elif "invalid" in reason.lower() or "404" in reason:
                    logger.info("%s invalid model; skipping", model_name)
                else:
                    logger.info("%s %s; skipping", model_name, reason)
                continue

            logger.info("Attempting extraction with Gemini model: %s", model_name)
            remaining_available = [
                m for m in all_models[i + 1:] if gemini_manager.is_available(m)[0]
            ]
            next_model = remaining_available[0] if remaining_available else None

            try:
                result = _call_google_model(
                    client, model_name, temperature, max_retries, page_images, evidence, prompt=prompt
                )
                if result is not None:
                    logger.info("Extraction successful with %s", model_name)
                    gemini_manager.record_success(model_name)
                    return result, model_name

            except InvalidModelError as e:
                gemini_manager.mark_invalid(model_name, str(e))
                logger.warning("%s is invalid (404 NOT_FOUND); immediately falling over", model_name)
                if next_model:
                    logger.info("Failing over to %s", next_model)
                continue

            except DailyQuotaExhaustedError as e:
                gemini_manager.mark_daily_exhausted(model_name, str(e))
                logger.warning("%s daily quota exhausted", model_name)
                if next_model:
                    logger.info("Failing over to %s", next_model)
                continue

            except RateLimitExceededError as e:
                gemini_manager.mark_rate_limited(model_name, str(e))
                logger.warning("%s rate limit exceeded", model_name)
                if next_model:
                    logger.info("Failing over to %s", next_model)
                continue

            except TemporaryModelUnavailableError as e:
                gemini_manager.mark_temporarily_unavailable(model_name, str(e))
                logger.warning("%s temporarily unavailable", model_name)
                if next_model:
                    logger.info("Failing over to %s", next_model)
                continue

            except Exception as e:
                error_kind, summary = classify_gemini_error(e)
                if error_kind == ModelErrorKind.INVALID_MODEL:
                    gemini_manager.mark_invalid(model_name, summary)
                elif error_kind == ModelErrorKind.DAILY_QUOTA_EXHAUSTED:
                    gemini_manager.mark_daily_exhausted(model_name, summary)
                elif error_kind == ModelErrorKind.RATE_LIMITED:
                    gemini_manager.mark_rate_limited(model_name, summary)
                else:
                    gemini_manager.mark_temporarily_unavailable(model_name, summary)

                logger.warning("%s %s", model_name, summary)
                if next_model:
                    logger.info("Failing over to %s", next_model)
                continue

        # Level 5 — All models unavailable
        logger.error("All Gemini models in pool are unavailable or exhausted.")
        raise AllModelsUnavailableError(
            f"All Gemini models in pool ({all_models}) are unavailable or exhausted."
        )

    raise ValueError(f"Unsupported provider: {provider}")


def _call_openai(client, model, temperature, max_retries, page_images, evidence, prompt: Optional[str] = None) -> Optional[dict]:
    """Call OpenAI Vision API."""
    # Build message content with images
    content = [{"type": "text", "text": prompt or EXTRACTION_PROMPT}]

    for i, img_b64 in enumerate(page_images):
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_b64}",
                "detail": "high",
            },
        })

    # Add native text as supplementary evidence
    native_text_parts = []
    for page in evidence.pages:
        if page.has_native_text and page.native_text:
            native_text_parts.append(f"--- Page {page.page_number} native text ---\n{page.native_text}")

    if native_text_parts:
        content.append({
            "type": "text",
            "text": "\n\nSupplementary native PDF text (use to verify/supplement visual extraction):\n\n" + "\n\n".join(native_text_parts),
        })

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=temperature,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            response_text = response.choices[0].message.content
            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.warning("LLM returned invalid JSON (attempt %d): %s", attempt + 1, e)
            if attempt == max_retries - 1:
                # Try to extract JSON from the response
                return _try_extract_json(response_text)
        except Exception as e:
            logger.warning("LLM call failed (attempt %d): %s", attempt + 1, e)
            if attempt == max_retries - 1:
                raise

    return None


def _call_google_model(
    client,
    model_name: str,
    temperature: float,
    max_retries: int,
    page_images: list[str],
    evidence: EvidencePacket,
    prompt: Optional[str] = None,
) -> Optional[dict]:
    """Call Google Gemini Vision API with a specific model name.

    Immediately aborts retries and raises InvalidModelError on 404 or DailyQuotaExhaustedError on daily quota.
    Enforces the global Gemini rate limiter before every call.
    Transient errors and rate limits are retried with backoff.
    """
    import base64
    import time
    from google.genai import types

    target_model = model_name
    effective_retries = int(os.getenv("GEMINI_MAX_RETRIES", str(max_retries)))

    # Build contents with image parts
    contents = [prompt or EXTRACTION_PROMPT]

    for img_b64 in page_images:
        img_bytes = base64.b64decode(img_b64)
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

    # Add native text if available
    native_text_parts = []
    for page in evidence.pages:
        if page.has_native_text and page.native_text:
            native_text_parts.append(f"--- Page {page.page_number} ---\n{page.native_text}")

    if native_text_parts:
        contents.append("\n\nSupplementary native PDF text:\n\n" + "\n\n".join(native_text_parts))

    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for attempt in range(effective_retries):
        # Enforce global rate limit interval
        gemini_rate_limiter.acquire()

        try:
            response = client.models.generate_content(
                model=target_model,
                contents=contents,
                config=config,
            )
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.warning("%s returned invalid JSON (attempt %d/%d): %s", target_model, attempt + 1, effective_retries, e)
            if attempt == effective_retries - 1:
                return _try_extract_json(getattr(response, "text", ""))
        except Exception as e:
            error_kind, err_summary = classify_gemini_error(e)

            # 1. 404 INVALID MODEL -> zero retries, immediate failover!
            if error_kind == ModelErrorKind.INVALID_MODEL:
                logger.warning("%s returned 404 NOT_FOUND. Aborting retries immediately.", target_model)
                raise InvalidModelError(target_model, err_summary) from e

            # 2. DAILY QUOTA EXHAUSTED -> zero retries, immediate failover!
            if error_kind == ModelErrorKind.DAILY_QUOTA_EXHAUSTED:
                logger.warning("%s daily quota exhausted. Aborting retries immediately.", target_model)
                raise DailyQuotaExhaustedError(target_model, err_summary) from e

            # 3. RATE LIMITED (429 RPM) -> retry with backoff up to effective_retries
            if error_kind == ModelErrorKind.RATE_LIMITED:
                logger.warning("%s rate limited (attempt %d/%d)", target_model, attempt + 1, effective_retries)
                if attempt == effective_retries - 1:
                    raise RateLimitExceededError(target_model, err_summary) from e
                time.sleep(2.5 * (attempt + 1))
                continue

            # 4. TEMPORARILY UNAVAILABLE (503) or TRANSIENT -> retry with backoff
            if error_kind in (ModelErrorKind.TEMPORARILY_UNAVAILABLE, ModelErrorKind.TRANSIENT_ERROR):
                logger.warning("%s %s (attempt %d/%d)", target_model, err_summary, attempt + 1, effective_retries)
                if attempt == effective_retries - 1:
                    raise TemporaryModelUnavailableError(target_model, err_summary) from e
                time.sleep(2.0 * (attempt + 1))
                continue

            # 5. PERMANENT ERROR
            logger.error("%s encountered permanent error: %s", target_model, err_summary)
            raise InfrastructureError(f"Permanent error for {target_model}: {err_summary}") from e

    return None




def _try_extract_json(text: str) -> Optional[dict]:
    """Try to extract JSON from a text that may contain markdown code blocks."""
    if not text:
        return None

    # Try to find JSON in markdown code block
    import re
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try the raw text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_llm_response(data: dict, evidence: EvidencePacket) -> tuple[list[AccountingIR], list]:
    """Parse LLM JSON response into AccountingIR objects and any declined entries."""
    from src.models.autodraft import DeclinedDocument

    candidates = []
    declined = []

    # Check if document is payable
    if not data.get("is_payable", True):
        reason = data.get("non_payable_reason", f"Document classified as non-payable: {data.get('document_type', 'unknown')}")
        doc_type = data.get("document_type", "unknown")
        logger.info("LLM classified as non-payable: %s", reason)
        declined.append(DeclinedDocument(doc_type=doc_type, reason=reason))
        return [], declined

    # Determine invoice type
    inv_type_str = data.get("invoice_type", "INVOICE").upper()
    inv_type = InvoiceType.CREDIT_MEMO if inv_type_str == "CREDIT_MEMO" else InvoiceType.INVOICE

    gross_val = data.get("gross_total") or data.get("total_amount") or data.get("total") or ""
    subtotal_val = data.get("subtotal") or data.get("subtotal_amount") or ""
    tax_val = data.get("total_tax_amount") or data.get("tax_amount") or data.get("tax_total") or ""
    disc_val = data.get("discount_amount") or data.get("header_discount") or ""
    extra_val = data.get("extra_charges") or data.get("other_charges") or ""

    supplier_dict = data.get("supplier") if isinstance(data.get("supplier"), dict) else {}
    buyer_dict = data.get("customer") if isinstance(data.get("customer"), dict) else {}

    # Build AccountingIR
    ir = AccountingIR(
        document_type=_map_doc_type(data.get("document_type", "invoice")),
        invoice_type=inv_type,
        invoice_number=str(data.get("invoice_number", "") or data.get("invoice_no", "") or ""),
        invoice_date=str(data.get("invoice_date", "")),
        due_date=str(data.get("due_date", "")),
        currency=str(data.get("currency", "")),

        supplier=SupplierIR(
            name=str(data.get("supplier_name", "") or supplier_dict.get("name", "")),
            address=str(data.get("supplier_address", "") or supplier_dict.get("address", "")),
            vat_id=str(data.get("supplier_vat_id", "") or supplier_dict.get("vat_number", "") or supplier_dict.get("tax_id", "")),
        ),

        buyer=BuyerIR(
            raw_name=str(data.get("buyer_name", "") or data.get("customer_name", "") or buyer_dict.get("name", "")),
            raw_address=str(data.get("buyer_address", "") or buyer_dict.get("address", "")),
        ),

        po_number=str(data.get("po_number", "")),

        gross_total=str(gross_val),
        subtotal=str(subtotal_val),
        total_tax_amount=str(tax_val),

        discount_amount=str(disc_val),
        freight_charges=str(data.get("freight_charges", "")),
        insurance_charges=str(data.get("insurance_charges", "")),
        extra_charges=str(extra_val),
        excise_duties=str(data.get("excise_duties", "")),

        source_pages=list(range(1, evidence.total_pages + 1)),
    )

    # Header taxes
    header_taxes_raw = data.get("header_taxes")
    if header_taxes_raw is None:
        header_taxes_raw = data.get("taxes")
    if isinstance(header_taxes_raw, list):
        for t in header_taxes_raw:
            if isinstance(t, dict):
                ir.taxes.append(TaxIR(
                    tax_type=str(t.get("tax_type", "")),
                    tax_name=str(t.get("tax_name", "")),
                    tax_rate=str(t.get("tax_rate", "")),
                    tax_amount=str(t.get("tax_amount", "")),
                    is_line_level=False,
                ))

    # Line items
    for li in data.get("line_items", []):
        if not isinstance(li, dict):
            continue

        line_tot = str(li.get("total") or li.get("net_amount") or li.get("line_base") or li.get("line_total") or li.get("gross_amount") or "")
        line_tax_rate = str(li.get("tax_rate", "") or "")
        line_tax_amt = str(li.get("tax_amount", "") or "")

        line = LineItemIR(
            description=str(li.get("description", "")),
            item_type=str(li.get("item_type", "SERVICE")),
            uom=str(li.get("uom", "")),
            quantity=str(li.get("quantity", "")),
            unit_price=str(li.get("unit_price", "")),
            total=line_tot,
            discount=str(li.get("discount", "")),
            discount_percentage=str(li.get("discount_percentage", "")),
            tax_rate=line_tax_rate,
            tax_amount=line_tax_amt,
        )

        # Line-level taxes
        line_taxes_raw = li.get("line_taxes") or li.get("taxes")
        if isinstance(line_taxes_raw, list):
            for t in line_taxes_raw:
                if isinstance(t, dict):
                    line.taxes.append(TaxIR(
                        tax_type=str(t.get("tax_type", "")),
                        tax_name=str(t.get("tax_name", "")),
                        tax_rate=str(t.get("tax_rate", "")),
                        tax_amount=str(t.get("tax_amount", "")),
                        is_line_level=True,
                    ))
        elif line_tax_rate or line_tax_amt:
            line.taxes.append(TaxIR(
                tax_type="TAX",
                tax_name="",
                tax_rate=line_tax_rate,
                tax_amount=line_tax_amt,
                is_line_level=True,
            ))

        ir.line_items.append(line)

    candidates.append(ir)
    logger.info(
        "Extracted payable: %s, %s %s, %d lines, %d header taxes",
        ir.invoice_number, ir.currency, ir.gross_total,
        len(ir.line_items), len(ir.taxes),
    )

    return candidates, declined


def _map_doc_type(doc_type_str: str) -> DocumentType:
    """Map a string document type to the DocumentType enum."""
    mapping = {
        "invoice": DocumentType.INVOICE,
        "credit_memo": DocumentType.CREDIT_MEMO,
        "credit_note": DocumentType.CREDIT_MEMO,
        "freight_invoice": DocumentType.FREIGHT_INVOICE,
        "utility_invoice": DocumentType.UTILITY_INVOICE,
        "service_invoice": DocumentType.SERVICE_INVOICE,
        "estimate": DocumentType.ESTIMATE,
        "reminder": DocumentType.REMINDER,
        "delivery_note": DocumentType.DELIVERY_NOTE,
        "statement": DocumentType.STATEMENT,
    }
    return mapping.get(doc_type_str.lower(), DocumentType.UNKNOWN)
