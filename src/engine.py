"""
Workflow Engine - Core Logic

This module implements the workflow state machine, validation, and transitions.
"""

import json
import yaml
import subprocess
import re
import hashlib
import fcntl
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple
import uuid

# Configure logging
logger = logging.getLogger(__name__)

from .schema import (
    WorkflowDef, WorkflowState, PhaseState, ItemState,
    WorkflowEvent, EventType, ItemStatus, PhaseStatus, WorkflowStatus,
    VerificationType, ChecklistItemDef
)

# Template pattern for {{variable}} substitution
_TEMPLATE_PATTERN = re.compile(r"\{\{(\w+)\}\}")

# Constants
COMMAND_TIMEOUT_SECONDS = 300  # 5 minutes
OUTPUT_TRUNCATE_LENGTH = 1000  # Max chars for stdout/stderr
MIN_SKIP_REASON_LENGTH = 10  # Minimum characters for skip reason


class WorkflowEngine:
    """
    The core workflow engine that manages state transitions and verification.
    """
    
    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.state_file = self.working_dir / ".workflow_state.json"
        self.log_file = self.working_dir / ".workflow_log.jsonl"
        self.workflow_def: Optional[WorkflowDef] = None
        self.state: Optional[WorkflowState] = None
    
    # ========================================================================
    # Template Substitution
    # ========================================================================
    
    def _substitute_template(self, text: str, sanitize_for_shell: bool = False) -> str:
        """
        Substitute {{var}} with values from workflow settings.
        
        Args:
            text: The text containing template variables
            sanitize_for_shell: If True, sanitize values to prevent shell injection
        """
        if not text or not self.workflow_def or not self.workflow_def.settings:
            return text
        
        def replace(match):
            key = match.group(1)
            if key in self.workflow_def.settings:
                value = str(self.workflow_def.settings[key])
                if sanitize_for_shell:
                    # Sanitize for shell safety - allow common command characters
                    # Spaces are OK (we use shlex.split), but block dangerous chars
                    import re as regex
                    dangerous_chars = r'[;&|`$(){}\[\]<>\\!\n\r]'
                    if regex.search(dangerous_chars, value):
                        raise ValueError(f"Unsafe characters in setting '{key}': {value}")
                return value
            return match.group(0)  # Leave unchanged if not found
        
        return _TEMPLATE_PATTERN.sub(replace, text)
    
    # ========================================================================
    # Datetime Parsing
    # ========================================================================
    
    def _parse_datetime(self, value, field_name: str = "unknown") -> Optional[datetime]:
        """Parse a datetime from string or return as-is if already datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Handle ISO format with or without timezone
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as e:
                logger.warning(f"Failed to parse datetime for field '{field_name}': {value} - {e}")
                return None
        logger.warning(f"Unexpected type for datetime field '{field_name}': {type(value)}")
        return None
    
    def _parse_state_datetimes(self, data: dict) -> dict:
        """Recursively parse datetime strings in state data."""
        datetime_fields = ['created_at', 'updated_at', 'completed_at', 'started_at', 'skipped_at']
        
        for field in datetime_fields:
            if field in data and data[field]:
                data[field] = self._parse_datetime(data[field], field)
        
        # Parse phases
        if 'phases' in data:
            for phase_id, phase_data in data['phases'].items():
                for field in datetime_fields:
                    if field in phase_data and phase_data[field]:
                        phase_data[field] = self._parse_datetime(phase_data[field], f"phases.{phase_id}.{field}")
                
                # Parse items within phases
                if 'items' in phase_data:
                    for item_id, item_data in phase_data['items'].items():
                        for field in datetime_fields:
                            if field in item_data and item_data[field]:
                                item_data[field] = self._parse_datetime(item_data[field], f"phases.{phase_id}.items.{item_id}.{field}")
        
        return data
    
    # ========================================================================
    # Loading and Saving
    # ========================================================================
    
    def load_workflow_def(self, yaml_path: str) -> WorkflowDef:
        """Load a workflow definition from a YAML file."""
        try:
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
            if data is None:
                raise ValueError(f"Empty or invalid YAML file: {yaml_path}")
            self.workflow_def = WorkflowDef(**data)
            return self.workflow_def
        except FileNotFoundError:
            raise ValueError(f"Workflow file not found: {yaml_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax in {yaml_path}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load workflow from {yaml_path}: {e}")
    
    def load_state(self) -> Optional[WorkflowState]:
        """Load the current workflow state from the state file."""
        if not self.state_file.exists():
            return None
        
        with open(self.state_file, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        # Parse datetime strings
        data = self._parse_state_datetimes(data)
        
        self.state = WorkflowState(**data)
        
        # PRIORITY 1: Use version-locked workflow definition from state (prevents schema drift)
        if self.state and self.state.workflow_definition:
            try:
                self.workflow_def = WorkflowDef(**self.state.workflow_definition)
                logger.debug("Loaded version-locked workflow definition from state")
                return self.state
            except Exception as e:
                logger.warning(f"Failed to load stored workflow definition: {e}")
                # Fall through to load from file
        
        # PRIORITY 2: Fallback to loading from YAML file (for backwards compatibility)
        if self.state and self.state.metadata.get("workflow_yaml_path"):
            yaml_path = Path(self.state.metadata["workflow_yaml_path"])
            if yaml_path.exists():
                self.load_workflow_def(str(yaml_path))
                # Warn about potential schema drift
                if self.state.workflow_definition is None:
                    logger.warning("Workflow state missing version-locked definition. Using current workflow.yaml which may have changed.")
            elif (self.working_dir / "workflow.yaml").exists():
                # Fallback to default location
                self.load_workflow_def(str(self.working_dir / "workflow.yaml"))
        
        return self.state
    
    def save_state(self):
        """Save the current workflow state to the state file (with file locking)."""
        if not self.state:
            return
        
        self.state.update_timestamp()
        
        # Write to temp file first, then atomic rename
        # Keep lock until after rename to prevent race condition
        temp_file = self.state_file.with_suffix('.tmp')
        
        with open(temp_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(self.state.model_dump(mode='json'), f, indent=2, default=str)
                f.flush()  # Ensure data is written before rename
                # Atomic rename while still holding lock
                temp_file.replace(self.state_file)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def log_event(self, event: WorkflowEvent):
        """Append an event to the log file (with file locking)."""
        with open(self.log_file, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(event.model_dump(mode='json'), default=str) + '\n')
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def get_events(self, limit: int = 100) -> list[WorkflowEvent]:
        """Read recent events from the log file."""
        if not self.log_file.exists():
            return []
        events = []
        line_num = 0
        with open(self.log_file, 'r') as f:
            for line in f:
                line_num += 1
                if line.strip():
                    try:
                        events.append(WorkflowEvent(**json.loads(line)))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Malformed JSON in log file at line {line_num}: {e}")
                    except Exception as e:
                        logger.warning(f"Failed to parse event at line {line_num}: {e}")
        return events[-limit:]
    
    def reload(self):
        """Reload state and workflow definition from disk."""
        self.load_state()
    
    # ========================================================================
    # Workflow Lifecycle
    # ========================================================================

    def archive_existing_docs(self, task_slug: str) -> list[str]:
        """
        Archive existing workflow documents before starting a new workflow.

        Moves docs/plan.md, docs/risk_analysis.md, and tests/test_cases.md
        to docs/archive/ with dated filenames.

        Args:
            task_slug: Slugified task description for filename

        Returns:
            List of archived file paths
        """
        from .utils import slugify

        docs_to_archive = [
            ("docs/plan.md", "plan"),
            ("docs/risk_analysis.md", "risk"),
            ("tests/test_cases.md", "test_cases"),
        ]
        archive_dir = self.working_dir / "docs" / "archive"

        archived = []
        date_str = datetime.now().strftime("%Y-%m-%d")

        for doc_path, suffix in docs_to_archive:
            src = self.working_dir / doc_path
            if src.exists():
                # Ensure archive directory exists
                archive_dir.mkdir(parents=True, exist_ok=True)

                # Generate unique filename
                dst = archive_dir / f"{date_str}_{task_slug}_{suffix}.md"
                counter = 1
                while dst.exists():
                    dst = archive_dir / f"{date_str}_{task_slug}_{suffix}_{counter}.md"
                    counter += 1

                # Move file to archive
                src.rename(dst)
                archived.append(str(dst))
                logger.info(f"Archived {doc_path} to {dst}")

        return archived

    def start_workflow(self, yaml_path: str, task_description: str, project: Optional[str] = None, constraints: Optional[list[str]] = None, no_archive: bool = False) -> WorkflowState:
        """Start a new workflow instance.

        Args:
            yaml_path: Path to the workflow YAML definition
            task_description: Description of the task
            project: Optional project name
            constraints: Optional list of task-specific constraints (Feature 4)
            no_archive: If True, skip archiving existing workflow documents (WF-004)
        """
        # Load the workflow definition
        yaml_path_resolved = Path(yaml_path).resolve()
        self.load_workflow_def(str(yaml_path_resolved))

        # Validate workflow has at least one phase
        if not self.workflow_def.phases:
            raise ValueError("Workflow definition must have at least one phase")

        # Check if there's already an active workflow
        existing = self.load_state()
        if existing and existing.status == WorkflowStatus.ACTIVE:
            raise ValueError(f"Active workflow already exists: {existing.workflow_id}. Complete or abandon it first.")

        # Archive existing workflow documents (WF-004)
        archived_files = []
        if not no_archive:
            from .utils import slugify
            task_slug = slugify(task_description, max_length=30)
            archived_files = self.archive_existing_docs(task_slug)
            if archived_files:
                logger.info(f"Archived {len(archived_files)} workflow document(s)")

        # Create new state
        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"
        first_phase = self.workflow_def.phases[0]
        
        # Initialize phase states
        phases = {}
        for phase_def in self.workflow_def.phases:
            items = {item.id: ItemState(id=item.id) for item in phase_def.items}
            phases[phase_def.id] = PhaseState(id=phase_def.id, items=items)
        
        # Set first phase as active
        phases[first_phase.id].status = PhaseStatus.ACTIVE
        phases[first_phase.id].started_at = datetime.now(timezone.utc)
        
        # Calculate YAML checksum
        with open(yaml_path_resolved, 'rb') as f:
            yaml_checksum = hashlib.sha256(f.read()).hexdigest()[:16]
        
        # Store version-locked workflow definition to prevent schema drift
        # This ensures the workflow runs with the same rules it started with
        workflow_def_dict = self.workflow_def.model_dump(mode='json')
        
        self.state = WorkflowState(
            workflow_id=workflow_id,
            workflow_type=self.workflow_def.name,
            workflow_version=self.workflow_def.version,
            task_description=task_description,
            project=project,
            current_phase_id=first_phase.id,
            phases=phases,
            workflow_definition=workflow_def_dict,  # Version-locked definition
            constraints=constraints or [],  # Feature 4: Task constraints
            metadata={
                "workflow_yaml_path": str(yaml_path_resolved),
                "workflow_yaml_checksum": yaml_checksum
            }
        )
        
        self.save_state()
        
        # Log events
        self.log_event(WorkflowEvent(
            event_type=EventType.WORKFLOW_STARTED,
            workflow_id=workflow_id,
            message=f"Started workflow: {task_description}",
            details={"project": project, "workflow_type": self.workflow_def.name}
        ))
        self.log_event(WorkflowEvent(
            event_type=EventType.PHASE_STARTED,
            workflow_id=workflow_id,
            phase_id=first_phase.id,
            message=f"Started phase: {first_phase.name}"
        ))
        
        return self.state
    
    def complete_workflow(self, notes: Optional[str] = None) -> WorkflowState:
        """Mark the workflow as completed."""
        if not self.state:
            raise ValueError("No active workflow")
        
        self.state.status = WorkflowStatus.COMPLETED
        self.state.completed_at = datetime.now(timezone.utc)
        if notes:
            self.state.metadata["completion_notes"] = notes
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.WORKFLOW_COMPLETED,
            workflow_id=self.state.workflow_id,
            message="Workflow completed",
            details={"notes": notes}
        ))
        
        return self.state
    
    def abandon_workflow(self, reason: str) -> WorkflowState:
        """Abandon the current workflow."""
        if not self.state:
            raise ValueError("No active workflow")
        
        self.state.status = WorkflowStatus.ABANDONED
        self.state.metadata["abandon_reason"] = reason
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.WORKFLOW_ABANDONED,
            workflow_id=self.state.workflow_id,
            message=f"Workflow abandoned: {reason}"
        ))
        
        return self.state
    
    # ========================================================================
    # Item Operations
    # ========================================================================
    
    def get_item_def(self, item_id: str, phase_id: Optional[str] = None) -> Optional[ChecklistItemDef]:
        """Get the definition of an item from the workflow definition."""
        if not self.workflow_def:
            return None
        
        # If phase specified, only look there
        if phase_id:
            phase = self.workflow_def.get_phase(phase_id)
            if phase:
                for item in phase.items:
                    if item.id == item_id:
                        return item
            return None
        
        # Otherwise search all phases
        for phase in self.workflow_def.phases:
            for item in phase.items:
                if item.id == item_id:
                    return item
        return None
    
    def get_item_state(self, item_id: str, phase_id: Optional[str] = None) -> Optional[ItemState]:
        """Get the current state of an item."""
        if not self.state:
            return None
        
        # If phase specified, only look there
        if phase_id:
            phase = self.state.phases.get(phase_id)
            return phase.items.get(item_id) if phase else None
        
        # Otherwise search all phases
        for phase in self.state.phases.values():
            if item_id in phase.items:
                return phase.items[item_id]
        return None
    
    def get_item_state_in_current_phase(self, item_id: str) -> Optional[ItemState]:
        """Get item state only if it's in the current phase."""
        if not self.state:
            return None
        phase_state = self.state.phases.get(self.state.current_phase_id)
        if phase_state and item_id in phase_state.items:
            return phase_state.items[item_id]
        return None
    
    def _validate_item_in_current_phase(self, item_id: str) -> Tuple[Optional[ChecklistItemDef], Optional[ItemState], Optional[str]]:
        """
        Validate that an item exists in the current phase.
        Returns (item_def, item_state, error_message).
        """
        if not self.state or not self.workflow_def:
            return None, None, "No active workflow"
        
        item_state = self.get_item_state_in_current_phase(item_id)
        if not item_state:
            # Check if item exists in another phase
            if self.get_item_state(item_id):
                return None, None, f"Item '{item_id}' exists but is not in current phase '{self.state.current_phase_id}'"
            return None, None, f"Item not found: {item_id}"
        
        item_def = self.get_item_def(item_id, self.state.current_phase_id)
        if not item_def:
            return None, None, f"Item definition not found: {item_id}"
        
        return item_def, item_state, None
    
    def start_item(self, item_id: str) -> ItemState:
        """Mark an item as in progress."""
        item_def, item_state, error = self._validate_item_in_current_phase(item_id)
        if error:
            raise ValueError(error)
        
        if item_state.status not in [ItemStatus.PENDING, ItemStatus.FAILED]:
            raise ValueError(f"Item {item_id} cannot be started (status: {item_state.status.value})")
        
        item_state.status = ItemStatus.IN_PROGRESS
        item_state.started_at = datetime.now(timezone.utc)
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.ITEM_STARTED,
            workflow_id=self.state.workflow_id,
            phase_id=self.state.current_phase_id,
            item_id=item_id,
            message=f"Started item: {item_id}"
        ))
        
        return item_state
    
    def complete_item(self, item_id: str, notes: Optional[str] = None, skip_verification: bool = False) -> Tuple[bool, str]:
        """
        Attempt to complete an item. Runs verification if configured.
        Returns (success, message).
        """
        item_def, item_state, error = self._validate_item_in_current_phase(item_id)
        if error:
            raise ValueError(error)
        
        if item_state.status == ItemStatus.COMPLETED:
            return True, "Item already completed"
        
        if item_state.status == ItemStatus.SKIPPED:
            return False, "Item was skipped, cannot complete"
        
        # Run verification if configured and not skipped
        if not skip_verification and item_def.verification.type != VerificationType.NONE:
            # Handle manual gates specially
            if item_def.verification.type == VerificationType.MANUAL_GATE:
                return False, f"Item '{item_id}' requires manual approval. Use 'orchestrator approve-item {item_id}' to approve."
            
            success, message, result = self._run_verification(item_def)
            item_state.verification_result = result
            
            if not success:
                item_state.status = ItemStatus.FAILED
                item_state.retry_count += 1
                self.save_state()
                self.log_event(WorkflowEvent(
                    event_type=EventType.VERIFICATION_FAILED,
                    workflow_id=self.state.workflow_id,
                    phase_id=self.state.current_phase_id,
                    item_id=item_id,
                    message=f"Verification failed: {message}",
                    details=result
                ))
                return False, f"Verification failed: {message}"
            
            self.log_event(WorkflowEvent(
                event_type=EventType.VERIFICATION_PASSED,
                workflow_id=self.state.workflow_id,
                phase_id=self.state.current_phase_id,
                item_id=item_id,
                message="Verification passed",
                details=result
            ))
        
        # Mark as completed
        item_state.status = ItemStatus.COMPLETED
        item_state.completed_at = datetime.now(timezone.utc)
        if notes:
            item_state.notes = notes
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.ITEM_COMPLETED,
            workflow_id=self.state.workflow_id,
            phase_id=self.state.current_phase_id,
            item_id=item_id,
            message=f"Completed item: {item_id}",
            details={"notes": notes}
        ))
        
        return True, "Item completed successfully"
    
    def skip_item(self, item_id: str, reason: str) -> Tuple[bool, str]:
        """Skip an item with a documented reason."""
        item_def, item_state, error = self._validate_item_in_current_phase(item_id)
        if error:
            raise ValueError(error)
        
        if not item_def.skippable:
            return False, f"Item {item_id} is not skippable"
        
        if item_state.status in [ItemStatus.COMPLETED, ItemStatus.SKIPPED]:
            return False, f"Item {item_id} is already {item_state.status.value}"
        
        if not reason or len(reason.strip()) < MIN_SKIP_REASON_LENGTH:
            return False, f"Skip reason must be at least {MIN_SKIP_REASON_LENGTH} characters"
        
        item_state.status = ItemStatus.SKIPPED
        item_state.skipped_at = datetime.now(timezone.utc)
        item_state.skip_reason = reason
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.ITEM_SKIPPED,
            workflow_id=self.state.workflow_id,
            phase_id=self.state.current_phase_id,
            item_id=item_id,
            message=f"Skipped item: {item_id}",
            details={"reason": reason}
        ))
        
        return True, f"Item {item_id} skipped"

    # ========================================================================
    # Skip Visibility Methods (CORE-010)
    # ========================================================================

    def get_skipped_items(self, phase_id: str) -> list[Tuple[str, str]]:
        """
        Get list of skipped items for a specific phase.

        Args:
            phase_id: The phase ID to query

        Returns:
            List of (item_id, skip_reason) tuples for skipped items
        """
        if not self.state:
            return []

        phase = self.state.phases.get(phase_id)
        if not phase:
            return []

        return [
            (item_id, item.skip_reason or "No reason provided")
            for item_id, item in phase.items.items()
            if item.status == ItemStatus.SKIPPED
        ]

    def get_all_skipped_items(self) -> dict[str, list[Tuple[str, str]]]:
        """
        Get all skipped items grouped by phase.

        Returns:
            Dict mapping phase_id to list of (item_id, skip_reason) tuples
        """
        if not self.state:
            return {}

        result = {}
        for phase_id in self.state.phases:
            skipped = self.get_skipped_items(phase_id)
            if skipped:
                result[phase_id] = skipped
        return result

    def get_item_definition(self, item_id: str):
        """
        Get the workflow definition for an item by ID.

        Args:
            item_id: The item ID to find

        Returns:
            ChecklistItemDef if found, None otherwise
        """
        if not self.workflow_def:
            return None

        for phase in self.workflow_def.phases:
            for item in phase.items:
                if item.id == item_id:
                    return item
        return None

    # ========================================================================
    # Workflow Summary Methods (CORE-011)
    # ========================================================================

    def get_workflow_summary(self) -> dict:
        """
        Get summary of items per phase.

        Returns:
            Dict mapping phase_id to dict with 'completed', 'skipped', 'total' counts
        """
        if not self.state:
            return {}

        summary = {}
        for phase_id, phase in self.state.phases.items():
            completed = sum(1 for i in phase.items.values()
                          if i.status == ItemStatus.COMPLETED)
            skipped = sum(1 for i in phase.items.values()
                         if i.status == ItemStatus.SKIPPED)
            total = len(phase.items)
            summary[phase_id] = {
                'completed': completed,
                'skipped': skipped,
                'total': total
            }
        return summary

    def approve_item(self, item_id: str, notes: Optional[str] = None) -> Tuple[bool, str]:
        """Approve a manual gate item."""
        item_def, item_state, error = self._validate_item_in_current_phase(item_id)
        if error:
            raise ValueError(error)
        
        # Verify this is a manual gate item
        if item_def.verification.type != VerificationType.MANUAL_GATE:
            return False, f"Item '{item_id}' is not a manual gate item"
        
        if item_state.status == ItemStatus.COMPLETED:
            return True, "Item already approved"
        
        # Mark as completed with approval info
        item_state.status = ItemStatus.COMPLETED
        item_state.completed_at = datetime.now(timezone.utc)
        item_state.verification_result = {
            "approved": True,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "type": "manual_gate"
        }
        if notes:
            item_state.notes = notes
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.ITEM_COMPLETED,
            workflow_id=self.state.workflow_id,
            phase_id=self.state.current_phase_id,
            item_id=item_id,
            message=f"Approved manual gate: {item_id}",
            details={"notes": notes, "approved": True},
            actor="human"
        ))
        
        return True, f"Item '{item_id}' approved"
    
    # ========================================================================
    # Phase Operations
    # ========================================================================
    
    def can_advance_phase(self) -> Tuple[bool, list[str], list[str]]:
        """
        Check if the current phase can be advanced.
        Returns (can_advance, blockers, skipped_items).
        """
        if not self.state or not self.workflow_def:
            return False, ["No active workflow"], []
        
        phase_def = self.workflow_def.get_phase(self.state.current_phase_id)
        phase_state = self.state.phases.get(self.state.current_phase_id)
        
        if not phase_def or not phase_state:
            return False, ["Invalid phase"], []
        
        blockers = []
        skipped = []
        
        for item_def in phase_def.items:
            item_state = phase_state.items.get(item_def.id)
            if not item_state:
                continue
            
            if item_state.status == ItemStatus.SKIPPED:
                skipped.append(f"{item_def.id}: {item_state.skip_reason}")
            elif item_def.required and item_state.status != ItemStatus.COMPLETED:
                blockers.append(f"{item_def.id} ({item_state.status.value})")
        
        # Check for manual gate
        if phase_def.exit_gate == "human_approval":
            if not self.state.metadata.get(f"phase_{phase_def.id}_approved"):
                blockers.append("Awaiting human approval")
        
        return len(blockers) == 0, blockers, skipped
    
    def advance_phase(self, force: bool = False) -> Tuple[bool, str]:
        """
        Advance to the next phase.
        Returns (success, message).
        """
        if not self.state or not self.workflow_def:
            return False, "No active workflow"
        
        can_advance, blockers, skipped = self.can_advance_phase()
        
        if not can_advance and not force:
            return False, f"Cannot advance. Blockers: {', '.join(blockers)}"
        
        # Mark current phase as completed
        current_phase = self.state.phases.get(self.state.current_phase_id)
        if current_phase:
            current_phase.status = PhaseStatus.COMPLETED
            current_phase.completed_at = datetime.now(timezone.utc)
        
        self.log_event(WorkflowEvent(
            event_type=EventType.PHASE_COMPLETED,
            workflow_id=self.state.workflow_id,
            phase_id=self.state.current_phase_id,
            message=f"Completed phase: {self.state.current_phase_id}",
            details={"skipped_items": skipped, "forced": force}
        ))
        
        # Get next phase
        next_phase_def = self.workflow_def.get_next_phase(self.state.current_phase_id)
        
        if not next_phase_def:
            # This was the last phase - complete the workflow
            return True, "All phases completed. Use 'finish' to complete the workflow."
        
        # Advance to next phase
        self.state.current_phase_id = next_phase_def.id
        next_phase_state = self.state.phases.get(next_phase_def.id)
        if next_phase_state:
            next_phase_state.status = PhaseStatus.ACTIVE
            next_phase_state.started_at = datetime.now(timezone.utc)
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.PHASE_STARTED,
            workflow_id=self.state.workflow_id,
            phase_id=next_phase_def.id,
            message=f"Started phase: {next_phase_def.name}"
        ))
        
        return True, f"Advanced to phase: {next_phase_def.name}"
    
    def approve_phase(self, phase_id: Optional[str] = None) -> Tuple[bool, str]:
        """Human approval for a phase gate."""
        if not self.state:
            return False, "No active workflow"
        
        phase_id = phase_id or self.state.current_phase_id
        self.state.metadata[f"phase_{phase_id}_approved"] = True
        self.state.metadata[f"phase_{phase_id}_approved_at"] = datetime.now(timezone.utc).isoformat()
        
        self.save_state()
        self.log_event(WorkflowEvent(
            event_type=EventType.HUMAN_OVERRIDE,
            workflow_id=self.state.workflow_id,
            phase_id=phase_id,
            message=f"Human approved phase: {phase_id}",
            actor="human"
        ))
        
        return True, f"Phase {phase_id} approved"
    
    # ========================================================================
    # Verification
    # ========================================================================
    
    def _run_verification(self, item_def: ChecklistItemDef) -> Tuple[bool, str, dict]:
        """
        Run verification for an item.
        Returns (success, message, details).
        """
        verification = item_def.verification
        result = {"type": verification.type.value, "timestamp": datetime.now(timezone.utc).isoformat()}
        
        if verification.type == VerificationType.FILE_EXISTS:
            # Substitute template variables in path
            file_path = self._substitute_template(verification.path)
            # Path traversal protection - use is_relative_to for proper security
            path = (self.working_dir / file_path).resolve()
            try:
                # Python 3.9+ - proper path containment check
                if not path.is_relative_to(self.working_dir.resolve()):
                    result["blocked"] = True
                    result["reason"] = "path_traversal"
                    return False, f"Path traversal blocked: {verification.path}", result
            except ValueError:
                # is_relative_to raises ValueError if not relative
                result["blocked"] = True
                result["reason"] = "path_traversal"
                return False, f"Path traversal blocked: {verification.path}", result
            
            exists = path.exists()
            result["path"] = str(path)
            result["exists"] = exists
            if exists:
                return True, f"File exists: {verification.path}", result
            else:
                return False, f"File not found: {verification.path}", result
        
        elif verification.type == VerificationType.COMMAND:
            import shlex
            
            # Substitute template variables with shell sanitization
            try:
                command = self._substitute_template(verification.command, sanitize_for_shell=True)
            except ValueError as e:
                result["error"] = str(e)
                result["blocked"] = True
                return False, f"Command blocked: {e}", result
            
            # Parse command into args list for shell=False execution
            try:
                command_args = shlex.split(command)
            except ValueError as e:
                result["error"] = f"Invalid command syntax: {e}"
                result["blocked"] = True
                return False, f"Command blocked: invalid syntax - {e}", result
            
            if not command_args:
                result["error"] = "Empty command"
                result["blocked"] = True
                return False, "Command blocked: empty command", result
            
            try:
                # Use shell=False for security - command is parsed into args
                proc = subprocess.run(
                    command_args,
                    shell=False,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=COMMAND_TIMEOUT_SECONDS
                )
                result["command"] = command
                result["command_args"] = command_args
                result["original_command"] = verification.command
                result["exit_code"] = proc.returncode
                result["stdout"] = proc.stdout[:OUTPUT_TRUNCATE_LENGTH] if proc.stdout else ""
                result["stderr"] = proc.stderr[:OUTPUT_TRUNCATE_LENGTH] if proc.stderr else ""
                
                if proc.returncode == verification.expect_exit_code:
                    return True, f"Command passed (exit code {proc.returncode})", result
                else:
                    return False, f"Command failed (exit code {proc.returncode}, expected {verification.expect_exit_code})", result
            except subprocess.TimeoutExpired:
                result["error"] = "Command timed out"
                return False, f"Command timed out after {COMMAND_TIMEOUT_SECONDS} seconds", result
            except FileNotFoundError:
                result["error"] = f"Command not found: {command_args[0]}"
                return False, f"Command not found: {command_args[0]}", result
            except Exception as e:
                result["error"] = str(e)
                return False, f"Command error: {e}", result
        
        elif verification.type == VerificationType.MANUAL_GATE:
            # Manual gates should be handled via approve_item, not complete_item
            result["awaiting_approval"] = True
            return False, "Awaiting manual approval. Use 'orchestrator approve-item <item_id>' to approve.", result
        
        # No verification configured
        return True, "No verification required", result
    
    # ========================================================================
    # Status and Reporting
    # ========================================================================
    
    def get_status(self) -> dict:
        """Get a comprehensive status report."""
        if not self.state or not self.workflow_def:
            return {"status": "no_active_workflow"}
        
        phase_def = self.workflow_def.get_phase(self.state.current_phase_id)
        phase_state = self.state.phases.get(self.state.current_phase_id)
        
        can_advance, blockers, skipped = self.can_advance_phase()
        
        # Build checklist status (with enum values, not enum objects)
        checklist = []
        if phase_def and phase_state:
            for item_def in phase_def.items:
                item_state = phase_state.items.get(item_def.id)
                checklist.append({
                    "id": item_def.id,
                    "name": item_def.name,
                    "required": item_def.required,
                    "skippable": item_def.skippable,
                    "status": item_state.status.value if item_state else "unknown",
                    "verification_type": item_def.verification.type.value,
                    "skip_reason": item_state.skip_reason if item_state else None,
                    "notes": item_def.notes if item_def.notes else []  # Feature 3: Operating notes
                })
        
        # Count progress
        completed = sum(1 for i in checklist if i["status"] == "completed")
        total_required = sum(1 for i in checklist if i["required"])
        
        return {
            "workflow_id": self.state.workflow_id,
            "workflow_type": self.state.workflow_type,
            "task": self.state.task_description,
            "project": self.state.project,
            "status": self.state.status.value,
            "current_phase": {
                "id": self.state.current_phase_id,
                "name": phase_def.name if phase_def else "Unknown",
                "progress": f"{completed}/{len(checklist)} items"
            },
            "phases": self.get_all_phases(),
            "checklist": checklist,
            "can_advance": can_advance,
            "blockers": blockers,
            "skipped_items": skipped,
            "created_at": self.state.created_at.isoformat() if self.state.created_at else None,
            "updated_at": self.state.updated_at.isoformat() if self.state.updated_at else None
        }
    
    def get_recitation_text(self) -> str:
        """
        Get a text summary suitable for recitation into LLM context.
        This is the key mechanism for keeping the workflow in recent attention.
        """
        if not self.state or not self.workflow_def:
            return "No active workflow. Start one with: orchestrator start <task>"
        
        status = self.get_status()
        
        lines = [
            "=" * 60,
            "WORKFLOW STATE (READ THIS FIRST)",
            "=" * 60,
            f"Task: {status['task']}",
            f"Phase: {status['current_phase']['id']} - {status['current_phase']['name']}",
            f"Progress: {status['current_phase']['progress']}",
        ]
        
        # Display constraints if present (Feature 4)
        if self.state.constraints:
            lines.append("")
            lines.append("Constraints:")
            for constraint in self.state.constraints:
                lines.append(f"  - {constraint}")
        
        # Display phase notes if present (Feature 3)
        phase_def = self.workflow_def.get_phase(self.state.current_phase_id)
        if phase_def and phase_def.notes:
            lines.append("")
            lines.append("Phase Notes:")
            for note in phase_def.notes:
                lines.append(f"  {self._format_note(note)}")
        
        lines.append("")
        lines.append("Checklist:")
        
        next_pending_item = None
        for item in status['checklist']:
            status_val = item['status']
            marker = "✓" if status_val == "completed" else \
                     "⊘" if status_val == "skipped" else \
                     "●" if status_val == "in_progress" else \
                     "○"
            req = "*" if item['required'] else " "
            # Include item ID for AI to use
            lines.append(f"  {marker} [{req}] {item['id']} — {item['name']}")
            if item['skip_reason']:
                lines.append(f"       └─ Skipped: {item['skip_reason']}")
            
            # Display item notes if present (Feature 3)
            item_notes = item.get('notes', [])
            if item_notes:
                for note in item_notes:
                    lines.append(f"       └─ {self._format_note(note)}")
            
            # Track first pending item for next action
            if not next_pending_item and status_val in ["pending", "failed"]:
                next_pending_item = item
        
        lines.append("")
        
        if status['can_advance']:
            lines.append("✓ Ready to advance to next phase")
            lines.append("")
            lines.append("NEXT_ACTION: orchestrator advance")
        else:
            lines.append("Blockers:")
            for b in status['blockers']:
                lines.append(f"  - {b}")
            lines.append("")
            
            # Suggest next action
            if next_pending_item:
                if next_pending_item.get('verification_type') == 'manual_gate':
                    lines.append(f"NEXT_ACTION: orchestrator approve-item {next_pending_item['id']}")
                else:
                    lines.append(f"NEXT_ACTION: orchestrator complete {next_pending_item['id']} --notes \"<what you did>\"")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _format_note(self, note: str) -> str:
        """
        Format a note with optional emoji rendering for categorized notes.
        
        Supports bracket prefixes:
        - [tip] → 💡
        - [caution] → ⚠️
        - [learning] → 📚
        - [context] → 📋
        - [important] → ❗
        """
        emoji_map = {
            '[tip]': '💡',
            '[caution]': '⚠️',
            '[learning]': '📚',
            '[context]': '📋',
            '[important]': '❗',
            '[warning]': '⚠️',
            '[note]': '📝',
        }
        
        for prefix, emoji in emoji_map.items():
            if note.lower().startswith(prefix):
                return f"{emoji} {note[len(prefix):].strip()}"
        
        return note
    
    def get_all_phases(self) -> list[dict]:
        """Get all phases from the workflow definition (for dashboard)."""
        if not self.workflow_def:
            return []
        
        phases = []
        for phase_def in self.workflow_def.phases:
            phase_state = self.state.phases.get(phase_def.id) if self.state else None
            phases.append({
                "id": phase_def.id,
                "name": phase_def.name,
                "status": phase_state.status.value if phase_state else "pending",
                "is_current": self.state.current_phase_id == phase_def.id if self.state else False
            })
        return phases

    # ========================================================================
    # Workflow Discovery and Cleanup
    # ========================================================================
    
    @staticmethod
    def find_workflows(search_dir: str = ".", max_depth: int = 3) -> list[dict]:
        """
        Find all workflow state files in the given directory and subdirectories.
        Returns a list of workflow summaries for discovery across sessions.
        """
        import os
        workflows = []
        search_path = Path(search_dir).resolve()
        
        for root, dirs, files in os.walk(search_path):
            # Check depth
            depth = len(Path(root).relative_to(search_path).parts)
            if depth > max_depth:
                dirs.clear()  # Don't descend further
                continue
            
            if ".workflow_state.json" in files:
                state_file = Path(root) / ".workflow_state.json"
                try:
                    with open(state_file, 'r') as f:
                        data = json.load(f)
                    
                    workflows.append({
                        "path": str(state_file),
                        "directory": str(root),
                        "workflow_id": data.get("workflow_id", "unknown"),
                        "task": data.get("task_description", "No description"),
                        "status": data.get("status", "unknown"),
                        "current_phase": data.get("current_phase_id", "unknown"),
                        "project": data.get("project"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at")
                    })
                except Exception as e:
                    logger.warning(f"Failed to read workflow state at {state_file}: {e}")
        
        # Sort by updated_at descending (most recent first)
        workflows.sort(key=lambda w: w.get("updated_at") or "", reverse=True)
        return workflows
    
    def cleanup_abandoned(self, max_age_days: int = 7) -> list[dict]:
        """
        Clean up abandoned workflows (active workflows older than max_age_days).
        Returns list of cleaned up workflows.
        """
        from datetime import timedelta
        
        cleaned = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        
        # Only clean up the current directory's workflow
        if not self.state_file.exists():
            return cleaned
        
        try:
            state = self.load_state()
            if not state:
                return cleaned
            
            # Only clean up ACTIVE workflows that are stale
            if state.status == WorkflowStatus.ACTIVE:
                updated_at = state.updated_at
                if updated_at and updated_at < cutoff:
                    # Mark as abandoned
                    state.status = WorkflowStatus.ABANDONED
                    state.metadata["abandoned_reason"] = f"Auto-cleanup: inactive for {max_age_days}+ days"
                    state.metadata["abandoned_at"] = datetime.now(timezone.utc).isoformat()
                    self.state = state
                    self.save_state()
                    
                    self.log_event(WorkflowEvent(
                        event_type=EventType.WORKFLOW_ABANDONED,
                        workflow_id=state.workflow_id,
                        message=f"Auto-abandoned: inactive for {max_age_days}+ days"
                    ))
                    
                    cleaned.append({
                        "workflow_id": state.workflow_id,
                        "task": state.task_description,
                        "last_updated": updated_at.isoformat() if updated_at else None
                    })
        except Exception as e:
            logger.error(f"Failed to cleanup workflow: {e}")
        
        return cleaned
    
    @staticmethod
    def cleanup_all_abandoned(search_dir: str = ".", max_age_days: int = 7, max_depth: int = 3) -> list[dict]:
        """
        Find and clean up all abandoned workflows in the search directory.
        """
        all_cleaned = []
        workflows = WorkflowEngine.find_workflows(search_dir, max_depth)
        
        for wf in workflows:
            if wf["status"] == "active":
                engine = WorkflowEngine(wf["directory"])
                cleaned = engine.cleanup_abandoned(max_age_days)
                all_cleaned.extend(cleaned)
        
        return all_cleaned
