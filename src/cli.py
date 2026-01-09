#!/usr/bin/env python3
"""
Workflow Orchestrator CLI

Command-line interface for managing AI workflow enforcement.
"""

import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

from src.engine import WorkflowEngine
from src.analytics import WorkflowAnalytics
from src.learning_engine import LearningEngine
from src.dashboard import start_dashboard, generate_static_dashboard
from src.schema import WorkflowDef, WorkflowEvent, EventType
from src.claude_integration import ClaudeCodeIntegration
from src.providers import get_provider, list_providers, AgentProvider
from src.environment import detect_environment, get_environment_info, Environment
from src.checkpoint import CheckpointManager, CheckpointData
from src.visual_verification import (
    VisualVerificationClient,
    VisualVerificationError,
    VerificationResult,
    CostSummary,
    create_desktop_viewport,
    create_mobile_viewport,
    format_verification_result,
    format_cost_summary,
    discover_visual_tests,
    run_all_visual_tests,
    DEVICE_PRESETS,
)
from src.review import (
    ReviewRouter,
    ReviewMethod,
    check_review_setup,
    setup_reviews,
)
from src.review.registry import get_review_item_mapping
from src.config import find_workflow_path, get_default_workflow_content, is_using_bundled_workflow
from src.validation import validate_constraints, validate_note
from src.secrets import (
    SecretsManager,
    get_secrets_manager,
    get_user_config,
    get_user_config_value,
    set_user_config_value,
    init_secrets_interactive,
    CONFIG_FILE,
    SIMPLE_SECRETS_FILE,
)
from src.git_conflict_resolver import (
    GitConflictResolver,
    check_conflicts,
    format_escalation_for_user,
)

VERSION = "2.0.0"


# ============================================================================
# Auto-Review Mapping (WF-010, ARCH-003)
# ============================================================================
# Maps workflow item IDs to third-party review types
# When completing these items, auto-run the corresponding review
# ARCH-003: Now imported from registry.py - single source of truth
REVIEW_ITEM_MAPPING = get_review_item_mapping()


def run_auto_review(review_type: str, working_dir: Path = None) -> tuple[bool, str, str, dict]:
    """
    Run an automated third-party review.

    Args:
        review_type: The review type (security, quality, consistency, holistic)
        working_dir: Working directory for the review

    Returns:
        Tuple of (success, notes, error_message, review_info)
        - success: True if review passed
        - notes: Completion notes describing the review result
        - error_message: Error description if review couldn't run (CLIs not available, etc.)
        - review_info: Dict with model info for tracking: {model_name, method, issues, success}
    """
    working_dir = working_dir or Path('.')

    try:
        router = ReviewRouter(working_dir=working_dir)
    except ValueError as e:
        return False, "", f"Review infrastructure not available: {e}", {}

    # Check if method is available
    if router.method == ReviewMethod.UNAVAILABLE:
        return False, "", "No review method available (install Codex/Gemini CLIs or configure OpenRouter API)", {}

    try:
        result = router.execute_review(review_type)

        # Build review info for tracking
        review_info = {
            "model": result.model_used or "unknown",
            "method": router.method.value,
            "success": not result.error and result.blocking_count == 0,
            "issues": len(result.findings) if result.findings else 0,
            "blocking": result.blocking_count,
        }

        if result.error:
            review_info["error"] = result.error
            return False, "", f"Review error: {result.error}", review_info

        # Build completion notes from review result
        model_info = f"[{router.method.value}] {result.model_used}"
        duration = f"{result.duration_seconds:.1f}s" if result.duration_seconds else "N/A"

        if result.findings:
            finding_count = len(result.findings)
            blocking_count = result.blocking_count
            if blocking_count > 0:
                notes = f"THIRD-PARTY REVIEW ({model_info}, {duration}): {finding_count} findings, {blocking_count} BLOCKING"
                return False, notes, f"Review found {blocking_count} blocking issue(s)", review_info
            else:
                notes = f"THIRD-PARTY REVIEW ({model_info}, {duration}): {finding_count} non-blocking findings. {result.summary or 'Passed'}"
                return True, notes, "", review_info
        else:
            notes = f"THIRD-PARTY REVIEW ({model_info}, {duration}): No issues found"
            return True, notes, "", review_info

    except Exception as e:
        return False, "", f"Review execution failed: {e}", {"error": str(e), "success": False}


# ============================================================================
# Helper Functions (CORE-010, CORE-011)
# ============================================================================

def format_duration(delta: timedelta) -> str:
    """
    Format a timedelta as a human-readable duration string.

    Args:
        delta: The timedelta to format

    Returns:
        Formatted string like "2h 15m", "45m", "1d 3h 30m", or "< 1m"
    """
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "< 1m"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    return " ".join(parts) if parts else "< 1m"


def get_engine(args) -> WorkflowEngine:
    """Create an engine instance with the working directory."""
    working_dir = getattr(args, 'dir', '.') or '.'
    engine = WorkflowEngine(working_dir)
    
    # Try to load existing state (this also loads workflow def from stored path)
    engine.load_state()
    
    # If no workflow def loaded yet, try default location
    if engine.state and not engine.workflow_def:
        yaml_path = Path(working_dir) / "workflow.yaml"
        if yaml_path.exists():
            engine.load_workflow_def(str(yaml_path))
        else:
            print(f"Warning: workflow.yaml not found. Some features may not work.", file=sys.stderr)
    
    return engine


def cmd_start(args):
    """Start a new workflow."""
    working_dir = Path(args.dir or '.')
    engine = WorkflowEngine(working_dir)

    # Use explicit workflow if specified, otherwise use config discovery
    if args.workflow and args.workflow != 'workflow.yaml':
        # Explicit workflow specified
        yaml_path = working_dir / args.workflow
        if not yaml_path.exists():
            print(f"Error: Workflow definition not found: {yaml_path}")
            sys.exit(1)
    else:
        # Use config discovery: local workflow.yaml or bundled default
        yaml_path = find_workflow_path(working_dir)
        if is_using_bundled_workflow(working_dir):
            print("Using bundled default workflow (no local workflow.yaml found)")

    # Parse constraints (Feature 4) - can be specified multiple times
    constraints = getattr(args, 'constraints', None) or []

    # Validate constraints (CORE-008)
    try:
        constraints = validate_constraints(constraints)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Get no_archive flag (WF-004)
    no_archive = getattr(args, 'no_archive', False)

    try:
        state = engine.start_workflow(
            str(yaml_path),
            args.task,
            project=args.project,
            constraints=constraints,
            no_archive=no_archive
        )
        print(f"\n✓ Workflow started: {state.workflow_id}")
        print(f"  Task: {args.task}")
        print(f"  Phase: {state.current_phase_id}")
        if constraints:
            print(f"  Constraints: {len(constraints)} specified")
        print("\nRun 'orchestrator status' to see the checklist.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_init(args):
    """Initialize a workflow.yaml in the current directory."""
    working_dir = Path(args.dir or '.')
    workflow_path = working_dir / 'workflow.yaml'

    # Check if workflow.yaml already exists
    if workflow_path.exists() and not args.force:
        print(f"workflow.yaml already exists at {workflow_path}")
        response = input("Overwrite? This will backup the existing file. [y/N] ").strip().lower()
        if response != 'y':
            print("Aborted.")
            sys.exit(0)

    # Backup existing file if it exists
    if workflow_path.exists():
        backup_path = working_dir / 'workflow.yaml.bak'
        import shutil
        shutil.copy2(workflow_path, backup_path)
        print(f"Backed up existing workflow to {backup_path}")

    # Write the default workflow
    try:
        content = get_default_workflow_content()
        workflow_path.write_text(content)
        print(f"\n✓ Created {workflow_path}")
        print("\nNext steps:")
        print("  1. Review and customize workflow.yaml for your project")
        print("  2. Start a workflow: orchestrator start \"Your task description\"")
        print("  3. Check status: orchestrator status")
    except Exception as e:
        print(f"Error creating workflow.yaml: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show current workflow status."""
    engine = get_engine(args)
    working_dir = Path(args.dir or '.')

    # CORE-023: Check for git conflicts and show warning
    has_conflict, conflict_files = check_conflicts(working_dir)
    if has_conflict:
        try:
            resolver = GitConflictResolver(repo_path=working_dir)
            conflict_type = "REBASE" if resolver.is_rebase_conflict() else "MERGE"
        except ValueError:
            conflict_type = "MERGE"

        if args.json:
            # Add conflict info to JSON
            status_json = engine.get_status_json()
            status_json['git_conflict'] = {
                'has_conflicts': True,
                'conflict_type': conflict_type.lower(),
                'files': conflict_files,
            }
            print(json.dumps(status_json, indent=2, default=str))
        else:
            # Show conflict warning before regular status
            print("=" * 60)
            print(f"GIT {conflict_type} CONFLICT DETECTED")
            print("=" * 60)
            print(f"{len(conflict_files)} file(s) in conflict:")
            for f in conflict_files[:5]:
                print(f"  - {f}")
            if len(conflict_files) > 5:
                print(f"  ... and {len(conflict_files) - 5} more")
            print()
            print("Run `orchestrator resolve` to resolve conflicts")
            print("=" * 60)
            print()
            print(engine.get_recitation_text())
    elif args.json:
        # WF-015: Use the new get_status_json for proper JSON output
        print(json.dumps(engine.get_status_json(), indent=2, default=str))
    else:
        print(engine.get_recitation_text())


def cmd_context_reminder(args):
    """WF-012: Output compact workflow state for context injection."""
    engine = get_engine(args)
    reminder = engine.get_context_reminder()
    print(json.dumps(reminder))


def cmd_verify_write_allowed(args):
    """WF-013: Check if writing implementation code is allowed."""
    engine = get_engine(args)
    allowed, reason = engine.verify_write_allowed()
    if allowed:
        print(f"✓ {reason}")
        sys.exit(0)
    else:
        print(f"✗ {reason}")
        sys.exit(1)


def cmd_resolve(args):
    """CORE-023: Resolve git merge/rebase conflicts."""
    working_dir = Path(args.dir or '.')

    # Handle abort first
    if args.abort:
        try:
            resolver = GitConflictResolver(repo_path=working_dir)
            if not resolver.has_conflicts():
                print("No conflicts to abort.")
                sys.exit(0)

            if resolver.abort():
                conflict_type = "rebase" if resolver.is_rebase_conflict() else "merge"
                print(f"✓ {conflict_type.title()} aborted successfully")
                sys.exit(0)
            else:
                print(f"✗ Failed to abort")
                sys.exit(2)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(2)

    # Check for conflicts
    try:
        resolver = GitConflictResolver(repo_path=working_dir)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(2)

    if not resolver.has_conflicts():
        print("No git conflicts detected.")
        sys.exit(0)

    # Get conflict info
    conflict_type = "rebase" if resolver.is_rebase_conflict() else "merge"
    files = resolver.get_conflicted_files()

    print("=" * 60)
    print(f"GIT {conflict_type.upper()} CONFLICT DETECTED")
    print("=" * 60)
    print()
    print(f"{len(files)} file(s) in conflict:")
    for f in files:
        print(f"  - {f}")
    print()

    # Preview mode (default)
    if not args.apply:
        print("PREVIEW MODE - No changes will be made")
        print()

        # Analyze what would happen
        results = resolver.resolve_all(strategy=args.strategy or "auto")

        if results.resolved_count > 0:
            print(f"Auto-resolvable: {results.resolved_count} file(s)")
            for r in results.results:
                if r.success:
                    print(f"  ✓ {r.file_path} ({r.strategy}, confidence: {r.confidence:.0%})")

        if results.escalated_count > 0:
            print()
            print(f"Need manual decision: {results.escalated_count} file(s)")
            for r in results.results:
                if r.needs_escalation:
                    print(f"  ? {r.file_path}")

        print()
        print("-" * 60)
        print("To apply resolutions: orchestrator resolve --apply")
        if args.strategy:
            print(f"                       (using strategy: {args.strategy})")
        print("-" * 60)

        # Exit code 3 = preview only
        sys.exit(3)

    # Apply mode
    print(f"APPLYING RESOLUTIONS (strategy: {args.strategy or 'auto'})")
    print()

    results = resolver.resolve_all(strategy=args.strategy or "auto")
    applied, failed = 0, 0

    # Handle successful auto-resolutions
    for result in results.results:
        if result.success:
            if resolver.apply_resolution(result):
                print(f"  ✓ {result.file_path} resolved ({result.strategy})")
                applied += 1
            else:
                print(f"  ✗ {result.file_path} failed to apply")
                failed += 1
        elif result.needs_escalation:
            # Interactive mode
            print()
            print(format_escalation_for_user(result))
            print()

            # Get user choice
            choice = input("Enter choice [A/B/C/D] (default: A): ").strip().upper() or "A"

            if choice == "A":
                # Keep ours
                ours_result = resolver.resolve_file(result.file_path, strategy="ours")
                if ours_result.success and resolver.apply_resolution(ours_result):
                    print(f"  ✓ {result.file_path} resolved (ours)")
                    applied += 1
                else:
                    print(f"  ✗ {result.file_path} failed: {ours_result.validation_error}")
                    failed += 1
            elif choice == "B":
                # Keep theirs
                theirs_result = resolver.resolve_file(result.file_path, strategy="theirs")
                if theirs_result.success and resolver.apply_resolution(theirs_result):
                    print(f"  ✓ {result.file_path} resolved (theirs)")
                    applied += 1
                else:
                    print(f"  ✗ {result.file_path} failed: {theirs_result.validation_error}")
                    failed += 1
            elif choice == "C":
                # Keep both
                both_result = resolver.resolve_file(result.file_path, strategy="both")
                if both_result.resolved_content and resolver.apply_resolution(both_result):
                    print(f"  ✓ {result.file_path} resolved (both - may need cleanup)")
                    applied += 1
                else:
                    print(f"  ✗ {result.file_path} failed: {both_result.validation_error}")
                    failed += 1
            elif choice == "D":
                # Open in editor
                editor = os.environ.get("EDITOR", "vim")
                file_path = working_dir / result.file_path
                import subprocess
                subprocess.run([editor, str(file_path)])
                # After editing, stage the file
                subprocess.run(["git", "add", result.file_path], cwd=working_dir)
                print(f"  ✓ {result.file_path} manually resolved")
                applied += 1
            else:
                print(f"  ? {result.file_path} skipped (invalid choice)")
        else:
            # Failed resolution
            print(f"  ✗ {result.file_path} failed: {result.validation_error}")
            failed += 1

    print()
    print("=" * 60)
    print(f"RESOLUTION SUMMARY")
    print("=" * 60)
    print(f"  Applied: {applied}")
    print(f"  Failed:  {failed}")

    # Auto-commit if requested
    if args.commit and failed == 0 and applied > 0:
        print()
        if resolver.continue_operation():
            print("✓ Merge/rebase completed successfully")
        else:
            print("✗ Failed to complete merge/rebase")
            print("  You may need to run 'git commit' or 'git rebase --continue' manually")

    # Exit codes
    if failed > 0:
        sys.exit(1)  # Partial success
    elif applied > 0:
        sys.exit(0)  # All resolved
    else:
        sys.exit(2)  # No files processed


def cmd_complete(args):
    """Mark an item as complete."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Validate notes (CORE-008)
    try:
        notes = validate_note(args.notes)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # WF-010: Auto-run third-party reviews for REVIEW phase items
    item_id = args.item
    if item_id in REVIEW_ITEM_MAPPING and not args.skip_auto_review:
        review_type = REVIEW_ITEM_MAPPING[item_id]
        
        engine.log_event(WorkflowEvent(
            event_type=EventType.REVIEW_STARTED,
            workflow_id=engine.state.workflow_id,
            phase_id=engine.state.current_phase_id,
            item_id=item_id,
            message=f"Starting {review_type} review",
            details={"review_type": review_type}
        ))

        print(f"Running third-party {review_type} review...")
        print()

        working_dir = Path(args.dir) if hasattr(args, 'dir') and args.dir else Path('.')
        review_success, review_notes, review_error, review_info = run_auto_review(review_type, working_dir)

        # Store review info in workflow metadata for visibility at finish
        if review_info:
            if "review_models" not in engine.state.metadata:
                engine.state.metadata["review_models"] = {}
            current_phase = engine.state.current_phase_id
            if current_phase not in engine.state.metadata["review_models"]:
                engine.state.metadata["review_models"][current_phase] = {}
            engine.state.metadata["review_models"][current_phase][review_info.get("model", item_id)] = {
                "success": review_info.get("success", False),
                "issues": review_info.get("issues", 0),
                "method": review_info.get("method", "unknown"),
                "blocking": review_info.get("blocking", 0),
            }
            engine.save_state()

        if review_error:
            engine.log_event(WorkflowEvent(
                event_type=EventType.REVIEW_FAILED,
                workflow_id=engine.state.workflow_id,
                phase_id=engine.state.current_phase_id,
                item_id=item_id,
                message=f"Review failed: {review_error}",
                details={"error": review_error}
            ))
            # Review couldn't run - block completion
            print("=" * 60)
            print(f"✗ CANNOT COMPLETE: Third-party review required")
            print("=" * 60)
            print(f"Error: {review_error}")
            print()
            print("Options:")
            print(f"  1. Fix the issue and try again")
            print(f"  2. Skip with explanation: orchestrator skip {item_id} --reason \"<why review unavailable>\"")
            print()
            print("Third-party reviews ensure code quality. Skipping requires justification.")
            sys.exit(1)

        if not review_success:
            engine.log_event(WorkflowEvent(
                event_type=EventType.REVIEW_FAILED,
                workflow_id=engine.state.workflow_id,
                phase_id=engine.state.current_phase_id,
                item_id=item_id,
                message=f"Review failed: {review_error or 'Blocking issues found'}",
                details={"review_notes": review_notes}
            ))
            # Review found blocking issues
            print("=" * 60)
            print(f"✗ REVIEW FAILED: {review_error or 'Blocking issues found'}")
            print("=" * 60)
            print(f"Review notes: {review_notes}")
            print()
            print("Options:")
            print(f"  1. Fix the issues and run: orchestrator complete {item_id}")
            print(f"  2. Skip with explanation: orchestrator skip {item_id} --reason \"<why issues acceptable>\"")
            sys.exit(1)

        engine.log_event(WorkflowEvent(
            event_type=EventType.REVIEW_COMPLETED,
            workflow_id=engine.state.workflow_id,
            phase_id=engine.state.current_phase_id,
            item_id=item_id,
            message=f"Review passed: {review_type}",
            details={"notes": review_notes}
        ))
        # Review passed - append review notes to user notes
        print(f"✓ Third-party review passed")
        print()
        if notes:
            notes = f"{notes}. {review_notes}"
        else:
            notes = review_notes

    try:
        success, message = engine.complete_item(
            args.item,
            notes=notes,
            skip_verification=args.skip_verify
        )

        if success:
            print(f"✓ {message}")
            if not args.quiet:
                print("\n" + engine.get_recitation_text())
        else:
            print(f"✗ {message}")
            sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_skip(args):
    """Skip an item with a reason."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    try:
        # Get item definition for context before skipping
        item_def = engine.get_item_definition(args.item)

        success, message = engine.skip_item(args.item, args.reason)

        if success:
            # CORE-010: Enhanced skip output
            print("=" * 60)
            print(f"⊘ SKIPPING: {args.item}")
            print("=" * 60)
            print(f"Reason: {args.reason}")
            print()

            # Show item description if available
            if item_def and item_def.description:
                print("What this item does:")
                print(f"  {item_def.description}")
                print()

            print("Implications:")
            item_name = item_def.name if item_def else args.item
            print(f"  • {item_name} will not be performed")
            print("=" * 60)

            if not args.quiet:
                print("\n" + engine.get_recitation_text())
        else:
            print(f"✗ {message}")
            sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_approve_item(args):
    """Approve a manual gate item."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Validate notes (CORE-008)
    try:
        notes = validate_note(args.notes)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        success, message = engine.approve_item(args.item, notes=notes)
        
        if success:
            print(f"✓ {message}")
            if not args.quiet:
                print("\n" + engine.get_recitation_text())
        else:
            print(f"✗ {message}")
            sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


# ============================================================================
# WF-005: Phase Summary Functions
# ============================================================================

def generate_phase_summary(engine) -> dict:
    """
    Generate summary of current phase for approval.

    Returns:
        Dictionary with completed items, skipped items, and git diff stat
    """
    if not engine.state:
        return {"completed": [], "skipped": [], "git_diff_stat": ""}

    phase_id = engine.state.current_phase_id
    phase = engine.state.phases.get(phase_id)

    # Get completed items with notes
    completed = []
    if phase:
        for item_id, item in phase.items.items():
            if item.status.value == "completed":
                completed.append({
                    "id": item_id,
                    "notes": item.notes or "No notes provided"
                })

    # Get skipped items
    skipped = engine.get_skipped_items(phase_id)

    # Get git diff stat
    git_diff_stat = _get_git_diff_stat(engine.working_dir)

    return {
        "completed": completed,
        "skipped": skipped,
        "git_diff_stat": git_diff_stat,
    }


def _get_git_diff_stat(working_dir) -> str:
    """Get git diff stat for display."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD~5"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""
    except Exception:
        return ""


def format_phase_summary(summary: dict, from_phase: str, to_phase: str) -> str:
    """Format phase summary for display."""
    lines = [
        "=" * 60,
        f"PHASE SUMMARY: {from_phase} -> {to_phase}",
        "=" * 60,
        "",
    ]

    # Completed items
    completed = summary.get("completed", [])
    if completed:
        lines.append(f"Completed Items ({len(completed)}):")
        for item in completed:
            notes = item["notes"]
            if len(notes) > 60:
                notes = notes[:57] + "..."
            lines.append(f"  ✓ {item['id']} - \"{notes}\"")
        lines.append("")
    else:
        lines.append("Completed Items: None")
        lines.append("")

    # Skipped items
    skipped = summary.get("skipped", [])
    if skipped:
        lines.append(f"Skipped Items ({len(skipped)}):")
        for item_id, reason in skipped:
            if len(reason) > 50:
                reason = reason[:47] + "..."
            lines.append(f"  ⊘ {item_id} - \"{reason}\"")
        lines.append("")

    # Git diff stat
    git_stat = summary.get("git_diff_stat", "")
    if git_stat:
        lines.append("Files Changed:")
        for line in git_stat.split("\n")[-5:]:  # Last 5 lines
            lines.append(f"  {line}")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


def cmd_advance(args):
    """Advance to the next phase."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Capture previous phase ID before advancing (for CORE-010 skip visibility)
    previous_phase_id = engine.state.current_phase_id

    # First check if we can advance
    can_advance, blockers, skipped = engine.can_advance_phase()

    if not can_advance and not args.force:
        print("✗ Cannot advance to next phase")
        print("\nBlockers:")
        for b in blockers:
            print(f"  - {b}")
        if skipped:
            print("\nSkipped items:")
            for s in skipped:
                print(f"  - {s}")
        print("\nUse --force to override (not recommended)")
        sys.exit(1)

    # WF-005: Show phase summary before advancing (unless --yes flag)
    next_phase_id = _get_next_phase_id(engine)
    if not getattr(args, 'yes', False) and next_phase_id:
        summary = generate_phase_summary(engine)
        print(format_phase_summary(summary, previous_phase_id, next_phase_id))
        print()

    # WF-008: Run AI critique if enabled (unless --no-critique flag)
    if not getattr(args, 'no_critique', False) and next_phase_id:
        try:
            from src.critique import PhaseCritique, format_critique_result

            critique = PhaseCritique(engine.working_dir)
            result = critique.run_if_enabled(engine, previous_phase_id, next_phase_id)

            if result:
                print(format_critique_result(result, previous_phase_id, next_phase_id))
                print()

                # If critical issues, prompt user
                if result.should_block and not getattr(args, 'yes', False):
                    response = input("Critical issues found. Continue anyway? [y/N]: ")
                    if response.lower() not in ['y', 'yes']:
                        print("Advance cancelled. Address issues before proceeding.")
                        sys.exit(1)
        except ImportError:
            pass  # Critique module not available
        except Exception as e:
            print(f"Warning: Critique failed: {e}. Continuing without critique.")

    success, message = engine.advance_phase(force=args.force)

    if success:
        print(f"✓ {message}")

        # CORE-010: Show skipped items from completed phase
        skipped_items = engine.get_skipped_items(previous_phase_id)
        if skipped_items:
            print(f"\nPhase {previous_phase_id} completed with {len(skipped_items)} skipped item(s):")
            for item_id, reason in skipped_items:
                print(f"  ⊘ {item_id} - \"{reason}\"")

        if not args.quiet:
            print("\n" + engine.get_recitation_text())
    else:
        print(f"✗ {message}")
        sys.exit(1)


def _get_next_phase_id(engine) -> str:
    """Get the next phase ID from the workflow definition."""
    if not engine.workflow_def or not engine.state:
        return ""

    phase_ids = [p.id for p in engine.workflow_def.phases]
    current_idx = -1

    for i, phase_id in enumerate(phase_ids):
        if phase_id == engine.state.current_phase_id:
            current_idx = i
            break

    if current_idx >= 0 and current_idx < len(phase_ids) - 1:
        return phase_ids[current_idx + 1]
    return ""


def cmd_approve(args):
    """Approve a phase gate."""
    engine = get_engine(args)
    
    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)
    
    success, message = engine.approve_phase(args.phase)
    
    if success:
        print(f"✓ {message}")
    else:
        print(f"✗ {message}")
        sys.exit(1)


def cmd_finish(args):
    """Complete or abandon the workflow."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Validate notes (CORE-008)
    try:
        notes = validate_note(args.notes)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.abandon:
        if not args.reason:
            print("Error: --reason is required when abandoning")
            sys.exit(1)
        engine.abandon_workflow(args.reason)
        print("✓ Workflow abandoned")
    else:
        # WF-014: Validate that required reviews were completed
        skip_review_check = getattr(args, 'skip_review_check', False)
        if not skip_review_check:
            is_valid, missing_reviews = engine.validate_reviews_completed()
            if not is_valid:
                print("=" * 60)
                print("⚠️  REVIEW VALIDATION FAILED")
                print("=" * 60)
                print(f"Missing required reviews: {', '.join(missing_reviews)}")
                print()
                print("External model reviews are REQUIRED before completing a workflow.")
                print("Run the reviews first, or use --skip-review-check with --reason")
                print()
                print("Example:")
                print('  orchestrator finish --skip-review-check --reason "Reviewed manually"')
                print("=" * 60)
                sys.exit(1)
        else:
            if not args.reason:
                print("Error: --reason is required when using --skip-review-check")
                sys.exit(1)
            print(f"⚠️  Skipping review check: {args.reason}")

        # CORE-011: Capture summary data before completing
        summary = engine.get_workflow_summary()
        all_skipped = engine.get_all_skipped_items()
        task_description = engine.state.task_description
        started_at = engine.state.created_at

        engine.complete_workflow(notes=notes)
        completed_at = engine.state.completed_at

        # CORE-011: Print comprehensive completion summary
        print("=" * 60)
        print("✓ WORKFLOW COMPLETED")
        print("=" * 60)
        print(f"Task: {task_description}")

        # Show duration if times are available
        if started_at and completed_at:
            duration = completed_at - started_at
            print(f"Duration: {format_duration(duration)}")
        print()

        # Phase summary table
        if summary:
            print("PHASE SUMMARY")
            print("-" * 60)
            total_completed = 0
            total_skipped = 0
            total_items = 0
            for phase_id, phase_data in summary.items():
                completed = phase_data['completed']
                skipped = phase_data['skipped']
                total = phase_data['total']
                total_completed += completed
                total_skipped += skipped
                total_items += total
                print(f"  {phase_id:12} {total} items ({completed} completed, {skipped} skipped)")
            print("-" * 60)
            print(f"  {'Total':12} {total_items} items ({total_completed} completed, {total_skipped} skipped)")
            print()

        # Skipped items summary
        if all_skipped:
            print("SKIPPED ITEMS (review for justification)")
            print("-" * 60)
            for phase_id, items in all_skipped.items():
                for item_id, reason in items:
                    # Truncate long reasons
                    short_reason = reason[:50] + "..." if len(reason) > 50 else reason
                    print(f"  • {item_id}: \"{short_reason}\"")
            print()

        # REVIEW MODEL VISIBILITY: Show which models reviewed each phase
        review_info = engine.state.metadata.get("review_models", {})
        if review_info:
            print("EXTERNAL REVIEWS PERFORMED")
            print("-" * 60)
            for phase_id, models in review_info.items():
                if models:
                    print(f"  {phase_id}:")
                    for model_name, status in models.items():
                        status_icon = "✓" if status.get("success") else "✗"
                        issues = status.get("issues", 0)
                        print(f"    {status_icon} {model_name}: {issues} issues found")
            print()
        else:
            print("EXTERNAL REVIEWS")
            print("-" * 60)
            print("  ⚠️  No external model reviews recorded!")
            print("  External reviews are REQUIRED for code changes.")
            print("  Ensure API keys are loaded: eval $(sops -d secrets.enc.yaml)")
            print()

        # LEARNINGS SUMMARY: Show actions vs roadmap items
        try:
            learnings_path = Path(args.dir or '.') / 'LEARNINGS.md'
            if learnings_path.exists():
                print("LEARNINGS SUMMARY")
                print("-" * 60)
                content = learnings_path.read_text()

                # Parse actions from learnings
                immediate_actions = []
                roadmap_items = []
                current_section = None

                for line in content.split('\n'):
                    line_lower = line.lower()
                    if 'immediate action' in line_lower or 'apply now' in line_lower:
                        current_section = 'immediate'
                    elif 'roadmap' in line_lower or 'future' in line_lower or 'later' in line_lower:
                        current_section = 'roadmap'
                    elif line.strip().startswith('- ') or line.strip().startswith('* '):
                        item = line.strip()[2:].strip()
                        if current_section == 'immediate' and item:
                            immediate_actions.append(item[:60])
                        elif current_section == 'roadmap' and item:
                            roadmap_items.append(item[:60])

                if immediate_actions:
                    print("  IMMEDIATE ACTIONS:")
                    for action in immediate_actions[:5]:
                        print(f"    → {action}")

                if roadmap_items:
                    print("  ROADMAP ITEMS:")
                    for item in roadmap_items[:5]:
                        print(f"    ○ {item}")

                if not immediate_actions and not roadmap_items:
                    print("  No specific actions identified. Review LEARNINGS.md manually.")
                print()
        except Exception as e:
            print(f"Warning: Could not parse LEARNINGS.md: {e}", file=sys.stderr)

        # Next steps prompt
        print("=" * 60)
        print("⚠️  WORKFLOW COMPLETE - WHAT'S NEXT?")
        print("=" * 60)
        print()
        print("The workflow is finished, but you may still need to:")
        print()
        print("  □ Create a PR:")
        # Generate suggested PR title from task description
        pr_title = task_description[:60] + "..." if len(task_description) > 60 else task_description
        print(f"    gh pr create --title \"{pr_title}\"")
        print()
        print("  □ Merge to main (if approved)")
        print()
        print("  □ Continue discussion with user about:")
        print("    • Any follow-up tasks?")
        print("    • Questions about the implementation?")
        print("    • Ready to close this session?")
        print()
        print("Reply to confirm next steps or start a new workflow.")
        print("=" * 60)

        # Trigger learning if available
        if not args.skip_learn:
            print("\nGenerating learning report...")
            try:
                learning = LearningEngine(args.dir or '.')
                report = learning.generate_learning_report()
                print(f"✓ Learning report saved to LEARNINGS.md")
            except Exception as e:
                print(f"Warning: Could not generate learning report: {e}")


def cmd_analyze(args):
    """Analyze workflow history."""
    analytics = WorkflowAnalytics(args.dir or '.')
    
    if args.json:
        print(json.dumps(analytics.get_summary(), indent=2, default=str))
    else:
        print(analytics.get_report())


def cmd_learn(args):
    """Generate a learning report from the current/last workflow."""
    learning = LearningEngine(args.dir or '.')
    
    report = learning.generate_learning_report()
    print(report)
    
    if not args.no_save:
        learning.append_to_learnings_file(report)
        print(f"\n✓ Report appended to LEARNINGS.md")


def cmd_dashboard(args):
    """Start the visual dashboard."""
    if args.static:
        html = generate_static_dashboard(args.dir or '.')
        output_path = Path(args.dir or '.') / 'dashboard.html'
        with open(output_path, 'w') as f:
            f.write(html)
        print(f"✓ Generated static dashboard: {output_path}")
    else:
        start_dashboard(args.dir or '.', args.port, not args.no_browser)


def cmd_validate(args):
    """Validate a workflow YAML file."""
    import yaml
    
    yaml_path = Path(args.dir or '.') / (args.workflow or 'workflow.yaml')
    
    if not yaml_path.exists():
        print(f"✗ File not found: {yaml_path}")
        sys.exit(1)
    
    try:
        with open(yaml_path, encoding='utf-8') as f:
            yaml_content = f.read()
            data = yaml.safe_load(yaml_content)
        
        # Validate against schema
        workflow_def = WorkflowDef(**data)
        
        # Additional validation
        issues = []
        
        # Check for duplicate item IDs
        all_item_ids = []
        for phase in workflow_def.phases:
            for item in phase.items:
                if item.id in all_item_ids:
                    issues.append(f"Duplicate item ID: {item.id}")
                all_item_ids.append(item.id)
        
        # Check for template variables without settings
        if workflow_def.settings:
            import re
            template_vars = set(re.findall(r'\{\{(\w+)\}\}', yaml_content))
            missing_vars = template_vars - set(workflow_def.settings.keys())
            if missing_vars:
                issues.append(f"Template variables without settings: {', '.join(missing_vars)}")
        
        if issues:
            print(f"⚠ {yaml_path} has issues:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"✓ {yaml_path} is valid")
            print(f"  Name: {workflow_def.name}")
            print(f"  Version: {workflow_def.version}")
            print(f"  Phases: {len(workflow_def.phases)}")
            total_items = sum(len(p.items) for p in workflow_def.phases)
            print(f"  Items: {total_items}")
            
    except yaml.YAMLError as e:
        print(f"✗ YAML syntax error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        sys.exit(1)


def cmd_handoff(args):
    """Generate a handoff prompt for an agent provider or execute directly."""
    engine = get_engine(args)
    
    if not engine.state or not engine.workflow_def:
        print("Error: No active workflow")
        sys.exit(1)
    
    # Get current phase info
    status = engine.get_status()
    phase_def = engine.workflow_def.get_phase(engine.state.current_phase_id)
    
    # Get pending items
    pending_items = [item for item in status['checklist'] 
                     if item['status'] not in ['completed', 'skipped']]
    
    if not pending_items:
        print("No pending items in current phase.")
        sys.exit(0)
    
    # Get the provider (explicit, environment-based, or auto-detected)
    env_override = getattr(args, 'env', None)
    try:
        provider = get_provider(
            name=getattr(args, 'provider', None),
            environment=env_override,
            working_dir=args.dir or '.'
        )
    except ValueError as e:
        print(f"Error: {e}")
        print(f"Available providers: {', '.join(list_providers())}")
        sys.exit(1)
    
    # Build context for prompt generation
    context = {
        "phase": phase_def.name if phase_def else engine.state.current_phase_id,
        "items": pending_items,
        "constraints": args.constraints.split(',') if args.constraints else [],
        "files": args.files.split(',') if args.files else [],
        "acceptance_criteria": args.criteria.split(',') if args.criteria else [],
        "notes": [],  # Will be populated when notes feature is implemented
    }
    
    # Generate the handoff prompt
    prompt = provider.generate_prompt(
        task=engine.state.task_description,
        context=context
    )
    
    if args.execute:
        # Execute directly with the provider
        if not provider.is_available():
            print(f"Error: Provider '{provider.name()}' is not available")
            if provider.name() == 'openrouter':
                print("Set OPENROUTER_API_KEY environment variable.")
            elif provider.name() == 'claude_code':
                print("Install Claude Code CLI from https://claude.ai/code")
            sys.exit(1)
        
        if not provider.supports_execution():
            print(f"Error: Provider '{provider.name()}' does not support direct execution.")
            print("Copy the prompt below and paste it into your preferred LLM.")
            print("=" * 60)
            print(prompt)
            print("=" * 60)
            sys.exit(1)
        
        model = getattr(args, 'model', None)
        print(f"Executing with {provider.name()} provider...")
        if model:
            print(f"Using model: {model}")
        print("=" * 60)
        
        result = provider.execute(prompt, model=model)
        
        print(result.output)
        print("=" * 60)
        
        if result.success:
            print(f"\n✓ Execution completed")
            if result.model_used:
                print(f"  Model: {result.model_used}")
            if result.duration_seconds:
                print(f"  Duration: {result.duration_seconds:.1f}s")
            if result.tokens_used:
                print(f"  Tokens: {result.tokens_used}")
        else:
            print(f"\n✗ Execution failed: {result.error}")
            sys.exit(1)
    else:
        # Just print the prompt for manual use
        print("=" * 60)
        print(f"HANDOFF PROMPT (Provider: {provider.name()})")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        print(f"\nTo execute: orchestrator handoff --execute")
        if provider.name() != 'manual':
            print(f"Provider: {provider.name()} (auto-detected)")
        print("Or copy the above prompt to your preferred LLM manually.")


def cmd_list(args):
    """List all workflows in the directory tree."""
    workflows = WorkflowEngine.find_workflows(args.search_dir, args.depth)
    
    if args.active_only:
        workflows = [w for w in workflows if w['status'] == 'active']
    
    if args.json:
        print(json.dumps(workflows, indent=2, default=str))
        return
    
    if not workflows:
        print("No workflows found.")
        return
    
    print(f"Found {len(workflows)} workflow(s):\n")
    
    for wf in workflows:
        status_icon = "●" if wf['status'] == 'active' else \
                      "✓" if wf['status'] == 'completed' else \
                      "✗" if wf['status'] == 'abandoned' else "○"
        
        print(f"{status_icon} {wf['workflow_id']}")
        print(f"  Task: {wf['task'][:60]}{'...' if len(wf['task']) > 60 else ''}")
        print(f"  Status: {wf['status']} | Phase: {wf['current_phase']}")
        print(f"  Directory: {wf['directory']}")
        if wf['updated_at']:
            print(f"  Updated: {wf['updated_at']}")
        print()


def cmd_cleanup(args):
    """Clean up abandoned workflows."""
    if args.dry_run:
        # Just show what would be cleaned
        workflows = WorkflowEngine.find_workflows(args.search_dir, args.depth)
        active = [w for w in workflows if w['status'] == 'active']
        
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.max_age)
        
        stale = []
        for wf in active:
            if wf['updated_at']:
                try:
                    updated = datetime.fromisoformat(wf['updated_at'].replace('Z', '+00:00'))
                    if updated < cutoff:
                        stale.append(wf)
                except (ValueError, TypeError):
                    # Skip workflows with invalid date formats
                    pass
        
        if not stale:
            print(f"No stale workflows found (older than {args.max_age} days).")
            return
        
        print(f"Would clean up {len(stale)} stale workflow(s):\n")
        for wf in stale:
            print(f"  - {wf['workflow_id']}: {wf['task'][:40]}...")
            print(f"    Last updated: {wf['updated_at']}")
        print("\nRun without --dry-run to actually clean up.")
    else:
        cleaned = WorkflowEngine.cleanup_all_abandoned(args.search_dir, args.max_age, args.depth)
        
        if not cleaned:
            print(f"No stale workflows found (older than {args.max_age} days).")
        else:
            print(f"Cleaned up {len(cleaned)} workflow(s):")
            for wf in cleaned:
                print(f"  - {wf['workflow_id']}: {wf['task'][:40]}...")


def cmd_visual_verify(args):
    """Run visual verification against a URL."""
    try:
        client = VisualVerificationClient()
    except VisualVerificationError as e:
        print(f"Error: {e}")
        print("\nSet VISUAL_VERIFICATION_URL and VISUAL_VERIFICATION_API_KEY environment variables.")
        sys.exit(1)
    
    # Load specification
    spec_path = Path(args.spec)
    if spec_path.exists():
        with open(spec_path, 'r') as f:
            specification = f.read()
    else:
        specification = args.spec
    
    # Load style guide if provided
    style_guide_content = None
    if args.style_guide:
        style_guide_path = Path(args.style_guide)
        if style_guide_path.exists():
            with open(style_guide_path, 'r') as f:
                style_guide_content = f.read()
        else:
            print(f"Warning: Style guide not found: {args.style_guide}")
    
    results = []
    
    # Desktop verification
    print("Running desktop verification...")
    try:
        actions = [{"type": "screenshot", "name": "desktop"}]
        if style_guide_content:
            desktop_result = client.verify_with_style_guide(
                args.url, specification, style_guide_content,
                actions=actions,
                viewport=create_desktop_viewport()
            )
        else:
            desktop_result = client.verify(
                args.url, specification,
                actions=actions,
                viewport=create_desktop_viewport()
            )
        desktop_result['viewport'] = 'desktop'
        results.append(desktop_result)
    except VisualVerificationError as e:
        print(f"Desktop verification failed: {e}")
        results.append({'status': 'error', 'viewport': 'desktop', 'reasoning': str(e)})
    
    # Mobile verification
    if args.mobile:
        print("Running mobile verification...")
        try:
            actions = [{"type": "screenshot", "name": "mobile"}]
            if style_guide_content:
                mobile_result = client.verify_with_style_guide(
                    args.url, specification, style_guide_content,
                    actions=actions,
                    viewport=create_mobile_viewport()
                )
            else:
                mobile_result = client.verify(
                    args.url, specification,
                    actions=actions,
                    viewport=create_mobile_viewport()
                )
            mobile_result['viewport'] = 'mobile'
            results.append(mobile_result)
        except VisualVerificationError as e:
            print(f"Mobile verification failed: {e}")
            results.append({'status': 'error', 'viewport': 'mobile', 'reasoning': str(e)})
    
    # Output results
    print("\n" + "="*60)
    all_passed = all(r.get('status') == 'pass' for r in results)
    
    for result in results:
        print(format_verification_result(result, result.get('viewport', 'unknown')))
        print()
    
    if all_passed:
        print("✓ ALL VERIFICATIONS PASSED")
        sys.exit(0)
    else:
        print("✗ SOME VERIFICATIONS FAILED")
        sys.exit(1)


def cmd_visual_verify_all(args):
    """Run all visual tests in a directory (VV-003)."""
    try:
        client = VisualVerificationClient(
            style_guide_path=args.style_guide if hasattr(args, 'style_guide') else None
        )
    except VisualVerificationError as e:
        print(f"Error: {e}")
        print("\nSet VISUAL_VERIFICATION_URL environment variable.")
        sys.exit(1)

    # Discover and run tests
    print(f"Discovering visual tests in {args.tests_dir}...")
    tests = discover_visual_tests(args.tests_dir)

    if not tests:
        print(f"No visual test files found in {args.tests_dir}")
        print("\nCreate test files with YAML frontmatter:")
        print("  ---")
        print("  url: /dashboard")
        print("  device: iphone-14")
        print("  tags: [core]")
        print("  ---")
        print("  The dashboard should display...")
        sys.exit(0)

    print(f"Found {len(tests)} test(s)")

    # Run tests
    results = run_all_visual_tests(
        client,
        tests_dir=args.tests_dir,
        app_url=args.app_url,
        tags=args.tag,
        save_baselines=args.save_baselines
    )

    # Display results
    print("\n" + "=" * 60)
    print("VISUAL TEST RESULTS")
    print("=" * 60)

    for item in results['results']:
        if 'error' in item:
            print(f"✗ {item['test']}: ERROR - {item['error']}")
        else:
            result = item['result']
            status_icon = '✓' if result.status == 'pass' else '✗'
            print(f"{status_icon} {item['test']}: {result.status}")
            if result.status != 'pass' and result.issues:
                for issue in result.issues[:3]:  # Show first 3 issues
                    print(f"    - [{issue.get('severity', 'unknown')}] {issue.get('description', '')}")

    # Summary
    summary = results['summary']
    print("\n" + "-" * 60)
    print(f"Total: {summary['total']} | Passed: {summary['passed']} | Failed: {summary['failed']} | Errors: {summary['errors']}")

    # Cost summary (VV-006)
    if args.show_cost:
        print(format_cost_summary(results['cost_summary']))

    # Exit code
    if summary['failed'] > 0 or summary['errors'] > 0:
        sys.exit(1)
    sys.exit(0)


def cmd_visual_template(args):
    """Generate a visual test template for a feature."""
    template = f'''# Visual UAT Test: {args.feature_name}

## Test URL
{{{{base_url}}}}/path/to/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Actions to Perform
1. Navigate to the page
2. [Action 2]
3. [Action 3]

## Specific Checks
- [ ] [Specific element] is visible
- [ ] [Specific functionality] works
- [ ] [Expected state] is achieved

## Open-Ended Evaluation (Mandatory)
1. Does this feature work as specified? Can the user complete the intended action?
2. Is the design consistent with our style guide?
3. Is the user journey intuitive? Would a first-time user understand what to do?
4. How does it handle edge cases (errors, empty states, unexpected input)?
5. Does it work well on mobile? Are there any responsive design issues?

## Open-Ended Evaluation (Optional)
- [ ] Accessibility: Are there any obvious accessibility concerns?
- [ ] Visual hierarchy: Does the layout guide the user appropriately?
- [ ] Performance: Do loading states feel responsive?
'''
    print(template)


def cmd_generate_md(args):
    """Generate a human-readable WORKFLOW.md from current state."""
    engine = get_engine(args)
    
    if not engine.state or not engine.workflow_def:
        print("Error: No active workflow")
        sys.exit(1)
    
    md_content = generate_workflow_md(engine)
    
    output_path = Path(args.dir or '.') / 'WORKFLOW.md'
    with open(output_path, 'w') as f:
        f.write(md_content)
    
    print(f"✓ Generated {output_path}")


def generate_workflow_md(engine: WorkflowEngine) -> str:
    """Generate markdown content for WORKFLOW.md"""
    status = engine.get_status()
    state = engine.state
    workflow_def = engine.workflow_def
    
    lines = [
        f"# Workflow: {state.task_description}",
        "",
        "## Current State (RECITE THIS FIRST)",
        "",
        f"**Phase:** {status['current_phase']['id']} - {status['current_phase']['name']}",
        f"**Progress:** {status['current_phase']['progress']}",
        f"**Status:** {'Ready to advance ✓' if status['can_advance'] else 'Blocked'}",
        f"**Last Updated:** {status['updated_at']}",
        "",
    ]
    
    if status['blockers']:
        lines.append("### Blockers")
        for b in status['blockers']:
            lines.append(f"- {b}")
        lines.append("")
    
    lines.append("## Checklist")
    lines.append("")
    
    # Group by phase
    for phase_def in workflow_def.phases:
        phase_state = state.phases.get(phase_def.id)
        phase_status = phase_state.status.value if phase_state else "pending"
        
        status_icon = "✓" if phase_status == "completed" else \
                      "●" if phase_def.id == state.current_phase_id else "○"
        
        lines.append(f"### {status_icon} {phase_def.id}: {phase_def.name}")
        lines.append("")
        
        for item_def in phase_def.items:
            item_state = phase_state.items.get(item_def.id) if phase_state else None
            item_status = item_state.status.value if item_state else "pending"
            
            checkbox = "[x]" if item_status == "completed" else \
                       "[~]" if item_status == "skipped" else \
                       "[-]" if item_status == "in_progress" else "[ ]"
            
            required = " *(required)*" if item_def.required else ""
            
            lines.append(f"- {checkbox} **{item_def.id}** — {item_def.name}{required}")
            
            if item_def.description:
                lines.append(f"  - {item_def.description}")
            
            if item_state and item_state.skip_reason:
                lines.append(f"  - *Skipped: {item_state.skip_reason}*")
            
            if item_state and item_state.notes:
                lines.append(f"  - Notes: {item_state.notes}")
        
        lines.append("")
    
    lines.extend([
        "## Activity Log",
        "",
        "| Time | Event | Details |",
        "|------|-------|---------|",
    ])
    
    events = engine.get_events(20)
    for event in reversed(events):
        time_str = event.timestamp.strftime("%H:%M")
        lines.append(f"| {time_str} | {event.event_type.value} | {event.message} |")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*Workflow ID: {state.workflow_id}*")
    
    return "\n".join(lines)


# ============================================================================
# Checkpoint Commands (Feature 5)
# ============================================================================

def cmd_checkpoint(args):
    """Create a checkpoint for the current workflow state."""
    engine = get_engine(args)
    
    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)
    
    checkpoint_mgr = CheckpointManager(args.dir or '.')
    
    # Parse key decisions
    decisions = getattr(args, 'decision', None) or []
    
    # Parse file manifest
    files = getattr(args, 'file', None) or []
    
    # Get current item ID if in progress
    current_item_id = None
    phase_state = engine.state.get_current_phase()
    if phase_state:
        for item_id, item_state in phase_state.items.items():
            if item_state.status.value == 'in_progress':
                current_item_id = item_id
                break
    
    checkpoint = checkpoint_mgr.create_checkpoint(
        workflow_id=engine.state.workflow_id,
        phase_id=engine.state.current_phase_id,
        item_id=current_item_id,
        message=getattr(args, 'message', None),
        key_decisions=decisions,
        file_manifest=files,
        workflow_state=engine.state.model_dump(mode='json'),
        auto_detect_files=True
    )
    
    print(f"\n✓ Checkpoint created: {checkpoint.checkpoint_id}")
    print(f"  Phase: {checkpoint.phase_id}")
    if checkpoint.item_id:
        print(f"  Item: {checkpoint.item_id}")
    if checkpoint.message:
        print(f"  Message: {checkpoint.message}")
    print(f"  Files tracked: {len(checkpoint.file_manifest)}")
    print("\nResume with: orchestrator resume")


def cmd_checkpoints(args):
    """List all checkpoints."""
    checkpoint_mgr = CheckpointManager(args.dir or '.')
    
    # Handle cleanup
    if getattr(args, 'cleanup', False):
        max_age = getattr(args, 'max_age', 30)
        removed = checkpoint_mgr.cleanup_old_checkpoints(max_age_days=max_age)
        print(f"Removed {removed} old checkpoints")
        return
    
    # Get workflow ID filter
    workflow_id = None
    if not getattr(args, 'all', False):
        engine = WorkflowEngine(args.dir or '.')
        engine.load_state()
        if engine.state:
            workflow_id = engine.state.workflow_id
    
    checkpoints = checkpoint_mgr.list_checkpoints(
        workflow_id=workflow_id,
        include_completed=getattr(args, 'completed', False)
    )
    
    if not checkpoints:
        print("No checkpoints found.")
        return
    
    print(f"\nFound {len(checkpoints)} checkpoint(s):\n")
    print(f"{'ID':<35} {'Phase':<12} {'Time':<20} {'Message'}")
    print("-" * 80)
    
    for cp in checkpoints:
        timestamp = cp.timestamp[:19].replace('T', ' ')
        message = (cp.message or '')[:30]
        print(f"{cp.checkpoint_id:<35} {cp.phase_id:<12} {timestamp:<20} {message}")


def cmd_resume(args):
    """Resume from a checkpoint."""
    checkpoint_mgr = CheckpointManager(args.dir or '.')

    # Get checkpoint
    checkpoint_id = getattr(args, 'from_checkpoint', None)

    if checkpoint_id:
        checkpoint = checkpoint_mgr.get_checkpoint(checkpoint_id)
        if not checkpoint:
            print(f"Error: Checkpoint not found: {checkpoint_id}")
            sys.exit(1)
    else:
        checkpoint = checkpoint_mgr.get_latest_checkpoint()
        if not checkpoint:
            print("Error: No checkpoints found. Create one with: orchestrator checkpoint")
            sys.exit(1)

    # Dry run mode
    if getattr(args, 'dry_run', False):
        print("\n[DRY RUN] Would resume from checkpoint:\n")
        print(checkpoint_mgr.generate_resume_prompt(checkpoint))
        return

    # Generate and print resume prompt
    print(checkpoint_mgr.generate_resume_prompt(checkpoint))

    # Also show current status
    engine = get_engine(args)
    if engine.state:
        print("\n" + engine.get_recitation_text())


# ============================================================================
# Review Commands (Multi-model AI reviews)
# ============================================================================

def cmd_review(args):
    """Run AI code reviews."""
    working_dir = Path(args.dir or '.')

    try:
        router = ReviewRouter(
            working_dir=working_dir,
            method=args.method if args.method != 'auto' else None
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Running reviews using {router.method.value} method...\n")

    review_type = args.review_type or 'all'

    if review_type == 'all':
        results = router.execute_all_reviews()
    else:
        results = {review_type: router.execute_review(review_type)}

    if args.json:
        output = {k: v.to_dict() for k, v in results.items()}
        print(json.dumps(output, indent=2, default=str))
        return

    # Pretty print results
    all_passed = True
    total_blocking = 0

    for review_name, result in results.items():
        icon = "✓" if result.success and not result.has_blocking_findings() else "✗"
        print(f"{icon} {review_name.upper()} REVIEW")
        print(f"  Model: {result.model_used}")
        print(f"  Method: {result.method_used}")

        if result.error:
            print(f"  Error: {result.error}")
            all_passed = False
        elif result.findings:
            print(f"  Findings: {len(result.findings)}")
            for finding in result.findings[:5]:  # Show first 5
                severity_icon = "🔴" if finding.severity.is_blocking() else "🟡"
                print(f"    {severity_icon} [{finding.severity.value.upper()}] {finding.issue[:60]}...")
                if finding.location:
                    print(f"       at {finding.location}")
            if len(result.findings) > 5:
                print(f"    ... and {len(result.findings) - 5} more")

            if result.has_blocking_findings():
                all_passed = False
                total_blocking += result.blocking_count
        else:
            print("  Findings: None")

        if result.summary:
            print(f"  Summary: {result.summary[:100]}...")

        if result.duration_seconds:
            print(f"  Duration: {result.duration_seconds:.1f}s")

        print()

    # Summary
    if all_passed:
        print("✓ ALL REVIEWS PASSED")
    else:
        print(f"✗ REVIEWS FOUND {total_blocking} BLOCKING ISSUE(S)")
        sys.exit(1)


def cmd_review_status(args):
    """Show review infrastructure status."""
    working_dir = Path(args.dir or '.')
    setup = check_review_setup(working_dir)

    print("Review Infrastructure Status:")
    print()

    # CLI tools
    codex_status = "✓" if setup.codex_cli else "✗"
    gemini_status = "✓" if setup.gemini_cli else "✗"
    print(f"  CLI Tools:      {codex_status} codex  {gemini_status} gemini")

    if not setup.codex_cli or not setup.gemini_cli:
        print("                  Install: npm install -g @openai/codex @google/gemini-cli")

    # Aider (Gemini via OpenRouter with full repo context)
    aider_status = "✓" if setup.aider_cli else "✗"
    aider_note = " (gemini via openrouter)" if setup.aider_available else ""
    print(f"  Aider:          {aider_status} aider{aider_note}")

    if not setup.aider_cli:
        print("                  Install: pip install aider-chat")

    # API key
    api_status = "✓" if setup.openrouter_key else "✗"
    print(f"  API Key:        {api_status} OPENROUTER_API_KEY")

    if not setup.openrouter_key:
        print("                  Set environment variable for API/Aider mode")

    # GitHub Actions
    actions_status = "✓" if setup.github_actions else "✗"
    print(f"  GitHub Actions: {actions_status} .github/workflows/ai-reviews.yml")

    # Config files
    styleguide_status = "✓" if setup.gemini_styleguide else "✗"
    agents_status = "✓" if setup.agents_md else "✗"
    print(f"  Config Files:   {styleguide_status} .gemini/styleguide.md  {agents_status} AGENTS.md")

    print()

    # Recommended action
    if setup.cli_available:
        print("  ✓ Ready to run reviews using CLI mode (best experience)")
    elif setup.aider_available:
        print("  ✓ Ready to run reviews using Aider (full repo context via repo map)")
    elif setup.api_available:
        print("  ⚠️  CLI/Aider not available. Will use API mode (reduced context)")
        print("     For better reviews, install: pip install aider-chat")
    else:
        print("  ✗ No review method available!")
        print("     Install: pip install aider-chat")
        print("     Or: npm install -g @openai/codex @google/gemini-cli")
        print("     And set: OPENROUTER_API_KEY")

    if not setup.github_actions:
        print()
        print("  💡 GitHub Actions not configured. PRs won't have automated reviews.")
        print("     Run: orchestrator setup-reviews")


def cmd_review_results(args):
    """Show results of completed reviews."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Look for stored review results in item states
    results = {}
    for phase_id, phase_state in engine.state.phases.items():
        for item_id, item_state in phase_state.items.items():
            if hasattr(item_state, 'review_result') and item_state.review_result:
                results[item_id] = item_state.review_result

    if not results:
        print("No review results found.")
        print("Run: orchestrator review")
        return

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return

    print(f"Found {len(results)} review result(s):\n")
    for item_id, result in results.items():
        print(f"## {item_id}")
        if isinstance(result, dict):
            print(f"  Success: {result.get('success', 'unknown')}")
            print(f"  Model: {result.get('model_used', 'unknown')}")
            findings = result.get('findings', [])
            print(f"  Findings: {len(findings)}")
            if result.get('summary'):
                print(f"  Summary: {result['summary'][:100]}...")
        print()


HOOK_CONTENT = '''#!/bin/bash
# Auto-install/update workflow orchestrator
# Added by: orchestrator install-hook
echo "Checking workflow orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
'''

HOOK_MARKER = "# Added by: orchestrator install-hook"


def _find_secrets_source() -> Path | None:
    """Find an existing secrets file to copy from.

    Checks in order:
    1. Orchestrator installation directory
    2. User config directory (~/.config/orchestrator/)

    Returns:
        Path to secrets file if found, None otherwise.
    """
    # Check orchestrator installation directory
    src_dir = Path(__file__).parent
    orchestrator_secrets = src_dir.parent / SIMPLE_SECRETS_FILE
    if orchestrator_secrets.exists():
        return orchestrator_secrets

    # Check user config directory
    user_secrets = Path.home() / ".config" / "orchestrator" / "secrets.enc"
    if user_secrets.exists():
        return user_secrets

    return None


def _copy_secrets_to_repo(source: Path, working_dir: Path) -> bool:
    """Copy secrets file to a repo.

    Args:
        source: Source secrets file path
        working_dir: Target repo directory

    Returns:
        True if copied successfully
    """
    import shutil

    dest = working_dir / SIMPLE_SECRETS_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy(source, dest)
        return True
    except Exception as e:
        print(f"Error copying secrets: {e}")
        return False


def cmd_setup(args):
    """Set up automatic updates for this repo, or remove the setup."""
    working_dir = Path(args.dir or '.')
    hooks_dir = working_dir / '.claude' / 'hooks'
    hook_file = hooks_dir / 'session-start.sh'

    if args.remove:
        # Remove the auto-update setup
        if not hook_file.exists():
            print("Auto-updates not configured for this repo.")
            return

        content = hook_file.read_text()

        if HOOK_MARKER not in content:
            print("Auto-updates not configured for this repo.")
            return

        # Remove the orchestrator section
        lines = content.split('\n')
        new_lines = []
        skip_until_empty = False

        for line in lines:
            if HOOK_MARKER in line:
                skip_until_empty = True
                continue
            if skip_until_empty:
                if line.strip() == '':
                    skip_until_empty = False
                continue
            new_lines.append(line)

        new_content = '\n'.join(new_lines).strip()

        if not new_content or new_content == '#!/bin/bash':
            # Hook file is now empty, remove it
            hook_file.unlink()
            # Clean up empty directories
            if hooks_dir.exists() and not any(hooks_dir.iterdir()):
                hooks_dir.rmdir()
                claude_dir = hooks_dir.parent
                if claude_dir.exists() and not any(claude_dir.iterdir()):
                    claude_dir.rmdir()
        else:
            hook_file.write_text(new_content + '\n')

        print("✓ Auto-updates disabled for this repo.")
        return

    # Set up auto-updates
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if hook_file.exists() and not args.force:
        content = hook_file.read_text()
        if HOOK_MARKER in content:
            print("✓ Auto-updates already enabled for this repo.")
            return
        # Append to existing hook
        with open(hook_file, 'a') as f:
            f.write('\n' + HOOK_CONTENT)
    else:
        hook_file.write_text(HOOK_CONTENT)

    # Make executable
    import os
    os.chmod(hook_file, 0o755)

    print("✓ Auto-updates enabled for this repo.")
    print("")
    print("The orchestrator will automatically update when you start a new Claude Code session.")
    print("Works in both Claude Code CLI and Claude Code Web.")

    # Check if secrets need to be copied
    local_secrets = working_dir / SIMPLE_SECRETS_FILE
    if not local_secrets.exists():
        source_secrets = _find_secrets_source()
        if source_secrets:
            print("")
            print(f"Found encrypted secrets at: {source_secrets}")

            # Auto-copy if --copy-secrets flag or prompt user
            if getattr(args, 'copy_secrets', False):
                if _copy_secrets_to_repo(source_secrets, working_dir):
                    print(f"✓ Secrets copied to {local_secrets}")
                    print("  Set SECRETS_PASSWORD env var to decrypt in Claude Code Web")
            else:
                print("Run with --copy-secrets to copy them to this repo")
                print("  orchestrator setup --copy-secrets")
        else:
            print("")
            print("No secrets file found in this repo.")
            print("Run 'orchestrator secrets init' to set up encrypted API keys")

    print("")
    print("To disable: orchestrator setup --remove")


def cmd_setup_reviews(args):
    """Set up review infrastructure in a repository."""
    working_dir = Path(args.dir or '.')

    print("Setting up review infrastructure...\n")

    results = setup_reviews(
        working_dir=working_dir,
        dry_run=args.dry_run,
        skip_actions=args.skip_actions,
        force=args.force,
    )

    if not results:
        print("All files already exist. Use --force to overwrite.")
        return

    for path, status in results.items():
        print(f"  {status}")

    if args.dry_run:
        print("\n[DRY RUN] No files were written. Remove --dry-run to create files.")
    else:
        print("\n✓ Review infrastructure set up!")
        print("\nNext steps:")
        print("  1. Add OPENAI_API_KEY to your GitHub repository secrets")
        print("  2. Customize .gemini/styleguide.md for your project")
        print("  3. Update AGENTS.md with your project conventions")
        print("  4. Push to GitHub to enable PR reviews")


def cmd_config(args):
    """Manage orchestrator configuration."""
    action = args.action

    if action == "set":
        if not args.key or not args.value:
            print("Error: 'config set' requires KEY and VALUE arguments")
            sys.exit(1)
        set_user_config_value(args.key, args.value)
        print(f"✓ Set {args.key} = {args.value}")
        print(f"  Saved to: {CONFIG_FILE}")

    elif action == "get":
        if not args.key:
            print("Error: 'config get' requires KEY argument")
            sys.exit(1)
        value = get_user_config_value(args.key)
        if value is not None:
            print(value)
        else:
            print(f"(not set)")
            sys.exit(1)

    elif action == "list":
        config = get_user_config()
        if not config:
            print("No configuration set")
            print(f"\nConfig file: {CONFIG_FILE}")
            return
        print("Current configuration:")
        for key, value in sorted(config.items()):
            print(f"  {key}: {value}")
        print(f"\nConfig file: {CONFIG_FILE}")

    else:
        print(f"Unknown action: {action}")
        print("Available actions: set, get, list")
        sys.exit(1)


def cmd_secrets(args):
    """Manage secrets and test secret access."""
    working_dir = Path(args.dir or '.')
    action = args.action

    if action == "init":
        # Secrets setup (interactive or from environment)
        password = getattr(args, 'password', None)
        from_env = getattr(args, 'from_env', False)
        init_secrets_interactive(working_dir, password=password, from_env=from_env)
        return

    secrets = get_secrets_manager(working_dir=working_dir)

    if action == "test":
        if not args.name:
            print("Error: 'secrets test' requires NAME argument")
            sys.exit(1)
        value = secrets.get_secret(args.name)
        if value is not None:
            print(f"✓ Secret '{args.name}' is accessible")
            print(f"  Length: {len(value)} characters")
        else:
            print(f"✗ Secret '{args.name}' not found in any source")
            sys.exit(1)

    elif action == "source":
        if not args.name:
            print("Error: 'secrets source' requires NAME argument")
            sys.exit(1)
        source = secrets.get_source(args.name)
        if source:
            print(source)
        else:
            print("(not found)")
            sys.exit(1)

    elif action == "sources":
        sources = secrets.list_sources()
        print("Secret Sources:")
        print("")
        for name, info in sources.items():
            status = "✓" if info["available"] else "✗"
            print(f"  {status} {name}: {info['description']}")
            if name == "simple":
                if not info.get("file_exists"):
                    print(f"      - File not found: {info.get('file_path')}")
                    print("      - Run: orchestrator secrets init")
                if not info.get("password_set"):
                    print("      - SECRETS_PASSWORD not set")
            elif name == "sops":
                if not info.get("installed"):
                    print("      - SOPS not installed")
                if not info.get("key_set"):
                    print("      - SOPS_AGE_KEY not set")
                if not info.get("file_exists"):
                    print(f"      - File not found: {info.get('file_path')}")
            elif name == "github":
                if not info.get("installed"):
                    print("      - GitHub CLI (gh) not installed")
                if not info.get("configured"):
                    print("      - secrets_repo not configured")
                    print("      - Run: orchestrator config set secrets_repo OWNER/REPO")
                elif info.get("repo"):
                    print(f"      - Repo: {info.get('repo')}")

    elif action == "copy":
        # SEC-004: Copy secrets between repos
        from src.secrets import copy_secrets_file

        source_dir = getattr(args, 'from_dir', None) or getattr(args, 'source', None)
        dest_dir = getattr(args, 'to_dir', None) or working_dir
        force = getattr(args, 'force', False)

        if not source_dir:
            print("Error: 'secrets copy' requires --from argument")
            print("Usage: orchestrator secrets copy --from /path/to/source [--to /path/to/dest]")
            sys.exit(1)

        source_path = Path(source_dir)
        dest_path = Path(dest_dir)

        if copy_secrets_file(source_path, dest_path, force=force):
            print(f"✓ Secrets copied from {source_path} to {dest_path}")
        else:
            print(f"✗ Failed to copy secrets")
            if (dest_path / SIMPLE_SECRETS_FILE).exists() and not force:
                print("  Destination already has secrets. Use --force to overwrite.")
            sys.exit(1)

    else:
        print(f"Unknown action: {action}")
        print("Available actions: init, test, source, sources, copy")
        sys.exit(1)


def cmd_update_models(args):
    """Update the model registry from OpenRouter API (CORE-017)."""
    from src.model_registry import get_model_registry

    working_dir = Path(args.dir or '.')
    force = getattr(args, 'force', False)
    check_only = getattr(args, 'check', False)

    registry = get_model_registry(working_dir=working_dir)

    if check_only:
        # Just check staleness
        if registry.is_stale():
            last = registry.last_updated
            if last:
                print(f"⚠️  Model registry is stale (last updated: {last.date()})")
            else:
                print("⚠️  Model registry has never been updated")
            print("Run 'orchestrator update-models' to update")
            sys.exit(1)
        else:
            print(f"✓ Model registry is up to date (last updated: {registry.last_updated.date()})")
            sys.exit(0)

    # Perform update
    print("Fetching latest models from OpenRouter API...")

    if registry.update(force=force):
        print(f"✓ Model registry updated with {len(registry.models)} models")
        print(f"  Last updated: {registry.last_updated}")

        # Show summary of function-calling capable models
        fc_models = [m for m, caps in registry.models.items()
                     if caps.get('supports_tools', False)]
        print(f"  Function-calling models: {len(fc_models)}")
    else:
        print("✗ Failed to update model registry")
        print("  API may be unavailable. Using cached data if available.")
        sys.exit(1)


# ============================================================================
# PRD Commands (Phase 6)
# ============================================================================

# ============================================================================
# Claude Squad Integration Commands (PRD-001)
# ============================================================================

def cmd_prd_check_squad(args):
    """Check Claude Squad compatibility."""
    from src.prd.squad_capabilities import CapabilityDetector

    detector = CapabilityDetector()
    caps = detector.detect()

    print("Claude Squad Compatibility Check")
    print("=" * 40)

    if not caps.installed:
        print("  Status: NOT INSTALLED")
        print("  Install: https://github.com/smtg-ai/claude-squad")
        sys.exit(1)

    print(f"  Version: {caps.version or 'unknown'}")
    print(f"  Status: {'Compatible' if caps.is_compatible else 'INCOMPATIBLE'}")
    print()
    print("Capabilities:")
    print(f"  Commands: new={caps.supports_new}, list={caps.supports_list}, "
          f"attach={caps.supports_attach}, kill={caps.supports_kill}")
    print(f"  Flags: prompt_file={caps.supports_prompt_file}, branch={caps.supports_branch}, "
          f"dir={caps.supports_dir}, autoyes={caps.supports_autoyes}")
    print(f"  JSON output: {caps.supports_json_output}")

    if caps.compatibility_issues:
        print()
        print("Issues:")
        for issue in caps.compatibility_issues:
            print(f"  - {issue}")
        sys.exit(1)

    print()
    print("Ready for PRD execution with Claude Squad!")


def cmd_prd_spawn(args):
    """Spawn Claude Squad sessions for PRD tasks using smart scheduling."""
    import yaml
    from src.prd import PRDExecutor, PRDConfig, PRDDocument, PRDTask

    working_dir = Path(args.dir or '.')

    if not args.prd_file:
        print("Error: --prd-file required to spawn sessions")
        sys.exit(1)

    # Load PRD
    try:
        with open(args.prd_file) as f:
            prd_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading PRD file: {e}")
        sys.exit(1)

    # Convert to PRDDocument
    tasks = []
    for task_data in prd_data.get('tasks', []):
        task = PRDTask(
            id=task_data['id'],
            description=task_data.get('description', ''),
            dependencies=task_data.get('dependencies', []),
            metadata=task_data.get('metadata'),
        )
        tasks.append(task)

    prd = PRDDocument(
        id=prd_data.get('id', 'prd-001'),
        title=prd_data.get('title', 'Untitled PRD'),
        tasks=tasks,
    )

    # Create executor and spawn
    config = PRDConfig(enabled=True)
    executor = PRDExecutor(config, working_dir)

    force_tasks = [args.force] if args.force else None

    result = executor.spawn(
        prd=prd,
        explain=args.explain,
        dry_run=args.dry_run,
        force_tasks=force_tasks,
    )

    # Display results
    if args.explain and result.explanation:
        print(result.explanation)
        return

    if args.dry_run:
        print(f"[DRY RUN] Would spawn {result.spawned_count} task(s) in wave {result.wave_number}")
        if result.task_ids:
            print(f"Tasks: {', '.join(result.task_ids)}")
        return

    if result.error:
        print(f"Error: {result.error}")
        if result.explanation:
            print(result.explanation)
        sys.exit(1)

    if result.spawned_count == 0:
        print(result.explanation or "No tasks to spawn")
        return

    print(f"Spawned {result.spawned_count} task(s) in wave {result.wave_number}")
    for task_id, session_id in zip(result.task_ids, result.session_ids):
        print(f"  {task_id}: {session_id}")


def cmd_prd_merge(args):
    """Merge a completed task into the integration branch."""
    import yaml
    from src.prd import PRDExecutor, PRDConfig, PRDDocument, PRDTask, TaskStatus

    working_dir = Path(args.dir or '.')

    if not args.prd_file:
        print("Error: --prd-file required")
        sys.exit(1)

    # Load PRD
    try:
        with open(args.prd_file) as f:
            prd_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading PRD file: {e}")
        sys.exit(1)

    # Convert to PRDDocument
    tasks = []
    for task_data in prd_data.get('tasks', []):
        task = PRDTask(
            id=task_data['id'],
            description=task_data.get('description', ''),
            dependencies=task_data.get('dependencies', []),
            metadata=task_data.get('metadata'),
        )
        # Mark tasks as running if they have sessions (simplified - real impl would load state)
        if task_data.get('status') == 'running':
            task.status = TaskStatus.RUNNING
            task.branch = task_data.get('branch', f"claude/{task.id}")
            task.agent_id = task_data.get('session_id')
        tasks.append(task)

    prd = PRDDocument(
        id=prd_data.get('id', 'prd-001'),
        title=prd_data.get('title', 'Untitled PRD'),
        tasks=tasks,
    )

    # Create executor and merge
    config = PRDConfig(enabled=True)
    executor = PRDExecutor(config, working_dir)

    result = executor.merge(
        prd=prd,
        task_id=args.task_id,
        dry_run=args.dry_run,
    )

    # Display results
    if args.dry_run:
        print(f"[DRY RUN] {result.explanation}")
        return

    if not result.success:
        print(f"Merge failed: {result.error}")
        sys.exit(1)

    print(f"Merged task {result.task_id}")
    print(f"  Branch: {result.branch}")
    if result.commit_sha:
        print(f"  Commit: {result.commit_sha}")
    if result.conflicts_resolved > 0:
        print(f"  Conflicts auto-resolved: {result.conflicts_resolved}")


def cmd_prd_sync(args):
    """Sync: merge completed tasks and spawn the next wave."""
    import yaml
    from src.prd import PRDExecutor, PRDConfig, PRDDocument, PRDTask

    working_dir = Path(args.dir or '.')

    if not args.prd_file:
        print("Error: --prd-file required")
        sys.exit(1)

    # Load PRD
    try:
        with open(args.prd_file) as f:
            prd_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading PRD file: {e}")
        sys.exit(1)

    # Convert to PRDDocument
    tasks = []
    for task_data in prd_data.get('tasks', []):
        task = PRDTask(
            id=task_data['id'],
            description=task_data.get('description', ''),
            dependencies=task_data.get('dependencies', []),
            metadata=task_data.get('metadata'),
        )
        tasks.append(task)

    prd = PRDDocument(
        id=prd_data.get('id', 'prd-001'),
        title=prd_data.get('title', 'Untitled PRD'),
        tasks=tasks,
    )

    # Create executor and sync
    config = PRDConfig(enabled=True)
    executor = PRDExecutor(config, working_dir)

    result = executor.sync(
        prd=prd,
        dry_run=args.dry_run,
    )

    # Display results
    if args.dry_run:
        print(f"[DRY RUN] Would merge {result.merged_count} task(s), spawn {result.spawned_count} task(s)")
        return

    print(f"Merged: {result.merged_count} task(s)")
    print(f"Spawned: {result.spawned_count} task(s)")

    if result.spawn_result and result.spawn_result.task_ids:
        print(f"New sessions: {', '.join(result.spawn_result.task_ids)}")


def cmd_prd_sessions(args):
    """List active Claude Squad sessions."""
    from src.prd.squad_adapter import ClaudeSquadAdapter, CapabilityError
    from datetime import datetime, timezone

    working_dir = Path(args.dir or '.')

    try:
        adapter = ClaudeSquadAdapter(working_dir)
    except CapabilityError as e:
        print(f"Error: {e}")
        sys.exit(1)

    sessions = adapter.list_sessions()

    if not sessions:
        print("No active sessions")
        return

    print(f"{'TASK':<20} {'SESSION':<25} {'STATUS':<12} {'AGE':<10}")
    print("-" * 70)

    now = datetime.now(timezone.utc)
    for s in sessions:
        created = datetime.fromisoformat(s.created_at)
        age_seconds = (now - created).total_seconds()
        if age_seconds < 60:
            age = f"{int(age_seconds)}s"
        elif age_seconds < 3600:
            age = f"{int(age_seconds // 60)}m"
        else:
            age = f"{int(age_seconds // 3600)}h"

        print(f"{s.task_id:<20} {s.session_name:<25} {s.status:<12} {age:<10}")


def cmd_prd_attach(args):
    """Attach to a Claude Squad session."""
    from src.prd.squad_adapter import ClaudeSquadAdapter, CapabilityError, SessionError

    working_dir = Path(args.dir or '.')

    try:
        adapter = ClaudeSquadAdapter(working_dir)
        adapter.attach(args.task_id)
    except CapabilityError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except SessionError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_prd_done(args):
    """Mark a Claude Squad task as complete."""
    from src.prd.squad_adapter import ClaudeSquadAdapter, CapabilityError, SessionError

    working_dir = Path(args.dir or '.')

    try:
        adapter = ClaudeSquadAdapter(working_dir)
        adapter.mark_complete(args.task_id, terminate_session=not args.keep_session)
        print(f"Task {args.task_id} marked complete")
        if not args.keep_session:
            print("Session terminated")
    except CapabilityError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except SessionError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_prd_cleanup(args):
    """Clean up orphaned Claude Squad sessions."""
    from src.prd.squad_adapter import ClaudeSquadAdapter, CapabilityError

    working_dir = Path(args.dir or '.')

    try:
        adapter = ClaudeSquadAdapter(working_dir)

        # Clean orphaned sessions
        cleaned = adapter.cleanup_orphaned()
        print(f"Cleaned {cleaned} orphaned session(s)")

        # Optionally clean old records
        if args.days:
            removed = adapter.registry.cleanup_old(days=args.days)
            print(f"Removed {removed} old record(s) (>{args.days} days)")

    except CapabilityError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_prd_start(args):
    """Start PRD execution from a PRD file."""
    import asyncio
    import yaml
    import json
    from src.prd import PRDExecutor, PRDConfig, PRDDocument, PRDTask, WorkerBackend
    from src.prd._deprecated.sequential import is_inside_claude_code

    working_dir = Path(args.dir or '.')
    prd_path = Path(args.prd_file)

    if not prd_path.exists():
        print(f"Error: PRD file not found: {prd_path}")
        sys.exit(1)

    # Load PRD YAML
    try:
        with open(prd_path) as f:
            prd_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error: Failed to parse PRD file: {e}")
        sys.exit(1)

    # Create PRD document from YAML
    try:
        tasks = []
        for task_data in prd_data.get('tasks', []):
            tasks.append(PRDTask(
                id=task_data['id'],
                description=task_data['description'],
                dependencies=task_data.get('dependencies', []),
            ))

        prd = PRDDocument(
            id=prd_data.get('id', f"prd-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
            title=prd_data.get('title', 'Untitled PRD'),
            tasks=tasks,
        )
    except KeyError as e:
        print(f"Error: Invalid PRD format - missing required field: {e}")
        sys.exit(1)

    # Map backend argument to enum
    backend_map = {
        'auto': WorkerBackend.AUTO,
        'local': WorkerBackend.LOCAL,
        'modal': WorkerBackend.MODAL,
        'render': WorkerBackend.RENDER,
        'github': WorkerBackend.GITHUB_ACTIONS,
        'manual': WorkerBackend.MANUAL,
    }

    # Create config
    config = PRDConfig(
        enabled=True,
        worker_backend=backend_map.get(args.backend, WorkerBackend.AUTO),
        max_concurrent_agents=args.max_agents,
        checkpoint_interval=args.checkpoint_interval,
    )

    # Check for sequential mode (inside Claude Code)
    if is_inside_claude_code():
        print("=" * 60)
        print("SEQUENTIAL MODE (Inside Claude Code)")
        print("=" * 60)
        print(f"PRD: {prd.title}")
        print(f"PRD ID: {prd.id}")
        print(f"Tasks: {len(prd.tasks)}")
        print()
        print("Tasks will be yielded one at a time for this session to execute.")
        print()

        # Save PRD state for sequential execution
        state_file = working_dir / ".claude" / "prd_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # Get first ready task
        ready_tasks = prd.get_ready_tasks()
        if not ready_tasks:
            print("No tasks are ready to execute.")
            sys.exit(0)

        first_task = ready_tasks[0]

        # Save state
        state = {
            "prd_id": prd.id,
            "prd_title": prd.title,
            "prd_file": str(prd_path.absolute()),
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "dependencies": t.dependencies,
                    "status": t.status.value,
                }
                for t in prd.tasks
            ],
            "current_task": first_task.id,
            "completed_tasks": [],
            "checkpoint_interval": args.checkpoint_interval,
        }
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

        # Print first task
        print("=" * 60)
        print(f"TASK: {first_task.id}")
        print("=" * 60)
        print()
        print(first_task.description)
        print()
        print("-" * 60)
        print("When this task is complete, run:")
        print(f"  orchestrator prd task-done {first_task.id}")
        print("-" * 60)

        sys.exit(0)

    # Standard async execution mode
    print(f"Starting PRD execution: {prd.title}")
    print(f"  PRD ID: {prd.id}")
    print(f"  Tasks: {len(prd.tasks)}")
    print(f"  Backend: {config.worker_backend.value}")
    print(f"  Max agents: {config.max_concurrent_agents}")
    print()

    # Create executor with callbacks
    def on_task_complete(task, result):
        status = "✓" if result.success else "✗"
        print(f"  {status} Task {task.id} completed")

    def on_checkpoint(checkpoint):
        print(f"  Checkpoint PR created: {checkpoint.pr_url}")

    executor = PRDExecutor(
        config=config,
        working_dir=working_dir,
        on_task_complete=on_task_complete,
        on_checkpoint=on_checkpoint,
    )

    # Run execution
    try:
        result = asyncio.run(executor.execute_prd(prd))
    except KeyboardInterrupt:
        print("\nExecution interrupted")
        executor.cancel()
        sys.exit(1)

    # Print results
    print()
    print("=" * 60)
    print("PRD EXECUTION COMPLETE")
    print("=" * 60)
    print(f"  Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Tasks completed: {result.tasks_completed}")
    print(f"  Tasks failed: {result.tasks_failed}")
    print(f"  Duration: {result.duration_seconds:.1f}s")

    if result.checkpoint_prs:
        print(f"  Checkpoint PRs: {len(result.checkpoint_prs)}")
        for cp in result.checkpoint_prs:
            print(f"    - {cp.pr_url}")

    if result.final_pr_url:
        print(f"  Final PR: {result.final_pr_url}")

    if result.error:
        print(f"  Error: {result.error}")

    sys.exit(0 if result.success else 1)


def cmd_prd_status(args):
    """Show PRD execution status."""
    from src.prd import PRDExecutor, PRDConfig

    working_dir = Path(args.dir or '.')

    # Create a minimal executor to check status
    config = PRDConfig(enabled=True)
    executor = PRDExecutor(config=config, working_dir=working_dir)

    status = executor.get_status()

    if status.get('status') == 'idle':
        print("No PRD execution in progress")
        sys.exit(0)

    print("PRD Execution Status")
    print("=" * 40)
    print(f"  PRD ID: {status.get('prd_id', 'N/A')}")
    print(f"  Status: {status.get('status', 'unknown')}")

    if progress := status.get('progress'):
        print(f"  Progress: {progress}")

    if queue := status.get('queue'):
        print(f"  Queue: {queue}")

    if workers := status.get('workers'):
        print(f"  Workers: {workers}")


def cmd_prd_cancel(args):
    """Cancel PRD execution."""
    from src.prd import PRDExecutor, PRDConfig

    working_dir = Path(args.dir or '.')

    config = PRDConfig(enabled=True)
    executor = PRDExecutor(config=config, working_dir=working_dir)

    if executor.cancel():
        print("✓ PRD execution cancelled")
    else:
        print("No PRD execution to cancel")


def cmd_prd_validate(args):
    """Validate a PRD file without executing."""
    import yaml
    from src.prd import PRDTask

    prd_path = Path(args.prd_file)

    if not prd_path.exists():
        print(f"Error: PRD file not found: {prd_path}")
        sys.exit(1)

    try:
        with open(prd_path) as f:
            prd_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error: Failed to parse YAML: {e}")
        sys.exit(1)

    errors = []
    warnings = []

    # Check required fields
    if 'id' not in prd_data:
        warnings.append("Missing 'id' field - will be auto-generated")

    if 'title' not in prd_data:
        warnings.append("Missing 'title' field")

    if 'tasks' not in prd_data:
        errors.append("Missing 'tasks' field - PRD must have at least one task")
    elif not isinstance(prd_data['tasks'], list):
        errors.append("'tasks' must be a list")
    elif len(prd_data['tasks']) == 0:
        errors.append("PRD must have at least one task")
    else:
        # Validate tasks
        task_ids = set()
        for i, task in enumerate(prd_data['tasks']):
            if not isinstance(task, dict):
                errors.append(f"Task {i}: must be a dictionary")
                continue

            if 'id' not in task:
                errors.append(f"Task {i}: missing 'id' field")
            else:
                if task['id'] in task_ids:
                    errors.append(f"Task {i}: duplicate task ID '{task['id']}'")
                task_ids.add(task['id'])

            if 'description' not in task:
                errors.append(f"Task {i}: missing 'description' field")

            # Check dependencies exist
            for dep in task.get('dependencies', []):
                if dep not in task_ids:
                    # Dep might be defined later
                    pass

        # Second pass: verify all dependencies exist
        for task in prd_data['tasks']:
            for dep in task.get('dependencies', []):
                if dep not in task_ids:
                    errors.append(f"Task '{task.get('id', '?')}': dependency '{dep}' not found")

    # Print results
    if errors:
        print("✗ PRD validation FAILED")
        print()
        for error in errors:
            print(f"  ERROR: {error}")
    else:
        print("✓ PRD validation passed")

    if warnings:
        print()
        for warning in warnings:
            print(f"  WARNING: {warning}")

    if not errors:
        print()
        print(f"  Tasks: {len(prd_data.get('tasks', []))}")

        # Show task summary
        for task in prd_data.get('tasks', []):
            deps = task.get('dependencies', [])
            dep_str = f" (deps: {', '.join(deps)})" if deps else ""
            print(f"    - {task.get('id', '?')}: {task.get('description', 'No description')[:50]}{dep_str}")

    sys.exit(1 if errors else 0)


def cmd_prd_task_done(args):
    """Mark a task as complete in sequential mode."""
    import json
    from src.prd import TaskStatus

    working_dir = Path(args.dir or '.')
    state_file = working_dir / ".claude" / "prd_state.json"

    if not state_file.exists():
        print("Error: No PRD execution in progress.")
        print("Start a PRD with: orchestrator prd start <prd_file>")
        sys.exit(1)

    # Load state
    with open(state_file) as f:
        state = json.load(f)

    task_id = args.task_id

    # Find the task
    task_found = False
    for task in state["tasks"]:
        if task["id"] == task_id:
            task_found = True
            if task["status"] == "completed":
                print(f"Task {task_id} is already completed.")
            else:
                task["status"] = "completed"
                state["completed_tasks"].append(task_id)
                print(f"Task {task_id} marked as complete.")
            break

    if not task_found:
        print(f"Error: Task '{task_id}' not found in PRD.")
        sys.exit(1)

    # Find next ready task
    def get_ready_tasks():
        """Get tasks that are pending and have all dependencies satisfied."""
        completed = set(state["completed_tasks"])
        ready = []
        for task in state["tasks"]:
            if task["status"] != "pending":
                continue
            deps = set(task.get("dependencies", []))
            if deps <= completed:
                ready.append(task)
        return ready

    ready_tasks = get_ready_tasks()

    # Save updated state
    if ready_tasks:
        state["current_task"] = ready_tasks[0]["id"]
    else:
        state["current_task"] = None

    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

    # Show progress
    completed_count = len(state["completed_tasks"])
    total_count = len(state["tasks"])
    print()
    print(f"Progress: {completed_count}/{total_count} tasks complete")
    print()

    if not ready_tasks:
        # Check if all done
        all_complete = all(t["status"] == "completed" for t in state["tasks"])
        if all_complete:
            print("=" * 60)
            print("PRD EXECUTION COMPLETE")
            print("=" * 60)
            print(f"All {total_count} tasks completed successfully.")
            # Clean up state file
            state_file.unlink()
        else:
            # Some tasks blocked
            pending = [t for t in state["tasks"] if t["status"] == "pending"]
            print("No more tasks are ready to execute.")
            if pending:
                print(f"Blocked tasks: {[t['id'] for t in pending]}")
    else:
        next_task = ready_tasks[0]
        print("=" * 60)
        print(f"NEXT TASK: {next_task['id']}")
        print("=" * 60)
        print()
        print(next_task['description'])
        print()
        print("-" * 60)
        print("When this task is complete, run:")
        print(f"  orchestrator prd task-done {next_task['id']}")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="AI Workflow Orchestrator - Enforce multi-phase workflows with active verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  orchestrator start "Add user authentication feature"
  orchestrator status
  orchestrator complete initial_plan --notes "Created plan document"
  orchestrator skip risk_analysis --reason "Simple bug fix with minimal risk"
  orchestrator approve-item user_approval --notes "Looks good"
  orchestrator advance
  orchestrator finish
  orchestrator analyze
  orchestrator learn
  orchestrator validate
        """
    )
    
    parser.add_argument('--dir', '-d', default='.', help='Working directory (default: current)')
    parser.add_argument('--version', '-v', action='version', version=f'%(prog)s {VERSION}')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start a new workflow')
    start_parser.add_argument('task', help='Task description')
    start_parser.add_argument('--workflow', '-w', default='workflow.yaml', help='Workflow YAML file')
    start_parser.add_argument('--project', '-p', help='Project name')
    start_parser.add_argument('--constraints', '-c', action='append', default=[],
                              help='Task constraint (can be specified multiple times)')
    start_parser.add_argument('--no-archive', action='store_true',
                              help='Skip archiving existing workflow documents')
    start_parser.set_defaults(func=cmd_start)

    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize workflow.yaml in current directory')
    init_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing workflow.yaml without prompting')
    init_parser.set_defaults(func=cmd_init)

    # Status command
    status_parser = subparsers.add_parser('status', help='Show current workflow status')
    status_parser.add_argument('--json', action='store_true', help='Output as JSON (WF-015)')
    status_parser.set_defaults(func=cmd_status)

    # Context reminder command (WF-012)
    context_reminder_parser = subparsers.add_parser('context-reminder',
        help='Output compact workflow state for context injection after compaction')
    context_reminder_parser.set_defaults(func=cmd_context_reminder)

    # Verify write allowed command (WF-013)
    verify_write_parser = subparsers.add_parser('verify-write-allowed',
        help='Check if writing implementation code is allowed in current phase')
    verify_write_parser.set_defaults(func=cmd_verify_write_allowed)

    # Resolve command (CORE-023)
    resolve_parser = subparsers.add_parser('resolve', help='Resolve git merge/rebase conflicts')
    resolve_parser.add_argument('--apply', action='store_true',
                                help='Apply resolutions (default is preview mode)')
    resolve_parser.add_argument('--strategy', '-s', choices=['auto', 'ours', 'theirs'],
                                help='Resolution strategy (default: auto)')
    resolve_parser.add_argument('--commit', action='store_true',
                                help='Auto-commit after resolving all conflicts')
    resolve_parser.add_argument('--abort', action='store_true',
                                help='Abort the current merge or rebase')
    resolve_parser.set_defaults(func=cmd_resolve)

    # Complete command
    complete_parser = subparsers.add_parser('complete', help='Mark an item as complete')
    complete_parser.add_argument('item', help='Item ID to complete')
    complete_parser.add_argument('--notes', '-n', help='Notes about the completion')
    complete_parser.add_argument('--skip-verify', action='store_true', help='Skip verification')
    complete_parser.add_argument('--skip-auto-review', action='store_true',
                                 help='Skip auto-running third-party review (not recommended)')
    complete_parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')
    complete_parser.add_argument('--dir', '-d', help='Working directory')
    complete_parser.set_defaults(func=cmd_complete)
    
    # Skip command
    skip_parser = subparsers.add_parser('skip', help='Skip an item with a reason')
    skip_parser.add_argument('item', help='Item ID to skip')
    skip_parser.add_argument('--reason', '-r', required=True, help='Reason for skipping (min 10 chars)')
    skip_parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')
    skip_parser.set_defaults(func=cmd_skip)
    
    # Approve-item command (NEW)
    approve_item_parser = subparsers.add_parser('approve-item', help='Approve a manual gate item')
    approve_item_parser.add_argument('item', help='Item ID to approve')
    approve_item_parser.add_argument('--notes', '-n', help='Notes about the approval')
    approve_item_parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')
    approve_item_parser.set_defaults(func=cmd_approve_item)
    
    # Advance command
    advance_parser = subparsers.add_parser('advance', help='Advance to the next phase')
    advance_parser.add_argument('--force', '-f', action='store_true', help='Force advance even with blockers')
    advance_parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')
    advance_parser.add_argument('--yes', '-y', action='store_true', help='Skip summary/critique prompts (WF-005, WF-008)')
    advance_parser.add_argument('--no-critique', action='store_true', help='Skip AI critique at phase gate (WF-008)')
    advance_parser.set_defaults(func=cmd_advance)
    
    # Approve command (for phase gates)
    approve_parser = subparsers.add_parser('approve', help='Approve a phase gate')
    approve_parser.add_argument('--phase', '-p', help='Phase ID (default: current)')
    approve_parser.set_defaults(func=cmd_approve)
    
    # Finish command
    finish_parser = subparsers.add_parser('finish', help='Complete or abandon the workflow')
    finish_parser.add_argument('--abandon', action='store_true', help='Abandon instead of complete')
    finish_parser.add_argument('--reason', '-r', help='Reason for abandoning (or for skipping review check)')
    finish_parser.add_argument('--notes', '-n', help='Completion notes')
    finish_parser.add_argument('--skip-learn', action='store_true', help='Skip learning report')
    finish_parser.add_argument('--skip-review-check', action='store_true', dest='skip_review_check',
                              help='Skip the external review validation (requires --reason)')
    finish_parser.set_defaults(func=cmd_finish)
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze workflow history')
    analyze_parser.add_argument('--json', action='store_true', help='Output as JSON')
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # Learn command
    learn_parser = subparsers.add_parser('learn', help='Generate a learning report')
    learn_parser.add_argument('--no-save', action='store_true', help='Do not save to LEARNINGS.md')
    learn_parser.set_defaults(func=cmd_learn)
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser('dashboard', help='Start the visual dashboard')
    dashboard_parser.add_argument('--port', '-p', type=int, default=8080, help='Port number')
    dashboard_parser.add_argument('--static', action='store_true', help='Generate static HTML instead')
    dashboard_parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    dashboard_parser.set_defaults(func=cmd_dashboard)
    
    # Validate command (NEW)
    validate_parser = subparsers.add_parser('validate', help='Validate a workflow YAML file')
    validate_parser.add_argument('--workflow', '-w', default='workflow.yaml', help='Workflow YAML file')
    validate_parser.set_defaults(func=cmd_validate)
    
    # Handoff command
    handoff_parser = subparsers.add_parser('handoff', help='Generate or execute a handoff to an agent provider')
    handoff_parser.add_argument('--execute', '-x', action='store_true', help='Execute with the provider directly')
    handoff_parser.add_argument('--provider', '-p', choices=['openrouter', 'claude_code', 'manual'],
                                help='Provider to use (default: auto-detect)')
    handoff_parser.add_argument('--env', '-e', choices=['claude_code', 'manus', 'standalone'],
                                help='Override environment detection')
    handoff_parser.add_argument('--model', '-m', help='Model to use (provider-specific)')
    handoff_parser.add_argument('--files', '-f', help='Comma-separated list of relevant files')
    handoff_parser.add_argument('--constraints', '-c', help='Comma-separated list of constraints')
    handoff_parser.add_argument('--criteria', help='Comma-separated acceptance criteria')
    handoff_parser.add_argument('--timeout', '-t', type=int, default=600, help='Timeout in seconds (default: 600)')
    handoff_parser.set_defaults(func=cmd_handoff)
    
    # Generate-md command
    genmd_parser = subparsers.add_parser('generate-md', help='Generate WORKFLOW.md from current state')
    genmd_parser.set_defaults(func=cmd_generate_md)
    
    # List command (NEW)
    list_parser = subparsers.add_parser('list', help='Find all workflows in directory tree')
    list_parser.add_argument('--search-dir', '-s', default='.', help='Directory to search (default: current)')
    list_parser.add_argument('--depth', '-d', type=int, default=3, help='Max search depth (default: 3)')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--active-only', action='store_true', help='Show only active workflows')
    list_parser.set_defaults(func=cmd_list)
    
    # Visual-verify command (NEW)
    visual_verify_parser = subparsers.add_parser('visual-verify', help='Run visual verification against a URL')
    visual_verify_parser.add_argument('--url', '-u', required=True, help='URL to verify')
    visual_verify_parser.add_argument('--spec', '-s', required=True, help='Path to specification file or inline spec')
    visual_verify_parser.add_argument('--device', '-d', choices=list(DEVICE_PRESETS.keys()), help='Device preset (e.g., iphone-14, desktop)')
    visual_verify_parser.add_argument('--no-mobile', dest='mobile', action='store_false', default=True, help='Skip mobile viewport test')
    visual_verify_parser.add_argument('--style-guide', '-g', help='Path to style guide file')
    visual_verify_parser.add_argument('--show-cost', action='store_true', help='Show cost/token usage (VV-006)')
    visual_verify_parser.add_argument('--save-baseline', action='store_true', help='Save screenshots as baselines (VV-004)')
    visual_verify_parser.set_defaults(func=cmd_visual_verify)

    # Visual-verify-all command (VV-003)
    visual_verify_all_parser = subparsers.add_parser('visual-verify-all', help='Run all visual tests in tests/visual/')
    visual_verify_all_parser.add_argument('--tests-dir', '-t', default='tests/visual', help='Directory containing test files')
    visual_verify_all_parser.add_argument('--app-url', '-a', help='Base URL to prepend to relative URLs')
    visual_verify_all_parser.add_argument('--tag', action='append', help='Filter tests by tag (can repeat)')
    visual_verify_all_parser.add_argument('--save-baselines', action='store_true', help='Save screenshots as baselines')
    visual_verify_all_parser.add_argument('--show-cost', action='store_true', help='Show cost summary')
    visual_verify_all_parser.set_defaults(func=cmd_visual_verify_all)

    # Visual-template command (NEW)
    visual_template_parser = subparsers.add_parser('visual-template', help='Generate a visual test template')
    visual_template_parser.add_argument('feature_name', help='Name of the feature to test')
    visual_template_parser.set_defaults(func=cmd_visual_template)
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up abandoned workflows')
    cleanup_parser.add_argument('--search-dir', '-s', default='.', help='Directory to search (default: current)')
    cleanup_parser.add_argument('--max-age', '-a', type=int, default=7, help='Max age in days for active workflows (default: 7)')
    cleanup_parser.add_argument('--depth', '-d', type=int, default=3, help='Max search depth (default: 3)')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='Show what would be cleaned without doing it')
    cleanup_parser.set_defaults(func=cmd_cleanup)
    
    # Checkpoint command (Feature 5)
    checkpoint_parser = subparsers.add_parser('checkpoint', help='Create a checkpoint for session recovery')
    checkpoint_parser.add_argument('--message', '-m', help='Checkpoint message/description')
    checkpoint_parser.add_argument('--decision', '-d', action='append', default=[],
                                   help='Key decision made (can be specified multiple times)')
    checkpoint_parser.add_argument('--file', '-f', action='append', default=[],
                                   help='Important file to track (can be specified multiple times)')
    checkpoint_parser.set_defaults(func=cmd_checkpoint)
    
    # Checkpoints command (list checkpoints)
    checkpoints_parser = subparsers.add_parser('checkpoints', help='List all checkpoints')
    checkpoints_parser.add_argument('--all', '-a', action='store_true', help='Show checkpoints from all workflows')
    checkpoints_parser.add_argument('--completed', action='store_true', help='Include checkpoints from completed workflows')
    checkpoints_parser.add_argument('--cleanup', action='store_true', help='Remove old checkpoints')
    checkpoints_parser.add_argument('--max-age', type=int, default=30, help='Max age in days for cleanup (default: 30)')
    checkpoints_parser.set_defaults(func=cmd_checkpoints)
    
    # Resume command (Feature 5)
    resume_parser = subparsers.add_parser('resume', help='Resume from a checkpoint')
    resume_parser.add_argument('--from', dest='from_checkpoint', help='Checkpoint ID to resume from (default: latest)')
    resume_parser.add_argument('--dry-run', action='store_true', help='Show resume prompt without executing')
    resume_parser.set_defaults(func=cmd_resume)

    # Review command (Multi-model reviews)
    review_parser = subparsers.add_parser('review', help='Run AI code reviews')
    review_parser.add_argument('review_type', nargs='?',
                               choices=['security', 'consistency', 'quality', 'holistic', 'all'],
                               default='all', help='Review type to run (default: all)')
    review_parser.add_argument('--method', '-m', choices=['auto', 'cli', 'aider', 'api'],
                               default='auto', help='Execution method (default: auto-detect)')
    review_parser.add_argument('--json', action='store_true', help='Output as JSON')
    review_parser.set_defaults(func=cmd_review)

    # Review-status command
    review_status_parser = subparsers.add_parser('review-status', help='Show review infrastructure status')
    review_status_parser.set_defaults(func=cmd_review_status)

    # Review-results command
    review_results_parser = subparsers.add_parser('review-results', help='Show results of completed reviews')
    review_results_parser.add_argument('--json', action='store_true', help='Output as JSON')
    review_results_parser.set_defaults(func=cmd_review_results)

    # Setup-reviews command
    setup_reviews_parser = subparsers.add_parser('setup-reviews', help='Set up review infrastructure in a repository')
    setup_reviews_parser.add_argument('--dry-run', action='store_true', help='Show what would be created without writing')
    setup_reviews_parser.add_argument('--skip-actions', action='store_true', help='Skip GitHub Actions workflow creation')
    setup_reviews_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing files')
    setup_reviews_parser.set_defaults(func=cmd_setup_reviews)

    # Setup command (auto-updates)
    setup_parser = subparsers.add_parser('setup', help='Enable automatic updates for this repo')
    setup_parser.add_argument('--dir', '-d', help='Target directory (default: current)')
    setup_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing setup')
    setup_parser.add_argument('--remove', action='store_true', help='Remove auto-updates from this repo')
    setup_parser.add_argument('--copy-secrets', action='store_true', help='Copy encrypted secrets from orchestrator repo')
    setup_parser.set_defaults(func=cmd_setup)

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage orchestrator configuration')
    config_parser.add_argument('action', choices=['set', 'get', 'list'], help='Config action')
    config_parser.add_argument('key', nargs='?', help='Configuration key')
    config_parser.add_argument('value', nargs='?', help='Configuration value (for set)')
    config_parser.set_defaults(func=cmd_config)

    # Secrets command
    secrets_parser = subparsers.add_parser('secrets', help='Manage and test secret access')
    secrets_parser.add_argument('action', choices=['init', 'test', 'source', 'sources', 'copy'], help='Secrets action')
    secrets_parser.add_argument('name', nargs='?', help='Secret name (for test/source)')
    secrets_parser.add_argument('--password', help='Encryption password for init (otherwise prompted)')
    secrets_parser.add_argument('--from-env', action='store_true', help='Read API keys from environment instead of prompting')
    secrets_parser.add_argument('--from', dest='from_dir', help='Source directory for copy action')
    secrets_parser.add_argument('--to', dest='to_dir', help='Destination directory for copy action')
    secrets_parser.add_argument('--force', action='store_true', help='Overwrite existing secrets file')
    secrets_parser.set_defaults(func=cmd_secrets)

    # Update-models command (CORE-017)
    update_models_parser = subparsers.add_parser('update-models', help='Update model registry from OpenRouter API')
    update_models_parser.add_argument('--force', action='store_true', help='Update even if not stale')
    update_models_parser.add_argument('--check', action='store_true', help='Only check if registry is stale')
    update_models_parser.set_defaults(func=cmd_update_models)

    # PRD command (Phase 6)
    prd_parser = subparsers.add_parser('prd', help='Execute PRD mode with multiple concurrent agents')
    prd_subparsers = prd_parser.add_subparsers(dest='prd_command', help='PRD subcommands')

    # prd start
    prd_start = prd_subparsers.add_parser('start', help='Start PRD execution from a PRD file')
    prd_start.add_argument('prd_file', help='Path to PRD YAML file')
    prd_start.add_argument('--backend', choices=['auto', 'local', 'modal', 'render', 'github', 'manual'],
                          default='auto', help='Worker backend (default: auto)')
    prd_start.add_argument('--max-agents', type=int, default=20, help='Maximum concurrent agents (default: 20)')
    prd_start.add_argument('--checkpoint-interval', type=int, default=5,
                          help='Create checkpoint PR every N tasks (default: 5)')
    prd_start.add_argument('-d', '--dir', help='Working directory')
    prd_start.set_defaults(func=cmd_prd_start)

    # prd status
    prd_status = prd_subparsers.add_parser('status', help='Show PRD execution status')
    prd_status.add_argument('-d', '--dir', help='Working directory')
    prd_status.set_defaults(func=cmd_prd_status)

    # prd cancel
    prd_cancel = prd_subparsers.add_parser('cancel', help='Cancel PRD execution')
    prd_cancel.add_argument('-d', '--dir', help='Working directory')
    prd_cancel.set_defaults(func=cmd_prd_cancel)

    # prd validate
    prd_validate = prd_subparsers.add_parser('validate', help='Validate a PRD file without executing')
    prd_validate.add_argument('prd_file', help='Path to PRD YAML file')
    prd_validate.set_defaults(func=cmd_prd_validate)

    # prd task-done (for sequential mode)
    prd_task_done = prd_subparsers.add_parser('task-done', help='Mark a task as complete (sequential mode)')
    prd_task_done.add_argument('task_id', help='ID of the completed task')
    prd_task_done.add_argument('-d', '--dir', help='Working directory')
    prd_task_done.set_defaults(func=cmd_prd_task_done)

    # Claude Squad Integration Commands (PRD-001)
    # prd check-squad
    prd_check_squad = prd_subparsers.add_parser('check-squad', help='Check Claude Squad compatibility')
    prd_check_squad.set_defaults(func=cmd_prd_check_squad)

    # prd spawn
    prd_spawn = prd_subparsers.add_parser('spawn', help='Spawn next wave of tasks via Claude Squad')
    prd_spawn.add_argument('--prd-file', required=True, help='Path to PRD YAML file')
    prd_spawn.add_argument('--explain', action='store_true', help='Show wave groupings without spawning')
    prd_spawn.add_argument('--dry-run', action='store_true', help='Show what would be spawned without acting')
    prd_spawn.add_argument('--force', metavar='TASK_ID', help='Force spawn specific task (bypasses scheduler)')
    prd_spawn.add_argument('-d', '--dir', help='Working directory')
    prd_spawn.set_defaults(func=cmd_prd_spawn)

    # prd merge
    prd_merge = prd_subparsers.add_parser('merge', help='Merge a completed task into integration branch')
    prd_merge.add_argument('task_id', help='Task ID to merge')
    prd_merge.add_argument('--prd-file', required=True, help='Path to PRD YAML file')
    prd_merge.add_argument('--dry-run', action='store_true', help='Show what would be merged without acting')
    prd_merge.add_argument('-d', '--dir', help='Working directory')
    prd_merge.set_defaults(func=cmd_prd_merge)

    # prd sync
    prd_sync = prd_subparsers.add_parser('sync', help='Merge completed tasks and spawn next wave')
    prd_sync.add_argument('--prd-file', required=True, help='Path to PRD YAML file')
    prd_sync.add_argument('--dry-run', action='store_true', help='Show what would happen without acting')
    prd_sync.add_argument('-d', '--dir', help='Working directory')
    prd_sync.set_defaults(func=cmd_prd_sync)

    # prd sessions
    prd_sessions = prd_subparsers.add_parser('sessions', help='List active Claude Squad sessions')
    prd_sessions.add_argument('-d', '--dir', help='Working directory')
    prd_sessions.set_defaults(func=cmd_prd_sessions)

    # prd attach
    prd_attach = prd_subparsers.add_parser('attach', help='Attach to a Claude Squad session')
    prd_attach.add_argument('task_id', help='Task ID to attach to')
    prd_attach.add_argument('-d', '--dir', help='Working directory')
    prd_attach.set_defaults(func=cmd_prd_attach)

    # prd done
    prd_done = prd_subparsers.add_parser('done', help='Mark a Claude Squad task as complete')
    prd_done.add_argument('task_id', help='Task ID to mark complete')
    prd_done.add_argument('--keep-session', action='store_true', help='Keep the session running')
    prd_done.add_argument('-d', '--dir', help='Working directory')
    prd_done.set_defaults(func=cmd_prd_done)

    # prd cleanup
    prd_cleanup = prd_subparsers.add_parser('cleanup', help='Clean up orphaned Claude Squad sessions')
    prd_cleanup.add_argument('--days', type=int, help='Also remove records older than N days')
    prd_cleanup.add_argument('-d', '--dir', help='Working directory')
    prd_cleanup.set_defaults(func=cmd_prd_cleanup)

    prd_parser.set_defaults(func=lambda args: prd_parser.print_help() if not args.prd_command else None)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
