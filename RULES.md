# BOOKABLE PAYABLE RECONSTRUCTION — ENGINEERING RULES

**Version:** 2.0  
**Status:** Binding implementation rules  
**Priority:** These rules define how the system must behave during development and evaluation.

---

# 1. Golden Rule

> **Never invent a value to make the ERP balance.**

Evidence comes first.

If the document does not support a value, do not fabricate it merely because it makes the accounting equation work.

---

# 2. Rule Hierarchy

When rules conflict, use this order:

1. Assignment/grader contract
2. Supplied `erp.py`
3. Source-document evidence
4. Explicit accounting/reconstruction rules
5. Master-data evidence
6. ERP reconciliation diagnostics
7. LLM interpretation

The LLM is an interpretation mechanism. It is never the final authority.

---

# 3. Sacred Boundaries

The following are read-only:

- `erp.py`
- source PDFs
- master-data files

Never modify:

```text
erp.py
master_data/*
documents/*
```

The system must adapt to the provided environment.

---

# 4. Evidence Grounding

Every emitted value must be:

- directly supported by document evidence; or
- a deterministic, semantics-preserving normalization/transformation of evidenced data.

Allowed examples:

```text
1.234,56 → 1234.56
12/02/2026 → 2026-02-12
" ACME LTD " → normalized comparison form
printed credit amount → schema-required positive magnitude
```

Not allowed:

```text
guessing a missing tax code
guessing a PO number
inventing a supplier
adding an unexplained charge
subtracting an unexplained discount
creating a tax because the total needs one
```

Derived arithmetic is allowed only when every operand is independently evidenced.

---

# 5. Document = Evidence Packet

Treat every PDF as an evidence packet, not automatically as one payable.

A PDF may contain:

- one payable;
- multiple payables;
- a payable plus supporting pages;
- only non-payable material.

Therefore:

> **Segment pages before constructing accounting objects.**

---

# 6. Page Classification

Classify pages by accounting/document role.

Possible roles:

- invoice;
- credit note;
- invoice lines;
- tax summary;
- payment/remittance;
- statement/history;
- delivery/shipping;
- customs/supporting;
- estimate/quote;
- reminder/dunning;
- duplicate/copy;
- unrelated/non-payable.

Do not assume every page containing an amount belongs to the payable.

---

# 7. Accounting Intent, Not Vocabulary

Classification must reflect accounting intent.

The following are not automatically bookable merely because they contain supplier names, amounts, or the word “invoice”:

- estimates;
- quotes;
- payment reminders;
- dunning letters;
- delivery notes;
- shipping documents;
- historical statements;
- supporting customs documents;
- informational packets.

Do not classify from one keyword.

Use document identity, dates, totals, line items, payment language, and page context.

---

# 8. Payable Construction

A payable candidate should be constructed only when there is sufficient evidence of a current accounting obligation.

Required reasoning:

```text
Is this a bookable obligation?
        ↓
Which pages belong to it?
        ↓
What is the document type?
        ↓
What accounting structure is evidenced?
        ↓
Can the structure be represented safely?
        ↓
Can the ERP compute it correctly?
```

---

# 9. Multiple Payables

A single PDF may contain multiple independent payables.

Never force unrelated invoices into one record.

Each payable must have its own:

- document evidence;
- supplier;
- invoice/document number;
- dates;
- lines;
- tax/charge structure;
- accounting identity.

---

# 10. Duplicate and Copy Pages

Do not double-book duplicate pages.

If the same invoice appears twice in a packet:

- identify the duplicate relationship;
- retain the strongest evidence;
- create only one payable unless the document explicitly represents separate obligations.

---

# 11. Current Amount vs Historical Amount

Statements and utility/service invoices may contain:

- previous balance;
- previous payments;
- credits;
- current charges;
- current tax;
- amount due;
- outstanding balance.

Do not automatically book the largest or most visually prominent number.

Prefer the amount explicitly associated with the current accounting obligation.

Historical balances must not be converted into new charges.

---

# 12. Evidence Provenance

Material emitted fields should retain provenance.

At minimum, preserve where possible:

```text
field
raw value
normalized value
page
source text/table cell
bounding box
extraction method
confidence
```

Every final accounting field should be traceable back to evidence.

---

# 13. LLM Rules

The LLM may:

- interpret semantic roles;
- identify document type;
- associate labels with values;
- reconstruct table relationships;
- identify tax/discount/charge structure;
- propose candidate master-data matches.

The LLM may not:

- invent missing values;
- invent master-data codes;
- choose an unsupported accounting treatment;
- insert balancing values;
- silently convert historical amounts into current charges;
- override deterministic validation rules.

The final accounting representation is produced by deterministic post-processing and validation.

---

# 14. LLM Multi-Pass Strategy

Use a bounded workflow:

### Pass 1

```text
evidence → extraction → reconstruction → ERP
```

### Pass 2

If validation fails:

```text
ERP diagnostic
    ↓
identify specific suspect
    ↓
targeted evidence re-examination
    ↓
reconstruction
    ↓
ERP
```

### Pass 3

Only if independently justified.

Maximum:

```text
3 total passes
```

Do not implement open-ended self-reflection loops.

Do not call a second LLM simply because a second opinion sounds useful.

---

# 15. Reconciliation Is a Validator

ERP reconciliation tells us whether the proposed representation behaves correctly.

It does **not** tell us what missing value to invent.

Correct:

```text
ERP mismatch
→ diagnose tax placement
→ inspect tax evidence
→ targeted re-extraction
```

Incorrect:

```text
ERP mismatch
→ add 153.42 to "other charges"
```

unless the document independently evidences that charge.

---

# 16. Accounting Representation

Keep these concepts separate:

```text
Document representation
        ↓
Accounting semantics
        ↓
ERP representation
```

Do not make the LLM responsible for final ERP arithmetic.

The accounting layer must deterministically translate semantic evidence into the ERP structure.

---

# 17. ERP Rules

`erp.py` is authoritative and must not be changed.

Respect its behavior for:

- quantity × unit price;
- line discounts;
- per-line rounding;
- header discount;
- line taxes;
- header taxes;
- freight;
- insurance;
- extra charges;
- excise;
- explicit tax amounts;
- negative withholding where supported;
- final gross rounding.

Use `Decimal` for all financial calculations.

---

# 18. Line Structure

For every line, distinguish:

```text
quantity
unit price
discount
tax
line total
```

Do not assume:

```text
qty × unit_price = printed line total
```

without considering:

- discounts;
- tax;
- rounding;
- other line-level adjustments.

The validation rule must reflect the actual ERP semantics.

---

# 19. Unit Price Semantics

The supplied ERP treats `unit_price` as tax-exclusive/net for its line-base calculation.

Do not feed tax-inclusive prices into `unit_price` unless the document evidence and deterministic reconstruction justify a transformation.

---

# 20. Rounding

Financial calculations must use:

```python
Decimal
```

and the rounding behavior required by the supplied ERP.

Do not use binary floating-point arithmetic for final accounting values.

Per-line rounding must be preserved where required by ERP behavior.

---

# 21. Taxes

Preserve tax placement.

Possible structures include:

```text
line tax
header tax
multiple rates
zero tax
reverse charge
compound levy
withholding
```

Never flatten all taxes into one header tax unless the document and ERP representation support that transformation.

---

# 22. Explicit Tax Amounts

When the document explicitly provides a tax amount, prefer the explicit amount over recomputation when:

- the tax is correctly identified;
- its placement is correctly understood;
- the amount is independently evidenced.

Do not replace explicit evidence with an inferred rate calculation merely because the inferred result looks cleaner.

---

# 23. Compound Taxes

Compound tax sequences must preserve their economic/order semantics.

For example:

```text
base
 → levy A
 → levy B
 → levy C
 → VAT
```

Do not collapse compound taxes into a single arbitrary percentage.

If the supplied schema/ERP cannot safely represent the structure, decline rather than fabricate a representation.

---

# 24. Withholding

Where the ERP/schema represents withholding as an explicit negative tax amount:

```text
withholding → negative tax amount
```

Use the independently evidenced withholding amount.

Do not invent a withholding percentage or amount.

---

# 25. Discounts

Distinguish:

- line discount;
- header discount.

A printed “discount” must be placed according to its documented scope.

Do not use an unexplained ERP reconciliation delta as a discount.

---

# 26. Charges

Distinguish:

- freight;
- insurance;
- extra charges;
- excise;
- other documented charges.

Do not move charges between fields merely to achieve reconciliation.

---

# 27. Credit Memos

A credit note/memo must use:

```text
invoice_type = CREDIT_MEMO
```

and the positive-magnitude convention required by the output schema.

Do not infer credit status only from a negative number.

Look for document evidence such as:

- credit note/credit memo title;
- explicit credit wording;
- reference to original invoice;
- credit-note number;
- commercial credit context.

---

# 28. Master Data Is Ground Truth

Master data is read-only and authoritative for emitted controlled codes.

Never invent:

- supplier codes;
- tax codes;
- payment-term codes;
- buyer/organization codes;
- PO codes.

---

# 29. Supplier Matching

Preferred matching order:

1. exact VAT/tax identifier;
2. exact normalized legal identity;
3. IBAN as corroborating evidence;
4. exact name + address;
5. fuzzy name/address fallback.

IBAN is not an automatic primary key because bank accounts can change.

If candidates remain ambiguous, do not force a match.

---

# 30. Fuzzy Matching

Fuzzy matching is a fallback.

An initial candidate threshold such as:

```text
score >= 85
```

may be used, but acceptance must consider:

- competing candidates;
- country;
- address;
- identifiers;
- normalized legal name;
- evidence quality.

Never accept a fuzzy match solely because it is the highest score if the score is weak or contradictory.

---

# 31. Tax Master Matching

Match using available evidence:

- country;
- tax type;
- tax rate;
- tax description;
- document wording.

The final tax code must exist in the tax master.

---

# 32. Payment-Term Matching

Prefer:

1. explicit term code/text;
2. deterministic invoice-date/due-date relationship;
3. master-data candidate matching.

Do not infer a payment-term code solely from a generic phrase when the master contains conflicting candidates.

---

# 33. PO Matching

Prefer exact, document-supported PO numbers.

Never invent a PO because:

- a supplier usually uses one;
- another invoice uses one;
- the ERP output looks better with one.

---

# 34. Buyer/Organization Matching

Use explicit identifiers and normalized names/addresses.

If the document does not support the required organizational code, do not invent one.

---

# 35. Normalization Rules

Normalization is allowed when it preserves meaning.

Examples:

```text
1.234,56 → 1234.56
€ 1,234.50 → 1234.50
2026/02/12 → 2026-02-12
```

Normalization must not create unsupported data.

---

# 36. Table Reconstruction

Do not trust OCR line order alone.

Reconstruct tables using:

- row/column coordinates;
- repeated alignment;
- headers;
- page continuation;
- totals;
- tax columns;
- neighboring labels.

Validate that:

```text
description
quantity
unit price
discount
tax
line total
```

belong to the same logical row.

---

# 37. Multi-Page Rules

A continuation page may contain:

- additional lines;
- tax summaries;
- payment information;
- supporting details.

Join pages only when evidence indicates they belong to the same accounting object.

Do not merge merely because:

- supplier name is the same;
- currency is the same;
- pages are consecutive.

---

# 38. Classification of Common Non-Payables

Treat the following as non-payable unless the evidence clearly establishes a current bookable obligation:

- estimates;
- quotations;
- payment reminders;
- dunning letters;
- delivery notes;
- shipping copies;
- historical statements;
- informational notices;
- supporting customs paperwork;
- non-standard requests without a supplier payable obligation.

---

# 39. Unsupported Accounting Structures

If the document contains a structure that cannot be represented safely in the provided schema/ERP:

> decline.

Do not approximate.

---

# 40. Acceptance Conditions

Accept only when all required conditions are satisfied:

- document is bookable;
- correct accounting type;
- required evidence exists;
- master codes are valid;
- accounting structure is defensible;
- no unsupported inference was introduced;
- ERP computation succeeds;
- gross reconciles exactly;
- no unexplained balancing adjustment exists.

---

# 41. Decline Conditions

Decline when:

- document is non-payable;
- evidence is missing or unreadable;
- classification remains ambiguous;
- master match is unsafe;
- tax placement is unresolved;
- current amount cannot be distinguished from history;
- multiple interpretations remain;
- ERP mismatch remains unexplained;
- accounting structure is unsupported.

Decline is preferable to fabrication.

---

# 42. Error Handling

The system must fail safely.

Examples:

```text
OCR failure
→ retry with alternate extraction/rendering
→ decline if evidence remains insufficient

LLM failure
→ bounded retry
→ preserve previous evidence
→ decline if extraction remains unavailable

Master-data ambiguity
→ retain candidate set
→ targeted resolution
→ decline if unresolved

ERP mismatch
→ deterministic diagnosis
→ targeted recheck
→ decline if unexplained
```

Do not swallow exceptions silently.

---

# 43. Structured Logging

Each processed document should log:

- file;
- page;
- document candidate;
- classification;
- extraction method;
- master candidates;
- selected matches;
- accounting reconstruction;
- ERP result;
- mismatch diagnostics;
- retry count;
- final decision;
- decline reason.

Logs must be structured enough to reproduce and debug failures.

---

# 44. Reproducibility

Keep:

- fixed prompts;
- structured extraction schemas;
- model/provider version;
- normalized evidence;
- extraction outputs;
- deterministic post-processing;
- evaluation results.

Where supported, use deterministic model settings for extraction.

---

# 45. No Filename-Specific Logic

Never write:

```python
if filename == "INV-13":
```

or equivalent page-number hacks.

Instead write:

```python
if document_has_multiple_tax_rates(...):
```

General rules are allowed.

Document-specific exceptions are prohibited unless they are a clearly reusable document-class rule.

---

# 46. No Hidden Balancing

Forbidden patterns include:

```python
other_charges = expected_total - computed_total
```

or:

```python
tax = total - subtotal
```

unless the document independently establishes that the residual is the corresponding tax/charge.

Residual arithmetic is diagnostic, not evidence.

---

# 47. Validation Layers

Every accepted record should pass:

### Evidence validation

The emitted fields are grounded.

### Accounting validation

The reconstructed structure matches the document.

### ERP validation

The supplied ERP produces the expected result.

All three are required.

---

# 48. Debugging Checklist

When ERP gross does not match:

1. Is the document actually payable?
2. Are the correct pages included?
3. Is it a credit memo?
4. Is the current amount confused with history?
5. Are all lines present?
6. Are quantity and unit price correct?
7. Are discounts placed correctly?
8. Are taxes line-level or header-level?
9. Are there multiple tax rates?
10. Are taxes compound?
11. Is withholding represented correctly?
12. Are freight/insurance/extra charges present?
13. Is excise present?
14. Is rounding performed at the correct stage?
15. Is a tax-inclusive value being used as a net unit price?
16. Is any value unsupported?
17. Is the master-data match correct?
18. Does the mismatch have an evidence-supported explanation?

If no defensible explanation exists:

> decline.

---

# 49. Development Order

Implement in this order:

1. inspect schema and ERP;
2. evaluation harness;
3. evidence/PDF ingestion;
4. page segmentation;
5. document classification;
6. accounting IR;
7. semantic extraction;
8. normalization;
9. master matching;
10. deterministic reconstruction;
11. ERP validation;
12. reconciliation diagnostics;
13. targeted re-extraction;
14. hard cases;
15. regression tests;
16. generalization cleanup.

Do not optimize the LLM before the deterministic evaluation path exists.

---

# 50. Final Acceptance Principle

The implementation must consistently follow:

> **Evidence > inference**  
> **Explicit value > derived value**  
> **Exact identifier > fuzzy similarity**  
> **Correct structure > total-only reconciliation**  
> **ERP validation > intuition**  
> **Abstention > fabrication**  
> **General rule > document-specific hack**

The goal is not to maximize the number of JSON records.

The goal is to maximize the number of **correct, defensible, ERP-valid records while declining cases that cannot be solved safely.**
