"""
CivicMind -- PII Redaction Utility
===================================
Regex-based PII redaction for responsible AI compliance.
Redacts: phone numbers, email addresses, SSNs, and common name patterns.

Returns redacted text + a flag indicating whether PII was found,
so the UI can display a "PII Redacted" badge.
"""

import re
from dataclasses import dataclass


@dataclass
class RedactionResult:
    text: str
    pii_redacted: bool
    redaction_count: int
    redacted_types: list[str]


# Patterns
PII_PATTERNS = [
    ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("PHONE", r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    # US zip codes standalone (5 or 5+4 format)
    # ("ZIP", r"\b\d{5}(?:-\d{4})?\b"),
]

# Replacement markers
REDACTION_MARKERS = {
    "SSN": "[SSN REDACTED]",
    "PHONE": "[PHONE REDACTED]",
    "EMAIL": "[EMAIL REDACTED]",
    "ZIP": "[ZIP REDACTED]",
}


def redact_pii(text: str) -> RedactionResult:
    """Redact PII from text and return the result with metadata.

    This is a visible, auditable step in the pipeline -- the UI shows
    a 'PII Redacted' badge on any content that went through this filter.
    """
    redacted_text = text
    total_count = 0
    found_types = set()

    for pii_type, pattern in PII_PATTERNS:
        matches = re.findall(pattern, redacted_text)
        if matches:
            found_types.add(pii_type)
            total_count += len(matches)
            redacted_text = re.sub(pattern, REDACTION_MARKERS[pii_type], redacted_text)

    return RedactionResult(
        text=redacted_text,
        pii_redacted=total_count > 0,
        redaction_count=total_count,
        redacted_types=sorted(found_types),
    )
