# Autodraft schema

The record the ERP consumes. You emit **one payable object per bookable payable**, wrapped per file as described in the brief's *Output contract*. You submit **raw components** — quantities, unit prices, discounts, and the taxes/charges you assign. The ERP (`erp.py`) derives everything else (per-line nets, tax amounts, subtotals, the gross). Do **not** pre-compute ERP totals; submit the parts.

## Per-file output

```jsonc
{
  "file": "X.pdf",
  "payables": [ <payable>, ... ],   // 0..N
  "declined": [ { "doc_type": "...", "reason": "..." }, ... ]
}
```

## A payable

```jsonc
{
  "invoice_number": "265345",
  "invoice_date":   "2026-02-02",        // ISO YYYY-MM-DD
  "due_date":       "2026-02-12",
  "invoice_type":   "INVOICE",           // INVOICE | CREDIT_MEMO
  "currency":       "EUR",

  "supplier": {
    "name":        "Phocus Direct Communication GmbH",
    "supplier_id": "2845695",            // master-data code, or "" if no match
    "address":     "Lina-Ammon-Strasse 19b, 90471 Nurnberg, DE",
    "vat_id":      "DE209177122"
  },
  "buyer": {                             // the tenant org (from master data)
    "company_code":       "BOLTGROUP",
    "business_unit_code": "EE004",
    "location_code":      "LOC_EE_001"
  },
  "payment_term_id": "Net_10",           // master-data code
  "po_number":       "",                  // PO number as printed on the document (raw)
  "po_id":           "",                  // matched master-data PO code, or "" if not in the PO master

  // ── totals exactly as printed on the document ──
  "gross_total":      "438.00",          // what the document says is owed
  "subtotal":         "438.00",          // optional
  "total_tax_amount": "0.00",            // declared total tax, as printed

  // ── header-level charges & discount ──
  "discount_amount":   "",
  "freight_charges":   "",
  "insurance_charges": "",
  "extra_charges":     "",
  "excise_duties":     "",

  // ── header-level taxes ──
  "taxes": [
    {
      "tax_type":  "VAT",
      "tax_name":  "VAT Reverse Charge",
      "tax_rate":  "0",                  // percent, no "%", dot-decimal
      "tax_amount": "0.00",             // may be "" — the ERP derives it from the rate; may be negative (withholding)
      "tax_type_code": "VAT"            // master-data code, or ""
    }
  ],

  // ── line items: raw components ──
  "line_items": [
    {
      "description":         "Projektmanagement Nachberechnung",
      "item_type":           "SERVICE",  // GOODS | SERVICE | FREIGHT | TAX
      "uom":                 "Hr",
      "quantity":            "4",
      "unit_price":          "73.00",    // NET unit price (excludes tax) — see note
      "total":               "292.00",   // line extension, as printed
      "discount":            "",         // amount discount (magnitude)
      "discount_percentage": "",         // percentage discount
      "tax_rate":            "",         // per-line rate (optional)
      "tax_amount":          "",         // per-line amount (optional)
      "taxes": []                        // OR an explicit per-line taxes[], same shape as header taxes
    }
  ]
}
```

## Field notes

- **Numbers are dot-decimal.** `1234.56`, not `1.234,56`. `erp.py` does not do locale parsing.
- **`unit_price` is NET** (tax-exclusive). The ERP adds tax on top of the prices you give it.
- **A tax may sit at the header (`taxes[]`) or on a line (`line_items[].taxes[]`).** Where you place it determines the base the ERP applies it to — and **placement itself is graded**: put each tax where the document places it (line-level taxes on the line, a single header tax at the header), with its correct name, rate, and amount. Same gross, wrong structure, still fails.
- **A tax is quantifiable only** — `tax_name`, `tax_rate`, `tax_amount` (and its `tax_type` / `tax_type_code`). Leave `tax_amount` empty to let the ERP derive it from the rate on that tax's base; give an explicit `tax_amount` when the amount is what's printed (or when the base isn't the plain net — e.g. a compound levy). A **negative** `tax_amount` models a withholding tax that reduces what is owed.
- **`invoice_type: "CREDIT_MEMO"`** for a credit — **same schema, same keys** as an invoice; the credit memo's own values fill the ordinary fields, delivered as **positive** magnitudes. There is no separate credit-memo shape.
- **Master-data codes — resolve and set them wherever a match exists.** For every field backed by a master, take the document's value, match it against the relevant master (how strictly, and on which fields, is your call), and put the resulting code in the autodraft. Populate the code whenever a match is found; leave `""` only when there is genuinely no match (an honest blank) — never a guessed code. The raw printed value stays in its own field (`supplier.name`, `po_number`, the tax's `tax_name`/`tax_rate`); the `_id`/`_code` carries the matched key:

  | Autodraft field | Resolves against |
  |---|---|
  | `supplier.supplier_id` | `suppliers.json` |
  | `buyer.company_code` / `business_unit_code` / `location_code` | `chart_of_books.json` |
  | `taxes[].tax_type_code` | `tax_master.json` |
  | `payment_term_id` | `payment_terms.json` |
  | `po_id` | `po_master.json` |
- **Ground every value** to the document; leave unknown fields empty rather than inventing them.

## Checking your work

Feed one payable to the oracle:

```
python erp.py my_payable.json
# -> {"will_book_gross": 438.00, "currency": "EUR"}
```

Compare `will_book_gross` to the gross the document states. `erp.py` is the same recompute we grade with.
