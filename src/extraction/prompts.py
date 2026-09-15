"""Versioned extraction prompts for the LLM semantic perception layer.

The prompt targets AccountingIR — never final ERP JSON or autodraft directly.
Rules enforce evidence grounding and strict refusal to invent numbers or codes.
"""

from __future__ import annotations

PROMPT_VERSION = "2026.09.1-v1"

EXTRACTION_SYSTEM_PROMPT = """You are an expert accounting perception system.
Your job is to read document images and extract raw accounting facts into an intermediate representation (AccountingIR).
CRITICAL CONSTRAINTS:
1. Grounding: Extract ONLY what is visibly printed on the document. NEVER invent, infer, or hallucinate numbers, codes, or supplier details.
2. Formats:
   - All numbers must be in dot-decimal format (e.g., 1234.56, not 1.234,56 or 1 234.56).
   - Dates must be in ISO format: YYYY-MM-DD.
   - Currency must be standard ISO code (e.g. EUR, USD, GBP) or standard symbol.
3. Accounting Semantics:
   - unit_price MUST be NET (tax-exclusive). If prices are tax-inclusive on the invoice, state the gross line amount in total.
   - Taxes: Preserve where they are placed. If taxes appear per line item, populate them in line_items[].line_taxes[]. If taxes appear as a summary at the invoice header, populate header_taxes[].
   - Credit Notes / Memos: If the document is a Credit Note/Gutschrift, set invoice_type to "CREDIT_MEMO" with positive numbers.
   - Non-payables: If the document is an estimate, pro forma, delivery note, packing slip, or statement of account, set is_payable to false and give non_payable_reason.
"""

EXTRACTION_USER_PROMPT = """Extract the structured accounting facts from this document. Return ONLY valid JSON matching this schema:

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
  ]
}
"""

TARGETED_RECHECK_PROMPT = """An accounting discrepancy was detected during deterministic ERP reconciliation:
- Discrepancy details: {discrepancy_details}
- Current extracted payable summary: {current_summary}

Please re-examine the document image focusing specifically on:
{suspect_regions}

Return the corrected JSON adhering strictly to the AccountingIR format without modifying fields that were already correct.
"""
