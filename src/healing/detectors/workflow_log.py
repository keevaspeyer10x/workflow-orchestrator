"""Workflow log detector for error detection.

This module detects errors from .workflow_log.jsonl files.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import uuid

from .base import BaseDetector
from ..fingerprint import Fingerprinter
from ..models import ErrorEvent


class WorkflowLogDetector(BaseDetector):
    """Detect errors from workflow log JSONL files.

    Parses .workflow_log.jsonl and extracts events with:
    - event_type: "error"
    - success: false (for failed operations)
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

    def detect(self, source: str) -> List[ErrorEvent]:
        """Detect errors from workflow log file.

        Args:
            source: Path to the .workflow_log.jsonl file.

        Returns:
            List of detected ErrorEvent instances.
        """
        path = Path(source)
        if not path.exists():
            return []

        errors = []
        try:
            with open(path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

                    error = self._parse_event(event)
                    if error:
                        errors.append(self._fingerprint(error))
        except (OSError, IOError):
            # File access errors - return empty
            return []

        return errors

    def _parse_event(self, event: dict) -> Optional[ErrorEvent]:
        """Parse a single log event.

        Args:
            event: Parsed JSON event from log.

        Returns:
            ErrorEvent if this is an error event, None otherwise.
        """
        event_type = event.get("event_type", "")

        # Check if this is an error event
        if event_type != "error" and event.get("success") is not False:
            return None

        # Parse timestamp
        timestamp_str = event.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        return ErrorEvent(
            error_id=event.get("error_id", f"wfl-{uuid.uuid4().hex[:8]}"),
            timestamp=timestamp,
            source="workflow_log",
            description=event.get("description", event.get("message", "Unknown error")),
            error_type=event.get("error_type"),
            file_path=event.get("file_path"),
            line_number=event.get("line_number"),
            stack_trace=event.get("stack_trace"),
            workflow_id=event.get("workflow_id", self.workflow_id),
            phase_id=event.get("phase_id", self.phase_id),
        )
