"""
Review result data structures.

Defines the output format for all review types.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Severity levels for review findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @classmethod
    def from_string(cls, s: str) -> "Severity":
        """Parse severity from string, case-insensitive."""
        s = s.upper().strip()
        mapping = {
            "CRITICAL": cls.CRITICAL,
            "HIGH": cls.HIGH,
            "MEDIUM": cls.MEDIUM,
            "LOW": cls.LOW,
            "INFO": cls.INFO,
            "INFORMATION": cls.INFO,
            "WARNING": cls.MEDIUM,
            "WARN": cls.MEDIUM,
            "ERROR": cls.HIGH,
        }
        return mapping.get(s, cls.INFO)

    def is_blocking(self) -> bool:
        """Whether this severity level should block the workflow."""
        return self in (Severity.CRITICAL, Severity.HIGH)


@dataclass
class ReviewFinding:
    """A single finding from a review."""
    severity: Severity
    issue: str
    location: Optional[str] = None
    evidence: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "issue": self.issue,
            "location": self.location,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewFinding":
        return cls(
            severity=Severity.from_string(data.get("severity", "info")),
            issue=data.get("issue", ""),
            location=data.get("location"),
            evidence=data.get("evidence"),
            recommendation=data.get("recommendation"),
        )


@dataclass
class ReviewResult:
    """Result of a single review execution."""
    review_type: str
    success: bool
    model_used: str
    method_used: str  # "cli", "api", "github-actions"
    findings: list[ReviewFinding] = field(default_factory=list)
    raw_output: str = ""
    summary: Optional[str] = None
    score: Optional[int] = None  # 1-10 for quality review
    assessment: Optional[str] = None  # APPROVED, APPROVED_WITH_NOTES, CHANGES_REQUESTED
    error: Optional[str] = None
    duration_seconds: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # WF-035 Phase 4: Fallback tracking
    was_fallback: bool = False  # True if a fallback model was used instead of primary
    fallback_reason: Optional[str] = None  # Why fallback was needed (e.g., "Primary rate limited")

    def has_blocking_findings(self) -> bool:
        """Check if any findings should block the workflow."""
        return any(f.severity.is_blocking() for f in self.findings)

    @property
    def blocking_count(self) -> int:
        """Count of blocking findings."""
        return sum(1 for f in self.findings if f.severity.is_blocking())

    def to_dict(self) -> dict:
        return {
            "review_type": self.review_type,
            "success": self.success,
            "model_used": self.model_used,
            "method_used": self.method_used,
            "findings": [f.to_dict() for f in self.findings],
            "raw_output": self.raw_output,
            "summary": self.summary,
            "score": self.score,
            "assessment": self.assessment,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat(),
            "blocking_count": self.blocking_count,
            # WF-035 Phase 4: Fallback tracking
            "was_fallback": self.was_fallback,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewResult":
        findings = [ReviewFinding.from_dict(f) for f in data.get("findings", [])]
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return cls(
            review_type=data.get("review_type", "unknown"),
            success=data.get("success", False),
            model_used=data.get("model_used", "unknown"),
            method_used=data.get("method_used", "unknown"),
            findings=findings,
            raw_output=data.get("raw_output", ""),
            summary=data.get("summary"),
            score=data.get("score"),
            assessment=data.get("assessment"),
            error=data.get("error"),
            duration_seconds=data.get("duration_seconds"),
            timestamp=timestamp,
            # WF-035 Phase 4: Fallback tracking
            was_fallback=data.get("was_fallback", False),
            fallback_reason=data.get("fallback_reason"),
        )


def parse_review_output(review_type: str, output: str) -> tuple[list[ReviewFinding], dict]:
    """
    Parse raw model output into structured findings.

    Returns (findings, metadata) where metadata contains summary, score, assessment.
    """
    findings = []
    metadata = {}

    # Extract summary
    summary_match = re.search(r"\*\*Summary:\*\*\s*(.+?)(?=\n\n|\n\*\*|$)", output, re.DOTALL)
    if summary_match:
        metadata["summary"] = summary_match.group(1).strip()

    # Extract score (for quality review)
    score_match = re.search(r"Quality Score:\s*\[?(\d+)\]?", output, re.IGNORECASE)
    if score_match:
        metadata["score"] = int(score_match.group(1))

    # Extract assessment (for architecture/consistency review)
    # Match longest first to avoid partial matches
    assessment_match = re.search(
        r"(?:Overall )?Assessment:\s*\[?(APPROVED_WITH_NOTES|CHANGES_REQUESTED|APPROVED)\]?",
        output,
        re.IGNORECASE
    )
    if assessment_match:
        metadata["assessment"] = assessment_match.group(1).upper()

    # Parse findings in format: ### [SEVERITY: LEVEL] or ### [LEVEL]
    finding_pattern = re.compile(
        r"###\s*\[(?:SEVERITY:\s*)?(CRITICAL|HIGH|MEDIUM|LOW|INFO)\]"
        r"(.*?)(?=###\s*\[|## |$)",
        re.DOTALL | re.IGNORECASE
    )

    for match in finding_pattern.finditer(output):
        severity_str = match.group(1)
        content = match.group(2).strip()

        # Extract fields from content
        issue = ""
        location = None
        evidence = None
        recommendation = None

        issue_match = re.search(r"\*\*(?:Issue|Finding):\*\*\s*(.+?)(?=\n\*\*|$)", content, re.DOTALL)
        if issue_match:
            issue = issue_match.group(1).strip()

        location_match = re.search(r"\*\*Location:\*\*\s*(.+?)(?=\n\*\*|$)", content, re.DOTALL)
        if location_match:
            location = location_match.group(1).strip()

        evidence_match = re.search(r"\*\*Evidence:\*\*\s*(.+?)(?=\n\*\*|$)", content, re.DOTALL)
        if evidence_match:
            evidence = evidence_match.group(1).strip()

        rec_match = re.search(r"\*\*(?:Recommendation|Fix):\*\*\s*(.+?)(?=\n\*\*|$)", content, re.DOTALL)
        if rec_match:
            recommendation = rec_match.group(1).strip()

        # If no structured issue found, use the whole content
        if not issue:
            issue = content[:500] if content else "Finding details not parsed"

        findings.append(ReviewFinding(
            severity=Severity.from_string(severity_str),
            issue=issue,
            location=location,
            evidence=evidence,
            recommendation=recommendation,
        ))

    # Also look for numbered findings: 1. [SEVERITY] issue
    numbered_pattern = re.compile(
        r"^\d+\.\s*\[?(CRITICAL|HIGH|MEDIUM|LOW|INFO)\]?\s*(.+?)(?=\n\d+\.\s*\[|$)",
        re.MULTILINE | re.IGNORECASE
    )

    for match in numbered_pattern.finditer(output):
        severity_str = match.group(1)
        content = match.group(2).strip()

        # Skip if we already captured this as a structured finding
        if any(content[:50] in f.issue for f in findings):
            continue

        findings.append(ReviewFinding(
            severity=Severity.from_string(severity_str),
            issue=content,
        ))

    return findings, metadata
