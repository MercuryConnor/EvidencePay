"""example_check.py — how to call the ERP oracle on one autodraft.

The oracle is `erp.py`. Its entry point is:

    erp_book(payable: dict) -> {"will_book_gross": <float>, "currency": <str>}

This script just loads a payable from a JSON file and prints what the ERP would book, so you
can compare that number to the gross the document states. It is a usage example, nothing more —
you decide what to do with the result.

    python example_check.py                       # uses sample_autodraft.json
    python example_check.py path/to/your.json     # uses your own payable

(Equivalently from the shell: `python erp.py path/to/your.json`.)
"""
import json
import sys

from erp import erp_book

path = sys.argv[1] if len(sys.argv) > 1 else "sample_autodraft.json"
payable = json.load(open(path, encoding="utf-8"))

result = erp_book(payable)          # <-- the one call you need: feed it ONE payable dict
print(f"will_book_gross = {result['will_book_gross']} {result['currency']}")
