# EvidencePay — Bookable Payable Reconstruction Engine

An evidence-grounded accounting reconstruction engine that converts supplier PDF documents into structured **autodrafts** conforming to `AUTODRAFT_SCHEMA.md`, validated against a sealed ERP oracle (`erp.py`).

**Core insight**: Decouple LLM perception from deterministic accounting. The Vision-LLM extracts verbatim document evidence into an expressive intermediate representation. Deterministic engines then reconcile taxes, discounts, bundles, and line hierarchies before validating against the immutable ERP contract.

---

## Quickstart

```bash
# 1. Install dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env → set GOOGLE_API_KEY=<your-key>

# 3. Process all 42 documents
python main.py process --input candidate_kit/candidate_kit/documents --output output

# 4. Evaluate against sealed ERP oracle
python main.py evaluate --output output

# 5. Run test suite
python -m pytest -q
```

---

## Architecture

```
              ┌──────────────────────────────────────────────────────────┐
              │                    PDF Document                         │
              └──────────────────────────┬───────────────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  1. Ingestion &     │
                              │  Evidence Rendering │  300 DPI raster + text layout
                              │  (PyMuPDF)          │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  2. Document        │
                              │  Classification     │  → delivery notes, reminders,
                              │                     │    forms, estimates: DECLINE
                              └──────────┬──────────┘
                                         │ payable candidate
                              ┌──────────▼──────────┐
                              │  3. Vision-LLM      │
                              │  Semantic Extraction │  Gemini multimodal → AccountingIR
                              │  (with model        │  (rate-limited, fallback-aware)
                              │   fallback)         │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  4. Normalization   │  EU/US decimals, dates,
                              │  & Master Data      │  supplier fuzzy match,
                              │  Resolution         │  tax code lookup
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  5. Deterministic   │  Tax placement, discount
                              │  Accounting         │  reconciliation, bundle
                              │  Reconstruction     │  hierarchy, operational
                              │                     │  measurement correction
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  6. Sealed ERP      │
                              │  Validation         │  erp_book() → delta must be
                              │  (erp.py oracle)    │  exactly 0.00
                              └──────────┬──────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                   delta = 0.00    delta ≠ 0.00    after 3 passes
                          │              │              │
                          ▼              ▼              ▼
                     ┌─────────┐  ┌──────────┐  ┌──────────────────┐
                     │ ACCEPT  │  │ Bounded  │  │ DECLINE          │
                     │ payable │  │ Recheck  │  │ RECONCILIATION   │
                     │         │  │ (max 2   │  │ FAILURE          │
                     │         │  │  passes) │  │ (with diagnostic │
                     │         │  │          │  │  root cause)     │
                     └─────────┘  └──────────┘  └──────────────────┘
                          │                              │
                          └──────────┬───────────────────┘
                                     ▼
                            output/{stem}.json
```

### Design Invariants

1. **The ERP Oracle is sealed** — `erp.py` is never modified. It is the sole arbiter of gross reconciliation.
2. **Every emitted value is grounded in document evidence** — no synthetic prices, invented discounts, or fabricated charges.
3. **Zero document-specific logic** — no `if filename == 'X.pdf'` branches anywhere in production code.
4. **Declining is a first-class output** — non-payables and irreconcilable documents are cleanly routed to `declined[]` with structured audit reasons.

---

## Evaluation Results

Across all 42 documents in the candidate kit:

| Metric | Value |
| :--- | :--- |
| Documents processed | **42** |
| Outputs generated | **42** |
| Processing errors | **0** |
| | |
| Payable candidates | **37** |
| Genuine non-payables | **5** |
| | |
| Accepted payables | **35** |
| Payable reconstruction failures | **2** |
| | |
| **Accepted-payable ERP match rate** | **35 / 35 (100.0%)** |
| **Overall payable reconciliation** | **35 / 37 (94.6%)** |

All 35 accepted payables book against the sealed ERP with delta **exactly 0.00**.

---

## Example: INV-02 (Bundle Hierarchy)

INV-02 is an Estonian equipment rental invoice with a parent bundle row (lighting package at €538.80) followed by itemized component lines that sum to the same total. Without intervention, the ERP would double-count components.

**Pipeline behaviour**: `reconcile_bundle_hierarchy` detects the parent–child price relationship, prunes duplicate components, and preserves independent service lines (transport, technician).

<details>
<summary>output/INV-02.json (truncated)</summary>

```json
{
  "file": "INV-02.pdf",
  "payables": [
    {
      "invoice_number": "9972-907",
      "invoice_date": "2026-03-18",
      "invoice_type": "INVOICE",
      "currency": "EUR",
      "gross_total": "608.23",
      "subtotal": "538.80",
      "discount_amount": "48.09",
      "taxes": [
        { "tax_type": "VAT", "tax_name": "Käibemaks", "tax_rate": "24.0", "tax_amount": "117.72" }
      ],
      "line_items": [
        { "description": "LED Bar FOS Luminus BAR",       "quantity": "9.0",  "unit_price": "6.00",   "total": "54.00"  },
        { "description": "Pioneer CDJ-3000",              "quantity": "2.0",  "unit_price": "45.00",  "total": "90.00"  },
        { "description": "Pioneer DJM-900 NXS2 mixer",    "quantity": "1.0",  "unit_price": "45.00",  "total": "45.00"  },
        { "description": "Aktiivkõlar Veritas 8000",      "quantity": "1.0",  "unit_price": "103.60", "total": "103.60" },
        { "description": "Linnasisesene transport",        "quantity": "1.0",  "unit_price": "50.00",  "total": "50.00"  },
        { "description": "Tehnik",                        "quantity": "2.0",  "unit_price": "84.00",  "total": "168.00" }
      ],
      "supplier": { "name": "Northwind Technology OÜ" },
      "buyer":    { "company_code": "BOLTGROUP", "business_unit_code": "EE001" }
    }
  ],
  "declined": []
}
```

ERP validation: `erp_book()` → `608.23`, stated gross → `608.23`, **delta = 0.00** ✓

</details>

---

## Principled Declines

Two payable candidates are intentionally declined rather than forcing an artificial match:

### HLD-05 — Compound Tax (`COMPOUND_TAX`)

Portuguese fuel invoice where excise duty (IEC, €312.39) is legally compounded into the VAT taxable base *before* 23% IVA is applied. The sealed ERP adds excise duties *after* computing taxes — making faithful representation impossible without fabricating synthetic line prices.

```json
{
  "file": "HLD-05.pdf",
  "payables": [],
  "declined": [{
    "doc_type": "invoice",
    "reason": "PAYABLE_RECONCILIATION_FAILURE: inv=856/AT, curr=EUR, stated=1012.14, erp=1324.53, delta=+312.39, category=COMPOUND_TAX: ..."
  }]
}
```

### INV-37 — Non-Linear Billing (`NON_LINEAR_BILLING_FORMULA`)

Industrial chilled water utility bill computed via a capacity formula (connected tons × annual rate ÷ 12 × multiplier). The ERP schema only supports linear quantity × unit_price — representing this formula would require manufacturing a synthetic unit price that doesn't exist on the document.

```json
{
  "file": "INV-37.pdf",
  "payables": [],
  "declined": [{
    "doc_type": "invoice",
    "reason": "PAYABLE_RECONCILIATION_FAILURE: inv=5568, curr=$, stated=2487.73, erp=2507.75, delta=+20.02, category=NON_LINEAR_BILLING_FORMULA: ..."
  }]
}
```

> In enterprise AP automation, surfacing an explainable exception for human review is strictly preferable to booking a fabricated number into the general ledger.

---

## Verification

### Run automated tests
```bash
python -m pytest -q
```

### Run the complete benchmark
```bash
python main.py process --input candidate_kit/candidate_kit/documents --output output
python main.py evaluate --output output
```

### Expected benchmark on the supplied candidate kit

- Documents processed: 42
- Payable candidates: 37
- Accepted payables: 35
- Genuine non-payables: 5
- Reconstruction failures: 2
- Accepted-payable ERP accuracy: 35/35 (100.0%)
- Overall payable reconciliation: 35/37 (94.6%)
- Processing errors: 0

### Inspect one document
```bash
python main.py inspect candidate_kit/candidate_kit/documents/INV-01.pdf
```

### Re-run targeted recovery
```bash
python main.py recheck candidate_kit/candidate_kit/documents/INV-01.pdf --output output
```

---

## Project Structure

```
├── candidate_kit/          # Sealed evaluation kit (DO NOT MODIFY)
│   └── candidate_kit/
│       ├── erp.py          # Immutable ERP oracle
│       ├── master_data/    # Suppliers, tax codes, POs, payment terms
│       └── documents/      # 42 input PDFs
├── src/
│   ├── ingestion/          # PDF rendering & text extraction
│   ├── classification/     # Document type classification
│   ├── extraction/         # Vision-LLM extraction, model manager, rate limiter
│   ├── normalization/      # Number, date, currency normalization
│   ├── master_data/        # Fuzzy matching against sealed master tables
│   ├── accounting/         # Deterministic reconstruction (taxes, discounts, bundles)
│   ├── validation/         # ERP validation & mismatch diagnostics
│   ├── models/             # Pydantic schemas (AccountingIR, AutodraftPayable)
│   └── output/             # JSON writer
├── scripts/
│   ├── evaluate.py         # 42-document evaluation harness
│   └── inspect_doc.py      # Single-document diagnostic inspector
├── tests/                  # 125 automated tests
├── main.py                 # CLI entry point
├── walkthrough.md          # Detailed technical walkthrough
├── DESIGN.md               # Design rationale & engineering questions
└── requirements.txt
```

---

## Design Documentation

For the detailed engineering walkthrough covering all 14 architectural sections, see [`walkthrough.md`](walkthrough.md).

For the design rationale answering the three core engineering questions, see [`DESIGN.md`](DESIGN.md).
