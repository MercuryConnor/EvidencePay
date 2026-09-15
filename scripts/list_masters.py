"""Script to inspect all master data and sample mappings."""

import json
from pathlib import Path

master_dir = Path("candidate_kit/candidate_kit/master_data")

print("=== SUPPLIERS ===")
with open(master_dir / "suppliers.json", "r", encoding="utf-8") as f:
    suppliers = json.load(f).get("suppliers", [])
for s in suppliers:
    print(f"{s['supplier_id']:<10} | {s['country']} | {s.get('vat_id', ''):<15} | {s['name']}")

print("\n=== PAYMENT TERMS ===")
with open(master_dir / "payment_terms.json", "r", encoding="utf-8") as f:
    terms = json.load(f).get("payment_terms", [])
for t in terms:
    print(f"{t['term_id']:<10} | days: {t.get('days_until_due', 0):<3} | aliases: {', '.join(t.get('aliases', []))}")

print("\n=== TAX MASTER (sample) ===")
with open(master_dir / "tax_master.json", "r", encoding="utf-8") as f:
    taxes = json.load(f).get("taxes", [])
for t in taxes[:15]:
    print(f"{t['code']:<12} | {t.get('country', '')} | rate: {t.get('rate', 0)}% | {t.get('tax_type', '')} | {t.get('description', '')}")
