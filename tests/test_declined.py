"""Unit tests for declined document handling and schemas."""

import json
import pytest
from src.models import DeclinedDocument, FileOutput
from src.output.writer import format_output_dict


class TestDeclinedOutput:
    """Test structure and decline reasons."""

    def test_declined_document_structure(self):
        declined_entry = DeclinedDocument(
            doc_type="estimate",
            reason="Document is a cost estimate / quotation, not a payable obligation",
        )
        file_output = FileOutput(file="estimate.pdf", declined=[declined_entry])

        out_dict = format_output_dict(file_output)
        assert out_dict["file"] == "estimate.pdf"
        assert len(out_dict["payables"]) == 0
        assert len(out_dict["declined"]) == 1
        assert out_dict["declined"][0]["doc_type"] == "estimate"
        assert "not a payable" in out_dict["declined"][0]["reason"]

    def test_empty_declined_present_for_accepted(self):
        # AUTODRAFT contract: declined must always be present, even if empty []
        file_output = FileOutput(file="invoice.pdf", payables=[])
        out_dict = format_output_dict(file_output)
        assert "declined" in out_dict
        assert isinstance(out_dict["declined"], list)
        assert "payables" in out_dict
        assert isinstance(out_dict["payables"], list)
