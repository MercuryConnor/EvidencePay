"""All enums used across the Bookable Payable system.

Centralised here so every module imports from one place.
"""

from __future__ import annotations
from enum import Enum


# ── Invoice / Document ──────────────────────────

class InvoiceType(str, Enum):
    INVOICE = "INVOICE"
    CREDIT_MEMO = "CREDIT_MEMO"


class ItemType(str, Enum):
    GOODS = "GOODS"
    SERVICE = "SERVICE"
    FREIGHT = "FREIGHT"
    TAX = "TAX"


class DocumentType(str, Enum):
    INVOICE = "invoice"
    CREDIT_MEMO = "credit_memo"
    FREIGHT_INVOICE = "freight_invoice"
    UTILITY_INVOICE = "utility_invoice"
    SERVICE_INVOICE = "service_invoice"
    ESTIMATE = "estimate"
    REMINDER = "reminder"
    DELIVERY_NOTE = "delivery_note"
    STATEMENT = "statement"
    INFORMATIONAL = "informational"
    NON_PAYABLE = "non_payable"
    UNKNOWN = "unknown"


# ── Page classification ─────────────────────────

class PageRole(str, Enum):
    INVOICE_HEADER = "invoice_header"
    INVOICE_LINES = "invoice_lines"
    TAX_SUMMARY = "tax_summary"
    CREDIT_NOTE = "credit_note"
    PAYMENT_REMITTANCE = "payment_remittance"
    STATEMENT_HISTORY = "statement_history"
    DELIVERY_SHIPPING = "delivery_shipping"
    CUSTOMS_SUPPORTING = "customs_supporting"
    ESTIMATE_QUOTE = "estimate_quote"
    REMINDER_DUNNING = "reminder_dunning"
    DUPLICATE_COPY = "duplicate_copy"
    NON_PAYABLE = "non_payable"
    UNKNOWN = "unknown"


# ── Extraction method ───────────────────────────

class ExtractionMethod(str, Enum):
    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    VISION_LLM = "vision_llm"
    COMPUTED = "computed"
    MANUAL = "manual"


# ── Pipeline state machine ──────────────────────

class AcceptanceState(str, Enum):
    UNKNOWN = "UNKNOWN"
    CANDIDATE = "CANDIDATE"
    RECONSTRUCT = "RECONSTRUCT"
    VALIDATE = "VALIDATE"
    ACCEPT = "ACCEPT"
    DECLINE = "DECLINE"
    TARGETED_RECHECK = "TARGETED_RECHECK"


# ── Validation diagnostics ──────────────────────

class DiagnosticCategory(str, Enum):
    TAX_PLACEMENT_MISMATCH = "TAX_PLACEMENT_MISMATCH"
    TAX_DOUBLE_COUNTING = "TAX_DOUBLE_COUNTING"
    LINE_DISCOUNT_MISMATCH = "LINE_DISCOUNT_MISMATCH"
    HEADER_DISCOUNT_MISMATCH = "HEADER_DISCOUNT_MISMATCH"
    DISCOUNT_DOUBLE_COUNTING = "DISCOUNT_DOUBLE_COUNTING"
    DISCOUNT_MISMATCH = "DISCOUNT_MISMATCH"
    CHARGE_PLACEMENT = "CHARGE_PLACEMENT"
    CHARGE_MISSING = "CHARGE_MISSING"
    CHARGE_DOUBLE_COUNTED = "CHARGE_DOUBLE_COUNTED"
    CURRENT_VS_HISTORICAL = "CURRENT_VS_HISTORICAL"
    CURRENT_VS_HISTORICAL_AMOUNT = "CURRENT_VS_HISTORICAL_AMOUNT"
    ROUNDING = "ROUNDING"
    ROUNDING_MISMATCH = "ROUNDING_MISMATCH"
    UNIT_PRICE = "UNIT_PRICE"
    COMPOUND_TAX = "COMPOUND_TAX"
    BUNDLE_HIERARCHY = "BUNDLE_HIERARCHY"
    OPERATIONAL_MEASUREMENT_VS_BILLABLE_AMOUNT = "OPERATIONAL_MEASUREMENT_VS_BILLABLE_AMOUNT"
    NON_LINEAR_BILLING_FORMULA = "NON_LINEAR_BILLING_FORMULA"
    LINE_STRUCTURE_MISMATCH = "LINE_STRUCTURE_MISMATCH"
    CREDIT_MEMO_SEMANTICS = "CREDIT_MEMO_SEMANTICS"
    MASTER_DATA_MISMATCH = "MASTER_DATA_MISMATCH"
    UNSUPPORTED_STRUCTURE = "UNSUPPORTED_STRUCTURE"
    OTHER = "OTHER"


# ── Master-data match confidence ────────────────

class MatchMethod(str, Enum):
    VAT_ID_EXACT = "VAT_ID_EXACT"
    IBAN_EXACT = "IBAN_EXACT"
    NAME_EXACT = "NAME_EXACT"
    NAME_FUZZY = "NAME_FUZZY"
    ADDRESS_FUZZY = "ADDRESS_FUZZY"
    IDENTIFIER_EXACT = "IDENTIFIER_EXACT"
    DATE_DIFF = "DATE_DIFF"
    TEXT_ALIAS = "TEXT_ALIAS"
    RATE_COUNTRY = "RATE_COUNTRY"
    NO_MATCH = "NO_MATCH"


class MatchConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AMBIGUOUS = "AMBIGUOUS"
    NONE = "NONE"
