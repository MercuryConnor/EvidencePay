"""End-to-end pipeline tests verifying full lifecycle from PDF to ERP-validated Autodraft output."""

import json
from pathlib import Path
import pytest

from src.accounting.reconstruction import reconstruct_autodraft
from src.classification.document import classify_document
from src.erp_validator import validate_payable
from src.extraction.llm import MockExtractor
from src.ingestion.pdf import ingest_pdf
from src.master_data.resolver import resolve_master_data
from src.models import (
    AccountingIR,
    BuyerIR,
    DeclinedDocument,
    FileOutput,
    LineItemIR,
    SupplierIR,
    TaxIR,
)
from src.normalization.numbers import normalize_accounting_ir
from src.output.writer import format_output_dict, write_output
from src.validation.schema import validate_schema


class TestEndToEndPipeline:
    """Integration tests simulating full document processing."""

    def test_mock_payable_pipeline_lifecycle(self, tmp_path):
        # 1. Start with an AccountingIR extracted by vision/LLM
        ir = AccountingIR(
            invoice_number="INV-E2E-100",
            invoice_date="15.03.2026",
            due_date="15.04.2026",
            currency="€",
            gross_total="1.190,00",
            subtotal="1.000,00",
            total_tax_amount="190,00",
            supplier=SupplierIR(
                name="Phocus Direct Communication GmbH",
                vat_id="DE209177122",
            ),
            buyer=BuyerIR(
                raw_name="Bolt Technology OU",
                country="EE",
            ),
            taxes=[
                TaxIR(tax_type="VAT", tax_rate="19%", tax_amount="190,00"),
            ],
            line_items=[
                LineItemIR(
                    description="Cloud Software Subscription",
                    quantity="1",
                    unit_price="1.000,00",
                    total="1.000,00",
                )
            ],
            source_pages=[1],
        )

        # 2. Normalization
        norm_ir = normalize_accounting_ir(ir)
        assert norm_ir.gross_total == "1190.00"
        assert norm_ir.subtotal == "1000.00"
        assert norm_ir.taxes[0].tax_rate == "19"

        # 3. Master Data Resolution
        resolved_ir, match_ev = resolve_master_data(norm_ir)
        assert resolved_ir.supplier.supplier_id == "2845695"
        assert resolved_ir.taxes[0].tax_type_code != ""

        # 4. Reconstruction
        payable = reconstruct_autodraft(resolved_ir)
        assert payable.supplier.supplier_id == "2845695"
        assert payable.gross_total == "1190.00"

        # 5. Schema Validation
        is_valid_schema, errors = validate_schema(payable)
        assert is_valid_schema, f"Schema validation failed: {errors}"

        # 6. ERP Validation
        erp_res = validate_payable(payable)
        assert erp_res.matches, f"ERP mismatch: delta={erp_res.delta}"
        assert abs(erp_res.will_book_gross - 1190.00) < 0.01

        # 7. Output Writing
        file_output = FileOutput(file="test_doc.pdf", payables=[payable])
        out_path = write_output(file_output, tmp_path)
        assert out_path.exists()

        with open(out_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["file"] == "test_doc.pdf"
        assert len(saved_data["payables"]) == 1
        assert saved_data["payables"][0]["invoice_number"] == "INV-E2E-100"
