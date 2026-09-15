"""PO matching — exact match only.

A PO not in the master is a non-ERP reference → po_id = "".
Never invent a PO.
"""

from __future__ import annotations

import logging

from src.master_data import loader
from src.models.diagnostics import MatchEvidence
from src.models.enums import MatchConfidence, MatchMethod

logger = logging.getLogger(__name__)


def match_po(po_number: str = "") -> MatchEvidence:
    """Match a PO number (exact match only).

    Returns MatchEvidence. If no match, po_id stays empty.
    """
    loader.ensure_loaded()

    po_num = po_number.strip()
    if po_num and po_num in loader.po_by_number:
        po = loader.po_by_number[po_num]
        return MatchEvidence(
            entity_type="po",
            matched_id=po["po_id"],
            match_method=MatchMethod.IDENTIFIER_EXACT,
            confidence=MatchConfidence.HIGH,
            score=100.0,
            document_evidence=po_number,
            master_value=po["po_number"],
        )

    return MatchEvidence(
        entity_type="po",
        match_method=MatchMethod.NO_MATCH,
        confidence=MatchConfidence.NONE,
        document_evidence=po_number,
        notes="PO not in master — may be non-ERP reference",
    )
