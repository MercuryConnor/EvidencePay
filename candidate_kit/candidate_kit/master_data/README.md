# Master data

Reference data the ERP matches against. Resolve a value from the document to its code by matching it against the relevant master. If nothing matches, leave the code empty (`""`) — a blank is a legitimate, honest answer; a fabricated code is not. *How* to match (which fields, how strict) is part of the task.

| File | Resolves |
|---|---|
| `suppliers.json` | `supplier_id` (+ addresses / bank) |
| `chart_of_books.json` | `company_code` / `business_unit_code` / `location_code` |
| `tax_master.json` | `tax_type_code` |
| `payment_terms.json` | `payment_term_id` |
| `po_master.json` | `po_id` (a PO not listed here is a non-ERP reference) |

Not every document's supplier, tax, or PO is present here. That is intentional — part of the task is resolving what *can* be resolved and leaving the rest empty rather than guessing.

**Scale.** These files hold only a **handful of example records**. In a real tenant these masters run to **hundreds of thousands or millions** of entries — design your matching to work at that scale: don't hardcode to the samples you see here, and don't assume a full scan of the master per lookup is free. The shape and field names stay the same; only the row count grows.
