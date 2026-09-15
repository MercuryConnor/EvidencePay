"""Master Data Loader — loads all master data, builds normalised indexes.

This is the ONLY module that reads from disk. All matching modules
get their data from the loaded store.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default master data path
_MASTER_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "candidate_kit" / "candidate_kit" / "master_data"

# ── In-memory store (loaded once, shared by all matchers) ──

suppliers: list[dict] = []
chart_of_books: list[dict] = []      # flattened: company → BU → location
tax_master: list[dict] = []
payment_terms: list[dict] = []
po_master: list[dict] = []

# ── Normalised indexes ──

supplier_by_vat: dict[str, dict] = {}
supplier_by_iban: dict[str, dict] = {}
supplier_by_name_lower: dict[str, dict] = {}

tax_by_country_rate: dict[str, list[dict]] = {}

po_by_number: dict[str, dict] = {}

payment_by_days: dict[int, dict] = {}

_loaded: bool = False


def load_master_data(master_dir: Path | None = None) -> None:
    """Load all master data files and build normalised indexes.

    Safe to call multiple times — will no-op if already loaded.
    """
    global _loaded
    if _loaded:
        return

    master_dir = master_dir or _MASTER_DATA_DIR

    _load_suppliers(master_dir)
    _load_chart_of_books(master_dir)
    _load_tax_master(master_dir)
    _load_payment_terms(master_dir)
    _load_po_master(master_dir)

    _loaded = True
    logger.info(
        "Master data loaded: %d suppliers, %d orgs, %d taxes, %d payment_terms, %d POs",
        len(suppliers), len(chart_of_books), len(tax_master),
        len(payment_terms), len(po_master),
    )


def ensure_loaded() -> None:
    """Ensure master data is loaded. Called by matchers."""
    if not _loaded:
        load_master_data()


def _load_suppliers(master_dir: Path) -> None:
    global suppliers, supplier_by_vat, supplier_by_iban, supplier_by_name_lower

    with open(master_dir / "suppliers.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    suppliers = data.get("suppliers", [])

    for s in suppliers:
        vat = s.get("vat_id", "").strip().upper()
        if vat:
            supplier_by_vat[vat] = s

        iban = s.get("bank_iban", "").strip().upper().replace(" ", "")
        if iban:
            supplier_by_iban[iban] = s

        name = s.get("name", "").strip().lower()
        if name:
            supplier_by_name_lower[name] = s


def _load_chart_of_books(master_dir: Path) -> None:
    global chart_of_books

    with open(master_dir / "chart_of_books.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for company in data.get("companies", []):
        company_code = company.get("company_code", "")
        company_name = company.get("company_name", "")
        for bu in company.get("business_units", []):
            bu_code = bu.get("business_unit_code", "")
            bu_name = bu.get("business_unit_name", "")
            for loc in bu.get("locations", []):
                chart_of_books.append({
                    "company_code": company_code,
                    "company_name": company_name,
                    "business_unit_code": bu_code,
                    "business_unit_name": bu_name,
                    "location_code": loc.get("location_code", ""),
                    "location_name": loc.get("location_name", ""),
                    "invoice_to_address": loc.get("invoice_to_address", ""),
                })


def _load_tax_master(master_dir: Path) -> None:
    global tax_master, tax_by_country_rate

    with open(master_dir / "tax_master.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    tax_master = data.get("taxes", [])

    for t in tax_master:
        country = t.get("country", "").upper()
        rate = float(t.get("rate", 0))
        tax_type = t.get("tax_type", "").upper()

        # Index by country+rate (normalised float)
        key_cr = f"{country}_{rate}"
        tax_by_country_rate.setdefault(key_cr, []).append(t)

        # Index by country+type+rate (more specific)
        key_ctr = f"{country}_{tax_type}_{rate}"
        tax_by_country_rate.setdefault(key_ctr, []).append(t)


def _load_payment_terms(master_dir: Path) -> None:
    global payment_terms, payment_by_days

    with open(master_dir / "payment_terms.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    payment_terms = data.get("payment_terms", [])

    for pt in payment_terms:
        days = pt.get("days", -1)
        if days >= 0:
            payment_by_days[days] = pt


def _load_po_master(master_dir: Path) -> None:
    global po_master, po_by_number

    with open(master_dir / "po_master.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    po_master = data.get("purchase_orders", [])

    for po in po_master:
        po_num = po.get("po_number", "").strip()
        if po_num:
            po_by_number[po_num] = po
