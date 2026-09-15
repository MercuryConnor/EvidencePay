"""Buyer / organisation matching — resolve company_code, BU, location.

Matches against the chart_of_books hierarchy using entity name, address,
and country signals.
"""

from __future__ import annotations

import logging

from rapidfuzz import fuzz

from src.master_data import loader
from src.models.diagnostics import MatchEvidence
from src.models.enums import MatchConfidence, MatchMethod

logger = logging.getLogger(__name__)


def match_buyer(
    entity_name: str = "",
    address: str = "",
    country: str = "",
) -> MatchEvidence:
    """Match a buyer org and return MatchEvidence.

    Result carries company_code, business_unit_code, location_code in notes.
    """
    loader.ensure_loaded()

    if not entity_name and not address and not country:
        return MatchEvidence(
            entity_type="buyer",
            match_method=MatchMethod.NO_MATCH,
            confidence=MatchConfidence.NONE,
        )

    best_score = 0
    best_entry = None

    for entry in loader.chart_of_books:
        score = 0

        if entity_name:
            bu_score = fuzz.ratio(entity_name.lower(), entry.get("business_unit_name", "").lower())
            company_score = fuzz.ratio(entity_name.lower(), entry.get("company_name", "").lower())
            location_score = fuzz.ratio(entity_name.lower(), entry.get("location_name", "").lower())
            score = max(bu_score, company_score, location_score)

        if address:
            inv_addr = entry.get("invoice_to_address", "")
            if inv_addr:
                addr_score = fuzz.partial_ratio(address.lower(), inv_addr.lower())
                score = max(score, addr_score)

        # Country bonus from BU code prefix
        if country:
            bu_code = entry.get("business_unit_code", "")
            if bu_code.startswith(country.upper()):
                score += 20

        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= 60:
        codes = (
            f"{best_entry['company_code']}/"
            f"{best_entry['business_unit_code']}/"
            f"{best_entry['location_code']}"
        )
        return MatchEvidence(
            entity_type="buyer",
            matched_id=codes,
            match_method=MatchMethod.NAME_FUZZY if entity_name else MatchMethod.ADDRESS_FUZZY,
            confidence=MatchConfidence.MEDIUM if best_score >= 80 else MatchConfidence.LOW,
            score=best_score,
            document_evidence=entity_name or address,
            master_value=best_entry.get("business_unit_name", ""),
            notes=f"company={best_entry['company_code']}, "
                  f"bu={best_entry['business_unit_code']}, "
                  f"loc={best_entry['location_code']}",
        )

    return MatchEvidence(
        entity_type="buyer",
        match_method=MatchMethod.NO_MATCH,
        confidence=MatchConfidence.NONE,
        document_evidence=entity_name or address,
    )


def parse_buyer_codes(evidence: MatchEvidence) -> dict:
    """Extract company_code, business_unit_code, location_code from MatchEvidence."""
    if evidence.match_method == MatchMethod.NO_MATCH:
        return {"company_code": "", "business_unit_code": "", "location_code": ""}

    parts = evidence.matched_id.split("/")
    return {
        "company_code": parts[0] if len(parts) > 0 else "",
        "business_unit_code": parts[1] if len(parts) > 1 else "",
        "location_code": parts[2] if len(parts) > 2 else "",
    }
