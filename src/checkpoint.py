"""
Checkpoint and Resume System (Feature 5)

This module provides checkpoint creation, listing, and resume functionality
for workflow state persistence across sessions.
"""

import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field, asdict

if TYPE_CHECKING:
    from .path_resolver import OrchestratorPaths

logger = logging.getLogger(__name__)


@dataclass
class CheckpointData:
    """
    Data model for a workflow checkpoint.
    
    Contains all information needed to resume a workflow in a new session.
    """
    checkpoint_id: str
    workflow_id: str
    phase_id: str
    item_id: Optional[str]
    timestamp: str
    message: Optional[str] = None
    context_summary: Optional[str] = None
    key_decisions: List[str] = field(default_factory=list)
    file_manifest: List[str] = field(default_factory=list)
    workflow_state_snapshot: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CheckpointData':
        """Create from dictionary."""
        return cls(**data)


class CheckpointManager:
    """
    Manages checkpoint creation, storage, and retrieval.
    """

    def __init__(
        self,
        working_dir: str = ".",
        paths: Optional["OrchestratorPaths"] = None
    ):
        self.working_dir = Path(working_dir).resolve()

        # CORE-025: Use OrchestratorPaths if provided, else use legacy path
        if paths is not None:
            self.checkpoints_dir = paths.checkpoints_dir()
        else:
            # Legacy path for backward compatibility
            self.checkpoints_dir = self.working_dir / ".workflow_checkpoints"

        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    def create_checkpoint(
        self,
        workflow_id: str,
        phase_id: str,
        item_id: Optional[str] = None,
        message: Optional[str] = None,
        context_summary: Optional[str] = None,
        key_decisions: Optional[List[str]] = None,
        file_manifest: Optional[List[str]] = None,
        workflow_state: Optional[dict] = None,
        auto_detect_files: bool = True
    ) -> CheckpointData:
        """
        Create a new checkpoint.
        
        Args:
            workflow_id: ID of the workflow
            phase_id: Current phase ID
            item_id: Optional current item ID
            message: Optional checkpoint message
            context_summary: Optional summary of current context
            key_decisions: Optional list of key decisions made
            file_manifest: Optional list of important files
            workflow_state: Optional workflow state snapshot
            auto_detect_files: Whether to auto-detect recently modified files
        
        Returns:
            CheckpointData: The created checkpoint
        """
        timestamp = datetime.now(timezone.utc)
        
        # Generate checkpoint ID
        checkpoint_id = f"cp_{timestamp.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(workflow_id.encode()).hexdigest()[:6]}"
        
        # Auto-detect files if requested
        files = list(file_manifest or [])
        if auto_detect_files:
            auto_files = self._auto_detect_important_files()
            files.extend(f for f in auto_files if f not in files)
        
        # Auto-generate context summary if not provided
        if not context_summary and workflow_state:
            context_summary = self._generate_context_summary(workflow_state, phase_id)
        
        checkpoint = CheckpointData(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            phase_id=phase_id,
            item_id=item_id,
            timestamp=timestamp.isoformat(),
            message=message,
            context_summary=context_summary,
            key_decisions=key_decisions or [],
            file_manifest=files,
            workflow_state_snapshot=workflow_state
        )
        
        # Save checkpoint
        self._save_checkpoint(checkpoint)
        
        logger.info(f"Created checkpoint: {checkpoint_id}")
        return checkpoint
    
    def _save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """Save a checkpoint to disk."""
        filepath = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"
        with open(filepath, 'w') as f:
            json.dump(checkpoint.to_dict(), f, indent=2, default=str)
    
    def _auto_detect_important_files(self, max_files: int = 10) -> List[str]:
        """
        Auto-detect important files based on recent modifications.
        
        Returns files modified in the last hour, excluding hidden files and common artifacts.
        """
        import time
        
        one_hour_ago = time.time() - 3600
        important_files = []
        
        # Patterns to exclude
        exclude_patterns = {
            '.git', '__pycache__', 'node_modules', '.pytest_cache',
            '.workflow_state.json', '.workflow_log.jsonl', '.workflow_checkpoints'
        }
        
        # Extensions to include
        include_extensions = {
            '.py', '.js', '.ts', '.yaml', '.yml', '.json', '.md',
            '.html', '.css', '.sh', '.sql', '.env'
        }
        
        try:
            for filepath in self.working_dir.rglob('*'):
                if filepath.is_file():
                    # Skip excluded patterns
                    if any(p in str(filepath) for p in exclude_patterns):
                        continue
                    
                    # Check extension
                    if filepath.suffix.lower() not in include_extensions:
                        continue
                    
                    # Check modification time
                    if filepath.stat().st_mtime > one_hour_ago:
                        rel_path = str(filepath.relative_to(self.working_dir))
                        important_files.append(rel_path)
                        
                        if len(important_files) >= max_files:
                            break
        except Exception as e:
            logger.warning(f"Error auto-detecting files: {e}")
        
        return important_files
    
    def _generate_context_summary(self, workflow_state: dict, phase_id: str) -> str:
        """Generate a context summary from workflow state."""
        lines = []
        
        task = workflow_state.get('task_description', 'Unknown task')
        lines.append(f"Task: {task}")
        lines.append(f"Current Phase: {phase_id}")
        
        # Count completed items
        phases = workflow_state.get('phases', {})
        total_completed = 0
        total_items = 0
        for phase_data in phases.values():
            items = phase_data.get('items', {})
            for item_data in items.values():
                total_items += 1
                if item_data.get('status') == 'completed':
                    total_completed += 1
        
        lines.append(f"Progress: {total_completed}/{total_items} items completed")
        
        # Add constraints if present
        constraints = workflow_state.get('constraints', [])
        if constraints:
            lines.append(f"Constraints: {len(constraints)} active")
        
        return "; ".join(lines)
    
    def list_checkpoints(
        self,
        workflow_id: Optional[str] = None,
        include_completed: bool = False
    ) -> List[CheckpointData]:
        """
        List all checkpoints, optionally filtered by workflow.
        
        Args:
            workflow_id: Optional workflow ID to filter by
            include_completed: Whether to include checkpoints from completed workflows
        
        Returns:
            List of checkpoints, sorted by timestamp (newest first)
        """
        checkpoints = []
        
        for filepath in self.checkpoints_dir.glob("cp_*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    checkpoint = CheckpointData.from_dict(data)
                    
                    # Filter by workflow if specified
                    if workflow_id and checkpoint.workflow_id != workflow_id:
                        continue
                    
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Error loading checkpoint {filepath}: {e}")
        
        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        
        return checkpoints
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Get a specific checkpoint by ID."""
        filepath = self.checkpoints_dir / f"{checkpoint_id}.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                return CheckpointData.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading checkpoint {checkpoint_id}: {e}")
            return None
    
    def get_latest_checkpoint(self, workflow_id: Optional[str] = None) -> Optional[CheckpointData]:
        """Get the most recent checkpoint."""
        checkpoints = self.list_checkpoints(workflow_id=workflow_id)
        return checkpoints[0] if checkpoints else None
    
    def cleanup_old_checkpoints(
        self,
        max_age_days: int = 30,
        keep_min: int = 5
    ) -> int:
        """
        Remove old checkpoints.
        
        Args:
            max_age_days: Maximum age in days for checkpoints to keep
            keep_min: Minimum number of checkpoints to keep regardless of age
        
        Returns:
            Number of checkpoints removed
        """
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        checkpoints = self.list_checkpoints()
        
        # Keep at least keep_min checkpoints
        if len(checkpoints) <= keep_min:
            return 0
        
        removed = 0
        for checkpoint in checkpoints[keep_min:]:
            try:
                checkpoint_time = datetime.fromisoformat(checkpoint.timestamp.replace('Z', '+00:00'))
                if checkpoint_time < cutoff:
                    filepath = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"
                    filepath.unlink()
                    removed += 1
                    logger.info(f"Removed old checkpoint: {checkpoint.checkpoint_id}")
            except Exception as e:
                logger.warning(f"Error removing checkpoint {checkpoint.checkpoint_id}: {e}")
        
        return removed
    
    def generate_resume_prompt(self, checkpoint: CheckpointData) -> str:
        """
        Generate a prompt for resuming from a checkpoint.
        
        This prompt is designed to be fed to an LLM to restore context.
        """
        lines = [
            "=" * 60,
            "WORKFLOW RESUME FROM CHECKPOINT",
            "=" * 60,
            "",
            f"Checkpoint: {checkpoint.checkpoint_id}",
            f"Created: {checkpoint.timestamp}",
            f"Workflow: {checkpoint.workflow_id}",
            f"Phase: {checkpoint.phase_id}",
        ]
        
        if checkpoint.item_id:
            lines.append(f"Last Item: {checkpoint.item_id}")
        
        if checkpoint.message:
            lines.append("")
            lines.append(f"Message: {checkpoint.message}")
        
        if checkpoint.context_summary:
            lines.append("")
            lines.append("Context Summary:")
            lines.append(f"  {checkpoint.context_summary}")
        
        if checkpoint.key_decisions:
            lines.append("")
            lines.append("Key Decisions Made:")
            for decision in checkpoint.key_decisions:
                lines.append(f"  - {decision}")
        
        if checkpoint.file_manifest:
            lines.append("")
            lines.append("Important Files:")
            for filepath in checkpoint.file_manifest:
                lines.append(f"  - {filepath}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append("Run 'orchestrator status' to see current workflow state.")
        lines.append("=" * 60)
        
        return "\n".join(lines)
