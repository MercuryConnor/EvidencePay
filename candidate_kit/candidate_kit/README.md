# The Bookable Payable
### A 3–4 day engineering challenge

> You will build a system that turns a supplier document into records an accounting system can book. This is not a document-extraction task, though it will look like one for the first few hours. Read the whole brief — including the last section — before you write anything.

---

## The mandate

Given a supplier document as a PDF, produce structured **autodrafts** — the records a downstream accounting system (the *ERP*) uses to book what is owed. You are given the exact record shape, a set of real documents, the reference data the ERP matches against, and one program — `erp.py` — that tells you the gross the ERP will book for any payable you produce.

Your goal is simple to state. Make as many of the documents book correctly as you can.

It is not simple to do. If it were, it would not take three days.

---

## What you are building

For each PDF, your system must decide **what the document is** and **what, if anything, is owed**, and emit one record per bookable payable. A single PDF may contain **no** payable, **one**, or **several** — and may include pages that are not payables at all. Getting that right is part of the task, not a preprocessing detail.

Where a value has a master-data entry — supplier, tax, buyer org, payment term, PO — resolve it against `master_data/` and set the corresponding code in the autodraft; leave that code blank only when there is genuinely no match.

---

## Your materials

| | |
|---|---|
| **`documents/`** | Real documents, provided as PDFs (mostly page images — extraction via OCR / vision / an LLM is up to you). Some are graded in the open; others are held back. Many currencies, several languages, 1–35 lines each. Not every one is an invoice, and **nothing is labelled or categorised.** |
| **`erp.py`** | The ERP recompute. Feed it a payable; it returns the gross it will book. Python 3.10+, **standard library only** (nothing to install). See below. |
| **`example_check.py`** | A minimal usage example: loads a payable JSON and prints `erp_book(...)`'s gross, so you can see which call to make. `python example_check.py [your_payable.json]`. |
| **`AUTODRAFT_SCHEMA.md`** | The exact record shape your system must output. |
| **`master_data/`** | Suppliers, tax reference, organisational structure, payment terms, POs — the reference data you resolve document values against to fill the master-data codes. How to match is up to you. **These are sample rows; real masters scale to hundreds of thousands / millions — design matching accordingly.** |
| **`sample_autodraft.json`** | One worked payable, to show the shape. |

---

## The oracle, and what it refuses to tell you

`erp.py` takes one payable, recomputes it exactly as the ERP will, and returns:

```
{ "will_book_gross": 216.48, "currency": "EUR" }
```

That is the entire response. It tells you the number the ERP will book. It will never tell you whether that number is right, which field is wrong, which line, which tax, or why. That silence is deliberate.

Read `erp.py`. It is short, and it is the exact contract you must satisfy — how the ERP turns your components into a gross. Knowing *how the machine computes* is not the same as knowing *what is unusual about any given document*. The second one is the work.

**`erp.py` is fixed. Do not change how it computes a gross** — we grade with the original, so any edit to its recompute is invisible to us and worthless to you. You may freely *import* it (`from erp import erp_book`), wrap it, or build tooling around it; you may even re-implement it elsewhere for speed. The one thing that must not change is the core calculation. Treat it as a sealed black box you call, not code you own.

---

## What "correct" means, precisely

A payable is correct when the ERP's own recomputation — **from the parts you supplied** — arrives at what the document genuinely says is owed, to the cent.

Sit with the shape of that sentence before you code. You are not being asked whether your output *looks like the document*. You are being asked whether a machine that rebuilds the total from your pieces reaches the truth. A record can mirror the page faithfully and still fail to book. Many of these documents are exactly that record. Understanding how a faithful copy can be a wrong answer is the first door you have to walk through, and most of the difficulty is behind it.

Note too: the ERP can reach the right gross by the wrong path. Two different structures can foot to the same number, and only one of them is the payable that should be booked. Matching the total is necessary. It is not sufficient, and it is not the goal.

**Your autodraft must mirror the document's structure, not just its total.** The grader inspects the shape you emit, not only the number it foots to:

- **Placement is faithful.** A tax the document charges *at the line* belongs on that line (`line_items[].taxes[]` / the line's `tax_rate`); a tax stated *once at the header* belongs at the header (`taxes[]`). Do not migrate a tax from where the document puts it to wherever makes the arithmetic easier — a header rate invented over lines that carry their own rates, or per-line taxes collapsed into one header figure, is wrong even when it foots.
- **Each tax is represented correctly** — its **name**, its **rate**, and its **amount** as the document states them. A line with its own rate keeps that rate; a document with three rates across its lines yields three line-level taxes, not one blended rate.
- **Components stay decomposed.** Quantities, unit prices, discounts, charges and levies go in the fields that describe them — not pre-summed, not folded into each other. If the document itemises it, your record itemises it.

Same total, wrong structure, is a wrong answer. Reproduce *what the document says and where it says it*.

---

## Output contract

Your system runs with **one command** over the `documents/` directory and writes, for each input `X.pdf`, a file `output/X.json` — put **all** results in an `output/` folder (create it if absent), one JSON per input PDF:

```jsonc
{
  "file": "X.pdf",
  "payables": [            // 0..N bookable payables, each conforming to AUTODRAFT_SCHEMA.md
    { "invoice_type": "INVOICE", "currency": "EUR", "gross_total": "...",
      "line_items": [ ... ], "taxes": [ ... ], ... }
  ],
  "declined": [            // any documents you determine are NOT payables (may be empty)
    { "doc_type": "...", "reason": "why this is not a payable" }
  ]
}
```

- One entry in `payables[]` per bookable payable. A document with several payables ⇒ several entries; a document that is not a payable ⇒ `payables: []`.
- A **credit** is a payable of type `CREDIT_MEMO`. It uses the **same schema — the same keys** as any payable; only the values differ. Set `invoice_type: "CREDIT_MEMO"` and fill the ordinary fields (`line_items`, `taxes`, `gross_total`, …) with the credit memo's own figures, as **positive** magnitudes (see `erp.py`'s sign handling). There is no separate credit-memo shape — same record, credit values.
- Anything you judge **not** a payable goes in `declined[]`, never in `payables[]`.

Provide a `README` with a single documented command (a script or a `Dockerfile`) that runs your system over a folder of PDFs and produces these files. We will re-run it.

## Three rules — enforced, and also clues

1. **Every value you emit must appear on the document.** A number that is in your output only because it made the total come out right disqualifies that payable. If you are ever tempted to invent a figure to balance the books, the temptation is telling you something true about the document — listen to it instead of acting on it.
2. **Every code you emit must be a real match** against the master data. "No match" is a legitimate answer. A confident, fabricated code is not.
3. **Any correction your system makes must survive being wrong.** Some documents are built to *look* like they need a fix they do not. A fix that fires where it shouldn't — and corrupts a document that was already correct — costs you more than never fixing anything. Before your system changes a record, ask what independent fact gives it the right to.

---

## What you submit

- The working system (any stack; one documented command over `documents/` writing to `output/`).
- Your generated `output/*.json` for the open documents.
- **`DESIGN.md` (≤3 pages).** Not a feature list. Answer three questions honestly:
  - What did you eventually understand about these documents that you did not understand on day one?
  - When your system meets a document unlike any it has seen, what does it actually *do* — and why does that generalise instead of guessing?
  - Was there a document you concluded could **not** be solved the way the others were? If so, which, and how did you know?

The third question is not padding. At least one document asks something of you that the page does not contain the answer to. Recognising that, and refusing to fake it, is worth more than any code that pretends otherwise.

---

## How you are judged

In the open, your score reflects how many documents book, whether you identified the right payables (and correctly set aside what is not a payable), and a check of what the oracle cannot see — that your codes are real and every value is grounded in the document.

Your **final** standing is decided mostly by the **held-back** documents, graded the same way, which contain situations the open set does not — including at least one you will not have seen before at all. We report one number above your pass rate:

> **the distance between how well you do in the open and how well you do on the held-back set.**

A small distance means you understood the problem. A large one means you fitted the answers. You can make every open document book and still finish poorly if the way you did it falls apart the moment a document does something slightly new. Solving each document is not the same as solving *the problem*, and only one of those is being graded.

---

## Before you start (read this last, then reread it on day two)

The obvious approach — read the fields, fill the record — will book perhaps a third of these, and then stall, and the failures will not look like they have anything in common. There is no list of special cases to implement; if you find yourself building one, adding a branch each time a document defeats you, stop: that growing list is the symptom this problem is designed to produce in people who have not yet seen it whole.

Past that stall there is a shift in how you picture *what one of these documents actually is* — after which the failures stop being a dozen unrelated bugs and become one thing wearing a dozen masks.

We are not going to tell you what that shift is. Arriving at it, unaided, is the exam.
