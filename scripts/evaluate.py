"""Evaluation harness — batch evaluation of all PDFs and comprehensive financial reporting.

Processes every PDF/JSON in the output directory, validates against erp_book(),
aggregates financials per-currency, tracks exceptions, and reports results.

Separates business classification from accounting reconciliation:
1. Genuine non-payable (delivery notes, reminders, internal forms, estimates, sales orders)
2. Accepted payable with ERP reconciliation match
3. Payable candidate whose accounting reconstruction failed (PAYABLE_RECONCILIATION_FAILURE)

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --output output/
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_CANDIDATE_KIT = _PROJECT_ROOT / "candidate_kit" / "candidate_kit"
if str(_CANDIDATE_KIT) not in sys.path:
    sys.path.insert(0, str(_CANDIDATE_KIT))

from src.erp_validator import validate_payable_dict
from src.normalization.currency import normalize_currency
from src.normalization.numbers import parse_decimal

logger = logging.getLogger(__name__)

# Canonical diagnostic categories required by reporting
CANONICAL_CATEGORIES = [
    "TAX_DOUBLE_COUNTING",
    "DISCOUNT_DOUBLE_COUNTING",
    "CHARGE_PLACEMENT",
    "ROUNDING",
    "UNIT_PRICE",
    "CURRENT_VS_HISTORICAL",
    "COMPOUND_TAX",
    "BUNDLE_HIERARCHY",
    "OPERATIONAL_MEASUREMENT_VS_BILLABLE_AMOUNT",
    "NON_LINEAR_BILLING_FORMULA",
    "OTHER",
]


def _map_to_canonical_category(raw_cat: str) -> str:
    """Map any diagnostic category string to canonical categories."""
    upper = (raw_cat or "").upper().strip()
    if "BUNDLE" in upper:
        return "BUNDLE_HIERARCHY"
    if "OPERATIONAL" in upper:
        return "OPERATIONAL_MEASUREMENT_VS_BILLABLE_AMOUNT"
    if "NON_LINEAR" in upper or "NON-LINEAR" in upper or "FORMULA" in upper:
        return "NON_LINEAR_BILLING_FORMULA"
    if "COMPOUND" in upper:
        return "COMPOUND_TAX"
    if "UNIT_PRICE" in upper:
        return "UNIT_PRICE"
    if "TAX" in upper:
        return "TAX_DOUBLE_COUNTING"
    if "DISCOUNT" in upper:
        return "DISCOUNT_DOUBLE_COUNTING"
    if "CHARGE" in upper:
        return "CHARGE_PLACEMENT"
    if "ROUND" in upper:
        return "ROUNDING"
    if "CURRENT" in upper or "HISTORICAL" in upper:
        return "CURRENT_VS_HISTORICAL"
    return "OTHER"


def _extract_failure_details(
    filename: str,
    declined_entry: dict,
    docs_dir: Optional[Path] = None,
) -> dict:
    """Extract structured details for a payable reconstruction failure."""
    reason = declined_entry.get("reason", "")
    dtype = declined_entry.get("doc_type", "invoice")

    inv_num = ""
    curr = "UNKNOWN"
    stated_gross = 0.0
    erp_gross = 0.0
    delta = 0.0
    diag_cat = "OTHER"
    diag_desc = ""

    # 1. Try parsing structured PAYABLE_RECONCILIATION_FAILURE reason
    # Format: PAYABLE_RECONCILIATION_FAILURE: inv=X, curr=X, stated=X, erp=X, delta=X, category=X: X
    m_full = re.search(
        r"PAYABLE_RECONCILIATION_FAILURE:\s*inv=(?P<inv>[^,]*),\s*curr=(?P<curr>[^,]*),\s*"
        r"stated=(?P<stated>[^,]*),\s*erp=(?P<erp>[^,]*),\s*delta=(?P<delta>[^,]*),\s*"
        r"category=(?P<cat>[^:]*):\s*(?P<desc>.*)",
        reason,
    )
    if m_full:
        inv_num = m_full.group("inv").strip()
        curr = normalize_currency(m_full.group("curr").strip()) or m_full.group("curr").strip()
        try:
            stated_gross = float(parse_decimal(m_full.group("stated")))
        except Exception:
            pass
        try:
            erp_gross = float(m_full.group("erp"))
        except Exception:
            pass
        try:
            delta = float(m_full.group("delta"))
        except Exception:
            pass
        diag_cat = _map_to_canonical_category(m_full.group("cat"))
        diag_desc = m_full.group("desc").strip()
    else:
        # 2. Try parsing older format: ERP mismatch: delta=X, booked=X vs expected=X
        m_delta = re.search(r"delta=([+-]?[0-9.]+)", reason)
        m_booked = re.search(r"booked=([0-9.]+)", reason)
        m_exp = re.search(r"expected=([0-9.]+)", reason)
        if m_delta:
            delta = float(m_delta.group(1))
        if m_booked:
            erp_gross = float(m_booked.group(1))
        if m_exp:
            stated_gross = float(m_exp.group(1))

        # Check cache if available to resolve invoice number, currency, and diagnostics
        if docs_dir is None:
            docs_dir = _PROJECT_ROOT / "candidate_kit" / "candidate_kit" / "documents"
        pdf_path = docs_dir / filename
        try:
            from src.cache.extraction_cache import ExtractionCache
            from src.models.accounting import AccountingIR
            from src.validation.diagnostics import diagnose_mismatch

            cache = ExtractionCache(_PROJECT_ROOT / ".cache" / "extractions")
            cached = cache.get(pdf_path)
            if cached:
                ir = AccountingIR.model_validate(cached)
                inv_num = ir.invoice_number or ""
                curr = normalize_currency(ir.currency) or ir.currency or "UNKNOWN"
                if not stated_gross:
                    stated_gross = float(parse_decimal(ir.gross_total))
                diags = diagnose_mismatch(ir, erp_gross, str(ir.gross_total))
                if diags:
                    diag_cat = _map_to_canonical_category(diags[0].category.value)
                    diag_desc = diags[0].description
        except Exception as e:
            logger.debug("Could not inspect cache for %s: %s", filename, e)

    if not diag_desc:
        diag_desc = reason

    return {
        "file": filename,
        "invoice_number": inv_num,
        "doc_type": dtype,
        "currency": curr,
        "stated_gross": stated_gross,
        "erp_gross": erp_gross,
        "delta": delta,
        "diagnostic_category": diag_cat,
        "diagnostic_explanation": diag_desc,
    }


def evaluate_outputs(output_dir: Path, docs_dir: Optional[Path] = None) -> dict:
    """Evaluate all JSON outputs in a directory against erp_book().

    Returns comprehensive dataset, classification, accounting, and financial statistics.
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        logger.error("Output directory does not exist: %s", output_dir)
        return {"error": f"Directory not found: {output_dir}"}

    if docs_dir is None:
        docs_dir = _PROJECT_ROOT / "candidate_kit" / "candidate_kit" / "documents"
    docs_discovered = len(list(docs_dir.glob("*.pdf"))) if docs_dir.exists() else 0

    json_files = sorted([
        p for p in output_dir.glob("*.json")
        if not p.name.startswith("_") and p.name != "evaluation_summary.json"
    ])

    stats: Dict[str, Any] = {
        "dataset": {
            "documents_discovered": docs_discovered or len(json_files),
            "documents_processed": len(json_files),
            "outputs_generated": len(json_files),
            "errors": 0,
        },
        "classification": {
            "payable_candidates": 0,
            "accepted_payables": 0,
            "genuine_non_payables": 0,
            "payable_reconstruction_failures": 0,
            "empty_outputs": 0,
            # Backward-compatibility keys
            "payable_documents": 0,
            "declined_documents": 0,
        },
        "reconciliation": {
            "accepted_payables": 0,
            "erp_exact_matches_accepted": 0,
            "erp_mismatches_accepted": 0,
            "accepted_match_rate": 0.0,
            "accepted_match_rate_str": "0/0 (0.0%)",
            "overall_payable_candidates": 0,
            "overall_exact_matches": 0,
            "overall_reconstruction_failures": 0,
            "overall_reconciliation_rate": 0.0,
            "overall_reconciliation_rate_str": "0/0 (0.0%)",
        },
        # Backward-compatibility accounting block
        "accounting": {
            "payables_emitted": 0,
            "erp_matches": 0,
            "erp_mismatches": 0,
            "erp_match_rate": 0.0,
        },
        "diagnostics_summary": {cat: 0 for cat in CANONICAL_CATEGORIES},
        "financials_accepted": {},
        "financials_failures": {},
        "financials_by_currency": {},  # backward-compatibility alias to financials_accepted
        "payable_reconstruction_failures": [],
        "genuine_non_payables": [],
        "exceptions": {
            "infrastructure_failures": 0,
            "erp_mismatches": [],
            "non_payable_documents": [],
        },
        "documents": [],
    }

    currency_accum_accepted: Dict[str, Dict[str, Decimal]] = {}
    currency_accum_failures: Dict[str, Dict[str, Decimal]] = {}

    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read %s: %s", json_path, e)
            stats["dataset"]["errors"] += 1
            stats["exceptions"]["infrastructure_failures"] += 1
            stats["documents"].append({
                "file": json_path.name,
                "status": "READ_ERROR",
                "error": str(e),
            })
            continue

        filename = data.get("file", json_path.stem + ".pdf")
        payables = data.get("payables", [])
        declined = data.get("declined", [])

        is_accepted = bool(payables)
        is_declined = bool(declined) and not is_accepted

        if is_accepted:
            stats["classification"]["accepted_payables"] += 1
            stats["classification"]["payable_documents"] += 1
            doc_status = "ACCEPTED_PAYABLE"
        elif is_declined:
            stats["classification"]["declined_documents"] += 1
            dec = declined[0]
            dtype = dec.get("doc_type", "unknown")
            reason = dec.get("reason", "")

            # Disambiguate genuine non-payable from reconstruction failure:
            # Prefer explicit PAYABLE_RECONCILIATION_FAILURE decision marker or ERP mismatch indicators.
            # Do NOT classify merely because doc_type is invoice or credit_memo.
            is_recon_failure = (
                "PAYABLE_RECONCILIATION_FAILURE" in reason
                or "ERP mismatch" in reason
                or "erp_mismatch" in reason.lower()
            )

            if is_recon_failure:
                stats["classification"]["payable_reconstruction_failures"] += 1
                doc_status = "PAYABLE_RECONCILIATION_FAILURE"
                fail_details = _extract_failure_details(filename, dec, docs_dir)
                stats["payable_reconstruction_failures"].append(fail_details)

                # Track diagnostic category count
                cat = fail_details["diagnostic_category"]
                if cat in stats["diagnostics_summary"]:
                    stats["diagnostics_summary"][cat] += 1
                else:
                    stats["diagnostics_summary"]["OTHER"] += 1

                # Accumulate financials for failures
                f_curr = fail_details["currency"]
                f_gross = Decimal(str(fail_details["stated_gross"]))
                f_type = (fail_details["doc_type"] or "INVOICE").upper().strip()
                if f_curr not in currency_accum_failures:
                    currency_accum_failures[f_curr] = {
                        "invoices": Decimal("0.00"),
                        "credit_memos": Decimal("0.00"),
                        "net_due": Decimal("0.00"),
                        "count": Decimal("0"),
                    }
                currency_accum_failures[f_curr]["count"] += Decimal("1")
                if f_type == "CREDIT_MEMO":
                    currency_accum_failures[f_curr]["credit_memos"] += f_gross
                    currency_accum_failures[f_curr]["net_due"] -= f_gross
                else:
                    currency_accum_failures[f_curr]["invoices"] += f_gross
                    currency_accum_failures[f_curr]["net_due"] += f_gross
            else:
                stats["classification"]["genuine_non_payables"] += 1
                doc_status = "GENUINE_NON_PAYABLE"
                stats["genuine_non_payables"].append({
                    "file": filename,
                    "type": dtype,
                    "reason": reason,
                })
                stats["exceptions"]["non_payable_documents"].append({
                    "file": filename,
                    "type": dtype,
                    "reason": reason,
                })
        else:
            stats["classification"]["empty_outputs"] += 1
            doc_status = "EMPTY"

        stats["accounting"]["payables_emitted"] += len(payables)

        doc_summary = {
            "file": filename,
            "status": doc_status,
            "payables": [],
            "declined": declined,
        }

        # Process accepted payables
        for i, payable in enumerate(payables):
            erp_result = validate_payable_dict(payable)
            gross_dec = parse_decimal(payable.get("gross_total", "0"))
            raw_curr = (payable.get("currency") or "UNKNOWN").strip()
            curr = normalize_currency(raw_curr) or raw_curr.upper()
            inv_type = (payable.get("invoice_type") or "INVOICE").upper().strip()

            payable_entry = {
                "payable_index": i,
                "invoice_number": payable.get("invoice_number", ""),
                "invoice_type": inv_type,
                "currency": curr,
                "stated_gross": str(gross_dec),
                "erp_gross": erp_result.will_book_gross,
                "delta": erp_result.delta,
                "matches": erp_result.matches,
            }
            doc_summary["payables"].append(payable_entry)

            if erp_result.matches:
                stats["reconciliation"]["erp_exact_matches_accepted"] += 1
                stats["accounting"]["erp_matches"] += 1
            else:
                stats["reconciliation"]["erp_mismatches_accepted"] += 1
                stats["accounting"]["erp_mismatches"] += 1
                stats["exceptions"]["erp_mismatches"].append({
                    "file": filename,
                    "invoice_number": payable.get("invoice_number", ""),
                    "stated_gross": float(gross_dec),
                    "erp_gross": erp_result.will_book_gross,
                    "delta": erp_result.delta,
                })

            if curr not in currency_accum_accepted:
                currency_accum_accepted[curr] = {
                    "invoices": Decimal("0.00"),
                    "credit_memos": Decimal("0.00"),
                    "net_due": Decimal("0.00"),
                    "count": Decimal("0"),
                }

            currency_accum_accepted[curr]["count"] += Decimal("1")
            if inv_type == "CREDIT_MEMO":
                currency_accum_accepted[curr]["credit_memos"] += gross_dec
                currency_accum_accepted[curr]["net_due"] -= gross_dec
            else:
                currency_accum_accepted[curr]["invoices"] += gross_dec
                currency_accum_accepted[curr]["net_due"] += gross_dec

        stats["documents"].append(doc_summary)

    # Compute explicit reconciliation metrics
    acc_p = stats["classification"]["accepted_payables"]
    acc_matches = stats["reconciliation"]["erp_exact_matches_accepted"]
    acc_mismatches = stats["reconciliation"]["erp_mismatches_accepted"]
    recon_failures = stats["classification"]["payable_reconstruction_failures"]

    # Payable candidates = accepted payables + reconstruction failures
    payable_candidates = acc_p + recon_failures
    stats["classification"]["payable_candidates"] = payable_candidates

    stats["reconciliation"]["accepted_payables"] = acc_p
    stats["reconciliation"]["overall_payable_candidates"] = payable_candidates
    stats["reconciliation"]["overall_exact_matches"] = acc_matches
    stats["reconciliation"]["overall_reconstruction_failures"] = recon_failures

    acc_rate = round((acc_matches / acc_p * 100.0), 1) if acc_p > 0 else 0.0
    stats["reconciliation"]["accepted_match_rate"] = acc_rate
    stats["reconciliation"]["accepted_match_rate_str"] = f"{acc_matches}/{acc_p} ({acc_rate:.1f}%)"

    overall_rate = round((acc_matches / payable_candidates * 100.0), 1) if payable_candidates > 0 else 0.0
    stats["reconciliation"]["overall_reconciliation_rate"] = overall_rate
    stats["reconciliation"]["overall_reconciliation_rate_str"] = f"{acc_matches}/{payable_candidates} ({overall_rate:.1f}%)"

    # Backward compatibility accounting rate
    stats["accounting"]["erp_match_rate"] = acc_rate

    # Format financials for JSON
    for c, vals in sorted(currency_accum_accepted.items()):
        formatted = {
            "invoices": float(vals["invoices"]),
            "credit_memos": float(vals["credit_memos"]),
            "net_due": float(vals["net_due"]),
            "count": int(vals["count"]),
        }
        stats["financials_accepted"][c] = formatted
        stats["financials_by_currency"][c] = formatted

    for c, vals in sorted(currency_accum_failures.items()):
        stats["financials_failures"][c] = {
            "invoices": float(vals["invoices"]),
            "credit_memos": float(vals["credit_memos"]),
            "net_due": float(vals["net_due"]),
            "count": int(vals["count"]),
        }

    return stats


def print_report(stats: dict) -> None:
    """Print the exact evaluation report with explicit reconciliation metrics."""
    if "error" in stats:
        print(f"\n[ERROR] {stats['error']}")
        return

    ds = stats["dataset"]
    cl = stats["classification"]
    rec = stats["reconciliation"]
    diag = stats["diagnostics_summary"]
    fin_acc = stats["financials_accepted"]
    fin_fail = stats["financials_failures"]
    failures = stats["payable_reconstruction_failures"]
    genuine = stats["genuine_non_payables"]

    print("\n" + "=" * 78)
    print("              BOOKABLE PAYABLE -- EVALUATION REPORT")
    print("=" * 78)

    print("\nRUN")
    print("---")
    print(f"Documents discovered:     {ds['documents_discovered']}")
    print(f"Documents processed:      {ds['documents_processed']}")
    print(f"Outputs generated:        {ds['outputs_generated']}")
    print(f"Processing errors:        {ds['errors']}")

    print("\n## DOCUMENT CLASSIFICATION")
    print("--------------------------")
    print(f"Payable candidates:              {cl['payable_candidates']}")
    print(f"Accepted payables:               {cl['accepted_payables']}")
    print(f"Genuine non-payables:            {cl['genuine_non_payables']}")
    print(f"Payable reconstruction failures: {cl['payable_reconstruction_failures']}")
    print(f"Empty outputs:                   {cl['empty_outputs']}")

    print("\n## ERP RECONCILIATION")
    print("---------------------")
    print(f"Accepted payables:                              {rec['accepted_payables']}")
    print(f"ERP exact matches among accepted:               {rec['erp_exact_matches_accepted']}")
    print(f"ERP mismatches among accepted:                  {rec['erp_mismatches_accepted']}")
    print(f"Accepted-payable ERP match rate:                {rec['accepted_match_rate_str']}")
    print()
    print(f"Overall payable candidates:                     {rec['overall_payable_candidates']}")
    print(f"Overall exact ERP matches:                      {rec['overall_exact_matches']}")
    print(f"Overall ERP mismatches/reconstruction failures: {rec['overall_reconstruction_failures']}")
    print(f"Overall payable reconciliation rate:            {rec['overall_reconciliation_rate_str']}")

    print("\n## PAYABLE RECONSTRUCTION FAILURES")
    print("----------------------------------")
    if failures:
        header = f"{'File':<12} {'Invoice':<14} {'Curr':<5} {'Stated':>10} {'ERP':>10} {'Delta':>10}  Diagnostic"
        print(header)
        print("-" * 115)
        for f in failures:
            inv = f['invoice_number'] or "N/A"
            curr = f['currency'].encode('ascii', 'replace').decode('ascii')
            stated = f"{f['stated_gross']:.2f}"
            erp_val = f"{f['erp_gross']:.2f}"
            delta_val = f"{f['delta']:+.2f}"
            diag_str = f"{f['diagnostic_category']}: {f['diagnostic_explanation']}"
            if len(diag_str) > 55:
                diag_str = diag_str[:52] + "..."
            print(f"{f['file']:<12} {inv:<14} {curr:<5} {stated:>10} {erp_val:>10} {delta_val:>10}  {diag_str}")
    else:
        print("  <None -- 100% of payable candidates successfully reconciled>")

    print("\n## DIAGNOSTIC SUMMARY")
    print("---------------------")
    for cat in CANONICAL_CATEGORIES:
        count = diag.get(cat, 0)
        print(f"{cat:<26}: {count}")

    print("\n## FINANCIAL SUMMARY -- ACCEPTED PAYABLES")
    print("-----------------------------------------")
    print(f"{'Currency':<10} {'Invoices':>16} {'Credit Memos':>16} {'Net Due':>16}")
    print("-" * 62)
    if fin_acc:
        for c, f in sorted(fin_acc.items()):
            safe_c = c.encode('ascii', 'replace').decode('ascii')
            print(f"{safe_c:<10} {f['invoices']:>16.2f} {f['credit_memos']:>16.2f} {f['net_due']:>16.2f}")
    else:
        print("  <No financial transactions emitted>")

    if fin_fail:
        print("\n## FINANCIAL SUMMARY -- PAYABLE RECONSTRUCTION FAILURES")
        print("-------------------------------------------------------")
        print(f"{'Currency':<10} {'Invoices':>16} {'Credit Memos':>16} {'Net Due':>16}")
        print("-" * 62)
        for c, f in sorted(fin_fail.items()):
            safe_c = c.encode('ascii', 'replace').decode('ascii')
            print(f"{safe_c:<10} {f['invoices']:>16.2f} {f['credit_memos']:>16.2f} {f['net_due']:>16.2f}")

    print("\n## GENUINE NON-PAYABLE DOCUMENTS")
    print("--------------------------------")
    if genuine:
        for g in genuine:
            print(f"- {g['file']} [{g['type']}]: {g['reason']}")
    else:
        print("  <None>")

    print("\n" + "=" * 78 + "\n")


def main():
    """CLI entry point for evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Bookable Payable outputs")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output"),
        help="Directory containing output JSON files (default: output/)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    stats = evaluate_outputs(args.output)
    print_report(stats)

    # Write machine-readable evaluation_summary.json
    summary_path = args.output / "evaluation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"Saved evaluation summary: {summary_path}")


if __name__ == "__main__":
    main()
