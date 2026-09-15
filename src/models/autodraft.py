"""Autodraft output models — final schema conforming to AUTODRAFT_SCHEMA.md.

These are the models that get serialised to JSON and fed to erp_book().
They carry NO internal state, NO evidence — just the clean output contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Tax ─────────────────────────────────────────

class AutodraftTax(BaseModel):
    """Tax entry in the final autodraft output."""
    tax_type: str = ""
    tax_name: str = ""
    tax_rate: str = ""
    tax_amount: str = ""
    tax_type_code: str = ""


# ── Line item ───────────────────────────────────

class AutodraftLineItem(BaseModel):
    """Line item in the final autodraft output."""
    description: str = ""
    item_type: str = "SERVICE"
    uom: str = ""
    quantity: str = ""
    unit_price: str = ""
    total: str = ""
    discount: str = ""
    discount_percentage: str = ""
    tax_rate: str = ""
    tax_amount: str = ""
    taxes: list[AutodraftTax] = Field(default_factory=list)


# ── Supplier ────────────────────────────────────

class AutodraftSupplier(BaseModel):
    name: str = ""
    supplier_id: str = ""
    address: str = ""
    vat_id: str = ""


# ── Buyer ───────────────────────────────────────

class AutodraftBuyer(BaseModel):
    company_code: str = ""
    business_unit_code: str = ""
    location_code: str = ""


# ── Payable ─────────────────────────────────────

class AutodraftPayable(BaseModel):
    """A single payable record conforming to AUTODRAFT_SCHEMA.md.

    This is the exact structure consumed by erp_book().
    """
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    invoice_type: str = "INVOICE"
    currency: str = ""

    supplier: AutodraftSupplier = Field(default_factory=AutodraftSupplier)
    buyer: AutodraftBuyer = Field(default_factory=AutodraftBuyer)

    payment_term_id: str = ""
    po_number: str = ""
    po_id: str = ""

    gross_total: str = ""
    subtotal: str = ""
    total_tax_amount: str = ""

    discount_amount: str = ""
    freight_charges: str = ""
    insurance_charges: str = ""
    extra_charges: str = ""
    excise_duties: str = ""

    taxes: list[AutodraftTax] = Field(default_factory=list)
    line_items: list[AutodraftLineItem] = Field(default_factory=list)


# ── Declined document ──────────────────────────

class DeclinedDocument(BaseModel):
    """A declined (non-payable or unsolvable) document entry."""
    doc_type: str = ""
    reason: str = ""


# ── File-level output ──────────────────────────

class FileOutput(BaseModel):
    """Complete output for a single PDF file.

    One JSON per input PDF:
    {
        "file": "X.pdf",
        "payables": [...],    ← 0..N AutodraftPayable
        "declined": [...]     ← 0..N DeclinedDocument
    }
    """
    file: str
    payables: list[AutodraftPayable] = Field(default_factory=list)
    declined: list[DeclinedDocument] = Field(default_factory=list)

