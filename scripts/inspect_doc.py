"""Diagnostic inspector — inspect evidence, classification, and master-data matching for a single PDF.

Usage:
    python scripts/inspect_doc.py candidate_kit/candidate_kit/documents/INV-01.pdf
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "candidate_kit" / "candidate_kit"))

from src.classification.document import classify_document
from src.classification.page import classify_pages_in_packet
from src.ingestion.pdf import ingest_pdf
from src.master_data.loader import ensure_loaded


def inspect_pdf(pdf_path: Path) -> None:
    """Inspect a PDF document and print detailed diagnostic facts."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        return

    print("=" * 70)
    print(f"  DOCUMENT INSPECTOR: {pdf_path.name}")
    print("=" * 70)

    # 1. Ingestion
    packet = ingest_pdf(pdf_path)
    classify_pages_in_packet(packet.pages)

    print(f"\n[1] Ingestion Summary:")
    print(f"  Total Pages: {packet.total_pages}")
    for p in packet.pages:
        txt_preview = (p.native_text[:60].replace("\n", " ") + "...") if p.native_text else "<No text>"
        print(f"  Page {p.page_number}: Role={p.role.value:<18} NativeText={p.has_native_text:<5} ImageOnly={p.is_image_only:<5} Preview={txt_preview}")

    # 2. Heuristic Classification
    c_res = classify_document(packet)
    print(f"\n[2] Heuristic Classification:")
    print(f"  Document Type: {c_res.document_type}")
    is_image_only = all(p.is_image_only for p in packet.pages)
    heuristic_reason = "image-only (defers classification to LLM vision model)" if is_image_only else "text heuristic rules"
    print(f"  Heuristic Basis: {heuristic_reason}")
    print(f"  Is Non-Payable: {c_res.is_non_payable}")
    if c_res.is_non_payable:
        print(f"  Decline Reason: {c_res.decline_reason}")

    # 3. LLM Semantic Classification & Extraction
    print(f"\n[3] LLM Semantic Classification & Extraction:")
    candidates = []
    declined = []
    try:
        from src.extraction.extractor import extract_payables_with_declined
        from src.extraction.model_manager import gemini_manager
        candidates, declined = extract_payables_with_declined(packet, c_res)
        
        model_used = getattr(gemini_manager, "last_used_model", None) or "gemini-3.5-flash"
        fallback_used = "Yes" if getattr(gemini_manager, "fallback_count", 0) > 0 else "No"

        if declined:
            print(f"  Decision: DECLINED")
            print(f"  Candidate count: 0")
            print(f"  Model used: {model_used}")
            print(f"  Fallback used: {fallback_used}")
            for d in declined:
                print(f"  Decline reason: {d.reason}")
        elif candidates:
            print(f"  Decision: PAYABLE")
            print(f"  Candidate count: {len(candidates)}")
            print(f"  Model used: {model_used}")
            print(f"  Fallback used: {fallback_used}")
        else:
            print(f"  Decision: UNKNOWN / NO DATA EXTRACTED")
            print(f"  Candidate count: 0")
            print(f"  Model used: {model_used}")
            print(f"  Fallback used: {fallback_used}")
    except Exception as e:
        print(f"  LLM extraction error during inspection: {e}")

    # 4. Accounting Reconstruction & 5. ERP Validation
    if candidates:
        from src.accounting.reconstruction import reconstruct_autodraft
        from src.accounting.charges import total_charges
        from src.erp_validator import validate_payable
        from src.validation.diagnostics import diagnose_mismatch
        from src.normalization.numbers import parse_decimal

        for idx, cand in enumerate(candidates, 1):
            if len(candidates) > 1:
                print(f"\n--- Candidate {idx} ---")
            payable = reconstruct_autodraft(cand)

            # Compute accounting components
            line_base = sum(
                float(parse_decimal(li.quantity or "1")) * float(parse_decimal(li.unit_price or "0"))
                for li in cand.line_items
            )
            total_disc = (
                float(parse_decimal(cand.discount_amount)) if cand.discount_amount else 0.0
            ) + sum(float(parse_decimal(li.discount)) for li in cand.line_items if li.discount)
            total_tax = (
                sum(float(parse_decimal(t.tax_amount)) for t in cand.taxes if t.tax_amount)
                + sum(sum(float(parse_decimal(t.tax_amount)) for t in li.taxes if t.tax_amount) for li in cand.line_items)
            )
            if total_tax == 0 and cand.total_tax_amount:
                total_tax = float(parse_decimal(cand.total_tax_amount))
            charges = float(total_charges(cand))
            reconstructed_gross = payable.gross_total

            print(f"\n[4] Accounting Reconstruction:")
            print(f"  Line base:           {line_base:.2f}")
            print(f"  Discount:            {total_disc:.2f}")
            print(f"  Tax:                 {total_tax:.2f}")
            print(f"  Other charges:       {charges:.2f}")
            print(f"  Reconstructed gross: {reconstructed_gross}")

            print(f"\n[5] ERP Validation:")
            erp_res = validate_payable(payable)
            status_str = "MATCH" if erp_res.matches else "MISMATCH"
            print(f"  Document gross:      {erp_res.expected_gross:.2f}")
            print(f"  ERP gross:           {erp_res.will_book_gross:.2f}")
            print(f"  Delta:               {erp_res.delta:+.2f}")
            print(f"  Status:              {status_str}")

            if not erp_res.matches:
                diag_list = diagnose_mismatch(cand, erp_res.will_book_gross, str(cand.gross_total))
                print(f"  Diagnostic:")
                if diag_list:
                    for d in diag_list:
                        if d.category == DiagnosticCategory.TAX_PLACEMENT_MISMATCH and erp_res.delta > 0:
                            diag_label = "TAX_DOUBLE_COUNTING"
                        elif d.category in (DiagnosticCategory.HEADER_DISCOUNT_MISMATCH, DiagnosticCategory.LINE_DISCOUNT_MISMATCH) and erp_res.delta != 0:
                            diag_label = "DISCOUNT_DOUBLE_COUNTING"
                        else:
                            diag_label = d.category.value
                        print(f"    {diag_label}")
                else:
                    print(f"    UNCLASSIFIED_DELTA ({erp_res.delta:+.2f})")

    # 6. Master Data Status
    ensure_loaded()
    print(f"\n[6] Master Data Indexes:")
    from src.master_data import loader
    print(f"  Suppliers loaded:    {len(loader.suppliers)}")
    print(f"  VAT IDs indexed:     {len(loader.supplier_by_vat)}")
    print(f"  Taxes indexed:       {len(loader.tax_master)}")
    print(f"  Payment terms:       {len(loader.payment_terms)}")
    print(f"  PO records loaded:   {len(loader.po_master)}")

    print("\nInspection complete.\n")



def main():
    parser = argparse.ArgumentParser(description="Inspect single PDF document")
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    inspect_pdf(args.pdf_path)


if __name__ == "__main__":
    main()
