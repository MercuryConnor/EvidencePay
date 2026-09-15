"""Pipeline orchestrator — connects all processing stages.

Architecture:
  PDF → Evidence → Classification → LLM Extraction(→IR) → Normalization →
  Master Resolution → Reconstruction(→Autodraft) → Validation → Accept/Decline

The LLM is one component. The deterministic accounting path is the spine.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.models.accounting import AccountingIR
from src.models.autodraft import AutodraftPayable, DeclinedDocument, FileOutput
from src.models.diagnostics import ERPResult, ProcessingLog
from src.models.enums import AcceptanceState
from src.output.writer import write_output
from src.extraction.model_manager import InfrastructureError

logger = logging.getLogger(__name__)



def process_single_pdf(pdf_path: Path) -> FileOutput:
    """Process a single PDF through the full pipeline.

    Returns a FileOutput with payables and/or declined entries.
    One document's failure must never crash the entire pipeline.
    """
    filename = pdf_path.name
    logger.info("=== Processing: %s ===", filename)

    file_output = FileOutput(file=filename)
    proc_log = ProcessingLog(file=filename)

    try:
        # ── Stage 1: PDF Ingestion ──
        from src.ingestion.pdf import ingest_pdf
        evidence_packet = ingest_pdf(pdf_path)
        proc_log.total_pages = evidence_packet.total_pages
        logger.info("  Pages: %d", evidence_packet.total_pages)

        # ── Stage 2: Document Classification ──
        from src.classification.document import classify_document
        classification_result = classify_document(evidence_packet)
        proc_log.document_type = classification_result.document_type
        logger.info("  Classification: %s", classification_result.document_type)

        if classification_result.is_non_payable:
            file_output.declined.append(DeclinedDocument(
                doc_type=classification_result.document_type,
                reason=classification_result.decline_reason,
            ))
            proc_log.final_decision = "DECLINE"
            proc_log.decline_reason = classification_result.decline_reason
            logger.info("  Decision: DECLINED (%s)", classification_result.decline_reason)
            return file_output

        # ── Stage 3: LLM Semantic Extraction → AccountingIR ──
        from src.extraction.extractor import extract_payables_with_declined
        from src.extraction.model_manager import gemini_manager
        candidates, extracted_declined = extract_payables_with_declined(evidence_packet, classification_result)
        proc_log.extraction_method = "vision_llm"
        proc_log.extraction_pass_count = 1
        proc_log.llm_model_used = gemini_manager.last_used_model
        if gemini_manager.fallback_count > 0:
            proc_log.fallback_used = True
            proc_log.fallback_reason = gemini_manager.last_fallback_reason

        if extracted_declined:
            file_output.declined.extend(extracted_declined)

        if not candidates:
            if not extracted_declined:
                file_output.declined.append(DeclinedDocument(
                    doc_type="unknown",
                    reason="No payable candidates extracted",
                ))
                proc_log.decline_reason = "No payable candidates extracted"
            else:
                proc_log.decline_reason = extracted_declined[0].reason
            proc_log.final_decision = "DECLINE"
            return file_output

        # ── Stage 4-7: For each candidate ──
        for i, candidate in enumerate(candidates):
            logger.info("  Candidate %d: %s", i + 1, candidate.invoice_number)
            candidate.state = AcceptanceState.CANDIDATE

            # Stage 4: Normalisation
            from src.normalization.numbers import normalize_accounting_ir
            candidate = normalize_accounting_ir(candidate)

            # Stage 5: Master Data Resolution
            from src.master_data.resolver import resolve_master_data
            candidate, match_evidence = resolve_master_data(candidate)
            proc_log.master_matches.extend(match_evidence)

            # Stage 6: Deterministic Reconstruction → Autodraft
            candidate.state = AcceptanceState.RECONSTRUCT
            from src.accounting.reconstruction import reconstruct_autodraft
            autodraft = reconstruct_autodraft(candidate)

            # Stage 7: ERP Validation
            candidate.state = AcceptanceState.VALIDATE
            from src.erp_validator import validate_payable
            erp_result = validate_payable(autodraft)
            proc_log.erp_result = erp_result

            if erp_result.matches:
                candidate.state = AcceptanceState.ACCEPT
                file_output.payables.append(autodraft)
                proc_log.final_decision = "ACCEPT"
                logger.info("  Candidate %d: ACCEPTED (gross=%s)", i + 1, erp_result.will_book_gross)
            else:
                # Targeted recheck (bounded, max 2 more passes = 3 total)
                autodraft, accepted = _targeted_recheck(
                    evidence_packet, candidate, autodraft, erp_result, proc_log
                )
                if accepted:
                    file_output.payables.append(autodraft)
                    proc_log.final_decision = "ACCEPT"
                    logger.info("  Candidate %d: ACCEPTED after recheck", i + 1)
                else:
                    from src.validation.diagnostics import diagnose_mismatch
                    diags = diagnose_mismatch(candidate, erp_result.will_book_gross, str(candidate.gross_total))
                    diag_cat = diags[0].category.value if diags else "LINE_STRUCTURE_MISMATCH"
                    diag_desc = diags[0].description if diags else "Unexplained delta between ERP and document gross"

                    decline_reason = (
                        f"PAYABLE_RECONCILIATION_FAILURE: inv={candidate.invoice_number}, "
                        f"curr={candidate.currency}, stated={candidate.gross_total}, "
                        f"erp={erp_result.will_book_gross:.2f}, delta={erp_result.delta:+.2f}, "
                        f"category={diag_cat}: {diag_desc}"
                    )
                    file_output.declined.append(DeclinedDocument(
                        doc_type=candidate.document_type.value,
                        reason=decline_reason,
                    ))
                    proc_log.final_decision = "PAYABLE_RECONCILIATION_FAILURE"
                    proc_log.decline_reason = decline_reason
                    logger.warning(
                        "  Candidate %d: PAYABLE_RECONCILIATION_FAILURE (delta=%.2f, cat=%s)",
                        i + 1, erp_result.delta, diag_cat,
                    )

    except InfrastructureError as e:
        logger.error(
            "  Infrastructure failure processing %s: %s (NOT marked as declined/non-payable)",
            filename,
            e,
        )
        proc_log.final_decision = "INFRASTRUCTURE_ERROR"
        proc_log.decline_reason = f"Infrastructure failure: {str(e)}"
        raise
    except Exception as e:
        logger.error("  Error processing %s: %s", filename, e, exc_info=True)
        proc_log.final_decision = "ERROR"
        proc_log.decline_reason = f"Processing error: {str(e)}"
        raise

    payable_count = len(file_output.payables)
    declined_count = len(file_output.declined)
    logger.info("  Result: %d payables, %d declined", payable_count, declined_count)

    return file_output


def _targeted_recheck(
    evidence_packet,
    candidate: AccountingIR,
    autodraft: AutodraftPayable,
    erp_result: ERPResult,
    proc_log: ProcessingLog,
) -> tuple[AutodraftPayable, bool]:
    """Bounded targeted re-extraction. Max 2 additional passes (3 total).

    Returns (final_autodraft, accepted_bool).
    """
    from src.erp_validator import validate_payable

    max_rechecks = 2

    for pass_num in range(2, 2 + max_rechecks):
        candidate.state = AcceptanceState.TARGETED_RECHECK
        candidate.pass_count = pass_num
        proc_log.recheck_attempts += 1
        logger.info("    Recheck pass %d...", pass_num)

        try:
            from src.extraction.targeted_recheck import targeted_recheck
            updated_candidate = targeted_recheck(
                evidence_packet, candidate, erp_result, pass_num
            )

            if updated_candidate is None:
                proc_log.recheck_results.append(f"Pass {pass_num}: no changes suggested")
                logger.info("    No recheck changes, stopping.")
                break

            # Re-normalize, re-resolve, re-reconstruct
            from src.normalization.numbers import normalize_accounting_ir
            updated_candidate = normalize_accounting_ir(updated_candidate)

            from src.master_data.resolver import resolve_master_data
            updated_candidate, _ = resolve_master_data(updated_candidate)

            from src.accounting.reconstruction import reconstruct_autodraft
            autodraft = reconstruct_autodraft(updated_candidate)

            erp_result = validate_payable(autodraft)
            proc_log.erp_result = erp_result

            if erp_result.matches:
                proc_log.recheck_results.append(f"Pass {pass_num}: MATCHED")
                return autodraft, True

            proc_log.recheck_results.append(f"Pass {pass_num}: delta={erp_result.delta:.2f}")
            candidate = updated_candidate

        except Exception as e:
            proc_log.recheck_results.append(f"Pass {pass_num}: error={str(e)}")
            logger.warning("    Recheck pass %d failed: %s", pass_num, e)
            break

    return autodraft, False


def run_pipeline(pdf_files: list[Path], output_dir: Path) -> list[FileOutput]:
    """Run the full pipeline over a list of PDF files.

    Writes output JSON for each file. Returns all FileOutputs.
    """
    from src.extraction.model_manager import InfrastructureError

    results = []

    for pdf_path in pdf_files:
        try:
            file_output = process_single_pdf(pdf_path)
            write_output(file_output, output_dir)
            results.append(file_output)
        except InfrastructureError as e:
            logger.error(
                "Pipeline stopped due to infrastructure failure on %s: %s. "
                "Halting batch to prevent treating infrastructure outages as non-payable declines.",
                pdf_path.name,
                e,
            )
            raise

    return results
