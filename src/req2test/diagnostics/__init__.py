"""Evidence-first diagnostics primitives for Failure Analysis V2."""

from .evidence import (
    EvidenceCollector,
    EvidenceSeverity,
    EvidenceType,
    FailureEvidence,
    TraceContext,
    sanitize_evidence,
)
from .classifier import (
    DiagnosisConfidence,
    FailureAnalysisV2,
    FailureDiagnosis,
    RootCauseCategory,
    classify_failures,
)

__all__ = [
    "EvidenceCollector",
    "EvidenceSeverity",
    "EvidenceType",
    "FailureEvidence",
    "TraceContext",
    "sanitize_evidence",
    "DiagnosisConfidence",
    "FailureAnalysisV2",
    "FailureDiagnosis",
    "RootCauseCategory",
    "classify_failures",
]
