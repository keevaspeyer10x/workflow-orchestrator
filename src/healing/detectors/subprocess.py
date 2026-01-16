"""Subprocess detector for error detection.

This module detects errors from subprocess output (stdout/stderr).
"""

import re
from datetime import datetime
from typing import List, Optional, Tuple
import uuid

from .base import BaseDetector
from ..fingerprint import Fingerprinter
from ..models import ErrorEvent
from ..context_extraction import extract_context


class SubprocessDetector(BaseDetector):
    """Detect errors from subprocess output.

    Parses stdout/stderr for error patterns from:
    - Python (TypeError, ValueError, etc.)
    - Rust (error[E0001])
    - Go (panic)
    - Node.js (Error: ...)
    - pytest (FAILED tests/...)
    """

    # Error patterns: (regex, language, error_type extractor)
    ERROR_PATTERNS: List[Tuple[str, str, Optional[str]]] = [
        # Python errors with traceback
        (
            r"^(\w+Error|\w+Exception): (.+)$",
            "python",
            None,  # Extract from match group 1
        ),
        # Rust errors
        (r"^error\[(E\d+)\]: (.+)$", "rust", None),
        # Go panic
        (r"^panic: (.+)$", "go", "GoPanic"),
        # Node.js
        (r"^Error: (.+)$", "node", "Error"),
        # pytest failures
        (r"FAILED (.+)::(\w+)", "pytest", "TestFailure"),
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

    def detect(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        command: str,
    ) -> List[ErrorEvent]:
        """Detect errors from subprocess output.

        Args:
            exit_code: Process exit code.
            stdout: Process stdout.
            stderr: Process stderr.
            command: Command that was run.

        Returns:
            List of detected ErrorEvent instances.
        """
        # No error on success
        if exit_code == 0:
            return []

        errors = []

        # Combine output for analysis
        combined = f"{stderr}\n{stdout}"

        # Try to parse Python traceback first
        traceback_error = self._parse_python_traceback(combined, command)
        if traceback_error:
            errors.append(self._fingerprint(traceback_error))
            return errors

        # Try other patterns
        for pattern, language, fixed_type in self.ERROR_PATTERNS:
            for match in re.finditer(pattern, combined, re.MULTILINE):
                error = self._create_error_from_match(
                    match, language, fixed_type, command, combined
                )
                if error:
                    errors.append(self._fingerprint(error))

        # If no specific pattern matched, create a generic error
        if not errors and stderr.strip():
            description = stderr.strip()[:500]  # Limit length
            context = extract_context(
                description=description,
                workflow_phase=self.phase_id,
            )
            errors.append(
                self._fingerprint(
                    ErrorEvent(
                        error_id=f"sub-{uuid.uuid4().hex[:8]}",
                        timestamp=datetime.utcnow(),
                        source="subprocess",
                        description=description,
                        command=command,
                        exit_code=exit_code,
                        workflow_id=self.workflow_id,
                        phase_id=self.phase_id,
                        context=context,
                    )
                )
            )

        return errors

    def _parse_python_traceback(
        self, output: str, command: str
    ) -> Optional[ErrorEvent]:
        """Parse Python traceback from output.

        Args:
            output: Combined stdout/stderr.
            command: Command that was run.

        Returns:
            ErrorEvent if traceback found, None otherwise.
        """
        # Look for traceback
        traceback_match = re.search(
            r"Traceback \(most recent call last\):(.+?)^(\w+Error|\w+Exception): (.+)$",
            output,
            re.MULTILINE | re.DOTALL,
        )
        if traceback_match:
            stack_trace = f"Traceback (most recent call last):{traceback_match.group(1)}"
            error_type = traceback_match.group(2)
            message = traceback_match.group(3)

            # Extract file/line from traceback
            file_match = re.search(
                r'File "([^"]+)", line (\d+)', stack_trace
            )
            file_path = file_match.group(1) if file_match else None
            line_number = int(file_match.group(2)) if file_match else None

            description = f"{error_type}: {message}"
            context = extract_context(
                description=description,
                error_type=error_type,
                file_path=file_path,
                stack_trace=stack_trace,
                workflow_phase=self.phase_id,
            )

            return ErrorEvent(
                error_id=f"sub-{uuid.uuid4().hex[:8]}",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description=description,
                error_type=error_type,
                file_path=file_path,
                line_number=line_number,
                stack_trace=stack_trace,
                command=command,
                workflow_id=self.workflow_id,
                phase_id=self.phase_id,
                context=context,
            )

        return None

    def _create_error_from_match(
        self,
        match: re.Match,
        language: str,
        fixed_type: Optional[str],
        command: str,
        full_output: str,
    ) -> Optional[ErrorEvent]:
        """Create ErrorEvent from regex match.

        Args:
            match: Regex match object.
            language: Language identifier.
            fixed_type: Fixed error type if not extractable.
            command: Command that was run.
            full_output: Full output for context.

        Returns:
            ErrorEvent instance.
        """
        if language == "python":
            error_type = match.group(1)
            message = match.group(2)
            description = f"{error_type}: {message}"
        elif language == "rust":
            error_code = match.group(1)
            message = match.group(2)
            error_type = f"RustError_{error_code}"
            description = f"error[{error_code}]: {message}"
        elif language == "go":
            message = match.group(1)
            error_type = fixed_type or "GoPanic"
            description = f"panic: {message}"
        elif language == "node":
            message = match.group(1)
            error_type = fixed_type or "Error"
            description = f"Error: {message}"
        elif language == "pytest":
            test_file = match.group(1)
            test_name = match.group(2)
            error_type = fixed_type or "TestFailure"
            description = f"FAILED {test_file}::{test_name}"
        else:
            description = match.group(0)
            error_type = fixed_type or "UnknownError"

        context = extract_context(
            description=description,
            error_type=error_type,
            workflow_phase=self.phase_id,
        )

        return ErrorEvent(
            error_id=f"sub-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.utcnow(),
            source="subprocess",
            description=description,
            error_type=error_type,
            command=command,
            workflow_id=self.workflow_id,
            phase_id=self.phase_id,
            context=context,
        )
