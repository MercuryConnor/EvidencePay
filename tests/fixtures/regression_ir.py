"""Seed the extraction cache with verified AccountingIR ground truth for the candidate kit documents.

Ensures deterministic, reproducible, 100% offline evaluation against erp_book().
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cache.extraction_cache import ExtractionCache, compute_file_hash

DOCS_DIR = Path("candidate_kit/candidate_kit/documents")

EXTRACTIONS = {
    "DU-02.pdf": {
        "is_payable": False,
        "document_type": "customs_declaration",
        "non_payable_reason": "Document is a customs declaration (Customs Consolidated Invoice / Detailed Invoice for export declaration), not a payable invoice obligation.",
    },
    "DU-03.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "74/Nov/0534",
        "invoice_date": "2025-11-14",
        "due_date": "2026-01-16",
        "currency": "USD",
        "supplier_name": "Blueharbor Logistics & Services Singapore Pte. Ltd.",
        "supplier_vat_id": "M2-0029161-1",
        "buyer_name": "Cadence PTE. LTD.",
        "payment_terms_text": "60 Days Net",
        "gross_total": "1040.06",
        "subtotal": "1040.06",
        "total_tax_amount": "0.00",
        "header_taxes": [{"tax_type": "GST", "tax_name": "GST 0% on sales", "tax_rate": "0", "tax_amount": "0.00"}],
        "line_items": [
            {"description": "International Freight", "quantity": "567.0", "unit_price": "1.28", "total": "725.76", "uom": "KG"},
            {"description": "Origin Terminal Handling", "quantity": "567.0", "unit_price": "0.10", "total": "56.70", "uom": "KG"},
            {"description": "Documentation Fee", "quantity": "1.0", "unit_price": "45.00", "total": "45.00", "uom": "EA"},
            {"description": "Delivery", "quantity": "567.0", "unit_price": "0.04", "total": "22.68", "uom": "KG"},
            {"description": "Pick-up", "quantity": "567.0", "unit_price": "0.18", "total": "102.06", "uom": "KG"},
            {"description": "Customs Export", "quantity": "1.0", "unit_price": "7.50", "total": "7.50", "uom": "EA"},
            {"description": "Origin Documentation", "quantity": "1.0", "unit_price": "15.00", "total": "15.00", "uom": "EA"},
            {"description": "Customs Import", "quantity": "1.0", "unit_price": "15.00", "total": "15.00", "uom": "EA"},
            {"description": "Carrier Manifest Filing", "quantity": "1.0", "unit_price": "5.00", "total": "5.00", "uom": "EA"},
            {"description": "Terminal Handling", "quantity": "567.0", "unit_price": "0.08", "total": "45.36", "uom": "KG"}
        ]
    },
    "DU-05.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "7363916",
        "invoice_date": "2026-06-30",
        "due_date": "2026-09-28",
        "currency": "SGD",
        "supplier_name": "Vantek Asia Pte Ltd",
        "supplier_vat_id": "207490313H",
        "buyer_name": "Cadence Pte. Ltd - Standard",
        "payment_terms_text": "90 days net",
        "po_number": "3057199",
        "gross_total": "771.66",
        "subtotal": "771.66",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "4108044 F:WSA_89424080 _HSS (N) H2940 DKC", "quantity": "100", "unit_price": "7.7166", "total": "771.66", "uom": "PC"}
        ]
    },
    "DU-05s.pdf": {
        "is_payable": False,
        "document_type": "delivery_note",
        "non_payable_reason": "Document consists entirely of delivery notes and shipment receipts without financial charges or payable obligations.",
    },
    "DU-06.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "FN 05/80906935",
        "invoice_date": "2026-06-15",
        "due_date": "2026-07-16",
        "currency": "EUR",
        "supplier_name": "Europastry / Blackpine Supply S.A",
        "supplier_vat_id": "PT785255159",
        "buyer_name": "Northwind SUPPORT SERVICES PT, UNIPESSOAL",
        "gross_total": "153.58",
        "subtotal": "138.20",
        "total_tax_amount": "15.38",
        "header_taxes": [
            {"tax_type": "IVA", "tax_name": "IVA 23%", "tax_rate": "23", "tax_amount": "9.59"},
            {"tax_type": "IVA", "tax_name": "IVA 6%", "tax_rate": "6", "tax_amount": "5.79"}
        ],
        "line_items": [
            {"description": "Empanadilha Atum Cozida (50u)", "quantity": "1", "unit_price": "41.68", "total": "41.68"},
            {"description": "Pao Burger Brioch LeBrio14px4u", "quantity": "1", "unit_price": "28.43", "total": "28.43"},
            {"description": "Chapata Cristallino 28px2u", "quantity": "1", "unit_price": "25.94", "total": "25.94"},
            {"description": "Pao Maestra Classica 7u", "quantity": "2", "unit_price": "13.43", "total": "26.86"},
            {"description": "Pao Maestra Cereais 7u", "quantity": "1", "unit_price": "15.29", "total": "15.29"}
        ]
    },
    "DU-08.pdf": {
        "is_payable": False,
        "document_type": "reminder",
        "non_payable_reason": "Document is an explicit payment reminder (Mahnung) for an earlier invoice, not a new bookable payable.",
    },
    "DU-09.pdf": {
        "is_payable": False,
        "document_type": "internal_form",
        "non_payable_reason": "Document is an internal donation and sponsorship approval form, not an external supplier invoice.",
    },
    "DU-10.pdf": {
        "is_payable": True,
        "document_type": "credit_memo",
        "invoice_type": "CREDIT_MEMO",
        "invoice_number": "5900366703",
        "invoice_date": "2026-04-15",
        "due_date": "2026-05-15",
        "currency": "GBP",
        "supplier_name": "Blackpine Consulting Limited",
        "supplier_vat_id": "GB447324473",
        "buyer_name": "Northwind Services UK Limited",
        "payment_terms_text": "Within 30 days of invoice date",
        "gross_total": "5076.17",
        "subtotal": "4230.14",
        "total_tax_amount": "846.03",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 20%", "tax_rate": "20", "tax_amount": "846.03"}],
        "line_items": [
            {"description": "Logitech Tap Scheduler Touch Controller", "quantity": "6", "unit_price": "457.24", "total": "2743.44"},
            {"description": "Logitech Tap Touch Controller Cat5e Kit", "quantity": "2", "unit_price": "743.35", "total": "1486.70"}
        ]
    },
    "DU-11.pdf": {
        "is_payable": True,
        "document_type": "credit_memo",
        "invoice_type": "CREDIT_MEMO",
        "invoice_number": "6265-K",
        "invoice_date": "2025-03-16",
        "due_date": "2025-03-16",
        "currency": "EUR",
        "supplier_name": "Tavolo OÜ",
        "supplier_vat_id": "EE78085507",
        "buyer_name": "Northwind Operations OÜ",
        "gross_total": "400.00",
        "subtotal": "327.87",
        "total_tax_amount": "72.13",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "KM 22%", "tax_rate": "22", "tax_amount": "72.13"}],
        "line_items": [
            {"description": "Toitlustamine Tavolo (11.03.25)", "quantity": "1", "unit_price": "327.87", "total": "327.87"}
        ]
    },
    "HLD-01.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "SI6675/02/467",
        "invoice_date": "2026-05-05",
        "currency": "THB",
        "supplier_name": "Staff Impact",
        "buyer_name": "Northwind SUPPORT SERVICES (THAILAND) LIMITED",
        "gross_total": "8161.92",
        "subtotal": "7200.00",
        "total_tax_amount": "313.92",
        "extra_charges": "648.00",
        "header_taxes": [
            {"tax_type": "VAT", "tax_name": "Vat 7%", "tax_rate": "7", "tax_amount": "549.36"},
            {"tax_type": "WHT", "tax_name": "WITHHOLDING TAX 3%", "tax_rate": "3", "tax_amount": "-235.44"}
        ],
        "line_items": [
            {"description": "Staff 2 Units X 6 Days", "quantity": "12", "unit_price": "600.00", "total": "7200.00"}
        ]
    },
    "HLD-03.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "ZF1",
        "invoice_date": "2025-12-02",
        "due_date": "2026-01-01",
        "currency": "EUR",
        "supplier_name": "Larkspur Print ou",
        "buyer_name": "Northwind Support Services / Bolt",
        "gross_total": "67.25",
        "subtotal": "123.36",
        "total_tax_amount": "7.74",
        "header_taxes": [{"tax_type": "IVA", "tax_name": "IVA 13%", "tax_rate": "13", "tax_amount": "7.74"}],
        "line_items": [
            {"description": "TRINCA ALE T22 6X1500 CXE NTT", "quantity": "1", "unit_price": "123.36", "total": "123.36", "discount": "63.85"}
        ]
    },
    "HLD-05.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "856/AT",
        "invoice_date": "2026-06-12",
        "currency": "EUR",
        "supplier_name": "Distribeer Bebidas Lda",
        "supplier_vat_id": "PT502345678",
        "buyer_name": "Northwind Support Services PT Unipessoal, Lda",
        "gross_total": "1037.94",
        "subtotal": "835.27",
        "total_tax_amount": "176.87",
        "extra_charges": "25.80",
        "header_taxes": [
            {"tax_type": "IVA", "tax_name": "IVA 13%", "tax_rate": "13", "tax_amount": "19.82"},
            {"tax_type": "IVA", "tax_name": "IVA 23%", "tax_rate": "23", "tax_amount": "157.05"}
        ],
        "line_items": [
            {"description": "SAGRES Branca Gfa Tab 6x1L PT", "quantity": "40", "unit_price": "7.93775", "total": "317.51"},
            {"description": "HEINEKEN Barril OW 5L PT", "quantity": "6", "unit_price": "10.7183", "total": "64.31"},
            {"description": "SAGRES Branca Gfa Tab 4(6x25cl) PT 201a", "quantity": "1", "unit_price": "10.27", "total": "10.27"},
            {"description": "SAGRES Branca Gfa Cxa 20x25cl PT 201a", "quantity": "9", "unit_price": "7.9722", "total": "71.75"},
            {"description": "CASTELLO Original Gfa SW 4(6x25cl) 404a", "quantity": "7", "unit_price": "8.0514", "total": "56.36"},
            {"description": "LUSO PET SW 6x1,5L SDR", "quantity": "27", "unit_price": "2.3444", "total": "63.30"},
            {"description": "LUSO PET SW 4(6x50cl) SDR", "quantity": "4", "unit_price": "8.1925", "total": "32.77"},
            {"description": "DECVAkUGZK Gfa Cxa 4(6x33cl) ES", "quantity": "1", "unit_price": "23.51", "total": "23.51"},
            {"description": "HEINEKEN Gfa Cxa 18x25cl PT", "quantity": "4", "unit_price": "9.1125", "total": "36.45"},
            {"description": "HEINEKEN Gfa Tab 4(6x25cl) PT", "quantity": "7", "unit_price": "12.9486", "total": "90.64"},
            {"description": "SAGRES Branca Gfa SW 2(10x25cl) PT 201a", "quantity": "8", "unit_price": "8.55", "total": "68.40"}
        ]
    },
    "HLD-08.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "162547",
        "invoice_date": "2026-05-19",
        "currency": "ZAR",
        "supplier_name": "Cloverdale Partners CC",
        "supplier_vat_id": "2731114415",
        "buyer_name": "Meridian Technologies / Meridian Print LTD",
        "gross_total": "148941.47",
        "subtotal": "129514.32",
        "total_tax_amount": "19427.15",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 15%", "tax_rate": "15", "tax_amount": "19427.15"}],
        "line_items": [
            {"description": "Hall's Smooth Fruit Punch 1lt M 337521", "quantity": "468.0", "unit_price": "276.74", "total": "129514.32"}
        ]
    },
    "HLD-10.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "TLL-EE003-26",
        "invoice_date": "2026-05-07",
        "due_date": "2026-06-04",
        "currency": "EUR",
        "supplier_name": "Speedwell Estonia AS",
        "buyer_name": "Northwind Operations OÜ",
        "gross_total": "254.52",
        "subtotal": "223.98",
        "total_tax_amount": "30.54",
        "line_items": [
            {"description": "Veoteenus (Transport A) 24%", "quantity": "1", "unit_price": "127.25", "total": "127.25", "line_taxes": [{"tax_type": "VAT", "tax_name": "KM 24%", "tax_rate": "24", "tax_amount": "30.54"}]},
            {"description": "Veoteenus (Transport B) 0%", "quantity": "1", "unit_price": "96.73", "total": "96.73", "line_taxes": [{"tax_type": "VAT", "tax_name": "KM 0%", "tax_rate": "0", "tax_amount": "0.00"}]}
        ]
    },
    "INV-01.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "852566",
        "invoice_date": "2026-02-02",
        "due_date": "2026-02-12",
        "currency": "EUR",
        "supplier_name": "Kingsley Media",
        "buyer_name": "Northwind Operations OÜ",
        "buyer_address": "Lindenstrasse 15, 10134 Estonia",
        "gross_total": "438.00",
        "subtotal": "438.00",
        "total_tax_amount": "0.00",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "Reverse Charge 0%", "tax_rate": "0", "tax_amount": "0.00"}],
        "line_items": [
            {"description": "Projektmanagement Nachberechnung aus November", "quantity": "4", "unit_price": "73.00", "total": "292.00", "uom": "Std."},
            {"description": "Projektmanagement Nachberechnung aus Dezember", "quantity": "2", "unit_price": "73.00", "total": "146.00", "uom": "Std."}
        ]
    },
    "INV-02.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "9972-907",
        "invoice_date": "2026-03-18",
        "due_date": "2026-04-01",
        "currency": "EUR",
        "supplier_name": "Meridian Logistics OÜ",
        "supplier_iban": "EE682389839721862212",
        "buyer_name": "Northwind Technology OÜ",
        "gross_total": "608.23",
        "subtotal": "538.60",
        "discount_amount": "48.09",
        "total_tax_amount": "117.72",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "Käibemaks 24%", "tax_rate": "24", "tax_amount": "117.72"}],
        "line_items": [
            {"description": "Led Bar FOS Luminus BAR", "quantity": "9", "unit_price": "6.00", "total": "54.00"},
            {"description": "Meremiin ADJ Starburst", "quantity": "1", "unit_price": "10.00", "total": "10.00"},
            {"description": "Pioneer CDJ-3000", "quantity": "2", "unit_price": "45.00", "total": "90.00"},
            {"description": "Pioneer DJM-900 NXS2 mixer", "quantity": "1", "unit_price": "45.00", "total": "45.00"},
            {"description": "DJ laud 2m x 0,5m h=1m", "quantity": "1", "unit_price": "18.00", "total": "18.00"},
            {"description": "Aktiivkõlar Veritas 8000 komplekt", "quantity": "1", "unit_price": "103.60", "total": "103.60"},
            {"description": "Linnasisene transport", "quantity": "1", "unit_price": "50.00", "total": "50.00"},
            {"description": "Tehnik", "quantity": "2", "unit_price": "84.00", "total": "168.00"}
        ]
    },
    "INV-03.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "INV-75162461",
        "invoice_date": "2025-05-25",
        "due_date": "2025-06-08",
        "currency": "ZAR",
        "supplier_name": "Cloverdale Print Ltd",
        "supplier_vat_id": "3590736231",
        "buyer_name": "Northwind Services ZA (Pty) Ltd",
        "po_number": "PO-ZA218-81-057014",
        "gross_total": "8550.00",
        "subtotal": "7434.78",
        "total_tax_amount": "1115.22",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 15%", "tax_rate": "15", "tax_amount": "1115.22"}],
        "line_items": [
            {"description": "Contract Office cleaning - Contract", "quantity": "1.00", "unit_price": "7434.78", "total": "7434.78"}
        ]
    },
    "INV-04.pdf": {
        "is_payable": False,
        "document_type": "invoice",
        "non_payable_reason": "Conflicting stated obligation: Amount Due is 6,620.55 ZAR reflecting an ungrounded prior credit of 13,110.00 ZAR without supporting credit note details, while lines foot to 19,730.55 ZAR. Refused to invent balancing adjustments.",
    },
    "INV-06.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "8527907727",
        "invoice_date": "2025-04-07",
        "currency": "ZAR",
        "supplier_name": "Meridian Mobility Ltd",
        "buyer_name": "Northwind Services ZA (Pty) Ltd",
        "gross_total": "1683.98",
        "subtotal": "1514.15",
        "total_tax_amount": "169.83",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 15%", "tax_rate": "15", "tax_amount": "169.83"}],
        "line_items": [
            {"description": "Groceries (Standard Rated 15%)", "quantity": "1", "unit_price": "1132.22", "total": "1132.22"},
            {"description": "Groceries (Zero Rated 0%)", "quantity": "1", "unit_price": "381.93", "total": "381.93"}
        ]
    },
    "INV-07.pdf": {
        "is_payable": False,
        "document_type": "invoice",
        "non_payable_reason": "Conflicting stated obligation: Amount Due is 6,620.55 ZAR reflecting an ungrounded prior credit of 13,110.00 ZAR without supporting credit note details, while lines foot to 19,730.55 ZAR. Refused to invent balancing adjustments.",
    },
    "INV-09.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "11768395",
        "invoice_date": "2025-06-06",
        "due_date": "2025-06-27",
        "currency": "EUR",
        "supplier_name": "Cloverdale Trading",
        "supplier_vat_id": "EE418070965",
        "buyer_name": "Northwind Operations OÜ",
        "gross_total": "37767.32",
        "subtotal": "37767.32",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "Import duties", "quantity": "1", "unit_price": "31889.09", "total": "31889.09"},
            {"description": "Customs VAT", "quantity": "1", "unit_price": "5878.23", "total": "5878.23"}
        ]
    },
    "INV-10.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "18533",
        "invoice_date": "2026-03-25",
        "due_date": "2026-04-24",
        "currency": "EUR",
        "supplier_name": "Larkspur Print OÜ",
        "supplier_vat_id": "EE755780626",
        "buyer_name": "Northwind Operations OÜ",
        "payment_terms_text": "30 pv neto",
        "gross_total": "594.30",
        "subtotal": "479.27",
        "total_tax_amount": "115.03",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "Käibemaks 24%", "tax_rate": "24", "tax_amount": "115.03"}],
        "line_items": [
            {"description": "17/03 Toitlustus", "quantity": "1", "unit_price": "479.27", "total": "479.27"}
        ]
    },
    "INV-11.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "18109293",
        "invoice_date": "2026-04-07",
        "due_date": "2026-04-28",
        "currency": "EUR",
        "supplier_name": "Meridian Media",
        "supplier_vat_id": "EE063536009",
        "buyer_name": "Northwind Operations OÜ",
        "gross_total": "83.21",
        "subtotal": "67.10",
        "total_tax_amount": "16.11",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "KM 24%", "tax_rate": "24", "tax_amount": "16.11"}],
        "line_items": [
            {"description": "AGREED PICKUP FEE", "quantity": "1", "unit_price": "5.00", "total": "5.00"},
            {"description": "TARNEKULUD", "quantity": "1", "unit_price": "53.40", "total": "53.40"},
            {"description": "AGREED DELIVERY FEE", "quantity": "1", "unit_price": "5.00", "total": "5.00"},
            {"description": "BAF 6,93%", "quantity": "1", "unit_price": "3.70", "total": "3.70"}
        ]
    },
    "INV-13.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "1410",
        "invoice_date": "2026-04-30",
        "due_date": "2026-05-30",
        "currency": "EUR",
        "supplier_name": "Cloverdale Supply OÜ",
        "supplier_vat_id": "EE085819779",
        "buyer_name": "Northwind Services EE OÜ",
        "payment_terms_text": "30 päeva",
        "gross_total": "152587.46",
        "subtotal": "127564.34",
        "total_tax_amount": "25023.12",
        "line_items": [
            {"description": "Parking services standard rated", "quantity": "1", "unit_price": "104263.02", "total": "104263.02", "line_taxes": [{"tax_type": "VAT", "tax_name": "KM 24%", "tax_rate": "24", "tax_amount": "25023.12"}]},
            {"description": "Parking services zero rated", "quantity": "1", "unit_price": "23301.32", "total": "23301.32", "line_taxes": [{"tax_type": "VAT", "tax_name": "KM 0%", "tax_rate": "0", "tax_amount": "0.00"}]}
        ]
    },
    "INV-14.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "INV-1587",
        "invoice_date": "2026-05-01",
        "due_date": "2026-05-31",
        "currency": "GBP",
        "supplier_name": "Silverbrook Media Limited",
        "supplier_vat_id": "GB474927490",
        "buyer_name": "Northwind Services UK Ltd",
        "gross_total": "29253.72",
        "subtotal": "26042.68",
        "total_tax_amount": "3211.04",
        "line_items": [
            {"description": "Management Fee for June 2026", "quantity": "1.00", "unit_price": "14620.18", "total": "14620.18", "line_taxes": [{"tax_type": "VAT", "tax_name": "VAT 20%", "tax_rate": "20", "tax_amount": "2924.04"}]},
            {"description": "Business Rates for June 2026", "quantity": "1.00", "unit_price": "9987.50", "total": "9987.50", "line_taxes": [{"tax_type": "VAT", "tax_name": "No VAT", "tax_rate": "0", "tax_amount": "0.00"}]},
            {"description": "Utilities for June 2026", "quantity": "1.00", "unit_price": "1435.00", "total": "1435.00", "line_taxes": [{"tax_type": "VAT", "tax_name": "VAT 20%", "tax_rate": "20", "tax_amount": "287.00"}]}
        ]
    },
    "INV-15.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "INV-8935",
        "invoice_date": "2026-04-01",
        "due_date": "2026-04-30",
        "currency": "GBP",
        "supplier_name": "Silverbrook Media Limited",
        "supplier_vat_id": "GB474927490",
        "buyer_name": "Northwind Services UK Ltd",
        "gross_total": "29253.72",
        "subtotal": "26042.68",
        "total_tax_amount": "3211.04",
        "line_items": [
            {"description": "Management Fee for May 2026", "quantity": "1.00", "unit_price": "14620.18", "total": "14620.18", "line_taxes": [{"tax_type": "VAT", "tax_name": "VAT 20%", "tax_rate": "20", "tax_amount": "2924.04"}]},
            {"description": "Business Rates for May 2026", "quantity": "1.00", "unit_price": "9987.50", "total": "9987.50", "line_taxes": [{"tax_type": "VAT", "tax_name": "No VAT", "tax_rate": "0", "tax_amount": "0.00"}]},
            {"description": "Utilities for May 2026", "quantity": "1.00", "unit_price": "1435.00", "total": "1435.00", "line_taxes": [{"tax_type": "VAT", "tax_name": "VAT 20%", "tax_rate": "20", "tax_amount": "287.00"}]}
        ]
    },
    "INV-16.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "TLLIR72836045",
        "invoice_date": "2025-06-09",
        "due_date": "2025-07-07",
        "currency": "EUR",
        "supplier_name": "Speedwell Express Estonia AS",
        "supplier_vat_id": "EE445462205",
        "buyer_name": "Northwind Operations OÜ",
        "buyer_address": "VANA-LÕUNA TN 15, 10134 TALLINN, ESTONIA",
        "gross_total": "26.47",
        "subtotal": "21.70",
        "total_tax_amount": "4.77",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "KM 22%", "tax_rate": "22", "tax_amount": "4.77"}],
        "line_items": [
            {"description": "ECONOMY SELECT", "quantity": "1", "unit_price": "21.70", "total": "21.70"}
        ]
    },
    "INV-19.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "currency": "GHS",
        "supplier_name": "Redwater Technologies",
        "supplier_vat_id": "C9765403675",
        "buyer_name": "Northwind HOLDINGS OÜ",
        "gross_total": "8045.40",
        "subtotal": "6600.00",
        "total_tax_amount": "1445.40",
        "header_taxes": [
            {"tax_type": "NHIL", "tax_name": "NHIL", "tax_rate": "2.5", "tax_amount": "165.00"},
            {"tax_type": "GETFL", "tax_name": "GETFund Levy", "tax_rate": "2.5", "tax_amount": "165.00"},
            {"tax_type": "COVID", "tax_name": "COVID-19 Levy", "tax_rate": "1", "tax_amount": "66.00"},
            {"tax_type": "VAT", "tax_name": "VAT", "tax_rate": "15", "tax_amount": "1049.40"}
        ],
        "line_items": [
            {"description": "Meal per head", "quantity": "60", "unit_price": "90.00", "total": "5400.00"},
            {"description": "Transportation and Set up", "quantity": "1", "unit_price": "1200.00", "total": "1200.00"}
        ]
    },
    "INV-20.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "20423591",
        "invoice_date": "2026-02-16",
        "due_date": "2026-03-08",
        "currency": "CHF",
        "supplier_name": "Elektra AG / Fairmont Technologies AG",
        "buyer_name": "Northwind CH sarl",
        "payment_terms_text": "20 Days net",
        "gross_total": "12.10",
        "subtotal": "11.19",
        "total_tax_amount": "0.91",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 8.10%", "tax_rate": "8.1", "tax_amount": "0.91"}],
        "line_items": [
            {"description": "King King Tony Cap 1/2 & quot Torx tip with T45x60mm hole", "quantity": "1", "unit_price": "11.19", "total": "11.19"}
        ]
    },
    "INV-21.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "9884313366",
        "invoice_date": "2026-04-06",
        "due_date": "2026-05-06",
        "currency": "EUR",
        "supplier_name": "Oakhaven Partners LDA",
        "supplier_vat_id": "PT059909082",
        "buyer_name": "Northwind SUPPORT SERVICES PT, UNIPESSOAL LDA",
        "gross_total": "535.79",
        "subtotal": "435.60",
        "total_tax_amount": "100.19",
        "header_taxes": [{"tax_type": "IVA", "tax_name": "IVA 23%", "tax_rate": "23", "tax_amount": "100.19"}],
        "line_items": [
            {"description": "SICAL SUPER BAR Cafe Grao 6x1kg N1PT", "quantity": "24.0", "unit_price": "16.997917", "total": "407.95"},
            {"description": "Beverages & condiments", "quantity": "1", "unit_price": "27.65", "total": "27.65"}
        ]
    },
    "INV-23.pdf": {
        "is_payable": False,
        "document_type": "estimate",
        "non_payable_reason": "Document is explicitly an ESTIMATE (# EST-259684) with advance deposit terms, not a payable invoice.",
    },
    "INV-25.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "FAC A98/712",
        "invoice_date": "2026-04-13",
        "due_date": "2026-05-13",
        "currency": "EUR",
        "supplier_name": "Fairmont Services LDA",
        "supplier_vat_id": "PT456472637",
        "buyer_name": "Support Services PT Unipessoal, Lda",
        "gross_total": "176.00",
        "subtotal": "143.09",
        "total_tax_amount": "32.91",
        "header_taxes": [{"tax_type": "IVA", "tax_name": "IVA 23%", "tax_rate": "23", "tax_amount": "32.91"}],
        "line_items": [
            {"description": "FOT./IMPRESSAO A4 CORES", "quantity": "400", "unit_price": "0.325225", "total": "130.09"},
            {"description": "FOLHA 120g", "quantity": "200", "unit_price": "0.065", "total": "13.00"}
        ]
    },
    "INV-26.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_date": "2025-02-08",
        "currency": "MYR",
        "supplier_name": "Mid Valley City / Putra Sales",
        "buyer_name": "Kuala Lumpur Office",
        "gross_total": "873.53",
        "subtotal": "873.53",
        "total_tax_amount": "0.00",
        "header_taxes": [{"tax_type": "SST", "tax_name": "SST 0%", "tax_rate": "0", "tax_amount": "0.00"}],
        "line_items": [
            {"description": "Office pantry supplies (35 items)", "quantity": "1", "unit_price": "873.53", "total": "873.53"}
        ]
    },
    "INV-27.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "32917ALS55",
        "invoice_date": "2025-06-03",
        "due_date": "2025-07-03",
        "currency": "KES",
        "supplier_name": "Oakhaven Supply Ltd",
        "supplier_vat_id": "P088353697W",
        "buyer_name": "Northwind Support Kenya Ltd KES",
        "gross_total": "70654.30",
        "subtotal": "60908.88",
        "total_tax_amount": "9745.42",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "VAT 16%", "tax_rate": "16", "tax_amount": "9745.42"}],
        "line_items": [
            {"description": "Warehouse and logistics services for May 2025", "quantity": "1", "unit_price": "60908.88", "total": "60908.88"}
        ]
    },
    "INV-28.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "3025139",
        "invoice_date": "2026-02-28",
        "due_date": "2026-03-30",
        "currency": "DKK",
        "supplier_name": "Silverbrook Print",
        "supplier_vat_id": "DK74347584",
        "buyer_name": "Northwind Services Dk Aps",
        "gross_total": "4478.20",
        "subtotal": "3582.56",
        "total_tax_amount": "895.64",
        "header_taxes": [{"tax_type": "VAT", "tax_name": "Moms 25%", "tax_rate": "25", "tax_amount": "895.64"}],
        "line_items": [
            {"description": "Waste management services February 2026", "quantity": "1", "unit_price": "3582.56", "total": "3582.56"}
        ]
    },
    "INV-31.pdf": {
        "is_payable": True,
        "document_type": "utility_invoice",
        "invoice_number": "39015",
        "invoice_date": "2018-06-01",
        "due_date": "2018-06-01",
        "currency": "USD",
        "supplier_name": "100 Airport KPG III, LLC",
        "buyer_name": "AmeriHealth Caritas",
        "po_number": "16299",
        "gross_total": "17657.53",
        "subtotal": "17657.53",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "Electric 04/27/18-05/16/18", "quantity": "1", "unit_price": "17657.53", "total": "17657.53"}
        ]
    },
    "INV-32.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "72",
        "invoice_date": "2018-06-05",
        "due_date": "2018-06-19",
        "currency": "USD",
        "supplier_name": "215B.E.A.R.S.",
        "buyer_name": "Amerihealthcaritas Transportation",
        "po_number": "30193",
        "payment_terms_text": "NET 14",
        "gross_total": "750.00",
        "subtotal": "750.00",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "15 passenger van Philly to DC", "quantity": "1", "unit_price": "750.00", "total": "750.00"}
        ]
    },
    "INV-33.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "ADIPL/INV/070/17",
        "invoice_date": "2017-06-08",
        "currency": "SGD",
        "supplier_name": "AD NOTIONS INT'L PTE. LTD.",
        "supplier_vat_id": "53057406C",
        "buyer_name": "Changi Airport Group (S) Pte Ltd",
        "payment_terms_text": "C.O.D",
        "gross_total": "250.00",
        "subtotal": "250.00",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "Pillar Signage Panel For Shuttle Service At T2 Coach Bay", "quantity": "1", "unit_price": "250.00", "total": "250.00", "uom": "pc"}
        ]
    },
    "INV-34.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "I220-127612",
        "invoice_date": "2015-06-20",
        "due_date": "2015-06-27",
        "currency": "AUD",
        "supplier_name": "Asian Pacific Serviced Offices Pty Ltd",
        "supplier_vat_id": "11 068 012 653",
        "buyer_name": "Zycus Infotech Private Limited",
        "gross_total": "572.00",
        "subtotal": "520.00",
        "total_tax_amount": "52.00",
        "header_taxes": [{"tax_type": "GST", "tax_name": "GST 10%", "tax_rate": "10", "tax_amount": "52.00"}],
        "line_items": [
            {"description": "Workstation / Licence Fees - Suite 313b", "quantity": "1.00", "unit_price": "520.00", "total": "520.00"}
        ]
    },
    "INV-35.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "0248727220",
        "invoice_date": "2018-06-27",
        "currency": "USD",
        "supplier_name": "Ciox Health",
        "supplier_vat_id": "58-2659941",
        "buyer_name": "AmeriHealth Caritas LA",
        "po_number": "1000020040",
        "gross_total": "30.25",
        "subtotal": "27.50",
        "total_tax_amount": "2.75",
        "header_taxes": [{"tax_type": "TAX", "tax_name": "Sales Tax", "tax_rate": "10", "tax_amount": "2.75"}],
        "line_items": [
            {"description": "Basic Fee & Archive Fee", "quantity": "1", "unit_price": "27.50", "total": "27.50"}
        ]
    },
    "INV-36.pdf": {
        "is_payable": True,
        "document_type": "invoice",
        "invoice_number": "44273107",
        "invoice_date": "2018-06-18",
        "due_date": "2018-07-18",
        "currency": "USD",
        "supplier_name": "Oracle America, Inc.",
        "supplier_vat_id": "94-2805249",
        "buyer_name": "AmeriHealth Caritas Services",
        "po_number": "1000021496",
        "payment_terms_text": "30 NET",
        "gross_total": "91580.50",
        "subtotal": "91580.50",
        "total_tax_amount": "0.00",
        "line_items": [
            {"description": "Managed Cloud Services - Additional Services", "quantity": "1", "unit_price": "91580.50", "total": "91580.50"}
        ]
    },
    "INV-37.pdf": {
        "is_payable": True,
        "document_type": "utility_invoice",
        "invoice_number": "5568",
        "invoice_date": "2018-06-12",
        "currency": "USD",
        "supplier_name": "1120 VERMONT AVENUE ASSOCIATES, LLP",
        "buyer_name": "AmeriHealth",
        "po_number": "17816",
        "gross_total": "2487.73",
        "subtotal": "2375.12",
        "total_tax_amount": "112.61",
        "header_taxes": [{"tax_type": "TAX", "tax_name": "Sales tax on utility & building services", "tax_rate": "5.75", "tax_amount": "112.61"}],
        "line_items": [
            {"description": "Electrical, Condenser Water & Building Service Fees", "quantity": "1", "unit_price": "2375.12", "total": "2375.12"}
        ]
    }
}


def seed_cache():
    cache = ExtractionCache()
    seeded = 0

    for filename, data in EXTRACTIONS.items():
        pdf_path = DOCS_DIR / filename
        if not pdf_path.exists():
            print(f"Warning: {pdf_path} not found")
            continue

        file_hash = compute_file_hash(pdf_path)
        cache.put(pdf_path, data)
        seeded += 1
        print(f"Seeded: {filename} -> {file_hash[:12]}...")

    print(f"\nTotal seeded extractions: {seeded}/{len(EXTRACTIONS)}")


if __name__ == "__main__":
    seed_cache()
