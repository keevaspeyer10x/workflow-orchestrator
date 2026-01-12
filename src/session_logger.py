"""
Enhanced Session Logger with Structured Event Logging and Analysis.

CORE-024: Session Transcript Logging with Secret Scrubbing
- Builds on TranscriptLogger for secret scrubbing
- Adds structured event logging (JSONL format)
- Provides async logging for performance (<5% overhead)
- Enables session analysis (completion rates, failure points, etc.)
"""

import json
import logging
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

# Session directory
SESSIONS_DIR = ".orchestrator/sessions"

# Event types
EVENT_WORKFLOW_STARTED = "workflow_started"
EVENT_WORKFLOW_FINISHED = "workflow_finished"
EVENT_WORKFLOW_ABANDONED = "workflow_abandoned"
EVENT_PHASE_ADVANCED = "phase_advanced"
EVENT_ITEM_COMPLETED = "item_completed"
EVENT_ITEM_SKIPPED = "item_skipped"
EVENT_COMMAND = "command"
EVENT_OUTPUT = "output"
EVENT_ERROR = "error"
EVENT_REVIEW_COMPLETED = "review_completed"

# Export constants
__all__ = [
    'SessionLogger',
    'SessionContext',
    'SessionAnalyzer',
    'format_analysis_report',
    'EVENT_WORKFLOW_STARTED',
    'EVENT_WORKFLOW_FINISHED',
    'EVENT_WORKFLOW_ABANDONED',
    'EVENT_PHASE_ADVANCED',
    'EVENT_ITEM_COMPLETED',
    'EVENT_ITEM_SKIPPED',
    'EVENT_COMMAND',
    'EVENT_OUTPUT',
    'EVENT_ERROR',
    'EVENT_REVIEW_COMPLETED',
]


@dataclass
class SessionContext:
    """Tracks current session state."""
    session_id: str
    task_description: str
    workflow_id: Optional[str]
    start_time: datetime
    log_file: Path
    end_time: Optional[datetime] = None
    status: Optional[str] = None  # completed, abandoned, error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "task_description": self.task_description,
            "workflow_id": self.workflow_id,
            "start_time": self.start_time.isoformat(),
            "log_file": str(self.log_file),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
        }


class SessionLogger:
    """
    Session logger with structured event logging and secret scrubbing.

    Features:
    - Async logging (background thread) for minimal performance overhead
    - Structured event logging in JSONL format
    - Automatic secret scrubbing via TranscriptLogger
    - Session metadata tracking
    - Session analysis capabilities

    Usage:
        logger = SessionLogger(working_dir=Path.cwd())
        session = logger.start_session("Implement feature X", workflow_id="wf_123")
        logger.log_event(EVENT_WORKFLOW_STARTED, {"task": "Implement X"})
        logger.log_event(EVENT_ITEM_COMPLETED, {"item_id": "check_roadmap"})
        logger.end_session("completed")
    """

    def __init__(
        self,
        working_dir: Path = None,
        secrets_manager = None,
        async_logging: bool = True,
    ):
        """
        Initialize session logger.

        Args:
            working_dir: Working directory (sessions stored in working_dir/.orchestrator/sessions/)
            secrets_manager: SecretsManager instance for secret scrubbing
            async_logging: Enable async logging (background thread)
        """
        self.working_dir = working_dir or Path.cwd()
        self.sessions_dir = self.working_dir / SESSIONS_DIR
        self._secrets_manager = secrets_manager
        self._async_logging = async_logging

        # Current session
        self._current_session: Optional[SessionContext] = None

        # Async logging
        if self._async_logging:
            self._log_queue: queue.Queue = queue.Queue()
            self._worker_thread: Optional[threading.Thread] = None
            self._stop_event = threading.Event()
            self._start_worker()

        # Import TranscriptLogger for secret scrubbing
        from src.transcript_logger import TranscriptLogger
        self._scrubber = TranscriptLogger(
            secrets_manager=secrets_manager,
            sessions_dir=self.sessions_dir,
        )

    def _start_worker(self):
        """Start background worker thread for async logging."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._log_worker, daemon=True)
        self._worker_thread.start()
        logger.debug("Async logging worker started")

    def _log_worker(self):
        """Background worker that writes events to disk."""
        while not self._stop_event.is_set():
            try:
                # Wait for events with timeout to check stop_event periodically
                try:
                    event_data = self._log_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Write event to disk
                self._write_event_to_disk(event_data)
                self._log_queue.task_done()

            except Exception as e:
                logger.error(f"Error in log worker: {e}")

    def _write_event_to_disk(self, event_data: Dict[str, Any]):
        """Write a single event to disk (called by worker thread)."""
        if not self._current_session:
            logger.warning("Attempted to write event without active session")
            return

        try:
            # Scrub secrets from event data
            scrubbed_data = self._scrub_event_data(event_data)

            # Write to session file
            with open(self._current_session.log_file, 'a') as f:
                f.write(json.dumps(scrubbed_data) + "\n")

        except Exception as e:
            logger.error(f"Failed to write event to disk: {e}")

    def _scrub_event_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Scrub secrets from event data recursively."""
        if isinstance(data, dict):
            return {k: self._scrub_event_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._scrub_event_data(item) for item in data]
        elif isinstance(data, str):
            return self._scrubber.scrub(data)
        else:
            return data

    def _ensure_sessions_dir(self):
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _generate_session_id(self, task_description: str) -> str:
        """
        Generate session ID in format: YYYY-MM-DD_HH-MM-SS_task-slug

        Args:
            task_description: Task description to slugify

        Returns:
            Session ID string
        """
        # Generate timestamp prefix
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Create slug from task description (lowercase, replace spaces with hyphens)
        slug = task_description.lower()
        slug = ''.join(c if c.isalnum() or c in [' ', '-'] else '' for c in slug)
        slug = '-'.join(slug.split())[:50]  # Limit length

        return f"{timestamp}_{slug}"

    def start_session(
        self,
        task_description: str,
        workflow_id: Optional[str] = None,
    ) -> SessionContext:
        """
        Start a new session.

        Args:
            task_description: Description of the task
            workflow_id: Optional workflow ID

        Returns:
            SessionContext object
        """
        self._ensure_sessions_dir()

        # Generate session ID
        session_id = self._generate_session_id(task_description)

        # Create session context
        log_file = self.sessions_dir / f"{session_id}.jsonl"
        session = SessionContext(
            session_id=session_id,
            task_description=task_description,
            workflow_id=workflow_id,
            start_time=datetime.now(),
            log_file=log_file,
        )

        self._current_session = session

        # Log session start event
        self.log_event(EVENT_WORKFLOW_STARTED, {
            "task": task_description,
            "workflow_id": workflow_id,
            "session_id": session_id,
        })

        logger.info(f"Session started: {session_id}")
        return session

    def log_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a structured event.

        Args:
            event_type: Type of event (e.g., "workflow_started", "item_completed")
            data: Event data
            metadata: Optional metadata
        """
        if not self._current_session:
            logger.warning(f"No active session, skipping event: {event_type}")
            return

        # Build event
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data,
        }

        if metadata:
            event["metadata"] = metadata

        # Queue for async writing or write synchronously
        if self._async_logging:
            self._log_queue.put(event)
        else:
            self._write_event_to_disk(event)

    def end_session(self, status: str = "completed"):
        """
        End the current session.

        Args:
            status: Session status ("completed", "abandoned", "error")
        """
        if not self._current_session:
            logger.warning("No active session to end")
            return

        # Update session context
        self._current_session.end_time = datetime.now()
        self._current_session.status = status

        # Log session end event
        duration = (self._current_session.end_time - self._current_session.start_time).total_seconds()
        self.log_event(EVENT_WORKFLOW_FINISHED if status == "completed" else EVENT_WORKFLOW_ABANDONED, {
            "status": status,
            "duration_seconds": duration,
            "session_id": self._current_session.session_id,
        })

        # Flush async queue if enabled
        if self._async_logging:
            self._log_queue.join()  # Wait for all events to be written

        logger.info(f"Session ended: {self._current_session.session_id} (status: {status}, duration: {duration:.1f}s)")
        self._current_session = None

    def get_current_session(self) -> Optional[SessionContext]:
        """Get the current session context."""
        return self._current_session

    def list_sessions(
        self,
        limit: Optional[int] = None,
        workflow_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List sessions.

        Args:
            limit: Maximum number of sessions to return
            workflow_id: Filter by workflow ID

        Returns:
            List of session info dicts
        """
        if not self.sessions_dir.exists():
            return []

        sessions = []
        for log_file in self.sessions_dir.glob("*.jsonl"):
            # Read first event to get session metadata
            try:
                with open(log_file, 'r') as f:
                    first_line = f.readline()
                    if first_line:
                        first_event = json.loads(first_line)
                        session_info = {
                            "session_id": first_event.get("data", {}).get("session_id", log_file.stem),
                            "task": first_event.get("data", {}).get("task", "Unknown"),
                            "workflow_id": first_event.get("data", {}).get("workflow_id"),
                            "start_time": first_event.get("timestamp"),
                            "file_path": str(log_file),
                            "size_bytes": log_file.stat().st_size,
                        }

                        # Filter by workflow_id if specified
                        if workflow_id and session_info["workflow_id"] != workflow_id:
                            continue

                        sessions.append(session_info)
            except Exception as e:
                logger.warning(f"Failed to read session file {log_file}: {e}")

        # Sort by start_time (newest first)
        sessions.sort(key=lambda x: x.get("start_time", ""), reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_session_events(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all events for a session.

        Args:
            session_id: Session ID

        Returns:
            List of event dicts, or None if session not found
        """
        # Find session file
        session_files = list(self.sessions_dir.glob(f"*{session_id}*.jsonl"))
        if not session_files:
            return None

        # Read all events
        events = []
        with open(session_files[0], 'r') as f:
            for line in f:
                try:
                    events.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse event line: {line}")

        return events

    def shutdown(self):
        """Shutdown the logger (stop worker thread, flush queue)."""
        if self._async_logging and self._worker_thread:
            logger.debug("Shutting down session logger...")
            self._log_queue.join()  # Wait for queue to empty
            self._stop_event.set()  # Signal worker to stop
            self._worker_thread.join(timeout=5)  # Wait for worker to finish
            logger.debug("Session logger shutdown complete")


class SessionAnalyzer:
    """
    Analyzes session patterns and generates statistics.

    Usage:
        analyzer = SessionAnalyzer(sessions_dir=Path(".orchestrator/sessions"))
        report = analyzer.analyze(last_n_days=30)
        print(report)
    """

    def __init__(self, sessions_dir: Path):
        """
        Initialize session analyzer.

        Args:
            sessions_dir: Directory containing session log files
        """
        self.sessions_dir = sessions_dir

    def analyze(
        self,
        last_n_days: Optional[int] = 30,
        last_n_sessions: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Analyze sessions and generate statistics.

        Args:
            last_n_days: Analyze sessions from last N days
            last_n_sessions: Analyze last N sessions

        Returns:
            Analysis report dict
        """
        # Load sessions
        sessions = self._load_sessions(last_n_days, last_n_sessions)

        if not sessions:
            return {
                "total_sessions": 0,
                "message": "No sessions found for analysis",
            }

        # Calculate statistics
        completion_rate = self._calculate_completion_rate(sessions)
        failure_points = self._identify_failure_points(sessions)
        duration_stats = self._calculate_duration_stats(sessions)
        error_frequency = self._calculate_error_frequency(sessions)
        phase_stats = self._calculate_phase_stats(sessions)

        return {
            "total_sessions": len(sessions),
            "completion_rate": completion_rate,
            "failure_points": failure_points,
            "duration_stats": duration_stats,
            "error_frequency": error_frequency,
            "phase_stats": phase_stats,
            "analysis_period_days": last_n_days,
        }

    def _load_sessions(
        self,
        last_n_days: Optional[int],
        last_n_sessions: Optional[int],
    ) -> List[List[Dict[str, Any]]]:
        """Load session events from log files."""
        if not self.sessions_dir.exists():
            return []

        # Get all session files
        session_files = sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        # Filter by time if specified
        if last_n_days:
            cutoff = datetime.now() - timedelta(days=last_n_days)
            session_files = [
                f for f in session_files
                if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff
            ]

        # Limit by count if specified
        if last_n_sessions:
            session_files = session_files[:last_n_sessions]

        # Load events from each session
        sessions = []
        for session_file in session_files:
            try:
                events = []
                with open(session_file, 'r') as f:
                    for line in f:
                        try:
                            events.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            pass
                if events:
                    sessions.append(events)
            except Exception as e:
                logger.warning(f"Failed to load session {session_file}: {e}")

        return sessions

    def _calculate_completion_rate(self, sessions: List[List[Dict[str, Any]]]) -> float:
        """Calculate workflow completion rate."""
        completed = sum(
            1 for session in sessions
            if any(e["type"] == EVENT_WORKFLOW_FINISHED for e in session)
        )
        return completed / len(sessions) if sessions else 0.0

    def _identify_failure_points(
        self,
        sessions: List[List[Dict[str, Any]]]
    ) -> Dict[str, int]:
        """Identify most common failure points (phases)."""
        failure_points = defaultdict(int)

        for session in sessions:
            # Check if session was abandoned
            abandoned = any(e["type"] == EVENT_WORKFLOW_ABANDONED for e in session)
            if not abandoned:
                continue

            # Find last phase before abandonment
            # Look for the "to_phase" field which indicates which phase we entered
            last_phase = None
            for event in reversed(session):
                if event["type"] == EVENT_PHASE_ADVANCED:
                    last_phase = event.get("data", {}).get("to_phase")
                    if last_phase:
                        break

            if last_phase:
                failure_points[last_phase] += 1

        # Sort by frequency
        return dict(sorted(failure_points.items(), key=lambda x: x[1], reverse=True))

    def _calculate_duration_stats(
        self,
        sessions: List[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Calculate session duration statistics."""
        durations = []
        phase_durations = defaultdict(list)

        for session in sessions:
            # Overall session duration
            start_event = next((e for e in session if e["type"] == EVENT_WORKFLOW_STARTED), None)
            end_event = next((e for e in session if e["type"] in [EVENT_WORKFLOW_FINISHED, EVENT_WORKFLOW_ABANDONED]), None)

            if start_event and end_event:
                start_time = datetime.fromisoformat(start_event["timestamp"])
                end_time = datetime.fromisoformat(end_event["timestamp"])
                duration = (end_time - start_time).total_seconds() / 60  # minutes
                durations.append(duration)

            # Phase durations (simplified - would need phase start/end tracking)
            # For now, just track time between phase advances

        if durations:
            return {
                "average_minutes": sum(durations) / len(durations),
                "min_minutes": min(durations),
                "max_minutes": max(durations),
                "total_sessions": len(durations),
            }
        else:
            return {"average_minutes": 0, "total_sessions": 0}

    def _calculate_error_frequency(
        self,
        sessions: List[List[Dict[str, Any]]]
    ) -> List[Tuple[str, int]]:
        """Calculate error frequency."""
        errors = defaultdict(int)

        for session in sessions:
            for event in session:
                if event["type"] == EVENT_ERROR:
                    error_msg = event.get("data", {}).get("message", "Unknown error")
                    # Simplify error message (first 50 chars)
                    error_key = error_msg[:50]
                    errors[error_key] += 1

        # Sort by frequency
        return sorted(errors.items(), key=lambda x: x[1], reverse=True)[:10]

    def _calculate_phase_stats(
        self,
        sessions: List[List[Dict[str, Any]]]
    ) -> Dict[str, int]:
        """Calculate phase completion statistics."""
        phase_completions = defaultdict(int)

        for session in sessions:
            for event in session:
                if event["type"] == EVENT_PHASE_ADVANCED:
                    phase = event.get("data", {}).get("to_phase")
                    if phase:
                        phase_completions[phase] += 1

        return dict(phase_completions)


def format_analysis_report(analysis: Dict[str, Any]) -> str:
    """
    Format analysis report for display.

    Args:
        analysis: Analysis report dict from SessionAnalyzer

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("Session Analysis")
    lines.append("=" * 60)
    lines.append(f"Total Sessions: {analysis.get('total_sessions', 0)}")

    if analysis.get("total_sessions", 0) == 0:
        lines.append("\nNo sessions found for analysis.")
        return "\n".join(lines)

    # Completion rate
    completion_rate = analysis.get("completion_rate", 0)
    lines.append(f"Workflow Completion Rate: {completion_rate:.1%}")

    # Failure points
    failure_points = analysis.get("failure_points", {})
    if failure_points:
        lines.append("\nMost Common Failure Points:")
        for phase, count in list(failure_points.items())[:5]:
            lines.append(f"  - {phase}: {count} failures")

    # Duration stats
    duration_stats = analysis.get("duration_stats", {})
    if duration_stats.get("average_minutes"):
        lines.append("\nDuration Statistics:")
        lines.append(f"  Average: {duration_stats['average_minutes']:.1f} minutes")
        lines.append(f"  Min: {duration_stats.get('min_minutes', 0):.1f} minutes")
        lines.append(f"  Max: {duration_stats.get('max_minutes', 0):.1f} minutes")

    # Error frequency
    error_frequency = analysis.get("error_frequency", [])
    if error_frequency:
        lines.append("\nTop Errors:")
        for error_msg, count in error_frequency[:5]:
            lines.append(f"  - {error_msg}... ({count} occurrences)")

    # Phase stats
    phase_stats = analysis.get("phase_stats", {})
    if phase_stats:
        lines.append("\nPhase Completion Counts:")
        for phase, count in sorted(phase_stats.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {phase}: {count} completions")

    lines.append(f"\nAnalysis Period: Last {analysis.get('analysis_period_days', 30)} days")
    lines.append("=" * 60)

    return "\n".join(lines)
