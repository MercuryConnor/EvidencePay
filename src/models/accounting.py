"""Accounting IR — intermediate representation between extraction and autodraft.

The LLM produces AccountingIR.
Deterministic reconstruction converts AccountingIR -> AutodraftPayable.
The LLM must NEVER produce final autodraft JSON directly.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import (
    AcceptanceState,
    DocumentType,
    InvoiceType,
)
from src.models.evidence import EvidenceValue


# ── Tax entry ───────────────────────────────────

class TaxIR(BaseModel):
    """Tax entry in the accounting intermediate representation."""
    tax_type: str = ""              # VAT, IVA, SST, GST, WHT, etc.
    tax_name: str = ""              # human-readable name from document
    tax_rate: str = ""              # dot-decimal rate (e.g. "19", "7.5")
    tax_amount: str = ""            # dot-decimal amount
    tax_type_code: str = ""         # resolved from master data
    is_line_level: bool = False     # placed on a specific line
    is_withholding: bool = False    # negative tax (reduces gross)
    evidence: Optional[EvidenceValue] = None


# ── Line item ───────────────────────────────────

class LineItemIR(BaseModel):
    """Line item in the accounting IR."""
    description: str = ""
    item_type: str = "SERVICE"      # GOODS | SERVICE | FREIGHT | TAX
    uom: str = ""                   # unit of measure
    quantity: str = ""              # dot-decimal
    unit_price: str = ""            # NET (tax-exclusive), dot-decimal
    total: str = ""                 # line extension as printed on document
    discount: str = ""              # discount amount (dot-decimal)
    discount_percentage: str = ""   # discount percentage (dot-decimal)
    tax_rate: str = ""              # per-line shorthand rate
    tax_amount: str = ""            # per-line shorthand amount
    taxes: list[TaxIR] = Field(default_factory=list)
    evidence: Optional[EvidenceValue] = None


# ── Supplier identity ──────────────────────────

class SupplierIR(BaseModel):
    """Supplier identity extracted from the document."""
    name: str = ""
    supplier_id: str = ""           # resolved from master data
    address: str = ""
    vat_id: str = ""
    iban: str = ""                  # for corroborating match
    evidence: Optional[EvidenceValue] = None


# ── Buyer / org identity ────────────────────────

class BuyerIR(BaseModel):
    """Buyer/organisation identity extracted from the document."""
    company_code: str = ""          # resolved from chart_of_books
    business_unit_code: str = ""
    location_code: str = ""
    raw_name: str = ""              # as printed on document
    raw_address: str = ""
    country: str = ""               # inferred from address/VAT
    evidence: Optional[EvidenceValue] = None


# ── Full Accounting IR ──────────────────────────

class AccountingIR(BaseModel):
    """Complete accounting intermediate representation for one payable candidate.

    Produced by: LLM extraction → normalisation → master resolution
    Consumed by: deterministic reconstruction → AutodraftPayable
    """
    # Identity
    document_type: DocumentType = DocumentType.UNKNOWN
    invoice_type: InvoiceType = InvoiceType.INVOICE
    invoice_number: str = ""
    invoice_date: str = ""          # YYYY-MM-DD
    due_date: str = ""              # YYYY-MM-DD
    currency: str = ""

    # Parties
    supplier: SupplierIR = Field(default_factory=SupplierIR)
    buyer: BuyerIR = Field(default_factory=BuyerIR)

    # References
    payment_terms_text: str = ""    # raw text from document
    payment_term_id: str = ""       # resolved from master data
    po_number: str = ""
    po_id: str = ""                 # resolved from master data

    # Totals (as printed on document — NOT computed)
    gross_total: str = ""
    subtotal: str = ""
    total_tax_amount: str = ""

    # Header-level charges & discounts
    discount_amount: str = ""
    freight_charges: str = ""
    insurance_charges: str = ""
    extra_charges: str = ""
    excise_duties: str = ""

    # Header-level taxes
    taxes: list[TaxIR] = Field(default_factory=list)

    # Line items
    line_items: list[LineItemIR] = Field(default_factory=list)

    # Pages this payable spans
    source_pages: list[int] = Field(default_factory=list)

    # State machine
    state: AcceptanceState = AcceptanceState.UNKNOWN
    pass_count: int = 0
    decline_reason: str = ""
    diagnostics: list[str] = Field(default_factory=list)

    # LLM notes (free-form observations from extraction)
    extraction_notes: str = ""
