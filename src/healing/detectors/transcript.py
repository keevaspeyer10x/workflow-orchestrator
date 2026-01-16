"""Transcript detector for error detection.

This module detects errors mentioned in conversation transcripts.
"""

import re
from datetime import datetime
from typing import List, Optional
import uuid

from .base import BaseDetector
from ..fingerprint import Fingerprinter
from ..models import ErrorEvent
from ..context_extraction import extract_context


class TranscriptDetector(BaseDetector):
    """Detect errors from conversation transcripts.

    Parses conversation text for error patterns:
    - Python exceptions (TypeError, ValueError, etc.)
    - Tracebacks
    - Error keywords in context
    """

    # Patterns to detect errors in conversation
    ERROR_PATTERNS = [
        # Python errors
        r"(\w+Error|\w+Exception): ([^\n]+)",
        # Tracebacks
        r"Traceback \(most recent call last\):(.+?)(?=\n\n|\Z)",
        # Error keywords with context
        r"(?:error|failed|failure|exception):\s*([^\n]+)",
    ]

    def __init__(
        self,
        fingerprinter: Fingerprinter,
        workflow_id: Optional[str] = None,
        phase_id: Optional[str] = None,
    ):
        """Initialize detector.

        Args:
            fingerprinter: Fingerprinter instance.
            workflow_id: Optional workflow ID to associate with errors.
            phase_id: Optional phase ID to associate with errors.
        """
        super().__init__(fingerprinter)
        self.workflow_id = workflow_id
        self.phase_id = phase_id

    def detect(self, source: str) -> List[ErrorEvent]:
        """Detect errors from transcript text.

        Args:
            source: Conversation transcript text.

        Returns:
            List of detected ErrorEvent instances.
        """
        errors = []
        seen_descriptions = set()

        # Python error pattern: TypeError: something
        for match in re.finditer(
            r"(\w+Error|\w+Exception): ([^\n]+)", source, re.IGNORECASE
        ):
            error_type = match.group(1)
            message = match.group(2)
            description = f"{error_type}: {message}"

            # Dedupe within this detection run
            if description in seen_descriptions:
                continue
            seen_descriptions.add(description)

            context = extract_context(
                description=description,
                error_type=error_type,
                workflow_phase=self.phase_id,
            )
            errors.append(
                self._fingerprint(
                    ErrorEvent(
                        error_id=f"trs-{uuid.uuid4().hex[:8]}",
                        timestamp=datetime.utcnow(),
                        source="transcript",
                        description=description,
                        error_type=error_type,
                        workflow_id=self.workflow_id,
                        phase_id=self.phase_id,
                        context=context,
                    )
                )
            )

        # Traceback pattern
        traceback_pattern = (
            r"Traceback \(most recent call last\):(.+?)(?:(\w+Error|\w+Exception): ([^\n]+))"
        )
        for match in re.finditer(traceback_pattern, source, re.DOTALL):
            stack_trace = match.group(1)
            error_type = match.group(2)
            message = match.group(3)
            description = f"{error_type}: {message}"

            if description in seen_descriptions:
                continue
            seen_descriptions.add(description)

            # Extract file/line from traceback
            file_match = re.search(r'File "([^"]+)", line (\d+)', stack_trace)
            file_path = file_match.group(1) if file_match else None
            line_number = int(file_match.group(2)) if file_match else None

            full_stack_trace = f"Traceback (most recent call last):{stack_trace}"
            context = extract_context(
                description=description,
                error_type=error_type,
                file_path=file_path,
                stack_trace=full_stack_trace,
                workflow_phase=self.phase_id,
            )
            errors.append(
                self._fingerprint(
                    ErrorEvent(
                        error_id=f"trs-{uuid.uuid4().hex[:8]}",
                        timestamp=datetime.utcnow(),
                        source="transcript",
                        description=description,
                        error_type=error_type,
                        file_path=file_path,
                        line_number=line_number,
                        stack_trace=full_stack_trace,
                        workflow_id=self.workflow_id,
                        phase_id=self.phase_id,
                        context=context,
                    )
                )
            )

        return errors
