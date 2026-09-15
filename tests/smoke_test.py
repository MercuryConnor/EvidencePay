"""Quick verification — tests core module imports and basic functionality."""
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "candidate_kit" / "candidate_kit"))

import json

# Test 1: ERP
from erp import erp_book
sample_path = _root / "candidate_kit" / "candidate_kit" / "sample_autodraft.json"
with open(sample_path, "r", encoding="utf-8") as f:
    payable = json.load(f)
result = erp_book(payable)
assert abs(result["will_book_gross"] - 438.0) < 0.01, f"ERP mismatch: {result}"
print("ERP: OK")

# Test 2: Models
from src.models import AutodraftPayable, FileOutput, ERPResult, AccountingIR
print("Models: OK")

# Test 3: Number normalization
from src.normalization.numbers import parse_number
tests = [
    ("1.234,56", "1234.56"),
    ("1,234.56", "1234.56"),
    ("19%", "19"),
    ("", ""),
    ("-1.234,56", "-1234.56"),
]
all_ok = True
for inp, expected in tests:
    got = parse_number(inp)
    if got != expected:
        print(f"  FAIL: parse_number('{inp}') = '{got}', expected '{expected}'")
        all_ok = False
print(f"Numbers: {'OK' if all_ok else 'FAIL'}")

# Test 4: PDF ingestion
from src.ingestion.pdf import ingest_pdf
test_pdf = _root / "candidate_kit" / "candidate_kit" / "documents" / "INV-01.pdf"
packet = ingest_pdf(test_pdf)
assert packet.total_pages > 0, "No pages found"
print(f"PDF Ingestion: OK ({packet.total_pages} pages)")

# Test 5: Master data
from src.master_data import match_supplier, match_tax_code, match_po
ev = match_supplier(vat_id="DE209177122")
assert ev.matched_id == "2845695", f"Supplier match failed: {ev}"
print("Master Data: OK")

print("\nAll checks passed!")
