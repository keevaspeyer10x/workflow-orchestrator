"""Historical Backfill - Phase 5 Observability & Hardening.

Processes existing workflow logs to populate the pattern database
with historical errors.

Usage:
    orchestrator heal backfill [--log-dir <dir>] [--dry-run] [--limit N]
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .fingerprint import Fingerprinter
from .models import ErrorEvent
from .costs import get_cost_tracker
from .context_extraction import extract_context

if TYPE_CHECKING:
    from .client import HealingClient


class HistoricalBackfill:
    """Process existing logs to build pattern database.

    Scans for .workflow_log.jsonl files and extracts error patterns
    to seed the healing database.

    Usage:
        backfill = HistoricalBackfill(healing_client)
        count = await backfill.backfill_workflow_logs(Path("."))
        print(f"Processed {count} historical errors")
    """

    def __init__(self, client: "HealingClient"):
        self.client = client
        self.fingerprinter = Fingerprinter()

    async def backfill_workflow_logs(
        self,
        log_dir: Path,
        limit: Optional[int] = None
    ) -> int:
        """Process historical workflow logs.

        Args:
            log_dir: Directory to scan for logs
            limit: Maximum number of log files to process

        Returns:
            Number of errors processed
        """
        # Find all workflow log files
        log_files = list(log_dir.glob("**/.workflow_log.jsonl"))
        log_files.extend(log_dir.glob("**/workflow_log.jsonl"))

        if limit:
            log_files = log_files[:limit]

        total_count = 0
        cost_tracker = get_cost_tracker()

        for log_file in log_files:
            # Check cost limits
            can_continue, reason = cost_tracker.can_validate()
            if not can_continue:
                break

            count = await self._process_log_file(log_file)
            total_count += count

        return total_count

    async def _process_log_file(self, log_file: Path) -> int:
        """Process a single workflow log file.

        Args:
            log_file: Path to the log file

        Returns:
            Number of errors found
        """
        count = 0

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                        error = self._extract_error(event)
                        if error:
                            await self._record_error(error)
                            count += 1
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
        except Exception:
            # Skip files we can't read
            pass

        return count

    def _extract_error(self, event: dict) -> Optional[ErrorEvent]:
        """Extract an error from a workflow log event.

        Args:
            event: Parsed log event

        Returns:
            ErrorEvent if this is an error event, else None
        """
        event_type = event.get("event_type") or event.get("type")

        # Look for error indicators
        if event_type not in ("error", "failure", "subprocess_failed", "verification_failed"):
            return None

        # Extract error details
        description = event.get("description") or event.get("message") or event.get("error")
        if not description:
            return None

        timestamp_str = event.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        error_type = event.get("error_type")
        file_path = event.get("file_path") or event.get("file")
        stack_trace = event.get("stack_trace") or event.get("traceback")
        phase_id = event.get("phase_id")

        # Extract context for intelligent pattern filtering
        context = extract_context(
            description=description,
            error_type=error_type,
            file_path=file_path,
            stack_trace=stack_trace,
            workflow_phase=phase_id,
        )

        error = ErrorEvent(
            error_id=event.get("id") or f"backfill-{timestamp.isoformat()}",
            timestamp=timestamp,
            source="backfill",
            description=description,
            error_type=error_type,
            file_path=file_path,
            line_number=event.get("line_number") or event.get("line"),
            stack_trace=stack_trace,
            command=event.get("command"),
            exit_code=event.get("exit_code"),
            workflow_id=event.get("workflow_id"),
            phase_id=phase_id,
            project_id=event.get("project_id"),
            context=context,
        )

        # Add fingerprints
        error.fingerprint = self.fingerprinter.fingerprint(error)
        error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)

        return error

    async def _record_error(self, error: ErrorEvent) -> None:
        """Record an error in the pattern database.

        Args:
            error: Error to record
        """
        try:
            await self.client.supabase.record_historical_error(error)
        except Exception:
            # Log but don't fail on individual errors
            pass

    async def estimate_count(self, log_dir: Path) -> int:
        """Estimate number of logs that would be processed.

        Args:
            log_dir: Directory to scan

        Returns:
            Estimated count of log files
        """
        log_files = list(log_dir.glob("**/.workflow_log.jsonl"))
        log_files.extend(log_dir.glob("**/workflow_log.jsonl"))
        return len(log_files)
