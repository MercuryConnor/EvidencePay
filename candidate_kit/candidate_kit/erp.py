"""erp.py — the ERP recompute you are graded against.

This is the accounting system on the receiving end of your work. Given ONE payable's
raw components (line quantities/prices/discounts and the taxes/charges you assign), it
recomputes the gross it will book and returns that single number.

    erp_book(payable) -> {"will_book_gross": <float>, "currency": <str>}

It reports the gross and nothing else — not whether it is right, not where it differs,
not the internal line/tax structure it built. Comparing that number to what the document
actually says is owed is your job.

Read it — it is the exact contract you must satisfy. Stdlib only, Python 3.10+.
CLI:  python erp.py path/to/payable.json
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

_CURRENCY = set("€$£¥₹ \t")


def num(v: Any) -> float:
    """Parse a plain dot-decimal number. A leading currency symbol and a '%' are stripped.
    Empty or unparseable input becomes 0.0."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").strip()
    i = 0
    while i < len(s) and s[i] in _CURRENCY:
        i += 1
    s = s[i:].strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def round2(x: float) -> float:
    """Round money to 2 decimal places, half-up."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _line_base(li: dict) -> float:
    """The line's net base: quantity x unit_price, less any line discount. Unit price is net."""
    qty = num(li.get("quantity"))
    price = num(li.get("unit_price"))
    disc_pct = abs(num(li.get("discount_percentage")))
    disc_amt = abs(num(li.get("discount")))
    sub_total = qty * price
    if disc_pct > 0:
        return round2(sub_total - (sub_total * disc_pct / 100.0))
    if disc_amt > 0 and qty != 0:
        item_price = price - (disc_amt / abs(qty))
        return round2(item_price * qty)
    return round2(sub_total)


def _line_taxes(li: dict, base: float) -> float:
    """Sum the line's taxes. Each tax is either given as an amount, or derived from its rate
    on the line's net base. Amounts may be negative (e.g. a withholding line-tax)."""
    taxes = li.get("taxes") or []
    if not taxes and (str(li.get("tax_rate") or "").strip() or str(li.get("tax_amount") or "").strip()):
        taxes = [{"tax_rate": li.get("tax_rate", ""), "tax_amount": li.get("tax_amount", "")}]
    line_tax = 0.0
    for t in taxes:
        if not isinstance(t, dict):
            continue
        rate_str = str(t.get("tax_rate") or "").replace("%", "").strip()
        rate = num(rate_str)
        amt = num(t.get("tax_amount"))
        if amt == 0 and rate > 0:
            amt = round2(base * rate / 100.0)
        if rate == 0 and amt == 0 and rate_str == "":
            continue
        line_tax += amt
    return line_tax


def _header_taxes(taxes: Any, net_base: float) -> float:
    """Sum the header taxes. Each is given as an amount, or derived from its rate on the net
    base. Amounts may be negative (e.g. a withholding tax that reduces what is owed)."""
    header_tax = 0.0
    for t in taxes or []:
        if not isinstance(t, dict):
            continue
        rate = num(str(t.get("tax_rate") or "").replace("%", "").strip())
        amt = num(t.get("tax_amount"))
        if amt == 0 and rate > 0:
            amt = round2(net_base * rate / 100.0)
        header_tax += amt
    return header_tax


def erp_book(payable: dict) -> dict:
    """Recompute the gross the ERP will book for one payable, from its raw components.
    Returns {"will_book_gross": <2dp float>, "currency": <str>}."""
    if not isinstance(payable, dict):
        raise ValueError("payable must be a JSON object")

    item_discounted_total = 0.0
    line_tax_total = 0.0
    for li in (payable.get("line_items") or []):
        if not isinstance(li, dict):
            raise ValueError("each line_items[] entry must be a JSON object")
        base = _line_base(li)
        item_discounted_total += base
        line_tax_total += _line_taxes(li, base)

    header_discount = abs(num(payable.get("discount_amount")))
    net_base = item_discounted_total - header_discount
    header_tax = _header_taxes(payable.get("taxes"), net_base)

    other_charges = (
        num(payable.get("freight_charges"))
        + num(payable.get("insurance_charges"))
        + num(payable.get("extra_charges"))
        + num(payable.get("excise_duties"))
    )

    gross = round2(
        item_discounted_total
        - header_discount
        + line_tax_total
        + header_tax
        + other_charges
    )
    return {"will_book_gross": gross, "currency": payable.get("currency", "") or ""}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python erp.py <payable.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as fh:
        _p = json.load(fh)
    print(json.dumps(erp_book(_p)))
