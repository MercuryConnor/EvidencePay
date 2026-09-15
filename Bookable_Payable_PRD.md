# Bookable Payable Reconstruction System — Product Requirements Document (PRD)

**Version:** 3.0  
**Status:** Implementation-ready  
**Purpose:** Build a reliable PDF-to-accounting reconstruction pipeline that converts heterogeneous business documents into ERP-bookable payable records while preserving evidence, accounting structure, master-data integrity, and exact ERP behavior.

---

## 1. Executive Summary

The system must transform a PDF document packet into one of two outcomes:

1. **One or more defensible payable records**, represented in the supplied autodraft schema and validated against the supplied ERP implementation.
2. **A decline record** when the document is not bookable, evidence is insufficient, the accounting structure cannot be reconstructed safely, or the system cannot produce a defensible ERP result.

The core problem is **not OCR alone** and is not simply “extract an invoice into JSON.”

The system must bridge three representations:

> **Document representation → Accounting semantics → ERP computational representation**

A document may express the same economic concept through invoices, credit notes, tax summaries, charges, discounts, deposits, remittance sections, payment pages, freight documents, or multi-page supporting material. The system therefore needs to reconstruct the **smallest defensible accounting representation** supported by the evidence.

The design combines the strongest elements of the candidate PRD and RULES:

- explicit grading and success criteria;
- evidence-first extraction and provenance;
- page/document segmentation;
- hybrid OCR/layout extraction plus vision-capable semantic interpretation;
- deterministic accounting reconstruction;
- production-scale master-data matching;
- exact validation through the supplied `erp.py`;
- controlled multi-pass targeted re-extraction;
- field-level confidence;
- explicit abstention;
- structured logging and reproducibility;
- an evaluation harness designed to prevent document-specific hacks.

The system must optimize for **correctness, structural fidelity, grounding, and generalization**, not merely the number of documents successfully emitted.

---

# 2. Problem Statement

The candidate kit contains heterogeneous PDFs, master data, an autodraft schema, and a sealed ERP implementation.

The input population includes:

- invoices;
- credit notes;
- freight documents;
- utility bills;
- service invoices;
- tax invoices;
- multi-page document packets;
- documents containing both payable and non-payable pages;
- documents containing historical balances or previous payments;
- estimates, reminders, delivery/shipping documentation, and other non-payables;
- multiple currencies;
- multiple languages;
- multiple tax structures;
- multiple discount and charge structures.

A PDF may therefore contain **zero, one, or multiple accounting objects**.

The system must not assume:

> one PDF = one invoice = one payable.

Instead:

> one PDF = an evidence packet from which zero or more accounting objects may be reconstructed.

---

# 3. Objective

Given a PDF:

```text
PDF
  ↓
page-level evidence
  ↓
page/document classification
  ↓
semantic extraction
  ↓
master-data resolution
  ↓
accounting reconstruction
  ↓
ERP computation
  ↓
validation/reconciliation
  ↓
accept or decline
  ↓
autodraft JSON
```

The output must contain:

```json
{
  "file": "example.pdf",
  "payables": [],
  "declined": []
}
```

Each payable must conform to the supplied autodraft schema.

The system must never modify the supplied ERP implementation, source documents, or master data.

---

# 4. Success Criteria

The system is successful only when it performs well across all of the following dimensions.

## 4.1 Arithmetic correctness

For every accepted payable:

```text
erp_book(payable).gross
```

must match the expected ERP result exactly.

No tolerance-based approximation is acceptable for final validation.

---

## 4.2 Structural fidelity

The output must represent the accounting structure actually evidenced by the document.

Examples:

- line-level taxes remain line-level when evidenced that way;
- header taxes remain header-level when evidenced that way;
- discounts are represented in the correct location;
- freight/insurance/other charges are not silently folded into unrelated fields;
- multiple tax rates are preserved;
- compound taxes are represented in a way consistent with the schema and ERP;
- credit memos preserve the required schema semantics;
- payment/historical balances are not confused with current charges.

A total that happens to reconcile is **not sufficient** if the underlying structure is wrong.

---

## 4.3 Evidence grounding

Every emitted field must be:

1. directly evidenced by the document; or
2. an explicitly permitted deterministic normalization/transformation of an evidenced value.

Permitted transformations include, for example:

- decimal separator normalization;
- date normalization;
- whitespace/casing normalization;
- currency formatting normalization;
- credit memo sign normalization when required by the schema;
- deterministic arithmetic reconstruction where the underlying operands are independently evidenced.

Unsupported inference is prohibited.

---

## 4.4 Master-data correctness

Every emitted master-data code must correspond to a real master-data record.

The system must not invent:

- supplier codes;
- tax codes;
- buyer/organization codes;
- payment-term codes;
- PO numbers;
- other controlled identifiers.

If a required match cannot be established safely, the field must remain unresolved or the payable must be declined according to the schema and business rules.

---

## 4.5 Payable classification

The system must correctly distinguish bookable documents from non-payables.

Examples of likely non-payables include:

- estimates/quotes;
- payment reminders/dunning letters;
- delivery notes;
- shipping/copy pages;
- informational statements;
- supporting customs documents when they do not contain a bookable obligation;
- sponsorship/contribution requests when they are not normal supplier invoices.

Classification must be based on **accounting intent and evidence**, not keywords alone.

---

## 4.6 Generalization

The solution must use reusable rules.

The implementation must not contain:

```python
if filename == "INV-19":
    ...
```

or equivalent document-specific branches.

Special handling is acceptable only when it represents a genuine reusable accounting/document pattern.

---

# 5. System Boundaries

## Immutable inputs

The following are read-only:

- `erp.py`;
- source PDFs;
- master-data files.

## ERP boundary

The supplied `erp.py` is the final computational authority.

The system may reproduce ERP calculations locally for diagnostics, but the supplied implementation remains authoritative.

## Output boundary

The system produces the required JSON output and diagnostics/logs. It does not modify the source documents or master data.

---

# 6. Core Design Principle

## Evidence > inference

The system should never invent a value to make a document balance.

The hierarchy is:

1. assignment/grader contract;
2. supplied `erp.py`;
3. document evidence;
4. accounting reconstruction rules;
5. master-data evidence;
6. ERP reconciliation diagnostics;
7. LLM interpretation.

ERP reconciliation is a **validator**, not a source of missing accounting facts.

If the document does not support a value, the system must not manufacture one merely because that value would produce the expected total.

---

# 7. Architecture

```text
                         ┌─────────────────────┐
                         │       PDF(s)         │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  PDF Ingestion      │
                         │  PyMuPDF            │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Evidence Layer      │
                         │ OCR + text + layout │
                         │ page/bbox/confidence │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Page Classification │
                         │ + segmentation      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Semantic Extraction │
                         │ Vision-capable LLM  │
                         │ behind abstraction  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Accounting IR       │
                         │ Pydantic models     │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          ┌────────────────────┐          ┌───────────────────┐
          │ Master Matching    │          │ Normalization     │
          │ supplier/tax/PO/   │          │ numbers/dates/    │
          │ terms/buyer        │          │ currency          │
          └─────────┬──────────┘          └─────────┬─────────┘
                    └───────────────┬───────────────┘
                                    ▼
                         ┌─────────────────────┐
                         │ Reconstruction      │
                         │ accounting semantics│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Original ERP        │
                         │ erp_book()          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Validation          │
                         │ evidence/accounting │
                         │ /ERP reconciliation │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                    ACCEPT                   DECLINE
                         │
                         ▼
                    autodraft.json
```

---

# 8. Evidence-First Intermediate Representation

Before constructing a payable, the system creates an evidence representation.

A field should conceptually contain:

```python
EvidenceValue(
    value=...,
    normalized_value=...,
    page=...,
    source_text=...,
    bbox=...,
    confidence=...,
    extraction_method=...,
)
```

The exact implementation may differ, but the following information must be recoverable for important fields:

- raw value;
- normalized value;
- source page;
- source text or table cell;
- bounding box when available;
- extraction method;
- confidence;
- relationship to the resulting accounting field.

This enables:

- debugging;
- targeted re-extraction;
- provenance validation;
- auditability;
- explainable declines;
- comparison of competing interpretations.

---

# 9. PDF Ingestion

## 9.1 Requirements

The ingestion layer must:

- preserve page boundaries;
- identify native PDF text when available;
- render pages for OCR/vision when necessary;
- preserve spatial information;
- retain page numbering;
- detect scanned/image-only pages;
- avoid modifying source PDFs.

## 9.2 Recommended tools

- PyMuPDF for PDF inspection/rendering;
- pdfplumber for table/layout support;
- PaddleOCR for OCR where native text is insufficient.

The system should not assume that one extraction method works for every PDF.

---

# 10. Page and Document Segmentation

Segmentation occurs before payable construction.

A page may be:

- invoice header;
- invoice line table;
- tax summary;
- payment/remittance page;
- credit-note page;
- shipping/delivery evidence;
- customs/supporting document;
- statement/history;
- unrelated/non-payable content.

A single PDF may contain multiple accounting objects.

The segmentation layer should identify:

```text
document packet
 ├── payable candidate A
 │    ├── pages 1–2
 │    └── page 4
 ├── supporting pages
 └── non-payable pages
```

The system must not blindly concatenate every page into one invoice.

---

# 11. Document Classification

Classification must answer:

1. Is this document/accounting segment potentially bookable?
2. What accounting type is it?
3. Which pages belong to it?
4. Is it a payable, credit memo, or non-payable?
5. Is the amount shown a current obligation or historical/informational amount?

Important classifications include:

- invoice;
- credit memo/credit note;
- freight/service invoice;
- utility invoice;
- estimate/quote;
- reminder/dunning letter;
- delivery note;
- statement;
- informational/supporting document;
- duplicate/copy packet.

Classification must use multiple signals:

- document title;
- invoice/credit-note identifiers;
- issue/due dates;
- supplier identity;
- line items;
- tax structure;
- payable language;
- payment terms;
- totals;
- document context;
- page relationships.

A keyword such as “invoice” is not sufficient by itself.

---

# 12. Extraction Strategy

## 12.1 Hybrid architecture

The preferred strategy is:

> deterministic PDF/OCR/layout evidence first, semantic vision extraction second.

Do not use a vision LLM as the only OCR system for every page.

### Stage A — Evidence extraction

Extract:

- native PDF text;
- OCR text;
- coordinates;
- tables;
- page images;
- OCR confidence where available.

### Stage B — Semantic interpretation

The vision-capable model receives the relevant evidence/page images and produces structured candidate fields.

Its responsibility is:

- identifying semantic roles;
- associating values with labels;
- reconstructing table relationships;
- identifying document type;
- identifying accounting structure.

Its responsibility is **not** to invent missing accounting values.

---

# 13. Accounting Intermediate Representation

The extraction layer should not directly write the final JSON.

Instead:

```text
Evidence
   ↓
Accounting IR
   ↓
Normalization
   ↓
Master resolution
   ↓
Reconstruction
   ↓
Final autodraft
```

The IR should represent concepts such as:

- document type;
- supplier identity evidence;
- invoice number;
- issue date;
- due date;
- currency;
- purchase order;
- payment terms;
- buyer/organization;
- lines;
- quantities;
- unit prices;
- line discounts;
- line taxes;
- header discounts;
- header taxes;
- freight;
- insurance;
- extra charges;
- excise;
- withholding;
- totals;
- tax summaries;
- supporting evidence;
- provenance;
- confidence.

The IR must preserve enough structure to reconstruct the supplied ERP input without forcing the LLM to perform final accounting calculations.

---

# 14. Accounting Reconstruction

The accounting layer is deterministic.

It converts document semantics into the representation expected by the ERP.

This is the critical bridge between:

> what the document says

and

> what the ERP computes.

The reconstruction layer must handle:

- tax placement;
- multiple tax rates;
- compound taxes;
- discounts;
- charges;
- withholding;
- currency;
- credit memo semantics;
- line/header allocation;
- current-vs-historical amounts.

---

# 15. ERP Semantics

The supplied `erp.py` must not be changed.

The implementation must respect its computational behavior, including:

- line base calculation;
- line discounts;
- per-line rounding;
- header discount;
- line taxes;
- header taxes;
- freight;
- insurance;
- extra charges;
- excise;
- explicit tax amounts, including negative withholding where supported;
- final gross rounding.

The system should create a small local diagnostic implementation only where useful for explaining a mismatch. It must not replace or modify `erp.py`.

---

# 16. Tax Reconstruction

Tax handling must preserve:

- tax rate;
- tax amount;
- tax location;
- tax ordering where relevant;
- tax base;
- multiple rates;
- zero-rated/reverse-charge cases;
- compound levies;
- withholding.

Examples of structures the system must be capable of representing include:

```text
line net
  → line VAT
```

```text
net
  → levy A
  → levy B
  → VAT
```

```text
header subtotal
  → discount
  → VAT
  → withholding
  → amount payable
```

The system must not assume every tax belongs at the header.

If the document provides an explicit tax amount, it should generally be preferred over recomputing that amount, provided its placement is correctly understood.

---

# 17. Discounts and Charges

The system must distinguish:

- line discount;
- header discount;
- freight;
- insurance;
- extra charges;
- excise;
- other documented charges.

A reconciliation delta must never automatically become a discount or charge.

There must be independent document evidence for such an adjustment.

---

# 18. Credit Memos

Credit memos use:

```text
invoice_type = CREDIT_MEMO
```

with the schema's required positive-magnitude semantics.

The system must not treat a printed negative total as permission to insert arbitrary negative line values if the schema expects positive magnitudes.

Credit classification must be supported by document evidence such as:

- credit note/credit memo wording;
- document type;
- reference to original invoice;
- negative commercial effect;
- credit-note numbering/format.

---

# 19. Master-Data Resolution

Master data is read-only.

Matching should be production-scalable and should avoid scanning every record for every field.

## 19.1 Supplier matching hierarchy

Preferred order:

1. exact VAT/tax identifier;
2. exact normalized legal identity;
3. IBAN/bank account as corroborating evidence;
4. exact/fuzzy name + address;
5. fuzzy fallback only when sufficiently strong.

IBAN should not automatically outrank legal identity because bank accounts may change.

## 19.2 Tax matching

Use evidence such as:

- country;
- tax type;
- tax rate;
- tax description;
- tax code text.

The selected tax code must exist in the master.

## 19.3 Payment terms

Use:

1. explicit payment-term text/code;
2. deterministic due-date/invoice-date relationship;
3. master-data match.

## 19.4 PO matching

Prefer exact document-supported PO numbers.

Never infer a PO solely because it would be convenient.

## 19.5 Buyer/organization matching

Use explicit identifiers and normalized names/addresses where supported.

## 19.6 Fuzzy matching

Fuzzy matching is a fallback, not the default.

A threshold such as ≥85% may be used as an initial candidate threshold, but final acceptance should also consider:

- field quality;
- competing candidates;
- identifier consistency;
- country/address consistency;
- corroborating evidence.

---

# 20. Normalization

Normalization is allowed only when deterministic and semantics-preserving.

Examples:

```text
1.234,56 → 1234.56
12/02/2026 → 2026-02-12
"ACME  LTD." → normalized comparison form
```

Normalization must not create a value that did not exist in the source.

All financial arithmetic must use `Decimal`.

Never use binary floating point for final accounting calculations.

---

# 21. Validation Framework

Validation has three independent layers.

## A. Evidence validation

Questions:

- Does the field exist in the document?
- Is the page correct?
- Is the source text correct?
- Is the table relationship correct?
- Is the evidence sufficiently clear?

## B. Accounting validation

Questions:

- Is the document type correct?
- Are lines structured correctly?
- Are taxes placed correctly?
- Are discounts and charges placed correctly?
- Is current amount distinguished from history?
- Is credit-note semantics correct?

## C. ERP validation

Questions:

- Does the supplied `erp_book()` accept the structure?
- Does computed gross reconcile exactly?
- If not, what structural mismatch explains the delta?

No single layer may substitute for the others.

---

# 22. Reconciliation and Diagnostics

A mismatch should produce a deterministic diagnostic.

Example diagnostic categories:

```text
TAX_PLACEMENT_MISMATCH
LINE_DISCOUNT_MISMATCH
HEADER_DISCOUNT_MISMATCH
CHARGE_MISSING
CHARGE_DOUBLE_COUNTED
CURRENT_VS_HISTORICAL_AMOUNT
ROUNDING_MISMATCH
LINE_STRUCTURE_MISMATCH
CREDIT_MEMO_SEMANTICS
MASTER_DATA_MISMATCH
UNSUPPORTED_STRUCTURE
```

The diagnostic layer should identify the smallest plausible area requiring re-investigation.

The system must not “solve” a mismatch by adding an unexplained balancing number.

---

# 23. Controlled Multi-Pass Extraction

The strongest recovery mechanism is a **targeted, bounded multi-pass workflow**.

### Pass 1 — Initial reconstruction

```text
evidence → classification → extraction → reconstruction → ERP
```

### Pass 2 — Targeted recheck

If validation fails:

1. compute deterministic diagnostics;
2. identify the suspected field/region/page;
3. re-examine only that evidence;
4. update the candidate;
5. rerun ERP validation.

### Pass 3 — Final targeted recheck

Only when independently justified by remaining evidence.

Maximum:

```text
3 total interpretation/recheck passes
```

The system must not enter an open-ended self-correction loop.

A second LLM call is therefore a **diagnostic tool**, not an unconditional second opinion.

---

# 24. Confidence Model

Confidence should be field-level rather than a single document-wide LLM score.

Useful dimensions:

- extraction confidence;
- evidence confidence;
- master-match confidence;
- accounting-structure confidence;
- ERP reconciliation status.

Example:

```text
invoice_number
  evidence = strong
  extraction = strong
  final = ACCEPT

supplier
  evidence = strong
  master_match = exact VAT
  final = ACCEPT

tax_code
  evidence = ambiguous
  master_match = multiple candidates
  final = DECLINE
```

A high LLM confidence score must never override missing evidence.

---

# 25. Acceptance State Machine

Recommended state machine:

```text
UNKNOWN
   ↓
CANDIDATE
   ↓
RECONSTRUCT
   ↓
VALIDATE
   ├──→ ACCEPT
   │
   ├──→ DECLINE
   │
   └──→ TARGETED_RECHECK
             ↓
         RECONSTRUCT
             ↓
         VALIDATE
```

Acceptance requires all mandatory conditions to pass.

Decline is a valid and often preferable outcome when evidence is insufficient.

---

# 26. Abstention Policy

The system must decline rather than fabricate when:

- the document is not a payable;
- accounting intent is ambiguous;
- required evidence is missing;
- master data cannot be safely resolved;
- tax structure cannot be reconstructed;
- the current amount due cannot be distinguished from historical balances;
- multiple competing interpretations remain;
- ERP reconciliation fails without an evidence-supported explanation;
- the document contains an unsupported accounting structure.

The objective is **defensible automation**, not forced automation.

---

# 27. Technology Stack

## Required / preferred

- Python 3.12
- PyMuPDF
- PaddleOCR
- pdfplumber
- Pydantic
- RapidFuzz
- Decimal
- pytest
- python-dotenv
- Typer or argparse
- supplied `erp.py`
- vision-capable LLM behind an abstraction layer

## Optional

- pdf2image
- structured-output support from the selected LLM provider
- lightweight local caching for reproducibility

## Explicitly avoid initially

- LangChain
- LangGraph
- autonomous agent frameworks
- vector databases
- Postgres
- Kafka
- Airflow
- Kubernetes
- microservice decomposition
- MLflow

These add operational complexity without solving the core reconstruction problem.

---

# 28. LLM Abstraction

The extraction system should depend on a protocol rather than a provider-specific implementation.

Conceptually:

```python
class DocumentExtractor(Protocol):
    def extract(self, evidence_packet) -> ExtractionResult:
        ...
```

Possible implementations:

```text
VisionLLMExtractor
LocalVLMExtractor
MockExtractor
```

This enables:

- provider replacement;
- testing;
- deterministic mocks;
- cost control;
- targeted re-extraction.

The LLM must return structured candidates, not final unchecked ERP JSON.

---

# 29. Repository Structure

```text
src/
├── pipeline.py
├── ingestion/
│   ├── pdf.py
│   ├── renderer.py
│   └── page.py
├── evidence/
│   ├── models.py
│   ├── ocr.py
│   ├── text.py
│   └── layout.py
├── classification/
│   ├── document.py
│   └── page.py
├── extraction/
│   ├── extractor.py
│   ├── llm.py
│   ├── prompts.py
│   └── targeted_recheck.py
├── accounting/
│   ├── models.py
│   ├── reconstruction.py
│   ├── taxes.py
│   ├── discounts.py
│   └── charges.py
├── normalization/
│   ├── numbers.py
│   ├── dates.py
│   └── currency.py
├── master_data/
│   ├── loader.py
│   ├── supplier.py
│   ├── buyer.py
│   ├── tax.py
│   ├── terms.py
│   └── po.py
├── validation/
│   ├── schema.py
│   ├── provenance.py
│   ├── reconciliation.py
│   └── diagnostics.py
└── output/
    └── writer.py

scripts/
└── evaluate.py

tests/
├── test_ingestion.py
├── test_classification.py
├── test_normalization.py
├── test_master_matching.py
├── test_accounting.py
├── test_erp_reconciliation.py
└── test_end_to_end.py
```

---

# 30. Evaluation Harness

The evaluation harness is a first-class component.

It should:

- process all supplied PDFs;
- produce the required JSON;
- validate schema;
- run ERP validation;
- report accepted/declined counts;
- report arithmetic mismatches;
- report master-data mismatches;
- report classification errors where ground truth is available;
- surface structural mismatches;
- preserve diagnostics for failed cases.

Evaluation should be runnable with a single command, for example:

```bash
python scripts/evaluate.py
```

The evaluation harness must make it difficult to hide failures behind document-specific code.

---

# 31. Testing Strategy

Tests must cover:

## Extraction

- OCR errors;
- decimal separators;
- dates;
- tables;
- multi-page joins.

## Classification

- invoice;
- credit memo;
- estimate;
- reminder;
- delivery note;
- statement;
- mixed packets.

## Accounting

- line discounts;
- header discounts;
- line taxes;
- header taxes;
- multiple VAT rates;
- compound taxes;
- withholding;
- freight;
- insurance;
- excise;
- rounding;
- credit memo semantics.

## Master data

- exact VAT;
- exact identity;
- IBAN corroboration;
- fuzzy matches;
- ambiguous candidates;
- missing matches.

## Reconciliation

- exact match;
- explainable mismatch;
- unexplained mismatch;
- targeted recheck;
- final decline.

---

# 32. Development Plan

## Phase 1 — Evaluation and foundations

- inspect schema and ERP;
- build evaluator;
- build evidence models;
- build PDF/page ingestion;
- implement Decimal normalization.

## Phase 2 — Segmentation and classification

- page classification;
- packet segmentation;
- payable/non-payable classification;
- credit memo detection.

## Phase 3 — Extraction

- evidence extraction;
- LLM semantic extraction;
- accounting IR;
- provenance.

## Phase 4 — Deterministic accounting

- reconstruction;
- tax placement;
- discounts;
- charges;
- credit memo handling;
- ERP validation.

## Phase 5 — Master data

- indexed candidate retrieval;
- exact identifiers;
- normalized identity;
- fuzzy fallback;
- ambiguity handling.

## Phase 6 — Recovery and hard cases

- reconciliation diagnostics;
- targeted re-extraction;
- multi-page edge cases;
- current-vs-historical amount handling;
- abstention.

## Phase 7 — Generalization cleanup

- remove document-specific hacks;
- add regression tests;
- run full evaluation;
- review open/held-out behavior;
- optimize only after correctness is stable.

---

# 33. Failure Modes and Required Responses

| Failure | Required response |
|---|---|
| OCR unreadable | Re-render/re-OCR or decline |
| Ambiguous supplier | Targeted evidence review or decline |
| Missing master code | Do not invent; leave unresolved/decline |
| Tax placement unclear | Recheck evidence or decline |
| ERP mismatch | Diagnose structure; targeted recheck |
| Historical balance mistaken for payable | Reclassify current amount |
| Estimate treated as invoice | Decline |
| Reminder treated as new payable | Decline |
| Credit note treated as invoice | Correct type or decline |
| Balancing delta required | Never invent |
| Duplicate/copy page | Do not double-book |
| Multi-payable packet | Segment into independent payables |
| Unsupported structure | Decline |

---

# 34. Observability and Reproducibility

Every run should provide structured logs containing:

- file;
- page;
- classification;
- extraction method;
- candidate master matches;
- selected master record;
- reconstruction summary;
- ERP result;
- validation result;
- retry/recheck reason;
- final decision;
- decline reason.

LLM calls should be reproducible where the provider permits it through:

- fixed prompts;
- structured outputs;
- captured inputs;
- captured outputs;
- model/version metadata;
- deterministic post-processing.

---

# 35. Security and Data Handling

- Do not modify source PDFs.
- Do not modify master data.
- Do not expose credentials in source code.
- Use environment variables for API keys.
- Avoid unnecessary persistence of sensitive document images/text.
- Keep intermediate artifacts clearly separated from final outputs.

---

# 36. Definition of Done

The project is complete when:

- [ ] all required PDFs can be processed end-to-end;
- [ ] output conforms to the required schema;
- [ ] non-payables are not bookable;
- [ ] multiple payables per PDF are supported;
- [ ] credit memos are correctly represented;
- [ ] master-data codes are grounded in master data;
- [ ] financial arithmetic uses `Decimal`;
- [ ] supplied `erp.py` remains untouched;
- [ ] accepted records reconcile exactly with ERP;
- [ ] evidence provenance exists for material emitted fields;
- [ ] targeted re-extraction is bounded;
- [ ] unexplained mismatches cause decline;
- [ ] evaluation runs from a single command;
- [ ] no filename-specific hacks are required;
- [ ] regression tests cover discovered edge cases;
- [ ] the system has a documented decline reason for every declined candidate.

---

# 37. Final Engineering Principle

The system should not ask:

> “How can I make this PDF into a valid invoice JSON?”

It should ask:

> **“What is the smallest accounting representation that is directly defensible from this evidence and produces the correct behavior in the supplied ERP?”**

That distinction is the central design principle of the project.
