"""Evidence-first diagnostics primitives for Failure Analysis V2."""

from .evidence import (
    EvidenceCollector,
    EvidenceSeverity,
    EvidenceType,
    FailureEvidence,
    TraceContext,
    sanitize_evidence,
)

__all__ = [
    "EvidenceCollector",
    "EvidenceSeverity",
    "EvidenceType",
    "FailureEvidence",
    "TraceContext",
    "sanitize_evidence",
]
