"""Tax code matching — resolve tax_type_code from country + type + rate.

Uses indexed retrieval by country+rate, disambiguates by tax type/name.
"""

from __future__ import annotations

import logging

from src.master_data import loader
from src.models.diagnostics import MatchEvidence
from src.models.enums import MatchConfidence, MatchMethod

logger = logging.getLogger(__name__)


def match_tax_code(
    country: str = "",
    tax_type: str = "",
    rate: float | str = 0,
    tax_name: str = "",
) -> MatchEvidence:
    """Match a tax entry against the tax master.

    Returns MatchEvidence with the resolved tax_type_code.
    """
    loader.ensure_loaded()

    rate_float = float(rate) if rate else 0.0
    country_upper = country.strip().upper()
    tax_type_upper = tax_type.strip().upper()

    # 1. Most specific: country + type + rate
    key_ctr = f"{country_upper}_{tax_type_upper}_{rate_float}"
    candidates = loader.tax_by_country_rate.get(key_ctr, [])
    if len(candidates) == 1:
        return MatchEvidence(
            entity_type="tax",
            matched_id=candidates[0]["code"],
            match_method=MatchMethod.IDENTIFIER_EXACT,
            confidence=MatchConfidence.HIGH,
            score=100.0,
            document_evidence=f"{country}/{tax_type}/{rate}",
            master_value=f"{candidates[0]['code']} ({candidates[0].get('name', '')})",
        )

    # 2. Country + rate only
    key_cr = f"{country_upper}_{rate_float}"
    candidates = loader.tax_by_country_rate.get(key_cr, [])

    if len(candidates) == 1:
        return MatchEvidence(
            entity_type="tax",
            matched_id=candidates[0]["code"],
            match_method=MatchMethod.RATE_COUNTRY,
            confidence=MatchConfidence.HIGH,
            score=95.0,
            document_evidence=f"{country}/{rate}",
            master_value=f"{candidates[0]['code']} ({candidates[0].get('name', '')})",
        )

    # 3. Multiple candidates — disambiguate by name/type
    if len(candidates) > 1:
        if tax_name:
            for c in candidates:
                c_name = c.get("name", "").lower()
                if any(kw in c_name for kw in tax_name.lower().split()):
                    return MatchEvidence(
                        entity_type="tax",
                        matched_id=c["code"],
                        match_method=MatchMethod.RATE_COUNTRY,
                        confidence=MatchConfidence.MEDIUM,
                        score=80.0,
                        document_evidence=f"{country}/{tax_type}/{rate}/{tax_name}",
                        master_value=f"{c['code']} ({c.get('name', '')})",
                        competing_candidates=len(candidates),
                        notes=f"Disambiguated by tax_name from {len(candidates)} candidates",
                    )

        # Fall back to first candidate (ordered by insertion)
        return MatchEvidence(
            entity_type="tax",
            matched_id=candidates[0]["code"],
            match_method=MatchMethod.RATE_COUNTRY,
            confidence=MatchConfidence.LOW,
            score=60.0,
            document_evidence=f"{country}/{rate}",
            master_value=f"{candidates[0]['code']}",
            competing_candidates=len(candidates),
            notes=f"Ambiguous: {len(candidates)} candidates at same country/rate",
        )

    # No match
    return MatchEvidence(
        entity_type="tax",
        match_method=MatchMethod.NO_MATCH,
        confidence=MatchConfidence.NONE,
        document_evidence=f"{country}/{tax_type}/{rate}",
        notes="No tax code match found",
    )
