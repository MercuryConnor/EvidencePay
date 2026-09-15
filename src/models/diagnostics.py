"""Diagnostic models — ERP results, match evidence, and processing logs.

These structures capture *why* a decision was made, not just *what*
the decision was. Essential for debugging and regression.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import (
    DiagnosticCategory,
    MatchConfidence,
    MatchMethod,
)


# ── Master-data match evidence ──────────────────

class MatchEvidence(BaseModel):
    """Records how and why a master-data match was chosen.

    Every master-data resolution should produce one of these so the
    decision can be reviewed, debugged, and tested.
    """
    entity_type: str = ""           # supplier, buyer, tax, payment_term, po
    matched_id: str = ""            # the resolved ID
    match_method: MatchMethod = MatchMethod.NO_MATCH
    confidence: MatchConfidence = MatchConfidence.NONE
    score: float = 0.0              # fuzzy score if applicable
    document_evidence: str = ""     # what the document showed (e.g. VAT ID)
    master_value: str = ""          # what the master data has
    competing_candidates: int = 0   # how many candidates were considered
    notes: str = ""                 # free-form explanation


# ── ERP reconciliation result ───────────────────

class ERPResult(BaseModel):
    """Result from erp_book() validation.

    Captures the comparison between what the ERP computed and what
    the document says the gross should be.
    """
    will_book_gross: float = 0.0
    currency: str = ""
    expected_gross: float = 0.0     # from document's stated gross_total
    matches: bool = False           # |delta| < 0.005
    delta: float = 0.0              # booked - expected


# ── Mismatch diagnostic ────────────────────────

class MismatchDiagnostic(BaseModel):
    """A specific diagnosis of why ERP reconciliation failed.

    Points to the suspect region so targeted recheck can focus.
    """
    category: DiagnosticCategory
    description: str = ""
    suspect_field: str = ""         # which field is likely wrong
    suspect_page: int = 0           # which page to re-examine
    evidence: str = ""              # what we saw
    suggested_action: str = ""      # what targeted recheck should do


# ── Processing log (per-document) ──────────────

class ProcessingLog(BaseModel):
    """Structured log for one document through the pipeline.

    Every field from RULES rule #43 is represented here.
    Logs must be structured enough to reproduce and debug failures.
    """
    file: str
    total_pages: int = 0

    # Classification
    page_roles: list[str] = Field(default_factory=list)
    document_type: str = ""

    # Extraction
    extraction_method: str = ""
    extraction_pass_count: int = 0
    raw_extraction_summary: str = ""     # summary of what LLM returned
    llm_model_used: Optional[str] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None

    # Master data
    master_matches: list[MatchEvidence] = Field(default_factory=list)

    # Reconstruction
    reconstruction_summary: str = ""

    # Validation
    erp_result: Optional[ERPResult] = None
    mismatch_diagnostics: list[MismatchDiagnostic] = Field(default_factory=list)

    # Decision
    final_decision: str = ""        # ACCEPT | DECLINE
    decline_reason: str = ""

    # Recheck
    recheck_attempts: int = 0
    recheck_results: list[str] = Field(default_factory=list)
