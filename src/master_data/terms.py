"""Payment term matching — resolve payment_term_id.

Priority:
1. Text alias match (case-insensitive substring)
2. Date-diff match (invoice_date → due_date → days → term)
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.master_data import loader
from src.models.diagnostics import MatchEvidence
from src.models.enums import MatchConfidence, MatchMethod

logger = logging.getLogger(__name__)


def match_payment_term(
    text: str = "",
    invoice_date: str = "",
    due_date: str = "",
) -> MatchEvidence:
    """Match a payment term and return MatchEvidence."""
    loader.ensure_loaded()

    # 1. Text alias match
    if text:
        text_lower = text.strip().lower()
        for pt in loader.payment_terms:
            for alias in pt.get("text_aliases", []):
                if alias.lower() in text_lower or text_lower in alias.lower():
                    return MatchEvidence(
                        entity_type="payment_term",
                        matched_id=pt["payment_term_id"],
                        match_method=MatchMethod.TEXT_ALIAS,
                        confidence=MatchConfidence.HIGH,
                        score=100.0,
                        document_evidence=text,
                        master_value=alias,
                    )

    # 2. Date difference match
    if invoice_date and due_date:
        try:
            inv = datetime.strptime(invoice_date, "%Y-%m-%d")
            due = datetime.strptime(due_date, "%Y-%m-%d")
            days = (due - inv).days

            # Exact days match
            if days in loader.payment_by_days:
                pt = loader.payment_by_days[days]
                return MatchEvidence(
                    entity_type="payment_term",
                    matched_id=pt["payment_term_id"],
                    match_method=MatchMethod.DATE_DIFF,
                    confidence=MatchConfidence.MEDIUM,
                    score=90.0,
                    document_evidence=f"{invoice_date} → {due_date} = {days} days",
                    master_value=f"{pt['payment_term_id']} ({pt.get('days', '')} days)",
                )

            # Close match (±1 day for weekends/holidays)
            for d in [days - 1, days + 1]:
                if d in loader.payment_by_days:
                    pt = loader.payment_by_days[d]
                    return MatchEvidence(
                        entity_type="payment_term",
                        matched_id=pt["payment_term_id"],
                        match_method=MatchMethod.DATE_DIFF,
                        confidence=MatchConfidence.LOW,
                        score=75.0,
                        document_evidence=f"{invoice_date} → {due_date} = {days} days (~{d})",
                        master_value=f"{pt['payment_term_id']} ({pt.get('days', '')} days)",
                        notes=f"Close match: actual={days}, term={d}",
                    )
        except (ValueError, TypeError):
            pass

    # No match
    return MatchEvidence(
        entity_type="payment_term",
        match_method=MatchMethod.NO_MATCH,
        confidence=MatchConfidence.NONE,
        document_evidence=text or f"{invoice_date}/{due_date}",
    )
