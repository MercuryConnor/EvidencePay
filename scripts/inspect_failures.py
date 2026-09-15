"""Inspect all 9 payable reconstruction failures in detail.

Collects:
* filename
* invoice number
* document type
* currency
* stated gross
* ERP/booked gross
* delta
* subtotal
* header taxes
* line taxes
* discounts
* freight
* insurance
* extra charges
* excise
* number of line items
* each line's quantity, unit price, line total, discount, tax rate, tax amount
* current diagnostic category
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.pdf import ingest_pdf
from src.classification.document import classify_document
from src.extraction.extractor import extract_payables_with_declined
from src.normalization.numbers import normalize_accounting_ir, parse_decimal
from src.master_data.resolver import resolve_master_data
from src.accounting.reconstruction import reconstruct_autodraft
from src.erp_validator import validate_payable
from candidate_kit.candidate_kit.erp import erp_book

FAILED_FILES = [
    "HLD-05.pdf",
    "HLD-10.pdf",
    "INV-02.pdf",
    "INV-06.pdf",
    "INV-11.pdf",
    "INV-16.pdf",
    "INV-21.pdf",
    "INV-31.pdf",
    "INV-37.pdf",
]

DOCS_DIR = Path("candidate_kit/candidate_kit/documents")

def main():
    out_file = Path("scratch/failure_analysis.txt")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as out:
        def log(msg=""):
            out.write(str(msg) + "\n")

        log("=" * 100)
        log("DETAILED FAILURE ANALYSIS FOR 9 RECONSTRUCTION FAILURES")
        log("=" * 100)

        for fname in FAILED_FILES:
            pdf_path = DOCS_DIR / fname
            if not pdf_path.exists():
                log(f"File not found: {pdf_path}")
                continue

            log(f"\n{'#' * 80}")
            log(f"FILE: {fname}")
            log(f"{'#' * 80}")

            ev = ingest_pdf(pdf_path)
            cls = classify_document(ev)
            candidates, declined = extract_payables_with_declined(ev, cls)

            if not candidates:
                log(f"No candidates extracted! Declined: {declined}")
                continue

            for idx, ir in enumerate(candidates):
                log(f"\n--- Candidate {idx + 1} (Raw / Pre-normalization) ---")
                log(f"Invoice Number : {ir.invoice_number}")
                log(f"Document Type  : {ir.document_type}")
                log(f"Currency       : {ir.currency}")
                log(f"Stated Gross   : {ir.gross_total}")
                log(f"Subtotal       : {ir.subtotal}")
                log(f"Total Tax Amt  : {ir.total_tax_amount}")
                log(f"Discount Amt   : {ir.discount_amount}")
                log(f"Freight Charges: {ir.freight_charges}")
                log(f"Insurance      : {ir.insurance_charges}")
                log(f"Extra Charges  : {ir.extra_charges}")
                log(f"Excise Duties  : {ir.excise_duties}")
                log(f"Header Taxes   : {[t.model_dump() for t in ir.taxes]}")
                log(f"Number of Lines: {len(ir.line_items)}")

                # Normalize & master data
                norm_ir = normalize_accounting_ir(ir)
                res_ir, _ = resolve_master_data(norm_ir)

                # Reconstruct
                autodraft = reconstruct_autodraft(res_ir)

                # ERP Validation
                erp_res = validate_payable(autodraft)
                dict_for_erp = json.loads(autodraft.model_dump_json())
                booked_raw = erp_book(dict_for_erp)

                log(f"\n--- Post-Reconstruction & ERP Book ---")
                log(f"Reconstructed Stated Gross : {autodraft.gross_total}")
                log(f"Reconstructed Subtotal     : {autodraft.subtotal}")
                log(f"Reconstructed Discount     : {autodraft.discount_amount}")
                log(f"Reconstructed Freight      : {autodraft.freight_charges}")
                log(f"Reconstructed Extra Charges: {autodraft.extra_charges}")
                log(f"Reconstructed Taxes (Header): {[t.model_dump() for t in autodraft.taxes]}")
                log(f"ERP Booked Gross           : {erp_res.will_book_gross:.2f}")
                log(f"Delta (Booked - Stated)    : {erp_res.delta:+.2f}")
                log(f"Matches?                   : {erp_res.matches}")

                log(f"\n--- Lines Detail ({len(autodraft.line_items)} lines) ---")
                for l_idx, li in enumerate(autodraft.line_items):
                    log(f"  Line {l_idx + 1}: desc={li.description[:40]!r} | qty={li.quantity} | price={li.unit_price} | total={li.total} | disc={li.discount} (pct={li.discount_percentage}) | tax_rate={li.tax_rate} | tax_amt={li.tax_amount} | taxes={[t.model_dump() for t in li.taxes]}")

                # Calculate components
                line_bases = sum(
                    max(0.0, float(parse_decimal(li.quantity or "1")) * float(parse_decimal(li.unit_price or "0")) - float(parse_decimal(li.discount or "0")))
                    for li in autodraft.line_items
                )
                line_discs = sum(float(parse_decimal(li.discount or "0")) for li in autodraft.line_items)
                hdr_disc = float(parse_decimal(autodraft.discount_amount or "0"))
                hdr_taxes = sum(float(parse_decimal(t.tax_amount or "0")) for t in autodraft.taxes)
                line_taxes = sum(
                    sum(float(parse_decimal(t.tax_amount or "0")) for t in li.taxes) + (float(parse_decimal(li.tax_amount or "0")) if not li.taxes else 0.0)
                    for li in autodraft.line_items
                )
                freight = float(parse_decimal(autodraft.freight_charges or "0"))
                insurance = float(parse_decimal(autodraft.insurance_charges or "0"))
                extra = float(parse_decimal(autodraft.extra_charges or "0"))
                excise = float(parse_decimal(autodraft.excise_duties or "0"))

                log(f"\n--- Independent Components Reconstructed ---")
                log(f"  A. Sum of line bases: {line_bases:.2f}")
                log(f"  B. Line discounts   : {line_discs:.2f}")
                log(f"  C. Header discounts : {hdr_disc:.2f}")
                log(f"  D. Header taxes     : {hdr_taxes:.2f}")
                log(f"     Line taxes       : {line_taxes:.2f}")
                log(f"  E. Freight          : {freight:.2f}")
                log(f"  F. Insurance        : {insurance:.2f}")
                log(f"  G. Extra charges    : {extra:.2f}")
                log(f"  H. Excise           : {excise:.2f}")
                reconstructed_gross = line_bases - hdr_disc + hdr_taxes + line_taxes + freight + insurance + extra + excise
                log(f"  I. Reconstructed Gross: {reconstructed_gross:.2f}")
                log(f"  J. ERP Booked Gross   : {erp_res.will_book_gross:.2f}")
                log(f"  K. Document Stated Gross: {float(parse_decimal(ir.gross_total)):.2f}")

    print("Finished writing to scratch/failure_analysis.txt")

if __name__ == "__main__":
    main()
