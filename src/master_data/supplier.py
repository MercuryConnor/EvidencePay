"""Supplier matching — resolve supplier identity from document evidence.

Priority:
1. Exact VAT/tax-ID match
2. Exact IBAN match (corroborating, not primary)
3. Exact normalised legal name match
4. Fuzzy name match (threshold >= 85, with competing-candidate detection)

Returns MatchEvidence so the decision is auditable.
"""

from __future__ import annotations

import logging

from rapidfuzz import fuzz

from src.master_data import loader
from src.models.diagnostics import MatchEvidence
from src.models.enums import MatchConfidence, MatchMethod

logger = logging.getLogger(__name__)


def match_supplier(
    name: str = "",
    vat_id: str = "",
    address: str = "",
    iban: str = "",
) -> MatchEvidence:
    """Match a supplier and return MatchEvidence.

    Returns MatchEvidence with matched_id, method, confidence, and audit trail.
    """
    loader.ensure_loaded()

    # 1. Exact VAT match — highest confidence
    vat_upper = vat_id.strip().upper()
    if vat_upper and vat_upper in loader.supplier_by_vat:
        s = loader.supplier_by_vat[vat_upper]
        return MatchEvidence(
            entity_type="supplier",
            matched_id=s["supplier_id"],
            match_method=MatchMethod.VAT_ID_EXACT,
            confidence=MatchConfidence.HIGH,
            score=100.0,
            document_evidence=vat_id,
            master_value=s.get("vat_id", ""),
        )

    # 2. IBAN match — corroborating, not primary
    iban_upper = iban.strip().upper().replace(" ", "")
    if iban_upper and iban_upper in loader.supplier_by_iban:
        s = loader.supplier_by_iban[iban_upper]
        return MatchEvidence(
            entity_type="supplier",
            matched_id=s["supplier_id"],
            match_method=MatchMethod.IBAN_EXACT,
            confidence=MatchConfidence.HIGH,
            score=100.0,
            document_evidence=iban,
            master_value=s.get("bank_iban", ""),
            notes="IBAN is corroborating — bank accounts can change",
        )

    # 3. Exact name match (case-insensitive)
    name_lower = name.strip().lower()
    if name_lower and name_lower in loader.supplier_by_name_lower:
        s = loader.supplier_by_name_lower[name_lower]
        return MatchEvidence(
            entity_type="supplier",
            matched_id=s["supplier_id"],
            match_method=MatchMethod.NAME_EXACT,
            confidence=MatchConfidence.HIGH,
            score=100.0,
            document_evidence=name,
            master_value=s.get("name", ""),
        )

    # 4. Fuzzy name match — must detect ambiguous competing candidates
    if name_lower:
        scored = []
        for s in loader.suppliers:
            score = fuzz.ratio(name_lower, s.get("name", "").lower())
            if score >= 70:  # candidate threshold
                scored.append((score, s))

        scored.sort(key=lambda x: -x[0])

        if scored:
            best_score, best = scored[0]

            # Detect ambiguity: if second-best is within 5 points, it's ambiguous
            if len(scored) >= 2 and scored[1][0] >= best_score - 5:
                return MatchEvidence(
                    entity_type="supplier",
                    matched_id=best["supplier_id"],
                    match_method=MatchMethod.NAME_FUZZY,
                    confidence=MatchConfidence.AMBIGUOUS,
                    score=best_score,
                    document_evidence=name,
                    master_value=best.get("name", ""),
                    competing_candidates=len(scored),
                    notes=f"Ambiguous: top {len(scored)} candidates within range",
                )

            if best_score >= 85:
                return MatchEvidence(
                    entity_type="supplier",
                    matched_id=best["supplier_id"],
                    match_method=MatchMethod.NAME_FUZZY,
                    confidence=MatchConfidence.MEDIUM,
                    score=best_score,
                    document_evidence=name,
                    master_value=best.get("name", ""),
                    competing_candidates=len(scored),
                )

    # No match
    return MatchEvidence(
        entity_type="supplier",
        matched_id="",
        match_method=MatchMethod.NO_MATCH,
        confidence=MatchConfidence.NONE,
        document_evidence=name or vat_id or iban,
        notes="No supplier match found",
    )
