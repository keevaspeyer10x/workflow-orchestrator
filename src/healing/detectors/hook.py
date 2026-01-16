"""Hook detector for error detection.

This module detects errors from orchestrator hook output.
"""

from datetime import datetime
from typing import Dict, List, Optional
import uuid

from .base import BaseDetector
from ..fingerprint import Fingerprinter
from ..models import ErrorEvent


class HookDetector(BaseDetector):
    """Detect errors from hook execution output.

    Parses hook stdout/stderr and exit codes to detect errors
    from pre/post command hooks.
    """

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

    def detect(self, source: Dict) -> List[ErrorEvent]:
        """Detect errors from hook output.

        Args:
            source: Dict with keys:
                - stdout: Hook stdout
                - stderr: Hook stderr
                - exit_code: Hook exit code
                - hook_name: Name of the hook

        Returns:
            List of detected ErrorEvent instances.
        """
        exit_code = source.get("exit_code", 0)
        if exit_code == 0:
            return []

        stdout = source.get("stdout", "")
        stderr = source.get("stderr", "")
        hook_name = source.get("hook_name", "unknown_hook")

        # Combine output
        output = stderr.strip() or stdout.strip() or f"Hook {hook_name} failed"

        error = ErrorEvent(
            error_id=f"hk-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.utcnow(),
            source="hook",
            description=output[:500],  # Limit length
            command=hook_name,
            exit_code=exit_code,
            workflow_id=self.workflow_id,
            phase_id=self.phase_id,
        )

        return [self._fingerprint(error)]
