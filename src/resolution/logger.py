"""
Resolution Logger - CORE-023 Part 3

Logs conflict resolutions to .workflow_log.jsonl following
the format specified in the source plan (lines 70-77):

    log_event(EventType.CONFLICT_RESOLVED, {
        "file": "src/cli.py",
        "strategy": "sequential_merge",
        "confidence": 0.85,
        "resolution_time_ms": 1250,
    })
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schema import EventType, WorkflowEvent


def _get_log_file(working_dir: Optional[Path] = None) -> Path:
    """Get the log file path."""
    if working_dir is None:
        working_dir = Path.cwd()
    return working_dir / ".workflow_log.jsonl"


def _write_event(event: WorkflowEvent, working_dir: Optional[Path] = None) -> None:
    """Write an event to the log file."""
    log_file = _get_log_file(working_dir)

    with open(log_file, 'a') as f:
        f.write(json.dumps(event.model_dump(mode='json'), default=str) + '\n')


def log_resolution(
    file_path: str,
    strategy: str,
    confidence: float,
    resolution_time_ms: int,
    llm_used: bool = False,
    llm_model: Optional[str] = None,
    working_dir: Optional[Path] = None,
) -> None:
    """
    Log a conflict resolution to .workflow_log.jsonl.

    Format follows source plan (lines 70-77):
    - event_type: "conflict_resolved"
    - details.file: path to resolved file
    - details.strategy: resolution strategy used
    - details.confidence: confidence score (0.0-1.0)
    - details.resolution_time_ms: time taken in milliseconds

    Args:
        file_path: Path to the resolved file
        strategy: Resolution strategy (e.g., "3way", "ours", "theirs", "llm")
        confidence: Confidence score (0.0-1.0)
        resolution_time_ms: Time taken to resolve in milliseconds
        llm_used: Whether an LLM was used for resolution
        llm_model: Name of the LLM model if used
        working_dir: Working directory (default: current directory)
    """
    if working_dir is not None:
        working_dir = Path(working_dir)

    details = {
        "file": file_path,
        "strategy": strategy,
        "confidence": confidence,
        "resolution_time_ms": resolution_time_ms,
    }

    if llm_used:
        details["llm_used"] = True
        if llm_model:
            details["llm_model"] = llm_model

    event = WorkflowEvent(
        event_type=EventType.CONFLICT_RESOLVED,
        workflow_id="",  # Will be filled by caller if in workflow context
        message=f"Resolved conflict in {file_path}",
        details=details,
    )

    _write_event(event, working_dir)


def log_escalation(
    file_path: str,
    reason: str,
    options: list[str],
    working_dir: Optional[Path] = None,
) -> None:
    """
    Log a conflict escalation to .workflow_log.jsonl.

    Used when a conflict requires human intervention.

    Args:
        file_path: Path to the file that needs escalation
        reason: Why escalation was needed (e.g., "low_confidence", "complex_merge")
        options: Available options for the user
        working_dir: Working directory (default: current directory)
    """
    if working_dir is not None:
        working_dir = Path(working_dir)

    event = WorkflowEvent(
        event_type=EventType.CONFLICT_ESCALATED,
        workflow_id="",
        message=f"Escalated conflict in {file_path}: {reason}",
        details={
            "file": file_path,
            "reason": reason,
            "options": options,
        },
    )

    _write_event(event, working_dir)
