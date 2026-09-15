"""Models package — re-exports all models for convenient importing.

Usage:
    from src.models import AccountingIR, AutodraftPayable, EvidencePacket
"""

# Enums
from src.models.enums import (
    AcceptanceState,
    DiagnosticCategory,
    DocumentType,
    ExtractionMethod,
    InvoiceType,
    ItemType,
    MatchConfidence,
    MatchMethod,
    PageRole,
)

# Evidence layer
from src.models.evidence import (
    BoundingBox,
    EvidencePacket,
    EvidenceValue,
    PageEvidence,
)

# Accounting IR
from src.models.accounting import (
    AccountingIR,
    BuyerIR,
    LineItemIR,
    SupplierIR,
    TaxIR,
)

# Autodraft output
from src.models.autodraft import (
    AutodraftBuyer,
    AutodraftLineItem,
    AutodraftPayable,
    AutodraftSupplier,
    AutodraftTax,
    DeclinedDocument,
    FileOutput,
)

# Diagnostics
from src.models.diagnostics import (
    ERPResult,
    MatchEvidence,
    MismatchDiagnostic,
    ProcessingLog,
)

__all__ = [
    # Enums
    "AcceptanceState", "DiagnosticCategory", "DocumentType",
    "ExtractionMethod", "InvoiceType", "ItemType",
    "MatchConfidence", "MatchMethod", "PageRole",
    # Evidence
    "BoundingBox", "EvidencePacket", "EvidenceValue", "PageEvidence",
    # Accounting IR
    "AccountingIR", "BuyerIR", "LineItemIR", "SupplierIR", "TaxIR",
    # Autodraft
    "AutodraftBuyer", "AutodraftLineItem", "AutodraftPayable",
    "AutodraftSupplier", "AutodraftTax", "DeclinedDocument", "FileOutput",
    # Diagnostics
    "ERPResult", "MatchEvidence", "MismatchDiagnostic", "ProcessingLog",
]
