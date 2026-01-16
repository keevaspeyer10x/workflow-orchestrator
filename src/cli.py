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
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.engine import WorkflowEngine
from src.mode_detection import detect_operator_mode, is_llm_mode, log_mode_detection
from src.analytics import WorkflowAnalytics
from src.learning_engine import LearningEngine
from src.dashboard import start_dashboard, generate_static_dashboard
from src.schema import WorkflowDef, WorkflowEvent, EventType, ItemStatus
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
from src.review.registry import get_review_item_mapping, get_all_review_types
from src.config import (
    find_workflow_path,
    get_default_workflow_content,
    is_using_bundled_workflow,
    detect_project_type,
    get_project_commands,
    load_settings_overrides,
)
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
from src.sync_manager import SyncManager, SyncResult
from src.resolution.llm_resolver import (
    LLMResolver,
    LLMResolutionResult,
    ConfidenceLevel,
)
from src.adherence_validator import (
    AdherenceValidator,
    format_adherence_report,
    find_session_log_for_workflow,
)
from src.path_resolver import OrchestratorPaths
from src.session_manager import SessionManager
from src.task_provider import (
    get_task_provider,
    TaskTemplate,
    TaskPriority,
    TaskStatus,
)

# Natural language command support (Issue #60)
NL_AVAILABLE = False
try:
    from src.nl_commands import register_nl_commands
    from ai_tool_bridge.argparse_adapter import add_nl_subcommand
    NL_AVAILABLE = True
except ImportError:
    pass  # ai-tool-bridge not installed

VERSION = "3.0.0"


# ============================================================================
# Non-Interactive Mode Detection (Issue #61)
# ============================================================================
def is_interactive() -> bool:
    """Check if running in an interactive terminal.

    Returns False if:
    - stdin is not a TTY (e.g., piped input, Claude Code subprocess)
    - stdout is not a TTY (e.g., output redirected)
    - CI environment variable is set
    - GITHUB_ACTIONS environment variable is set
    """
    if not sys.stdin.isatty():
        return False
    if not sys.stdout.isatty():
        return False
    if os.environ.get('CI'):
        return False
    if os.environ.get('GITHUB_ACTIONS'):
        return False
    return True


# ============================================================================
# LLM Mode Detection (V3)
# ============================================================================
# Core logic moved to src.mode_detection (Phase 0)



def confirm(prompt: str, yes_flag: bool = False) -> bool:
    """Prompt user for confirmation with non-interactive fail-fast.

    Args:
        prompt: The question to ask (should include [y/N] hint)
        yes_flag: If True, skip prompt and return True (--yes flag)

    Returns:
        True if confirmed, False otherwise

    Raises:
        SystemExit: If non-interactive mode and yes_flag is False
    """
    if yes_flag:
        return True
    if not is_interactive():
        # Extract the question part for the error message
        question = prompt.split('[')[0].strip() if '[' in prompt else prompt.rstrip(': ')
        print(f"ERROR: {question} - Cannot prompt in non-interactive mode.")
        print("Use --yes flag to auto-confirm, or run interactively.")
        sys.exit(1)
    response = input(prompt)
    return response.lower() in ['y', 'yes']


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


def check_project_mismatch(working_dir: Path, current_test_command: str) -> Optional[str]:
    """
    Check if detected project type doesn't match the test command.

    Args:
        working_dir: Project directory to check
        current_test_command: The test command that would be used

    Returns:
        Warning message if mismatch detected, None otherwise.
    """
    project_type = detect_project_type(working_dir)
    if not project_type:
        return None  # Can't detect, no warning

    commands = get_project_commands(working_dir)
    recommended_test = commands.get("test_command")

    if not recommended_test:
        return None

    # Check if current command matches recommended
    # Simple heuristic: check if the key tool matches
    current_lower = current_test_command.lower()
    recommended_lower = recommended_test.lower()

    # Extract the main command (first word)
    current_tool = current_lower.split()[0] if current_lower else ""
    recommended_tool = recommended_lower.split()[0] if recommended_lower else ""

    # Check for mismatch
    if current_tool != recommended_tool:
        return (
            f"Project type mismatch detected!\n"
            f"    Detected: {project_type} project\n"
            f"    Default test command: {current_test_command}\n"
            f"    Recommended: {recommended_test}\n"
            f"\n"
            f"    Auto-correcting test_command to '{recommended_test}'\n"
            f"    (Use --test-command to override, or create .orchestrator.yaml)"
        )

    return None


def check_review_api_keys() -> Optional[str]:
    """
    Check if API keys required for external model reviews are set.

    Only warns if NO keys are available (at least one key = reviews can work).
    Treats empty strings as missing.

    Returns:
        Warning message if NO keys are set, None if at least one key present.
    """
    review_keys = {
        "GEMINI_API_KEY": "Google Gemini",
        "OPENAI_API_KEY": "OpenAI GPT-5.2 / Codex",
        "OPENROUTER_API_KEY": "OpenRouter (fallback)",
        "XAI_API_KEY": "xAI Grok 4.1",
    }

    # Check which keys are available (non-empty)
    available = []
    missing = []
    for key, provider in review_keys.items():
        value = os.environ.get(key, "").strip()
        if value:
            available.append(provider)
        else:
            missing.append(f"  - {key}: {provider}")

    # If at least one key is available, reviews can work
    if available:
        return None

    # No keys available - warn user
    return (
        "⚠️  No external review API keys found!\n"
        "Reviews require at least one of these:\n"
        + "\n".join(missing) + "\n\n"
        "Load them with:\n"
        "  eval \"$(sops -d secrets.enc.yaml | yq -r 'to_entries | .[] | \"export \" + .key + \"=\" + .value')\"\n"
        "Or use direnv: direnv allow"
    )


def get_engine(args) -> WorkflowEngine:
    """Create an engine instance with the working directory.

    CORE-025: Uses SessionManager to get current session and passes it to engine.
    """
    working_dir = Path(getattr(args, 'dir', '.') or '.')

    # CORE-025: Check for current session
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)
    session_id = session_mgr.get_current_session()

    # Pass session_id to engine for session-aware path resolution
    engine = WorkflowEngine(str(working_dir), session_id=session_id)

    # Try to load existing state (this also loads workflow def from stored path)
    engine.load_state()

    # If no workflow def loaded yet, try default location
    if engine.state and not engine.workflow_def:
        yaml_path = working_dir / "workflow.yaml"
        if yaml_path.exists():
            engine.load_workflow_def(str(yaml_path))
        else:
            print(f"Warning: workflow.yaml not found. Some features may not work.", file=sys.stderr)

    return engine


def cmd_start(args):
    """Start a new workflow."""
    working_dir = Path(args.dir or '.')
    isolated = getattr(args, 'isolated', False)
    worktree_path = None
    original_branch = None

    # V3 Phase 5: Detect operator mode at workflow start
    from .mode_detection import detect_operator_mode
    from .audit import AuditLogger

    mode_result = detect_operator_mode()

    # CORE-025: Create new session for this workflow
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)
    session_id = session_mgr.create_session()

    # V3 Phase 5: Initialize audit logger and log workflow start
    audit_logger = AuditLogger(paths.orchestrator_dir)
    audit_logger.log_event(
        "workflow_start",
        session_id=session_id,
        task=args.task,
        operator_mode=mode_result.mode.value,
        mode_confidence=mode_result.confidence
    )

    # Create .gitignore in .orchestrator/ to ignore all session files
    gitignore_path = paths.orchestrator_dir / ".gitignore"
    if not gitignore_path.exists():
        paths.ensure_dirs()  # Create the directory first
        gitignore_path.write_text("*\n")

    # CORE-025 Phase 4: Handle --isolated flag for worktree isolation
    if isolated:
        from .worktree_manager import WorktreeManager, DirtyWorkingDirectoryError, BranchExistsError

        try:
            wt_manager = WorktreeManager(working_dir)

            # Get current branch before creating worktree
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=working_dir, capture_output=True, text=True
            )
            original_branch = result.stdout.strip()

            worktree_path = wt_manager.create(session_id)
            print(f"\n✓ Created isolated worktree at: {worktree_path}")
            print(f"  Branch: wf-{session_id}")
            print(f"  Original branch: {original_branch}")
            print(f"\n  To work in the worktree, run:")
            print(f"    cd {worktree_path}")
            print()

            # Update session metadata with worktree info
            updates = {
                'isolated': True,
                'worktree_path': str(worktree_path),
                'original_branch': original_branch,
                'worktree_branch': f"wf-{session_id}"
            }
            session_mgr.update_session_info(session_id, updates)

        except DirtyWorkingDirectoryError as e:
            print(f"Error: {e}")
            print("\nCommit or stash your changes before using --isolated")
            # Clean up the session we just created
            session_mgr.delete_session(session_id)
            sys.exit(1)
        except BranchExistsError as e:
            print(f"Error: {e}")
            # Clean up the session we just created
            session_mgr.delete_session(session_id)
            sys.exit(1)

    # Create .gitignore in .orchestrator/ to ignore all session files
    gitignore_path = paths.orchestrator_dir / ".gitignore"
    if not gitignore_path.exists():
        paths.ensure_dirs()  # Create the directory first
        gitignore_path.write_text("*\n")

    engine = WorkflowEngine(str(working_dir), session_id=session_id)

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

    # Build settings overrides from multiple sources (priority order):
    # 1. CLI flags (highest priority)
    # 2. .orchestrator.yaml file
    # 3. Auto-detected project type
    # 4. Bundled defaults (lowest priority)
    settings_overrides = {}

    # Load .orchestrator.yaml overrides
    file_overrides = load_settings_overrides(working_dir)
    if file_overrides:
        settings_overrides.update(file_overrides)
        print(f"Loaded settings from .orchestrator.yaml")

    # Auto-detect project type (only when using bundled workflow)
    using_bundled = is_using_bundled_workflow(working_dir)
    if using_bundled:
        detected_commands = get_project_commands(working_dir)
        project_type = detect_project_type(working_dir)

        # Check for mismatch between default (npm) and detected project
        if project_type and project_type != "node":
            # Show warning about auto-correction
            default_test = "npm test"  # The bundled default test command
            if detected_commands.get("test_command"):
                warning = check_project_mismatch(working_dir, default_test)
                if warning:
                    print(f"\n⚠️  {warning}\n")

        # Apply detected commands (if not already overridden by .orchestrator.yaml)
        if detected_commands.get("test_command") and "test_command" not in settings_overrides:
            settings_overrides["test_command"] = detected_commands["test_command"]
        elif not detected_commands.get("test_command") and "test_command" not in settings_overrides:
            # No project type detected - use no-op to avoid npm errors on config/docs repos
            settings_overrides["test_command"] = "true"
        if detected_commands.get("build_command") and "build_command" not in settings_overrides:
            settings_overrides["build_command"] = detected_commands["build_command"]
        elif not detected_commands.get("build_command") and "build_command" not in settings_overrides:
            # No project type detected - use no-op
            settings_overrides["build_command"] = "true"

    # Apply CLI flags (highest priority - overrides everything)
    test_command = getattr(args, 'test_command', None)
    build_command = getattr(args, 'build_command', None)

    if test_command:
        settings_overrides["test_command"] = test_command
        print(f"Using test command from --test-command: {test_command}")
    if build_command:
        settings_overrides["build_command"] = build_command
        print(f"Using build command from --build-command: {build_command}")

    # Parse constraints (Feature 4) - can be specified multiple times
    constraints = getattr(args, 'constraints', None) or []

    # Validate constraints (CORE-008)
    try:
        constraints = validate_constraints(constraints)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Check for API keys required for external model reviews
    api_key_warning = check_review_api_keys()
    if api_key_warning:
        print(f"\n{api_key_warning}\n")

    # Get no_archive flag (WF-004)
    no_archive = getattr(args, 'no_archive', False)

    try:
        state = engine.start_workflow(
            str(yaml_path),
            args.task,
            project=args.project,
            constraints=constraints,
            no_archive=no_archive,
            settings_overrides=settings_overrides
        )
        print(f"\n✓ Workflow started: {state.workflow_id}")
        print(f"  Task: {args.task}")
        print(f"  Phase: {state.current_phase_id}")
        if constraints:
            print(f"  Constraints: {len(constraints)} specified")
        if settings_overrides.get("test_command"):
            print(f"  Test command: {settings_overrides['test_command']}")
        print("\nRun 'orchestrator status' to see the checklist.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_init(args):
    """Initialize a workflow.yaml in the current directory."""
    working_dir = Path(args.dir or '.')
    workflow_path = working_dir / 'workflow.yaml'

    # Check if workflow.yaml already exists (Issue #61: fail-fast in non-interactive)
    if workflow_path.exists() and not args.force:
        print(f"workflow.yaml already exists at {workflow_path}")
        if not is_interactive():
            print("ERROR: Cannot prompt in non-interactive mode.")
            print("Use --force to overwrite: orchestrator init --force")
            sys.exit(1)
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

        # Analyze what would happen with Part 1 strategies
        results = resolver.resolve_all(strategy=args.strategy or "auto")

        if results.resolved_count > 0:
            print(f"Auto-resolvable (Part 1): {results.resolved_count} file(s)")
            for r in results.results:
                if r.success:
                    print(f"  ✓ {r.file_path} ({r.strategy}, confidence: {r.confidence:.0%})")

        # If --use-llm is set, analyze escalated files with LLM
        use_llm = getattr(args, 'use_llm', False)
        llm_results = {}

        if use_llm and results.escalated_count > 0:
            print()
            print("Analyzing with LLM (CORE-023-P2)...")
            try:
                llm_resolver = LLMResolver(
                    repo_path=working_dir,
                    auto_apply_threshold=args.auto_apply_threshold,
                )

                for r in results.results:
                    if r.needs_escalation:
                        conflict = resolver.get_conflict_info(r.file_path)
                        llm_result = llm_resolver.resolve(
                            file_path=r.file_path,
                            base=conflict.base,
                            ours=conflict.ours,
                            theirs=conflict.theirs,
                        )
                        llm_results[r.file_path] = llm_result

                # Show LLM analysis results
                print()
                llm_resolvable = sum(1 for lr in llm_results.values() if lr.success and not lr.needs_escalation)
                llm_needs_confirm = sum(1 for lr in llm_results.values() if lr.success and lr.confidence_level == ConfidenceLevel.MEDIUM)
                llm_escalated = sum(1 for lr in llm_results.values() if lr.needs_escalation)

                if llm_resolvable > 0:
                    print(f"LLM auto-resolvable (high confidence): {llm_resolvable} file(s)")
                    for fp, lr in llm_results.items():
                        if lr.success and lr.confidence_level == ConfidenceLevel.HIGH:
                            print(f"  ✓ {fp} (LLM, confidence: {lr.confidence:.0%})")

                if llm_needs_confirm > 0:
                    print()
                    print(f"LLM resolvable (needs confirmation): {llm_needs_confirm} file(s)")
                    for fp, lr in llm_results.items():
                        if lr.success and lr.confidence_level == ConfidenceLevel.MEDIUM:
                            print(f"  ? {fp} (LLM, confidence: {lr.confidence:.0%})")

                if llm_escalated > 0:
                    print()
                    print(f"Still need manual decision: {llm_escalated} file(s)")
                    for fp, lr in llm_results.items():
                        if lr.needs_escalation:
                            print(f"  ! {fp} ({lr.escalation_reason})")

            except ValueError as e:
                print(f"  LLM unavailable: {e}")
                print("  Set OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY to enable")

        elif results.escalated_count > 0:
            print()
            print(f"Need manual decision: {results.escalated_count} file(s)")
            for r in results.results:
                if r.needs_escalation:
                    print(f"  ? {r.file_path}")
            if not use_llm:
                print()
                print("  TIP: Use --use-llm to attempt LLM-based resolution")

        print()
        print("-" * 60)
        print("To apply resolutions: orchestrator resolve --apply")
        if args.strategy:
            print(f"                       (using strategy: {args.strategy})")
        if use_llm:
            print("                       (with --use-llm for LLM assistance)")
        print("-" * 60)

        # Exit code 3 = preview only
        sys.exit(3)

    # Apply mode
    use_llm = getattr(args, 'use_llm', False)
    confirm_all = getattr(args, 'confirm_all', False)

    print(f"APPLYING RESOLUTIONS (strategy: {args.strategy or 'auto'})")
    if use_llm:
        print(f"  LLM assistance: enabled (threshold: {args.auto_apply_threshold:.0%})")
    print()

    results = resolver.resolve_all(strategy=args.strategy or "auto")
    applied, failed = 0, 0

    # Initialize LLM resolver if needed
    llm_resolver = None
    if use_llm:
        try:
            llm_resolver = LLMResolver(
                repo_path=working_dir,
                auto_apply_threshold=args.auto_apply_threshold,
            )
        except ValueError as e:
            print(f"WARNING: LLM unavailable ({e}), falling back to interactive mode")

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
            # Try LLM resolution first if enabled
            if llm_resolver:
                conflict = resolver.get_conflict_info(result.file_path)
                llm_result = llm_resolver.resolve(
                    file_path=result.file_path,
                    base=conflict.base,
                    ours=conflict.ours,
                    theirs=conflict.theirs,
                )

                if llm_result.success and llm_result.merged_content:
                    # Check if we should auto-apply or ask for confirmation
                    auto_apply = (
                        llm_result.confidence_level == ConfidenceLevel.HIGH
                        and not confirm_all
                    )

                    if auto_apply:
                        # High confidence - auto-apply
                        full_path = working_dir / result.file_path
                        full_path.write_text(llm_result.merged_content)
                        subprocess.run(
                            ["git", "add", result.file_path],
                            cwd=working_dir,
                            capture_output=True
                        )
                        print(f"  ✓ {result.file_path} resolved (LLM, {llm_result.confidence:.0%} confidence)")
                        applied += 1
                        continue

                    # Medium/Low confidence or confirm_all - show diff and ask
                    print()
                    print("=" * 60)
                    print(f"LLM RESOLUTION: {result.file_path}")
                    print("=" * 60)
                    print(f"Confidence: {llm_result.confidence:.0%} ({llm_result.confidence_level.value})")
                    print(f"Strategy: {llm_result.strategy}")
                    if llm_result.confidence_reasons:
                        print("Reasons:")
                        for reason in llm_result.confidence_reasons:
                            print(f"  - {reason}")
                    print()
                    print("Preview of merged content (first 30 lines):")
                    print("-" * 40)
                    preview_lines = llm_result.merged_content.split('\n')[:30]
                    for i, line in enumerate(preview_lines, 1):
                        print(f"  {i:3d}│ {line}")
                    if len(llm_result.merged_content.split('\n')) > 30:
                        print(f"  ... ({len(llm_result.merged_content.split(chr(10))) - 30} more lines)")
                    print("-" * 40)
                    print()
                    print("Options:")
                    print("  [A] Apply LLM resolution")
                    print("  [B] Keep OURS")
                    print("  [C] Keep THEIRS")
                    print("  [D] Open in editor")
                    print()

                    # Issue #61: fail-fast in non-interactive mode
                    if not is_interactive():
                        print("ERROR: Cannot prompt for conflict resolution in non-interactive mode.")
                        print("Use explicit strategy: orchestrator resolve --apply --strategy ours")
                        print("  or: orchestrator resolve --apply --strategy theirs")
                        sys.exit(1)
                    choice = input("Enter choice [A/B/C/D] (default: A): ").strip().upper() or "A"

                    if choice == "A":
                        full_path = working_dir / result.file_path
                        full_path.write_text(llm_result.merged_content)
                        subprocess.run(
                            ["git", "add", result.file_path],
                            cwd=working_dir,
                            capture_output=True
                        )
                        print(f"  ✓ {result.file_path} resolved (LLM accepted)")
                        applied += 1
                        continue

                elif llm_result.needs_escalation:
                    print(f"  LLM could not resolve {result.file_path}: {llm_result.escalation_reason}")

            # Fall back to interactive mode (no LLM or user rejected)
            print()
            print(format_escalation_for_user(result))
            print()

            # Get user choice (Issue #61: fail-fast in non-interactive mode)
            if not is_interactive():
                print("ERROR: Cannot prompt for conflict resolution in non-interactive mode.")
                print("Use explicit strategy: orchestrator resolve --apply --strategy ours")
                print("  or: orchestrator resolve --apply --strategy theirs")
                sys.exit(1)
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

    # V3 Phase 5: Gate enforcement before completion
    if not args.skip_verify:
        try:
            item_def = engine.get_item_definition(args.item)
            if item_def and 'verification' in item_def:
                verification = item_def['verification']
                gate_type = verification.get('type')
                working_dir = Path(args.dir) if hasattr(args, 'dir') and args.dir else Path('.')

                if gate_type == 'file_exists':
                    from .gates import ArtifactGate
                    # Expand template variables in path
                    artifact_path = verification.get('path', '')
                    artifact_path = artifact_path.replace('{{docs_dir}}', 'docs')
                    artifact_path = artifact_path.replace('{{tests_dir}}', 'tests')

                    gate = ArtifactGate(path=artifact_path, validator='not_empty')
                    if not gate.validate(working_dir):
                        print("=" * 60)
                        print(f"✗ GATE FAILED: Required artifact missing")
                        print("=" * 60)
                        print(f"  Expected: {artifact_path}")
                        if gate.error:
                            print(f"  Error: {gate.error}")
                        print()
                        print(f"Create the required file, then run:")
                        print(f"  orchestrator complete {args.item}")
                        print()
                        print("Or skip verification with --skip-verify (not recommended)")
                        sys.exit(1)

                elif gate_type == 'command':
                    from .gates import CommandGate
                    command = verification.get('command', 'true')
                    gate = CommandGate(command=command)
                    if not gate.validate(working_dir):
                        print("=" * 60)
                        print(f"✗ GATE FAILED: Command verification failed")
                        print("=" * 60)
                        print(f"  Command: {command}")
                        if gate.error:
                            print(f"  Error: {gate.error}")
                        sys.exit(1)

        except Exception as e:
            logger.debug(f"Gate enforcement skipped due to error: {e}")

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

    # Get force flag
    force = getattr(args, 'force', False)

    try:
        # Get item definition for context before skipping
        item_def = engine.get_item_definition(args.item)

        # Check if this is a gate item and warn if using --force
        if force and item_def:
            print("=" * 60)
            print("⚠️  WARNING: Force-skipping a gate bypasses verification!")
            print("=" * 60)
            print("This should only be used when:")
            print("  • The verification command is incorrect for your project type")
            print("  • You have manually verified the gate's intent")
            print()

        success, message = engine.skip_item(args.item, args.reason, force=force)

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

                # If critical issues, prompt user (Issue #61: fail-fast in non-interactive)
                if result.should_block:
                    if not confirm("Critical issues found. Continue anyway? [y/N]: ",
                                   yes_flag=getattr(args, 'yes', False)):
                        print("Advance cancelled. Address issues before proceeding.")
                        sys.exit(1)
        except ImportError:
            pass  # Critique module not available
        except Exception as e:
            print(f"Warning: Critique failed: {e}. Continuing without critique.")

    success, message = engine.advance_phase(force=args.force)

    if success:
        # V3 Phase 5: Log phase transition to audit log
        try:
            from .audit import AuditLogger
            working_dir = Path(args.dir or '.')
            paths = OrchestratorPaths(base_dir=working_dir)
            audit_logger = AuditLogger(paths.orchestrator_dir)
            audit_logger.log_event(
                "phase_transition",
                workflow_id=str(engine.state.workflow_id),
                from_phase=str(previous_phase_id),
                to_phase=str(engine.state.current_phase_id)
            )
        except Exception as e:
            logger.debug(f"Failed to log phase transition to audit: {e}")

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
        # Validate all required items in current phase are completed
        # This uses the same logic as can_advance_phase() - driven by YAML required/skippable flags
        can_finish, blockers, _ = engine.can_advance_phase()
        skip_item_check = getattr(args, 'skip_item_check', False)
        if not can_finish and not skip_item_check:
            print("=" * 60)
            print("⚠️  INCOMPLETE ITEMS")
            print("=" * 60)
            print("Required items not completed:")
            for blocker in blockers:
                print(f"  • {blocker}")
            print()
            print("Complete the required items first, or use --force to skip this check.")
            print("=" * 60)
            sys.exit(1)

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

        # V3 Phase 5: Log workflow finish to audit log
        try:
            from .audit import AuditLogger
            working_dir = Path(args.dir or '.')
            paths_for_audit = OrchestratorPaths(base_dir=working_dir)
            audit_logger = AuditLogger(paths_for_audit.orchestrator_dir)
            audit_logger.log_event(
                "workflow_finish",
                workflow_id=str(engine.state.workflow_id),
                status="completed"
            )
        except Exception as e:
            logger.debug(f"Failed to log workflow finish to audit: {e}")

        # CORE-025 Phase 4: Handle worktree merge for isolated workflows
        worktree_merged = False
        worktree_merge_info = None
        working_dir = Path(args.dir or '.')
        paths = OrchestratorPaths(base_dir=working_dir)
        session_mgr = SessionManager(paths)
        current_session = session_mgr.get_current_session()

        if current_session:
            session_info = session_mgr.get_session_info(current_session)
            if session_info and session_info.get('isolated'):
                from .worktree_manager import WorktreeManager, MergeConflictError, WorktreeError
                import json

                original_branch = session_info.get('original_branch')
                worktree_path = session_info.get('worktree_path')

                if original_branch and worktree_path:
                    try:
                        wt_manager = WorktreeManager(working_dir)
                        merge_result = wt_manager.merge_and_cleanup(current_session, original_branch)
                        worktree_merged = True
                        worktree_merge_info = {
                            'success': merge_result.success,
                            'commits': merge_result.merged_commits,
                            'original_branch': original_branch
                        }
                    except MergeConflictError as e:
                        print()
                        print("=" * 60)
                        print("⚠️  WORKTREE MERGE CONFLICT")
                        print("=" * 60)
                        print(str(e))
                        print()
                        print("Resolve the conflict manually, then run:")
                        print(f"  orchestrator doctor --cleanup")
                        print("=" * 60)
                        # Don't exit - workflow is complete, just merge failed
                    except WorktreeError as e:
                        print(f"\n⚠️  Worktree cleanup warning: {e}")

        # CORE-031: Auto-sync with remote
        sync_result = None
        no_push = getattr(args, 'no_push', False)
        continue_sync = getattr(args, 'continue_sync', False)

        if not no_push:
            sync_mgr = SyncManager(working_dir)

            # Issue #92: Auto-commit uncommitted changes before syncing
            if sync_mgr.has_uncommitted_changes():
                print()
                print("Committing uncommitted changes...")
                commit_msg = f"Complete workflow: {task_description}"
                commit_result = sync_mgr.commit_all(commit_msg)
                if commit_result:
                    print(f"✓ Committed changes: {commit_msg[:50]}{'...' if len(commit_msg) > 50 else ''}")
                else:
                    print("⚠️  Failed to commit changes. Commit manually and run:")
                    print("  orchestrator finish --continue")
                    sys.exit(1)

            upstream = sync_mgr.get_remote_tracking_branch()

            if upstream:
                print()

                if continue_sync:
                    # --continue: User resolved conflicts, just try to push
                    print("Continuing sync after conflict resolution...")
                    sync_result = sync_mgr.push()
                else:
                    # Normal sync: fetch, check divergence, rebase if needed, push
                    print("Syncing with remote...")
                    sync_result = sync_mgr.sync()

                if not sync_result.success and sync_result.conflicts:
                    print()
                    print("=" * 60)
                    print("⚠️  SYNC CONFLICT DETECTED")
                    print("=" * 60)
                    print("Remote has changes that conflict with yours.")
                    print()
                    print("To resolve:")
                    print("  1. Run: orchestrator resolve --apply")
                    print("  2. Then: orchestrator finish --continue")
                    print()
                    print("Or to skip sync:")
                    print("  orchestrator finish --no-push")
                    print("=" * 60)
                    # Don't exit - workflow state is already saved, just sync failed
                elif sync_result.success and sync_result.pushed_commits > 0:
                    print(f"✓ Pushed {sync_result.pushed_commits} commit(s) to {upstream}")
                elif sync_result.success:
                    print("✓ Already in sync with remote")
                else:
                    print(f"⚠️  Sync failed: {sync_result.message}")

        # Issue #63: Update commit_and_sync item status after successful auto-sync
        # In zero_human mode, commit_and_sync is auto-skipped but sync still happens
        # Mark it as "completed" instead of "skipped" when sync succeeds
        if sync_result and sync_result.success:
            try:
                # Find commit_and_sync in LEARN phase
                learn_phase = engine.state.phases.get("LEARN")
                if learn_phase and "commit_and_sync" in learn_phase.items:
                    item_state = learn_phase.items["commit_and_sync"]
                    if item_state.status == ItemStatus.SKIPPED:
                        item_state.status = ItemStatus.COMPLETED
                        item_state.completed_at = datetime.now(timezone.utc)
                        item_state.notes = "Auto-completed via CORE-031 sync"
                        engine.save_state()
                        # Also update the cached summary data for correct output
                        if "LEARN" in all_skipped:
                            all_skipped["LEARN"] = [
                                item for item in all_skipped["LEARN"]
                                if not item.startswith("commit_and_sync:")
                            ]
                            if not all_skipped["LEARN"]:
                                del all_skipped["LEARN"]
                        if "LEARN" in summary:
                            summary["LEARN"]["skipped"] -= 1
                            summary["LEARN"]["completed"] += 1
            except Exception:
                pass  # Silently ignore - git sync already succeeded

        # WF-027: Capture summary to buffer for saving to file
        from io import StringIO
        summary_buffer = StringIO()

        def output(line=""):
            """Print to stdout and capture to buffer."""
            print(line)
            summary_buffer.write(line + "\n")

        # CORE-011: Print comprehensive completion summary
        output("=" * 60)
        output("✓ WORKFLOW COMPLETED")
        output("=" * 60)
        output(f"Task: {task_description}")

        # Show duration if times are available
        if started_at and completed_at:
            duration = completed_at - started_at
            output(f"Duration: {format_duration(duration)}")
        output()

        # Phase summary table
        if summary:
            output("PHASE SUMMARY")
            output("-" * 60)
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
                output(f"  {phase_id:12} {total} items ({completed} completed, {skipped} skipped)")
            output("-" * 60)
            output(f"  {'Total':12} {total_items} items ({total_completed} completed, {total_skipped} skipped)")
            output()

        # Skipped items summary (enhanced with full reasons, item_id, and gate highlighting)
        if all_skipped:
            total_skipped_count = sum(len(items) for items in all_skipped.values())
            output(f"SKIPPED ITEMS ({total_skipped_count} total - review for justification)")
            output("-" * 60)
            for phase_id, items in all_skipped.items():
                output(f"  [{phase_id}]")
                for item_id, reason in items:
                    # Look up item definition for description and step type
                    item_def = engine.get_item_definition(item_id)
                    if item_def:
                        description = item_def.description or item_id
                        step_type = getattr(item_def, 'step_type', None)
                        is_gate = step_type and 'gate' in str(step_type.value).lower()
                    else:
                        description = item_id
                        step_type = None
                        is_gate = False

                    # Highlight gate bypasses prominently
                    if is_gate:
                        output(f"    ⚠️  GATE BYPASSED: {item_id}: {description}")
                    else:
                        output(f"    • {item_id}: {description}")

                    # Show full reason, indented for readability
                    for line in reason.split('\n'):
                        output(f"      → {line}")
                output()
        else:
            output("SKIPPED ITEMS: None (all items completed)")
            output()

        # REVIEW MODEL VISIBILITY: Show which models reviewed each phase
        review_info = engine.state.metadata.get("review_models", {})
        if review_info:
            output("EXTERNAL REVIEWS PERFORMED")
            output("-" * 60)
            for phase_id, models in review_info.items():
                if models:
                    output(f"  {phase_id}:")
                    for model_name, status in models.items():
                        status_icon = "✓" if status.get("success") else "✗"
                        issues = status.get("issues", 0)
                        output(f"    {status_icon} {model_name}: {issues} issues found")
            output()
        else:
            output("EXTERNAL REVIEWS")
            output("-" * 60)
            output("  ⚠️  No external model reviews recorded!")
            output("  External reviews are REQUIRED for code changes.")
            output("  Ensure API keys are loaded: eval $(sops -d secrets.enc.yaml)")
            output()

        # Generate learning report FIRST (before displaying summary)
        # This ensures we show the CURRENT workflow's learnings, not stale ones
        if not args.skip_learn:
            output("Generating learning report...")
            try:
                learning = LearningEngine(args.dir or '.')
                report = learning.generate_learning_report()
                output(f"✓ Learning report saved to LEARNINGS.md")
                output()
            except Exception as e:
                output(f"Warning: Could not generate learning report: {e}")

        # LEARNINGS SUMMARY: Show actions vs roadmap items (now from freshly generated report)
        try:
            learnings_path = Path(args.dir or '.') / 'LEARNINGS.md'
            if learnings_path.exists():
                output("LEARNINGS SUMMARY")
                output("-" * 60)
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
                    output("  IMMEDIATE ACTIONS:")
                    for action in immediate_actions[:5]:
                        output(f"    → {action}")

                if roadmap_items:
                    output("  ROADMAP ITEMS:")
                    for item in roadmap_items[:5]:
                        output(f"    ○ {item}")

                if not immediate_actions and not roadmap_items:
                    output("  No specific actions identified. Review LEARNINGS.md manually.")
                output()
        except Exception as e:
            print(f"Warning: Could not parse LEARNINGS.md: {e}", file=sys.stderr)

        # CORE-025 Phase 4: Show worktree merge result
        if worktree_merged and worktree_merge_info:
            output()
            output("WORKTREE MERGE")
            output("-" * 60)
            output(f"  ✓ Merged {worktree_merge_info['commits']} commits to {worktree_merge_info['original_branch']}")
            output("  ✓ Worktree cleaned up")
            output()

        # CORE-031: Show sync result
        if sync_result is not None:
            output("REMOTE SYNC")
            output("-" * 60)
            if sync_result.success:
                if sync_result.pushed_commits > 0:
                    output(f"  ✓ Pushed {sync_result.pushed_commits} commit(s) to remote")
                else:
                    output("  ✓ Already in sync with remote")
            else:
                output(f"  ⚠️  {sync_result.message}")
            output()

        # Issue #62: Auto-close GitHub issues referenced in task description
        # Supports: #123, repo-name#123, owner/repo#123
        import re as regex

        # Pattern matches: owner/repo#num, repo#num, or just #num
        # Groups: (owner/, repo, num) where owner/ and repo are optional
        issue_pattern = regex.compile(r'(?:([a-zA-Z0-9_-]+)/)?([a-zA-Z0-9_-]+)?#(\d+)')
        issue_matches = issue_pattern.findall(task_description)

        if issue_matches and not getattr(args, 'no_close_issues', False):
            output("GITHUB ISSUES")
            output("-" * 60)

            for owner, repo, issue_num in issue_matches:
                # Build the issue reference and gh command
                if owner and repo:
                    # Full reference: owner/repo#num
                    issue_ref = f"{owner}/{repo}#{issue_num}"
                    gh_cmd = ['gh', 'issue', 'close', issue_num, '--repo', f'{owner}/{repo}']
                elif repo:
                    # Repo-only reference: repo#num (assumes current owner)
                    issue_ref = f"{repo}#{issue_num}"
                    gh_cmd = ['gh', 'issue', 'close', issue_num, '--repo', repo]
                else:
                    # Local reference: #num (uses current repo)
                    issue_ref = f"#{issue_num}"
                    gh_cmd = ['gh', 'issue', 'close', issue_num]

                gh_cmd.extend(['--comment', f'Closed automatically by orchestrator finish.\n\nTask: {task_description}'])

                try:
                    import subprocess
                    result = subprocess.run(gh_cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        output(f"  ✓ Closed issue {issue_ref}")
                    else:
                        # Issue might already be closed or not exist
                        if 'already closed' in result.stderr.lower():
                            output(f"  ○ Issue {issue_ref} already closed")
                        else:
                            output(f"  ⚠️  Could not close {issue_ref}: {result.stderr.strip()}")
                except FileNotFoundError:
                    output(f"  ⚠️  gh CLI not found - cannot auto-close {issue_ref}")
                    break
                except subprocess.TimeoutExpired:
                    output(f"  ⚠️  Timeout closing {issue_ref}")
            output()

        # WF-027: Save summary to archive file
        working_dir = Path(args.dir or '.')
        archive_dir = working_dir / 'docs' / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from date and task slug
        import re
        date_str = datetime.now().strftime("%Y-%m-%d")
        task_slug = re.sub(r'[^a-z0-9]+', '-', task_description.lower())[:40].strip('-')
        summary_filename = f"{date_str}_{task_slug}_summary.md"
        summary_path = archive_dir / summary_filename

        try:
            summary_path.write_text(summary_buffer.getvalue())
        except Exception as e:
            print(f"Warning: Could not save summary to {summary_path}: {e}", file=sys.stderr)

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
        print(f"  📄 Full summary saved to: {summary_path}")
        print()
        print("Reply to confirm next steps or start a new workflow.")
        print("=" * 60)


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
    
    # CORE-025: Use session-aware paths for checkpoints
    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)
    session_id = session_mgr.get_current_session()
    
    if session_id:
        paths = OrchestratorPaths(base_dir=working_dir, session_id=session_id)
        checkpoint_mgr = CheckpointManager(str(working_dir), paths=paths)
    else:
        checkpoint_mgr = CheckpointManager(str(working_dir))
    
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
    # CORE-025: Use session-aware paths for checkpoints
    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)
    session_id = session_mgr.get_current_session()
    
    if session_id:
        paths = OrchestratorPaths(base_dir=working_dir, session_id=session_id)
        checkpoint_mgr = CheckpointManager(str(working_dir), paths=paths)
    else:
        checkpoint_mgr = CheckpointManager(str(working_dir))
    
    # Handle cleanup
    if getattr(args, 'cleanup', False):
        max_age = getattr(args, 'max_age', 30)
        removed = checkpoint_mgr.cleanup_old_checkpoints(max_age_days=max_age)
        print(f"Removed {removed} old checkpoints")
        return
    
    # Get workflow ID filter
    workflow_id = None
    if not getattr(args, 'all', False):
        # CORE-025: Use get_engine for session-aware state loading
        engine = get_engine(args)
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
    # CORE-025: Use session-aware paths for checkpoints
    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)
    session_id = session_mgr.get_current_session()
    
    if session_id:
        paths = OrchestratorPaths(base_dir=working_dir, session_id=session_id)
        checkpoint_mgr = CheckpointManager(str(working_dir), paths=paths)
    else:
        checkpoint_mgr = CheckpointManager(str(working_dir))

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
            method=args.method if args.method != 'auto' else None,
            no_fallback=getattr(args, 'no_fallback', False)  # CORE-028b
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

    # Log reviews to workflow if active (fixes review persistence bug)
    engine = None
    try:
        engine = get_engine(args)
        if engine and engine.state:
            for review_name, result in results.items():
                event_type = EventType.REVIEW_COMPLETED if result.success else EventType.REVIEW_FAILED
                engine.log_event(WorkflowEvent(
                    event_type=event_type,
                    workflow_id=engine.state.workflow_id,
                    phase_id=engine.state.current_phase_id,
                    message=f"Review {review_name}: {'passed' if result.success else 'failed'}",
                    details={
                        "review_type": review_name,
                        "model": result.model_used,
                        "method": result.method_used,
                        "success": result.success,
                        "findings_count": len(result.findings) if result.findings else 0,
                        "blocking_count": result.blocking_count if hasattr(result, 'blocking_count') else 0,
                        "error": result.error,
                    }
                ))
            # Store in metadata for finish summary
            if "review_models" not in engine.state.metadata:
                engine.state.metadata["review_models"] = {}
            phase = engine.state.current_phase_id or "reviews"
            if phase not in engine.state.metadata["review_models"]:
                engine.state.metadata["review_models"][phase] = {}
            for review_name, result in results.items():
                engine.state.metadata["review_models"][phase][result.model_used] = {
                    "review_type": review_name,
                    "success": result.success,
                    "issues": len(result.findings) if result.findings else 0,
                    "method": result.method_used,
                }
            engine.save_state()
    except Exception:
        pass  # No active workflow, that's fine

    if args.json:
        output = {k: v.to_dict() for k, v in results.items()}
        print(json.dumps(output, indent=2, default=str))
        return

    # Pretty print results
    all_passed = True
    total_blocking = 0

    for review_name, result in results.items():
        icon = "✓" if result.success and not result.has_blocking_findings() else "✗"
        # CORE-028b: Show fallback indicator if used
        fallback_tag = " [fallback]" if getattr(result, 'was_fallback', False) else ""
        print(f"{icon} {review_name.upper()} REVIEW{fallback_tag}")
        print(f"  Model: {result.model_used}")
        print(f"  Method: {result.method_used}")
        if getattr(result, 'was_fallback', False) and getattr(result, 'fallback_reason', None):
            reason = result.fallback_reason[:60] + "..." if len(result.fallback_reason) > 60 else result.fallback_reason
            print(f"  Fallback reason: {reason}")

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


def cmd_review_retry(args):
    """Retry failed reviews after fixing issues (CORE-026)."""
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Get failed reviews
    failed = engine.get_failed_reviews()

    if not failed:
        print("No failed reviews to retry.")
        print("All reviews either passed or haven't been run yet.")
        print("\nTo run reviews: orchestrator review all")
        return

    print(f"Found {len(failed)} failed review(s) to retry:\n")

    working_dir = Path(args.dir or '.')

    for review_type, failure_info in failed.items():
        print(f"Retrying {review_type}...")
        print(f"  Previous error: {failure_info.get('error', 'Unknown')}")
        print(f"  Error type: {failure_info.get('error_type', 'unknown')}")

        # Validate API keys before retry
        from .review.router import validate_api_keys
        from .review.registry import get_model_for_review
        try:
            model = get_model_for_review(review_type)
            if model:
                valid, errors = validate_api_keys([model], ping=False)
                if not valid:
                    from .review.recovery import get_recovery_instructions
                    print(f"  Still failing: {errors.get(model.lower(), 'Unknown key error')}")
                    print(get_recovery_instructions(model))
                    continue
        except Exception as e:
            print(f"  Warning: Could not validate keys: {e}")

        # Run the review
        try:
            router = ReviewRouter(
                working_dir=working_dir,
                method=args.method if hasattr(args, 'method') and args.method != 'auto' else None
            )
            result = router.execute_review(review_type)

            if result.success and not result.has_blocking_findings():
                print(f"  ✓ {review_type} review passed!")
                # Log success
                engine.log_event(WorkflowEvent(
                    event_type=EventType.REVIEW_COMPLETED,
                    workflow_id=engine.state.workflow_id,
                    phase_id=engine.state.current_phase_id,
                    message=f"Review {review_type}: passed (retry)",
                    details={
                        "review_type": review_type,
                        "model": result.model_used,
                        "method": result.method_used,
                        "success": result.success,
                        "was_retry": True,
                    }
                ))
                engine.save_state()
            else:
                print(f"  ✗ {review_type} review still has issues")
                if result.error:
                    print(f"    Error: {result.error}")
                if result.findings:
                    print(f"    Blocking findings: {result.blocking_count}")

        except Exception as e:
            print(f"  ✗ Failed to run review: {e}")

        print()

    # Show summary
    remaining = engine.get_failed_reviews()
    if remaining:
        print(f"\n{len(remaining)} review(s) still need attention.")
        print("Fix the issues and run: orchestrator review retry")
    else:
        print("\nAll reviews passed!")


def cmd_validate_adherence(args):
    """Validate workflow adherence (WF-034 Phase 2)."""
    engine = get_engine(args)

    # Determine workflow ID
    if hasattr(args, 'workflow') and args.workflow:
        workflow_id = args.workflow
        task = "Unknown task"
    elif engine.state:
        workflow_id = engine.state.workflow_id
        task = engine.state.workflow_def.task or "Unknown task"
    else:
        print("Error: No active workflow and no --workflow specified")
        print("Usage: orchestrator validate-adherence [--workflow WORKFLOW_ID]")
        sys.exit(1)

    # Find session log
    session_log_path = find_session_log_for_workflow(workflow_id)

    # Create validator
    validator = AdherenceValidator(
        session_log_path=session_log_path,
        workflow_log_path=Path(".workflow_log.jsonl")
    )

    # Validate
    try:
        report = validator.validate(workflow_id=workflow_id, task=task)
    except Exception as e:
        print(f"Error during validation: {e}")
        sys.exit(1)

    # Output
    if hasattr(args, 'json') and args.json:
        # JSON output
        output = {
            "workflow_id": report.workflow_id,
            "task": report.task,
            "timestamp": report.timestamp.isoformat(),
            "score": report.score,
            "checks": {
                name: {
                    "passed": check.passed,
                    "confidence": check.confidence,
                    "explanation": check.explanation,
                    "evidence": check.evidence,
                    "recommendations": check.recommendations
                }
                for name, check in report.checks.items()
            },
            "critical_issues": report.critical_issues,
            "warnings": report.warnings,
            "recommendations": report.recommendations
        }
        print(json.dumps(output, indent=2))
    else:
        # Formatted text output
        print(format_adherence_report(report))


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


def cmd_enforce(args):
    """
    Zero-config workflow enforcement for agents.

    Auto-detects or starts orchestrator server, generates agent_workflow.yaml,
    and provides agent-ready instructions.
    """
    from src.orchestrator.auto_setup import ensure_orchestrator_running, ServerError
    from src.orchestrator.workflow_generator import analyze_repo, generate_workflow_yaml, save_workflow_yaml
    from src.orchestrator.agent_context import generate_agent_instructions, save_agent_instructions, format_agent_prompt

    working_dir = Path(args.dir or '.')

    try:
        # Step 1: Ensure server is running
        if not args.json:
            print("Checking for running orchestrator server...")

        port = args.port if hasattr(args, 'port') else 8000
        server_url = ensure_orchestrator_running(port=port)

        if not args.json:
            print(f"✓ Server running at {server_url}")

        # Step 2: Check for existing workflow.yaml, or generate new one
        workflow_path = working_dir / ".orchestrator" / "agent_workflow.yaml"
        if not workflow_path.exists():
            if not args.json:
                print("Analyzing repository...")

            analysis = analyze_repo(working_dir)

            if not args.json:
                print(f"✓ Detected: {analysis.language} project with {analysis.test_framework}")

            workflow_content = generate_workflow_yaml(args.task, analysis)
            workflow_path = save_workflow_yaml(workflow_content, working_dir)

            if not args.json:
                print(f"✓ Generated workflow: {workflow_path}")
        else:
            if not args.json:
                print(f"✓ Using existing workflow: {workflow_path}")

        # Step 3: Generate agent instructions
        mode = "parallel" if args.parallel else "sequential"
        instructions = generate_agent_instructions(
            task=args.task,
            server_url=server_url,
            workflow_path=workflow_path,
            mode=mode
        )

        # Step 4: Save instructions
        instructions_path = save_agent_instructions(instructions, working_dir)

        if not args.json:
            print(f"✓ Instructions saved: {instructions_path}")

        # Step 5: Output prompt
        if args.json:
            # Machine-readable JSON output
            import json
            print(json.dumps({
                "server_url": server_url,
                "workflow_path": str(workflow_path),
                "instructions_path": str(instructions_path),
                "mode": mode,
                "task": args.task
            }, indent=2))
        else:
            # Human/AI-readable formatted prompt
            prompt = format_agent_prompt(instructions, server_url, mode)
            print(prompt)

    except ServerError as e:
        print(f"✗ Server error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        if not args.json:
            print("\nFor troubleshooting, see:", file=sys.stderr)
            print("  .orchestrator/enforce.log", file=sys.stderr)
            print("  .orchestrator/server.log", file=sys.stderr)
        sys.exit(1)


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


def cmd_doctor(args):
    """Check worktree health and perform cleanup (CORE-025 Phase 4)."""
    from .worktree_manager import WorktreeManager

    working_dir = Path(args.dir or '.')
    cleanup = getattr(args, 'cleanup', False)
    fix = getattr(args, 'fix', False)
    older_than_days = getattr(args, 'older_than', 0)

    # Check if we're in a git repo
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=working_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: Not a git repository")
        sys.exit(1)

    wt_manager = WorktreeManager(working_dir)
    paths = OrchestratorPaths(base_dir=working_dir)
    session_mgr = SessionManager(paths)

    print("=" * 60)
    print("ORCHESTRATOR DOCTOR")
    print("=" * 60)
    print()

    # List all worktrees
    worktrees = wt_manager.list()
    sessions = session_mgr.list_sessions()

    print("WORKTREE STATUS")
    print("-" * 60)

    if not worktrees:
        print("  No orchestrator-managed worktrees found")
    else:
        for wt in worktrees:
            session_info = session_mgr.get_session_info(wt.session_id)
            # Display human-readable name if available, otherwise session_id
            display_name = wt.name if wt.name else wt.session_id
            age_str = ""
            if wt.created_at:
                age_days = (datetime.now() - wt.created_at).days
                age_str = f" ({age_days}d old)"

            if session_info:
                status = "active" if session_info.get('isolated') else "unknown"
                print(f"  ✓ {display_name}{age_str}")
                print(f"    Session: {wt.session_id}")
                print(f"    Branch: {wt.branch}")
                print(f"    Status: {status}")
            else:
                print(f"  ⚠ {display_name}{age_str} (ORPHANED)")
                print(f"    Session: {wt.session_id}")
                print(f"    Branch: {wt.branch}")
    print()

    # Find orphaned worktrees (worktrees without sessions)
    orphaned_worktrees = []
    for wt in worktrees:
        if wt.session_id not in sessions:
            orphaned_worktrees.append(wt)

    # Find sessions claiming isolated but no worktree
    missing_worktrees = []
    for session_id in sessions:
        session_info = session_mgr.get_session_info(session_id)
        if session_info and session_info.get('isolated'):
            has_worktree = any(wt.session_id == session_id for wt in worktrees)
            if not has_worktree:
                missing_worktrees.append(session_id)

    # Report issues
    issues_found = False

    if orphaned_worktrees:
        issues_found = True
        print("ISSUES FOUND")
        print("-" * 60)
        print(f"  ⚠ {len(orphaned_worktrees)} orphaned worktree(s)")
        for wt in orphaned_worktrees:
            print(f"    - {wt.session_id}: {wt.path}")

    if missing_worktrees:
        issues_found = True
        if not orphaned_worktrees:
            print("ISSUES FOUND")
            print("-" * 60)
        print(f"  ⚠ {len(missing_worktrees)} session(s) with missing worktrees")
        for session_id in missing_worktrees:
            print(f"    - {session_id}")

    if not issues_found:
        print("HEALTH CHECK")
        print("-" * 60)
        print("  ✓ No issues found")
    print()

    # Cleanup mode
    if cleanup or fix:
        # Filter orphaned worktrees by age if --older-than specified
        worktrees_to_cleanup = orphaned_worktrees
        if older_than_days > 0:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            worktrees_to_cleanup = [
                wt for wt in orphaned_worktrees
                if wt.created_at and wt.created_at < cutoff_date
            ]
            skipped = len(orphaned_worktrees) - len(worktrees_to_cleanup)
            if skipped > 0:
                print(f"  Skipping {skipped} orphaned worktree(s) newer than {older_than_days} days")

        if worktrees_to_cleanup:
            print("CLEANUP")
            print("-" * 60)
            for wt in worktrees_to_cleanup:
                display_name = wt.name if wt.name else wt.session_id
                try:
                    success = wt_manager.cleanup(wt.session_id)
                    if success:
                        print(f"  ✓ Removed orphaned worktree: {display_name}")
                    else:
                        print(f"  ✗ Failed to remove: {display_name}")
                except Exception as e:
                    print(f"  ✗ Error removing {display_name}: {e}")
            print()

        if missing_worktrees and fix:
            print("FIX")
            print("-" * 60)
            for session_id in missing_worktrees:
                # Clear the isolated flag since worktree is gone
                updates = {
                    'isolated': False,
                    'worktree_path': None
                }
                if session_mgr.update_session_info(session_id, updates):
                    print(f"  ✓ Cleared isolated flag for session: {session_id}")
            print()

    elif issues_found:
        print("To fix issues, run:")
        print("  orchestrator doctor --cleanup    # Remove orphaned worktrees")
        print("  orchestrator doctor --fix        # Fix session metadata")
        print()

    print("=" * 60)


def cmd_health(args):
    """Check orchestrator system health (V3 Phase 5)."""
    from .health import HealthChecker

    working_dir = Path(args.dir or '.')
    json_output = getattr(args, 'json', False)

    checker = HealthChecker(working_dir=working_dir)
    report = checker.full_check()

    if json_output:
        print(report.to_json())
    else:
        # Human-readable output
        print("=" * 60)
        print("ORCHESTRATOR HEALTH CHECK")
        print("=" * 60)
        print()

        status_symbols = {
            'ok': '✓',
            'warning': '⚠',
            'error': '✗'
        }

        print(f"Overall Status: {status_symbols.get(report.overall_status, '?')} {report.overall_status.upper()}")
        print()

        print("Components:")
        for component in report.components:
            symbol = status_symbols.get(component.status, '?')
            print(f"  {symbol} {component.name}: {component.status}")
            if component.message:
                print(f"      {component.message}")
            if component.details:
                for key, value in component.details.items():
                    print(f"      {key}: {value}")

        print()
        print(f"Timestamp: {report.timestamp}")
        print("=" * 60)


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


def cmd_sessions(args):
    """Manage session transcripts (CORE-024)."""
    from src.transcript_logger import TranscriptLogger, get_transcript_logger
    from src.session_logger import SessionAnalyzer, format_analysis_report

    working_dir = Path(args.dir or '.')
    action = args.action

    logger = get_transcript_logger(working_dir=working_dir)

    if action == "list":
        limit = getattr(args, 'limit', None) or 20
        sessions = logger.list_sessions(limit=limit)

        if not sessions:
            print("No sessions found.")
            return

        print(f"Recent Sessions ({len(sessions)} shown):")
        print("")
        for s in sessions:
            size_kb = s['size_bytes'] / 1024
            modified = s['modified'].strftime("%Y-%m-%d %H:%M")
            print(f"  {s['session_id']}")
            print(f"    Date: {modified}  Size: {size_kb:.1f} KB")
        print("")
        print(f"Sessions stored in: {logger._sessions_dir}")

    elif action == "show":
        if not args.session_id:
            print("Error: 'sessions show' requires SESSION_ID argument")
            sys.exit(1)

        content = logger.get_session(args.session_id)
        if content:
            print(content)
        else:
            print(f"Session not found: {args.session_id}")
            sys.exit(1)

    elif action == "clean":
        days = getattr(args, 'older', None) or 30
        removed = logger.clean(older_than_days=days)

        if removed:
            print(f"Removed {removed} session(s) older than {days} days")
        else:
            print(f"No sessions older than {days} days")


    elif action == "analyze":
        # Analyze session patterns and statistics
        days = getattr(args, 'days', None) or 30
        last_n = getattr(args, 'last', None)

        # Use SessionAnalyzer for enhanced session logs (.orchestrator/sessions/)
        # Fall back to basic stats from TranscriptLogger if no enhanced logs
        sessions_dir = working_dir / ".orchestrator" / "sessions"

        if sessions_dir.exists():
            analyzer = SessionAnalyzer(sessions_dir)
            report = analyzer.analyze(last_n_days=days, last_n_sessions=last_n)
            print(format_analysis_report(report))
        else:
            # Fallback: show basic stats from TranscriptLogger
            sessions = logger.list_sessions(limit=last_n)
            print(f"\nSession Statistics (last {days} days)")
            print("=" * 60)
            print(f"Total Sessions: {len(sessions)}")
            if sessions:
                total_size = sum(s['size_bytes'] for s in sessions) / 1024
                print(f"Total Size: {total_size:.1f} KB")
            print("\nNote: Enhanced session logging not enabled.")
            print("Enable by integrating SessionLogger in your workflow.")
            print("=" * 60)

    else:
        print(f"Unknown action: {action}")
        print("Available actions: list, show, clean")
        sys.exit(1)


def _find_approval_request(queue, request_id: str):
    """Find an approval request by full ID or prefix match."""
    # Try exact match first
    if queue.get(request_id):
        return request_id
    # Try prefix match in pending requests
    for req in queue.pending():
        if req.id.startswith(request_id):
            return req.id
    return None


def cmd_approval(args):
    """Manage parallel agent approval requests."""
    from src.approval_queue import ApprovalQueue
    from datetime import datetime, timezone

    working_dir = Path(args.dir or '.')
    action = args.approval_action

    queue = ApprovalQueue(working_dir / '.workflow_approvals.db')

    if action == "pending":
        # List pending approval requests
        pending = queue.pending()

        if not pending:
            print("No pending approval requests.")
            return

        print(f"\n{'='*60}")
        print(f" PENDING APPROVAL REQUESTS ({len(pending)})")
        print(f"{'='*60}\n")

        for req in pending:
            # Calculate wait time
            try:
                created = datetime.fromisoformat(req.created_at)
                # Normalize timezone: if naive, assume UTC
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                wait_secs = (now - created).total_seconds()
                if wait_secs < 60:
                    wait_str = f"{int(wait_secs)}s"
                elif wait_secs < 3600:
                    wait_str = f"{int(wait_secs // 60)}m"
                else:
                    wait_str = f"{int(wait_secs // 3600)}h {int((wait_secs % 3600) // 60)}m"
            except (ValueError, TypeError):
                wait_str = "?"

            risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(req.risk_level, "⚪")
            print(f"  [{req.id[:8]}] {risk_emoji} {req.risk_level.upper()}")
            print(f"    Agent: {req.agent_id}")
            print(f"    Phase: {req.phase}")
            print(f"    Operation: {req.operation}")
            print(f"    Waiting: {wait_str}")
            if req.context:
                files = req.context.get('files', [])
                if files:
                    print(f"    Files: {', '.join(files[:3])}{'...' if len(files) > 3 else ''}")
            print("")

        print(f"{'='*60}")
        print("Commands:")
        print(f"  orchestrator approval approve <id>  - Approve request")
        print(f"  orchestrator approval reject <id>   - Reject request")
        print(f"  orchestrator approval approve-all   - Approve all pending")
        print(f"{'='*60}\n")

    elif action == "approve":
        request_id = args.request_id
        if not request_id:
            print("Error: 'approval approve' requires REQUEST_ID")
            sys.exit(1)

        found = _find_approval_request(queue, request_id)
        if not found:
            print(f"Request not found: {request_id}")
            sys.exit(1)

        reason = getattr(args, 'reason', None) or "Approved via CLI"
        if queue.approve(found, reason):
            print(f"✅ Approved: {found[:8]}...")
        else:
            print(f"Failed to approve: {found}")
            sys.exit(1)

    elif action == "reject":
        request_id = args.request_id
        if not request_id:
            print("Error: 'approval reject' requires REQUEST_ID")
            sys.exit(1)

        found = _find_approval_request(queue, request_id)
        if not found:
            print(f"Request not found: {request_id}")
            sys.exit(1)

        reason = getattr(args, 'reason', None) or "Rejected via CLI"
        if queue.reject(found, reason):
            print(f"❌ Rejected: {found[:8]}...")
        else:
            print(f"Failed to reject: {found}")
            sys.exit(1)

    elif action == "approve-all":
        reason = getattr(args, 'reason', None) or "Batch approved via CLI"
        count = queue.approve_all(reason)
        if count > 0:
            print(f"✅ Approved {count} request(s)")
        else:
            print("No pending requests to approve.")

    elif action == "stats":
        stats = queue.stats()
        print("\nApproval Queue Statistics:")
        print(f"  Pending:  {stats.get('pending', 0)}")
        print(f"  Approved: {stats.get('approved', 0)}")
        print(f"  Rejected: {stats.get('rejected', 0)}")
        print(f"  Consumed: {stats.get('consumed', 0)}")
        print(f"  Expired:  {stats.get('expired', 0)}")
        print("")

    elif action == "cleanup":
        days = getattr(args, 'days', None) or 7
        expired = queue.expire_stale(timeout_minutes=60)
        cleaned = queue.cleanup(days=days)
        print(f"Expired {expired} stale request(s)")
        print(f"Cleaned {cleaned} old record(s) (older than {days} days)")

    elif action == "watch":
        import subprocess
        import shutil

        once = getattr(args, 'once', False)
        interval = getattr(args, 'interval', 5)
        seen_ids = set()

        print("👀 Watching for approval requests...")
        print("   Press Ctrl+C to stop\n")

        def notify_tmux_bell():
            """Trigger tmux bell for Happy app notifications."""
            if shutil.which("tmux"):
                try:
                    subprocess.run(
                        ["tmux", "send-keys", "-t", ":", ""],
                        capture_output=True,
                        timeout=2
                    )
                    # Send bell character
                    subprocess.run(
                        ["tmux", "run-shell", "echo -e '\\a'"],
                        capture_output=True,
                        timeout=2
                    )
                except (subprocess.SubprocessError, FileNotFoundError):
                    pass

        try:
            while True:
                pending = queue.pending()
                new_requests = [r for r in pending if r.id not in seen_ids]

                if new_requests:
                    notify_tmux_bell()
                    print(f"\n{'='*50}")
                    print(f"⏳ NEW APPROVAL REQUEST(S): {len(new_requests)}")
                    print(f"{'='*50}")

                    for req in new_requests:
                        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(req.risk_level, "⚪")
                        print(f"\n  {risk_emoji} [{req.id[:8]}] {req.risk_level.upper()}")
                        print(f"    Agent: {req.agent_id}")
                        print(f"    Phase: {req.phase}")
                        print(f"    Operation: {req.operation}")
                        if req.context:
                            files = req.context.get('files', [])
                            if files:
                                print(f"    Files: {', '.join(files[:3])}")
                        seen_ids.add(req.id)

                    print(f"\n  Run: orchestrator approval approve <id>")
                    print(f"  Or:  orchestrator approval approve-all")
                    print(f"{'='*50}\n")

                if once:
                    if not pending:
                        print("No pending requests.")
                    break

                import time
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n👋 Watch stopped.")

    elif action == "summary":
        summary = queue.decision_summary()

        print(f"\n{'='*60}")
        print(f" DECISION SUMMARY")
        print(f"{'='*60}\n")

        auto = summary.get("auto_approved", [])
        human = summary.get("human_approved", [])
        rejected = summary.get("rejected", [])

        if auto:
            print(f"  🤖 AUTO-APPROVED ({len(auto)}):")
            for item in auto[:10]:  # Limit display
                print(f"    • {item['operation']}")
                print(f"      Rationale: {item.get('rationale', item.get('reason', 'N/A'))}")
            if len(auto) > 10:
                print(f"    ... and {len(auto) - 10} more")
            print("")

        if human:
            print(f"  ✅ HUMAN APPROVED ({len(human)}):")
            for item in human[:10]:
                print(f"    • {item['operation']}")
                if item.get('reason'):
                    print(f"      Reason: {item['reason']}")
            if len(human) > 10:
                print(f"    ... and {len(human) - 10} more")
            print("")

        if rejected:
            print(f"  ❌ REJECTED ({len(rejected)}):")
            for item in rejected[:10]:
                print(f"    • {item['operation']}")
                if item.get('reason'):
                    print(f"      Reason: {item['reason']}")
            print("")

        if not (auto or human or rejected):
            print("  No decisions recorded yet.")

        print(f"{'='*60}\n")

    else:
        print(f"Unknown action: {action}")
        print("Available actions: pending, approve, reject, approve-all, stats, cleanup, watch, summary")
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

def cmd_prd_check_backend(args):
    """Check execution backend availability."""
    from src.prd.backend_selector import BackendSelector, ExecutionMode
    from src.prd.tmux_adapter import TmuxAdapter
    import shutil

    print("Execution Backend Check")
    print("=" * 40)

    # 1. Check Tmux
    tmux_path = shutil.which("tmux")
    if tmux_path:
        print(f"  tmux: INSTALLED ({tmux_path})")
        # Check if we can create sessions
        try:
            adapter = TmuxAdapter(Path("."))
            info = adapter.get_session_info()
            print(f"  tmux session: {'Active' if info['exists'] else 'Can be created'}")
        except Exception as e:
            print(f"  tmux error: {e}")
    else:
        print("  tmux: NOT INSTALLED (Required for interactive sessions)")

    # 2. Check Subprocess (always available)
    print("  Subprocess: AVAILABLE (Fallback)")

    # 3. Detect Mode
    mode = BackendSelector.detect(Path(".")).select(interactive=True)
    print()
    print(f"  Detected Mode: {mode.value.upper()}")

    if mode == ExecutionMode.INTERACTIVE:
        print("  ✓ Ready for interactive execution (tmux)")
    elif mode == ExecutionMode.SUBPROCESS:
        print("  ✓ Ready for background execution (subprocess)")
        print("    (Install tmux for interactive features)")
    elif mode == ExecutionMode.BATCH:
        print("  ✓ Ready for batch execution (GitHub Actions)")
    else:
        print(f"  Status: {mode.value}")


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

    # PRD-006: Handle --no-approval-gate flag
    inject_approval_gate = not getattr(args, 'no_approval_gate', False)

    result = executor.spawn(
        prd=prd,
        explain=args.explain,
        dry_run=args.dry_run,
        force_tasks=force_tasks,
        inject_approval_gate=inject_approval_gate,
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
    """List active agent sessions (tmux or subprocess)."""
    from src.prd.backend_selector import BackendSelector
    from datetime import datetime, timezone

    working_dir = Path(args.dir or '.')

    try:
        selector = BackendSelector.detect(working_dir)
        adapter = selector.get_adapter()
        if adapter is None:
            print("No execution backend available")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    sessions = adapter.list_agents()

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
    """Attach to an agent session (tmux only)."""
    from src.prd.backend_selector import BackendSelector
    from src.prd.tmux_adapter import TmuxError, SessionNotFoundError

    working_dir = Path(args.dir or '.')

    try:
        selector = BackendSelector.detect(working_dir)
        adapter = selector.get_adapter()
        if adapter is None:
            print("No execution backend available")
            sys.exit(1)
        adapter.attach(args.task_id)
    except NotImplementedError as e:
        print(f"Error: {e}")
        print("Attach is only supported with tmux backend")
        sys.exit(1)
    except (TmuxError, SessionNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_prd_done(args):
    """Mark a task as complete and terminate its session."""
    from src.prd.backend_selector import BackendSelector

    working_dir = Path(args.dir or '.')

    try:
        selector = BackendSelector.detect(working_dir)
        adapter = selector.get_adapter()
        if adapter is None:
            print("No execution backend available")
            sys.exit(1)
        adapter.mark_complete(args.task_id)
        print(f"Task {args.task_id} marked complete")
        print("Session terminated")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_prd_cleanup(args):
    """Clean up all agent sessions."""
    from src.prd.backend_selector import BackendSelector

    working_dir = Path(args.dir or '.')

    try:
        selector = BackendSelector.detect(working_dir)
        adapter = selector.get_adapter()
        if adapter is None:
            print("No execution backend available")
            sys.exit(1)

        # Clean all sessions
        adapter.cleanup()
        print("All sessions cleaned up")

        # Optionally clean old records from registry
        if args.days:
            removed = adapter.registry.cleanup_old(days=args.days)
            print(f"Removed {removed} old record(s) (>{args.days} days)")

    except Exception as e:
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


# ============================================================
# Phase 3b: Two-Tier Feedback Helper Functions
# ============================================================

def detect_repo_type(working_dir):
    """Detect repository language type from project files."""
    working_dir = Path(working_dir)

    # Check for language markers in priority order
    if (working_dir / 'setup.py').exists() or (working_dir / 'pyproject.toml').exists():
        return 'python'
    elif (working_dir / 'package.json').exists():
        return 'javascript'
    elif (working_dir / 'go.mod').exists():
        return 'go'
    elif (working_dir / 'Cargo.toml').exists():
        return 'rust'

    return 'unknown'


def anonymize_tool_feedback(feedback):
    """
    Remove PII from tool feedback for safe sharing (ALLOWLIST approach).

    Uses allowlist (not denylist) to ensure future fields don't leak PII.
    Adds salt to hash to prevent rainbow table attacks.
    Uses deepcopy to avoid nested structure issues.

    Safe fields (allowlist):
    - timestamp, mode, orchestrator_version, repo_type
    - duration_seconds, phases (dict of phase timings)
    - parallel_agents_used, reviews_performed (booleans)
    - errors_count, items_skipped_count (integers only, no details)
    """
    import hashlib
    import os
    from copy import deepcopy

    # Type check
    if not isinstance(feedback, dict):
        return {}

    # Deep copy to avoid modifying original or shared nested structures
    tool = deepcopy(feedback)

    # Salted hash for workflow_id (prevents rainbow table attacks)
    salt = os.environ.get("WORKFLOW_SALT", "workflow-orchestrator-default-salt-v1")
    if 'workflow_id' in tool:
        workflow_id_str = str(tool['workflow_id'])  # Handle non-string IDs
        hashed = hashlib.sha256((salt + workflow_id_str).encode()).hexdigest()[:16]
        tool['workflow_id_hash'] = hashed
        del tool['workflow_id']

    # ALLOWLIST approach - only keep explicitly safe fields
    safe_fields = {
        'timestamp',
        'workflow_id_hash',
        'mode',
        'orchestrator_version',
        'repo_type',
        'duration_seconds',
        'phases',  # Dict of phase timings (integers)
        'parallel_agents_used',
        'reviews_performed',
        'errors_count',  # Count only, no error details
        'items_skipped_count',  # Count only, no skip reasons
    }

    # Keep only safe fields
    tool = {k: v for k, v in tool.items() if k in safe_fields}

    # SECURITY: Validate nested structures don't leak PII
    # Phases dict keys must be phase names only (PLAN, EXECUTE, etc), not user content
    if 'phases' in tool and isinstance(tool['phases'], dict):
        # Allowed phase names (from standard workflow)
        allowed_phases = {'PLAN', 'EXECUTE', 'REVIEW', 'VERIFY', 'LEARN', 'TDD', 'IMPL'}
        # Filter to only allowed phase names
        tool['phases'] = {k: v for k, v in tool['phases'].items()
                         if k.upper() in allowed_phases and isinstance(v, (int, float))}
        # If no valid phases remain, remove the field
        if not tool['phases']:
            del tool['phases']

    return tool


def extract_tool_feedback_from_entry(entry):
    """
    Extract tool-relevant metrics from a feedback entry.

    Tool feedback focuses on orchestrator performance:
    - Phase timings
    - Error counts (not details)
    - Items skipped (count only)
    - Reviews performed (yes/no)
    - Parallel agents used (yes/no)
    """
    tool_fields = [
        'timestamp',
        'workflow_id',
        'mode',
        'orchestrator_version',
        'repo_type',
        'duration_seconds',
        'phases',
        'parallel_agents_used',
        'reviews_performed',
        'errors_count',
        'items_skipped_count',
    ]

    tool = {}
    for field in tool_fields:
        if field in entry:
            tool[field] = entry[field]

    return tool


def extract_process_feedback_from_entry(entry):
    """
    Extract process-relevant context from a feedback entry.

    Process feedback focuses on project-specific learnings:
    - Task description
    - Repo information
    - Learnings and challenges
    - What went well/poorly
    - Improvements needed
    """
    process_fields = [
        'timestamp',
        'workflow_id',
        'task',
        'repo',
        'mode',
        'parallel_agents_used',
        'errors_summary',
        'items_skipped_reasons',
        'learnings',
        'challenges',
        'what_went_well',
        'improvements',
    ]

    process = {}
    for field in process_fields:
        if field in entry:
            process[field] = entry[field]

    return process


def migrate_legacy_feedback(working_dir):
    """
    Migrate Phase 3a single-file feedback to Phase 3b two-tier system (ATOMIC).

    Uses temp-file + atomic-rename pattern to prevent data loss on crash.
    Implements all recommendations from multi-model review (5/5 AI models).

    Splits .workflow_feedback.jsonl into:
    - .workflow_tool_feedback.jsonl (anonymized, shareable)
    - .workflow_process_feedback.jsonl (private, local-only)

    Returns:
        bool: True if migration occurred, False if already migrated or no legacy file
    """
    import os

    working_dir = Path(working_dir)
    legacy_file = working_dir / '.workflow_feedback.jsonl'
    tool_file = working_dir / '.workflow_tool_feedback.jsonl'
    process_file = working_dir / '.workflow_process_feedback.jsonl'
    marker_file = working_dir / '.workflow_migration_in_progress'

    # Check for incomplete migration from previous crash
    if marker_file.exists():
        print("  ⚠ Detected incomplete migration from previous crash, cleaning up...")
        # Clean up partial files
        if tool_file.exists():
            try:
                tool_file.unlink()
            except:
                pass
        if process_file.exists():
            try:
                process_file.unlink()
            except:
                pass
        marker_file.unlink()
        # Continue with fresh migration

    # Skip if already migrated (check for partial states too - OR not AND)
    if tool_file.exists() or process_file.exists():
        return False

    # Skip if no legacy file
    if not legacy_file.exists():
        return False

    print("⚙ Migrating feedback to two-tier system...")

    # Create temp files in same directory (for atomic rename)
    tool_temp = working_dir / f'.workflow_tool_feedback.jsonl.tmp.{os.getpid()}'
    process_temp = working_dir / f'.workflow_process_feedback.jsonl.tmp.{os.getpid()}'

    # Clean up any stale temp files from previous crashes
    for stale in working_dir.glob('.workflow_*_feedback.jsonl.tmp.*'):
        try:
            stale.unlink()
        except:
            pass

    migrated = 0
    failed = 0

    try:
        # Detect repo type for tool feedback
        repo_type = detect_repo_type(working_dir)

        # Stream line-by-line (avoid loading entire file into memory)
        with open(legacy_file, 'r') as legacy_f, \
             open(tool_temp, 'w') as tool_f, \
             open(process_temp, 'w') as process_f:

            for line_num, line in enumerate(legacy_f, 1):
                try:
                    entry = json.loads(line)

                    # Extract and anonymize tool feedback
                    tool_data = extract_tool_feedback_from_entry(entry)
                    tool_data['repo_type'] = repo_type

                    # Add orchestrator version if not present
                    if 'orchestrator_version' not in tool_data:
                        try:
                            from . import __version__
                            tool_data['orchestrator_version'] = __version__
                        except:
                            tool_data['orchestrator_version'] = 'unknown'

                    anonymized_tool = anonymize_tool_feedback(tool_data)

                    # Extract process feedback (keep full context)
                    process_data = extract_process_feedback_from_entry(entry)

                    # Write to temp files (write mode, not append)
                    tool_f.write(json.dumps(anonymized_tool) + '\n')
                    process_f.write(json.dumps(process_data) + '\n')
                    migrated += 1

                except json.JSONDecodeError as e:
                    print(f"  Warning: Skipping malformed entry on line {line_num}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  Error processing line {line_num}: {e}")
                    failed += 1

            # Flush and fsync for durability (protects against power failure)
            tool_f.flush()
            os.fsync(tool_f.fileno())
            process_f.flush()
            os.fsync(process_f.fileno())

        # Atomic two-file migration using transaction marker
        # SECURITY: If first rename succeeds but second fails, marker prevents inconsistent state
        marker_file = working_dir / '.workflow_migration_in_progress'
        try:
            # Create marker before any renames
            marker_file.touch()

            # Atomic renames (os.replace is atomic on both POSIX and Windows)
            os.replace(tool_temp, tool_file)
            os.replace(process_temp, process_file)

            # Remove marker after both succeed
            marker_file.unlink()
        except Exception as e:
            # Rollback: if marker exists, migration was incomplete
            if marker_file.exists():
                # Clean up partial migration
                if tool_file.exists():
                    try:
                        tool_file.unlink()
                    except:
                        pass
                if process_file.exists():
                    try:
                        process_file.unlink()
                    except:
                        pass
                marker_file.unlink()
            raise  # Re-raise to trigger outer exception handler

        # Backup legacy file AFTER successful migration
        legacy_backup = working_dir / '.workflow_feedback.jsonl.migrated'
        try:
            legacy_file.rename(legacy_backup)
        except Exception as e:
            print(f"  Warning: Could not rename legacy file: {e}")

        # Print summary
        if failed > 0:
            print(f"✓ Migrated {migrated} entries ({failed} failed) to two-tier system")
        else:
            print(f"✓ Migrated {migrated} entries to two-tier system")

        return True

    except Exception as e:
        # Cleanup temp files on any failure
        print(f"✗ Migration failed: {e}")
        for temp_file in [tool_temp, process_temp]:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
        return False


# =============================================================================
# CORE-025 Phase 3: Workflow Session CLI Commands
# =============================================================================

def _format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '2h ago', '3d ago')."""
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # Assume UTC for naive datetime
        dt = dt.replace(tzinfo=timezone.utc)

    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago"
    elif seconds < 31536000:
        weeks = int(seconds / 604800)
        return f"{weeks}w ago"
    else:
        years = int(seconds / 31536000)
        return f"{years}y ago"


def _get_session_details(session_dir: Path) -> dict:
    """Get details for a session directory.

    Returns dict with: task, status, created_at, phase, progress
    """
    details = {
        'task': 'unknown',
        'status': 'unknown',
        'created_at': None,
        'phase': None,
        'progress': None
    }

    # Read meta.json for creation time
    meta_file = session_dir / 'meta.json'
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            if 'created_at' in meta:
                details['created_at'] = datetime.fromisoformat(meta['created_at'])
        except (json.JSONDecodeError, ValueError):
            pass

    # Read state.json for task/status/phase
    state_file = session_dir / 'state.json'
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            details['task'] = state.get('task', 'unknown')
            details['status'] = state.get('status', 'unknown')
            details['phase'] = state.get('current_phase')

            # Calculate progress
            phases = state.get('phases', {})
            if phases:
                completed = sum(1 for p in phases.values() if p.get('status') == 'complete')
                total = len(phases)
                details['progress'] = f"{completed}/{total}"
        except json.JSONDecodeError:
            pass

    return details


def cmd_workflow_list(args):
    """List all workflow sessions (CORE-025 Phase 3)."""
    from src.path_resolver import OrchestratorPaths
    from src.session_manager import SessionManager

    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    manager = SessionManager(paths)

    sessions = manager.list_sessions()
    current_session = manager.get_current_session()

    if not sessions:
        print("No workflow sessions found.")
        print(f"\nStart a workflow with: orchestrator start \"task description\"")
        return

    print(f"Workflow Sessions in {working_dir.absolute()}:")
    print("")

    # Sort sessions by creation time (newest first)
    session_data = []
    for sid in sessions:
        session_dir = paths.orchestrator_dir / "sessions" / sid
        details = _get_session_details(session_dir)
        session_data.append((sid, details))

    # Sort by created_at, newest first (None dates go to end)
    session_data.sort(key=lambda x: x[1]['created_at'] or datetime.min, reverse=True)

    for sid, details in session_data:
        is_current = sid == current_session
        marker = "*" if is_current else " "
        current_label = " (current)" if is_current else ""

        time_str = _format_relative_time(details['created_at']) if details['created_at'] else "unknown"

        # Truncate task if too long
        task = details['task']
        if len(task) > 40:
            task = task[:37] + "..."

        print(f"  {marker} {sid}{current_label}")
        print(f"      Task: {task}")
        print(f"      Status: {details['status']} | {time_str}")
        print("")


def cmd_workflow_switch(args):
    """Switch to a different workflow session (CORE-025 Phase 3)."""
    from src.path_resolver import OrchestratorPaths
    from src.session_manager import SessionManager

    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    manager = SessionManager(paths)

    session_id = args.session_id
    current = manager.get_current_session()

    if session_id == current:
        print(f"Already on session {session_id}")
        return

    try:
        manager.set_current_session(session_id)
        print(f"Switched to session {session_id}")
    except ValueError as e:
        print(f"Error: {e}")
        print(f"\nUse 'orchestrator workflow list' to see available sessions.")


def cmd_workflow_info(args):
    """Show details about a workflow session (CORE-025 Phase 3)."""
    from src.path_resolver import OrchestratorPaths
    from src.session_manager import SessionManager

    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    manager = SessionManager(paths)

    session_id = args.session_id

    if not session_id:
        session_id = manager.get_current_session()
        if not session_id:
            print("No current session. Specify a session ID or start a workflow.")
            return

    # Check session exists
    session_dir = paths.orchestrator_dir / "sessions" / session_id
    if not session_dir.exists():
        print(f"Session not found: {session_id}")
        print(f"\nUse 'orchestrator workflow list' to see available sessions.")
        return

    details = _get_session_details(session_dir)
    current = manager.get_current_session()
    is_current = session_id == current

    print(f"Session: {session_id}" + (" (current)" if is_current else ""))
    print(f"Task: {details['task']}")
    if details['created_at']:
        print(f"Created: {details['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Status: {details['status']}")
    if details['phase']:
        print(f"Phase: {details['phase']}" + (f" ({details['progress']})" if details['progress'] else ""))


def cmd_workflow_cleanup(args):
    """Remove old workflow sessions (CORE-025 Phase 3)."""
    from src.path_resolver import OrchestratorPaths
    from src.session_manager import SessionManager

    working_dir = Path(args.dir or '.')
    paths = OrchestratorPaths(base_dir=working_dir)
    manager = SessionManager(paths)

    sessions = manager.list_sessions()
    current_session = manager.get_current_session()

    if not sessions:
        print("No workflow sessions found.")
        return

    older_than_days = args.older_than
    status_filter = args.status
    dry_run = args.dry_run
    skip_confirm = args.yes

    # Find sessions to remove
    to_remove = []
    cutoff_date = datetime.now() - timedelta(days=older_than_days)

    for sid in sessions:
        # Never remove current session
        if sid == current_session:
            continue

        session_dir = paths.orchestrator_dir / "sessions" / sid
        details = _get_session_details(session_dir)

        # Check age filter
        if details['created_at']:
            from datetime import timezone
            created = details['created_at']
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            cutoff = cutoff_date.replace(tzinfo=timezone.utc)
            if created > cutoff:
                continue

        # Check status filter
        if status_filter and status_filter != 'all':
            if details['status'] != status_filter:
                continue

        to_remove.append((sid, details))

    if not to_remove:
        print("No sessions match the cleanup criteria.")
        if current_session:
            print(f"(Current session '{current_session}' is always protected)")
        return

    # Show what will be removed
    print(f"Found {len(to_remove)} session(s) to remove:")
    print("")
    for sid, details in to_remove:
        age = ""
        if details['created_at']:
            days_old = (datetime.now() - details['created_at'].replace(tzinfo=None)).days
            age = f" - {days_old}d old"
        print(f"  {sid} - {details['status']}{age}")
    print("")

    if dry_run:
        print("(dry-run mode - no sessions removed)")
        return

    # Confirm (Issue #61: fail-fast in non-interactive mode)
    try:
        if not confirm("Remove these sessions? [y/N]: ", yes_flag=skip_confirm):
            print("Cancelled.")
            return
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    # Remove sessions
    removed = 0
    for sid, _ in to_remove:
        if manager.delete_session(sid):
            removed += 1

    print(f"Removed {removed} session(s).")


def cmd_feedback_capture(args):
    """Capture workflow feedback (WF-034 Phase 3b - Two-tier system)."""
    # Check opt-out
    if os.environ.get('ORCHESTRATOR_SKIP_FEEDBACK') == '1':
        print("Feedback capture disabled (ORCHESTRATOR_SKIP_FEEDBACK=1)")
        return

    working_dir = Path(args.dir or '.')

    # Phase 3b: Run migration if needed
    migrate_legacy_feedback(working_dir)

    state_file = working_dir / '.workflow_state.json'
    log_file = working_dir / '.workflow_log.jsonl'
    tool_feedback_file = working_dir / '.workflow_tool_feedback.jsonl'
    process_feedback_file = working_dir / '.workflow_process_feedback.jsonl'

    # Get mode
    is_interactive = getattr(args, 'interactive', False)
    mode = 'interactive' if is_interactive else 'auto'

    feedback = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mode': mode,
    }

    # Load workflow state if available
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
                feedback['workflow_id'] = state.get('id', 'unknown')
                feedback['task'] = state.get('task', '')

                # Get repo from git remote
                try:
                    import subprocess
                    result = subprocess.run(['git', 'remote', 'get-url', 'origin'],
                                          capture_output=True, text=True, cwd=working_dir)
                    if result.returncode == 0:
                        feedback['repo'] = result.stdout.strip()
                    else:
                        feedback['repo'] = 'unknown'
                except:
                    feedback['repo'] = 'unknown'

        except Exception as e:
            print(f"Warning: Could not load workflow state: {e}")
            feedback['workflow_id'] = 'unknown'
    else:
        print("Warning: No active workflow found (.workflow_state.json missing)")
        feedback['workflow_id'] = 'unknown'

    if is_interactive:
        # Interactive mode - prompt questions
        print("\n=== Workflow Feedback (Interactive Mode) ===\n")

        # Combined questions (tool + process)
        print("1. Did you use parallel agents for this workflow?")
        parallel = input("   (yes/no/not-applicable): ").strip().lower()
        feedback['parallel_agents_used'] = parallel == 'yes'

        print("\n2. Were external AI reviews performed?")
        reviews = input("   (yes/no/skipped): ").strip().lower()
        feedback['reviews_performed'] = reviews == 'yes'

        print("\n3. What went well in this workflow?")
        feedback['what_went_well'] = input("   ").strip()

        print("\n4. What challenges did you face?")
        feedback['challenges'] = input("   ").strip()

        print("\n5. What did you learn?")
        feedback['learnings'] = input("   ").strip()

        print("\n6. Any improvements or suggestions?")
        feedback['improvements'] = input("   ").strip()

    else:
        # Auto mode - infer from logs
        feedback['parallel_agents_used'] = False
        feedback['reviews_performed'] = False
        feedback['errors_count'] = 0
        feedback['errors_summary'] = []
        feedback['items_skipped_count'] = 0
        feedback['items_skipped_reasons'] = []
        feedback['learnings'] = ''
        feedback['duration_seconds'] = 0
        feedback['phases'] = {}

        if log_file.exists():
            try:
                phase_timings = {}
                first_timestamp = None
                last_timestamp = None
                learnings_notes = []

                with open(log_file) as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_type = event.get('type')

                            # Track timestamps
                            ts = event.get('timestamp')
                            if ts:
                                if first_timestamp is None:
                                    first_timestamp = ts
                                last_timestamp = ts

                            # Check for errors
                            if event_type == 'error':
                                feedback['errors_count'] += 1
                                error_msg = event.get('error', 'Unknown error')
                                feedback['errors_summary'].append(error_msg)

                            # Check for skipped items
                            if event_type == 'item_skipped':
                                feedback['items_skipped_count'] += 1
                                item_id = event.get('item_id', 'unknown')
                                reason = event.get('reason', 'No reason provided')
                                feedback['items_skipped_reasons'].append(f"{item_id}: {reason}")

                            # Check for parallel agents
                            if 'parallel' in str(event).lower():
                                feedback['parallel_agents_used'] = True

                            # Check for reviews (handle None item_id)
                            item_id = event.get('item_id') or ''
                            if event_type == 'review_completed' or 'review' in item_id:
                                feedback['reviews_performed'] = True

                            # Extract learnings from document_learnings item
                            if event.get('item_id') == 'document_learnings' and event_type == 'item_completed':
                                notes = event.get('details', {}).get('notes', '')
                                if notes:
                                    learnings_notes.append(notes)

                            # Track phase timings
                            if event_type == 'phase_started':
                                phase = event.get('phase')
                                if phase:
                                    phase_timings[phase] = {'start': ts}
                            elif event_type == 'phase_completed':
                                phase = event.get('phase')
                                if phase and phase in phase_timings:
                                    phase_timings[phase]['end'] = ts

                        except json.JSONDecodeError:
                            # Skip malformed lines
                            continue

                # Calculate duration
                if first_timestamp and last_timestamp:
                    try:
                        start = datetime.fromisoformat(first_timestamp.replace('Z', '+00:00'))
                        end = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                        feedback['duration_seconds'] = int((end - start).total_seconds())
                    except:
                        pass

                # Calculate phase durations
                for phase, times in phase_timings.items():
                    if 'start' in times and 'end' in times:
                        try:
                            start = datetime.fromisoformat(times['start'].replace('Z', '+00:00'))
                            end = datetime.fromisoformat(times['end'].replace('Z', '+00:00'))
                            feedback['phases'][phase] = int((end - start).total_seconds())
                        except:
                            pass

                # Combine learnings
                if learnings_notes:
                    feedback['learnings'] = ' '.join(learnings_notes)

            except Exception as e:
                print(f"Warning: Could not parse workflow log: {e}")

    # Phase 3b: Split and save to two-tier system
    try:
        # Detect repo type
        repo_type = detect_repo_type(working_dir)

        # Extract tool feedback and anonymize
        tool_data = extract_tool_feedback_from_entry(feedback)
        tool_data['repo_type'] = repo_type

        # Add orchestrator version
        try:
            from . import __version__
            tool_data['orchestrator_version'] = __version__
        except:
            tool_data['orchestrator_version'] = 'unknown'

        anonymized_tool = anonymize_tool_feedback(tool_data)

        # Extract process feedback (keep full context)
        process_data = extract_process_feedback_from_entry(feedback)

        # Save to both files
        with open(tool_feedback_file, 'a') as f:
            f.write(json.dumps(anonymized_tool) + '\n')

        with open(process_feedback_file, 'a') as f:
            f.write(json.dumps(process_data) + '\n')

        print(f"\n✓ Feedback saved:")
        print(f"  • Tool feedback:    {tool_feedback_file.name} (anonymized, shareable)")
        print(f"  • Process feedback: {process_feedback_file.name} (private, local)")

    except Exception as e:
        print(f"\n✗ Error saving feedback: {e}")
        sys.exit(1)


def cmd_feedback_review(args):
    """Review workflow feedback patterns (WF-034 Phase 3b - Two-tier system)."""
    working_dir = Path(args.dir or '.')

    # Phase 3b: Run migration if needed
    migrate_legacy_feedback(working_dir)

    # Determine which files to load based on flags
    show_tool = getattr(args, 'tool', False)
    show_process = getattr(args, 'process', False)

    # Default: show both if no flags specified
    if not show_tool and not show_process:
        show_tool = True
        show_process = True

    tool_feedback_file = working_dir / '.workflow_tool_feedback.jsonl'
    process_feedback_file = working_dir / '.workflow_process_feedback.jsonl'

    # Load feedback entries from appropriate files
    entries = []
    feedback_types = []

    if show_tool and tool_feedback_file.exists():
        try:
            with open(tool_feedback_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        entry['_feedback_type'] = 'tool'
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            feedback_types.append('tool')
        except Exception as e:
            print(f"Warning: Error reading tool feedback file: {e}")

    if show_process and process_feedback_file.exists():
        try:
            with open(process_feedback_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        entry['_feedback_type'] = 'process'
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            feedback_types.append('process')
        except Exception as e:
            print(f"Warning: Error reading process feedback file: {e}")

    if not entries:
        print("No feedback data found. Run workflows to collect feedback.")
        if show_tool:
            print(f"Expected file: {tool_feedback_file}")
        if show_process:
            print(f"Expected file: {process_feedback_file}")
        return

    if not entries:
        print("No feedback entries found")
        return

    # Filter by date range
    cutoff_date = None
    if not args.all:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days)

    filtered_entries = []
    for entry in entries:
        if cutoff_date:
            try:
                ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                if ts >= cutoff_date:
                    filtered_entries.append(entry)
            except:
                filtered_entries.append(entry)  # Include if can't parse timestamp
        else:
            filtered_entries.append(entry)

    if not filtered_entries:
        print(f"No feedback entries found in the last {args.days} days")
        return

    # Display summary
    print("=" * 60)
    if args.all:
        print(f"Feedback Review (all time, {len(filtered_entries)} workflows)")
    else:
        print(f"Feedback Review (last {args.days} days, {len(filtered_entries)} workflows)")
    print("=" * 60)
    print()

    # Calculate statistics
    parallel_count = sum(1 for e in filtered_entries if e.get('parallel_agents_used', False))
    reviews_count = sum(1 for e in filtered_entries if e.get('reviews_performed', False))
    total_errors = sum(e.get('errors_count', 0) for e in filtered_entries)
    total_skipped = sum(e.get('items_skipped_count', 0) for e in filtered_entries)

    # Pattern detection
    error_patterns = {}
    skip_patterns = {}
    challenges = []
    learnings = []

    for entry in filtered_entries:
        # Group errors
        for error in entry.get('errors_summary', []):
            error_patterns[error] = error_patterns.get(error, 0) + 1

        # Group skipped items
        for skip in entry.get('items_skipped_reasons', []):
            skip_patterns[skip] = skip_patterns.get(skip, 0) + 1

        # Collect challenges and learnings
        if entry.get('challenges'):
            challenges.append(entry['challenges'])
        if entry.get('learnings'):
            learnings.append(entry['learnings'])

    # Display patterns
    print("PATTERNS DETECTED:")
    print()

    # Parallel agent usage
    parallel_pct = int(100 * parallel_count / len(filtered_entries))
    if parallel_pct < 30:
        print(f"⚠ Parallel agents rarely used ({parallel_count} of {len(filtered_entries)}, {parallel_pct}%)")
        print("   → Suggestion: Improve Phase 0 guidance in workflow.yaml")
        print()
    else:
        print(f"✓ Parallel agents used: {parallel_count} of {len(filtered_entries)} ({parallel_pct}%)")
        print()

    # Reviews
    reviews_pct = int(100 * reviews_count / len(filtered_entries))
    if reviews_pct < 50:
        print(f"⚠ Reviews rarely performed ({reviews_count} of {len(filtered_entries)}, {reviews_pct}%)")
        print("   → Suggestion: Add review reminders or enforcement")
        print()
    else:
        print(f"✓ Reviews performed consistently ({reviews_count} of {len(filtered_entries)}, {reviews_pct}%)")
        print()

    # Common errors
    if error_patterns:
        common_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:5]
        if common_errors[0][1] >= 2:
            print("⚠ Common errors detected:")
            for error, count in common_errors:
                if count >= 2:
                    print(f"   • \"{error[:60]}{'...' if len(error) > 60 else ''}\" ({count} occurrences)")
            print("   → Suggestion: Add roadmap items to address these errors")
            print()

    # Frequently skipped items
    if skip_patterns:
        common_skips = sorted(skip_patterns.items(), key=lambda x: x[1], reverse=True)[:5]
        skip_threshold = int(0.8 * len(filtered_entries))
        if common_skips[0][1] >= skip_threshold:
            print("⚠ Frequently skipped items:")
            for skip, count in common_skips:
                if count >= skip_threshold:
                    pct = int(100 * count / len(filtered_entries))
                    print(f"   • {skip[:60]}{'...' if len(skip) > 60 else ''} ({pct}%)")
            print("   → Suggestion: Consider making these items optional or removing them")
            print()

    # Summary stats
    print("SUMMARY:")
    print(f"  • Total workflows: {len(filtered_entries)}")
    print(f"  • Total errors encountered: {total_errors}")
    print(f"  • Total items skipped: {total_skipped}")
    print(f"  • Avg duration: {int(sum(e.get('duration_seconds', 0) for e in filtered_entries) / len(filtered_entries) / 60)} min")
    print()

    # Common challenges
    if challenges:
        print("COMMON CHALLENGES:")
        for i, challenge in enumerate(challenges[:5], 1):
            print(f"  {i}. {challenge}")
        print()

    # Learnings
    if learnings:
        print("LEARNINGS:")
        for i, learning in enumerate(learnings[:5], 1):
            print(f"  {i}. {learning}")
        print()

    # Suggest mode
    if args.suggest:
        suggestions = []

        # Generate suggestions from patterns
        if parallel_pct < 30:
            suggestions.append({
                'title': 'Improve Phase 0 parallel execution guidance',
                'description': f'Only {parallel_pct}% of workflows use parallel agents. Enhance prompts and examples.',
                'complexity': 'LOW'
            })

        if reviews_pct < 50:
            suggestions.append({
                'title': 'Add review enforcement or reminders',
                'description': f'Only {reviews_pct}% of workflows perform reviews. Consider making reviews mandatory.',
                'complexity': 'MEDIUM'
            })

        # Suggest fixes for common errors
        for error, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:3]:
            if count >= 2:
                suggestions.append({
                    'title': f'Fix common error: {error[:50]}',
                    'description': f'This error occurred in {count} workflows. Investigate and fix root cause.',
                    'complexity': 'MEDIUM'
                })

        if suggestions:
            print("=" * 60)
            print(f"ROADMAP SUGGESTIONS ({len(suggestions)} items)")
            print("=" * 60)
            print()
            for i, sugg in enumerate(suggestions, 1):
                print(f"{i}. {sugg['title']}")
                print(f"   {sugg['description']}")
                print(f"   Complexity: {sugg['complexity']}")
                print()

            # Issue #61: fail-fast in non-interactive mode
            if not is_interactive():
                print("\nSkipping ROADMAP update in non-interactive mode.")
                print("Run interactively to add suggestions, or add manually.")
                return
            response = input(f"Add {len(suggestions)} suggestions to ROADMAP.md? (y/n): ").strip().lower()
            if response == 'y':
                roadmap_file = working_dir / 'ROADMAP.md'
                try:
                    with open(roadmap_file, 'a') as f:
                        f.write(f"\n## Feedback-Generated Suggestions ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n\n")
                        for sugg in suggestions:
                            f.write(f"### {sugg['title']}\n")
                            f.write(f"**Complexity:** {sugg['complexity']}\n")
                            f.write(f"{sugg['description']}\n\n")
                    print(f"\n✓ Added {len(suggestions)} suggestions to ROADMAP.md")
                except Exception as e:
                    print(f"\n✗ Error updating ROADMAP.md: {e}")
        else:
            print("No suggestions generated - patterns look good!")


def cmd_feedback_sync(args):
    """Upload anonymized tool feedback to GitHub Gist (WF-034 Phase 3b)."""
    import requests
    from datetime import datetime

    working_dir = Path(args.dir or '.')
    tool_feedback_file = working_dir / '.workflow_tool_feedback.jsonl'

    # Check if tool feedback file exists
    if not tool_feedback_file.exists():
        print("✗ No tool feedback found")
        print(f"Expected file: {tool_feedback_file}")
        print("\nRun workflows and capture feedback first:")
        print("  orchestrator feedback")
        sys.exit(1)

    # Check GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token and not args.status and not args.dry_run:
        print("✗ GITHUB_TOKEN not set. Required for sync.")
        print("\nSetup:")
        print("1. Create token: https://github.com/settings/tokens")
        print("   Scopes needed: 'gist' (create/update gists)")
        print("2. Set token: export GITHUB_TOKEN=ghp_xxx")
        print("3. Retry: orchestrator feedback sync")
        print("\nOr use --dry-run to preview what would be uploaded:")
        print("  orchestrator feedback sync --dry-run")
        sys.exit(1)

    # Load tool feedback entries
    entries = []
    try:
        with open(tool_feedback_file) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"✗ Error reading tool feedback: {e}")
        sys.exit(1)

    if not entries:
        print("No tool feedback entries found")
        return

    # Status mode
    if args.status:
        synced = sum(1 for e in entries if 'synced_at' in e)
        unsynced = len(entries) - synced
        print("Sync Status:")
        print(f"  • Total entries:   {len(entries)}")
        print(f"  • Synced:          {synced}")
        print(f"  • Pending sync:    {unsynced}")
        return

    # Force mode: remove synced_at timestamps
    if args.force:
        print("Force mode: Re-syncing all entries...")
        for entry in entries:
            if 'synced_at' in entry:
                del entry['synced_at']

    # Filter unsynced entries
    unsynced_entries = [e for e in entries if 'synced_at' not in e]

    if not unsynced_entries:
        print("✓ No new entries to sync (all up to date)")
        print("\nUse --force to re-sync all entries:")
        print("  orchestrator feedback sync --force")
        return

    # Dry run mode
    if args.dry_run:
        print(f"Dry Run - Would upload {len(unsynced_entries)} entries:")
        print()
        for i, entry in enumerate(unsynced_entries[:3], 1):
            print(f"Entry {i}:")
            print(json.dumps(entry, indent=2))
            print()
        if len(unsynced_entries) > 3:
            print(f"... and {len(unsynced_entries) - 3} more entries")
            print()
        print("No data was uploaded (dry run mode).")
        print("\nTo upload, run:")
        print("  orchestrator feedback sync")
        return

    # Verify anonymization
    print(f"Verifying anonymization of {len(unsynced_entries)} entries...")
    for entry in unsynced_entries:
        # Check for PII
        entry_str = json.dumps(entry).lower()
        if 'task' in entry or 'repo' in entry:
            print("✗ PII detected in tool feedback!")
            print("  Entry contains 'task' or 'repo' fields")
            print("  This should not happen - feedback not anonymized properly")
            sys.exit(1)

    print("✓ Anonymization verified")

    # Upload to GitHub Gist
    print(f"\nUploading {len(unsynced_entries)} entries to GitHub Gist...")

    try:
        # Prepare gist content (all entries as JSON lines)
        gist_content = '\n'.join(json.dumps(e) for e in unsynced_entries)

        # Try to update existing gist first
        gist_api = 'https://api.github.com/gists'
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # Search for existing workflow-orchestrator feedback gist
        print("Checking for existing gist...")
        response = requests.get(gist_api, headers=headers)
        response.raise_for_status()

        existing_gist_id = None
        for gist in response.json():
            if gist.get('description') == 'workflow-orchestrator tool feedback':
                existing_gist_id = gist['id']
                print(f"Found existing gist: {gist['html_url']}")
                break

        if existing_gist_id:
            # Update existing gist (append)
            print("Appending to existing gist...")
            gist_url = f"{gist_api}/{existing_gist_id}"
            get_response = requests.get(gist_url, headers=headers)
            get_response.raise_for_status()

            existing_content = get_response.json()['files']['tool_feedback.jsonl']['content']
            updated_content = existing_content + '\n' + gist_content

            payload = {
                'files': {
                    'tool_feedback.jsonl': {
                        'content': updated_content
                    }
                }
            }

            response = requests.patch(gist_url, headers=headers, json=payload)
            response.raise_for_status()
        else:
            # Create new gist
            print("Creating new gist...")
            payload = {
                'description': 'workflow-orchestrator tool feedback',
                'public': False,
                'files': {
                    'tool_feedback.jsonl': {
                        'content': gist_content
                    }
                }
            }

            response = requests.post(gist_api, headers=headers, json=payload)
            response.raise_for_status()

        gist_data = response.json()
        print(f"✓ Uploaded successfully: {gist_data['html_url']}")

        # Mark entries as synced
        now = datetime.now(timezone.utc).isoformat()
        for entry in entries:
            if 'synced_at' not in entry:
                entry['synced_at'] = now

        # Write back to file with synced_at timestamps
        with open(tool_feedback_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        print(f"✓ Marked {len(unsynced_entries)} entries as synced")

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            print("\n✗ GitHub API rate limit exceeded")
            if 'X-RateLimit-Reset' in e.response.headers:
                reset_time = datetime.fromtimestamp(int(e.response.headers['X-RateLimit-Reset']))
                print(f"  Rate limit resets at: {reset_time} UTC")
            print("\nWait and try again later.")
        else:
            print(f"\n✗ GitHub API error: {e}")
            print(f"  Status code: {e.response.status_code}")
            print(f"  Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error uploading to GitHub: {e}")
        sys.exit(1)


# =============================================================================
# Task Commands (Issue #56)
# =============================================================================


def cmd_task_list(args):
    """List tasks from configured backend."""
    try:
        # Get provider (auto-detect if not specified - #64)
        provider_name = getattr(args, 'provider', None)
        provider = get_task_provider(provider_name)

        # Build filters
        status = TaskStatus(args.status) if args.status else None
        priority = TaskPriority(args.priority) if args.priority else None

        tasks = provider.list_tasks(status=status, priority=priority)

        if not tasks:
            print("No tasks found.")
            return

        # Display tasks
        print(f"{'ID':<6} {'Priority':<10} {'Status':<12} {'Title'}")
        print("-" * 60)
        for task in tasks:
            priority_str = task.priority.value if task.priority else "---"
            print(f"{task.id:<6} {priority_str:<10} {task.status.value:<12} {task.title[:40]}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_task_next(args):
    """Show the highest priority open task."""
    try:
        # Auto-detect provider if not specified (#64)
        provider_name = getattr(args, 'provider', None)
        provider = get_task_provider(provider_name)

        task = provider.get_next_task()

        if not task:
            print("No open tasks.")
            return

        print(f"Next task (ID: {task.id}):")
        print(f"  Title: {task.title}")
        print(f"  Priority: {task.priority.value if task.priority else 'N/A'}")
        print(f"  Status: {task.status.value}")
        if task.url:
            print(f"  URL: {task.url}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_task_add(args):
    """Quick add a task with minimal prompts."""
    try:
        # Auto-detect provider if not specified (#64)
        provider_name = getattr(args, 'provider', None)
        provider = get_task_provider(provider_name)

        # Map priority string to enum
        priority_map = {
            'P0': TaskPriority.CRITICAL,
            'P1': TaskPriority.HIGH,
            'P2': TaskPriority.MEDIUM,
            'P3': TaskPriority.LOW,
        }
        priority = priority_map.get(args.priority, TaskPriority.MEDIUM)

        template = TaskTemplate(
            title=args.title,
            description=args.description or args.title,
            problem_solved=args.description or "Task to be completed",
            priority=priority,
            labels=args.labels.split(',') if args.labels else [],
        )

        task = provider.create_task(template)

        print(f"✓ Task created (ID: {task.id})")
        print(f"  Title: {task.title}")
        print(f"  Priority: {task.priority.value if task.priority else 'N/A'}")
        if task.url:
            print(f"  URL: {task.url}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_task_close(args):
    """Close a task by ID."""
    try:
        # Auto-detect provider if not specified (#64)
        provider_name = getattr(args, 'provider', None)
        provider = get_task_provider(provider_name)

        task = provider.close_task(args.task_id, comment=args.comment)

        print(f"✓ Task {task.id} closed")
        print(f"  Title: {task.title}")

    except KeyError:
        print(f"Error: Task {args.task_id} not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_task_show(args):
    """Show details of a specific task."""
    try:
        # Auto-detect provider if not specified (#64)
        provider_name = getattr(args, 'provider', None)
        provider = get_task_provider(provider_name)

        task = provider.get_task(args.task_id)

        if not task:
            print(f"Error: Task {args.task_id} not found")
            sys.exit(1)

        print(f"Task {task.id}:")
        print(f"  Title: {task.title}")
        print(f"  Status: {task.status.value}")
        print(f"  Priority: {task.priority.value if task.priority else 'N/A'}")
        if task.labels:
            print(f"  Labels: {', '.join(task.labels)}")
        if task.url:
            print(f"  URL: {task.url}")
        print()
        print("Description:")
        print(task.body[:500] if task.body else "(no description)")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_heal(args):
    """Handle heal subcommand."""
    from src.healing.cli_heal import (
        heal_status,
        heal_apply,
        heal_ignore,
        heal_unquarantine,
        heal_explain,
        heal_export,
        heal_backfill,
    )

    heal_action = args.heal_action

    if heal_action == 'status':
        sys.exit(heal_status())

    elif heal_action == 'apply':
        if not args.fix_id:
            print("Error: fix_id is required")
            sys.exit(1)
        sys.exit(heal_apply(
            args.fix_id,
            force=getattr(args, 'force', False),
            dry_run=getattr(args, 'dry_run', False)
        ))

    elif heal_action == 'ignore':
        if not args.fingerprint:
            print("Error: fingerprint is required")
            sys.exit(1)
        reason = getattr(args, 'reason', None)
        if not reason:
            print("Error: --reason is required for ignore")
            sys.exit(1)
        sys.exit(heal_ignore(args.fingerprint, reason))

    elif heal_action == 'unquarantine':
        if not args.fingerprint:
            print("Error: fingerprint is required")
            sys.exit(1)
        reason = getattr(args, 'reason', None)
        if not reason:
            print("Error: --reason is required for unquarantine")
            sys.exit(1)
        sys.exit(heal_unquarantine(args.fingerprint, reason))

    elif heal_action == 'explain':
        if not args.fingerprint:
            print("Error: fingerprint is required")
            sys.exit(1)
        sys.exit(heal_explain(args.fingerprint))

    elif heal_action == 'export':
        sys.exit(heal_export(
            format=getattr(args, 'format', 'yaml'),
            output=getattr(args, 'output', None)
        ))

    elif heal_action == 'backfill':
        sys.exit(heal_backfill(
            log_dir=getattr(args, 'log_dir', None),
            dry_run=getattr(args, 'dry_run', False),
            limit=getattr(args, 'limit', None)
        ))

    else:
        print(f"Unknown heal action: {heal_action}")
        sys.exit(1)


def cmd_issues(args):
    """Handle issues subcommand."""
    from src.healing.cli_issues import (
        issues_list,
        issues_review,
    )

    issues_action = args.issues_action

    if issues_action == 'list':
        sys.exit(issues_list(
            status=getattr(args, 'status', None),
            severity=getattr(args, 'severity', None),
            limit=getattr(args, 'limit', 20)
        ))

    elif issues_action == 'review':
        sys.exit(issues_review())

    else:
        print(f"Unknown issues action: {issues_action}")
        sys.exit(1)


def main():
    # V3 Phase 0: Log operator mode for audit
    log_mode_detection()

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
    start_parser.add_argument('--test-command', dest='test_command',
                              help='Override test command (e.g., "pytest -v")')
    start_parser.add_argument('--build-command', dest='build_command',
                              help='Override build command (e.g., "pip install -e .")')
    start_parser.add_argument('--isolated', action='store_true',
                              help='Create git worktree for isolated execution (CORE-025)')
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
    resolve_parser.add_argument('--use-llm', action='store_true',
                                help='Use LLM for complex conflict resolution (CORE-023-P2)')
    resolve_parser.add_argument('--auto-apply-threshold', type=float, default=0.8,
                                help='Confidence threshold for auto-applying LLM resolutions (default: 0.8)')
    resolve_parser.add_argument('--confirm-all', action='store_true',
                                help='Require confirmation for all LLM resolutions regardless of confidence')
    resolve_parser.add_argument('--dir', '-d', default='.',
                                help='Working directory (default: current directory)')
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
    skip_parser.add_argument('--force', '-f', action='store_true',
                             help='Force skip gate items (requires detailed reason)')
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
    finish_parser.add_argument('--force', action='store_true', dest='skip_item_check',
                              help='Skip incomplete items check (finish even if required items not done)')
    finish_parser.add_argument('--no-push', action='store_true', dest='no_push',
                              help='Skip auto-push to remote (CORE-031)')
    finish_parser.add_argument('--continue', action='store_true', dest='continue_sync',
                              help='Continue after resolving sync conflicts (CORE-031)')
    finish_parser.add_argument('--no-close-issues', action='store_true', dest='no_close_issues',
                              help='Skip auto-closing GitHub issues referenced in task description')
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
    # Issue #65: Use registry as single source of truth for review type choices
    review_choices = list(get_all_review_types()) + ['all']
    review_parser = subparsers.add_parser('review', help='Run AI code reviews')
    review_parser.add_argument('review_type', nargs='?',
                               choices=review_choices,
                               default='all', help='Review type to run (default: all)')
    review_parser.add_argument('--method', '-m', choices=['auto', 'cli', 'aider', 'api'],
                               default='auto', help='Execution method (default: auto-detect)')
    review_parser.add_argument('--no-fallback', action='store_true',
                               help='Disable model fallback on transient failures (CORE-028b)')
    review_parser.add_argument('--json', action='store_true', help='Output as JSON')
    review_parser.set_defaults(func=cmd_review)

    # Review-status command
    review_status_parser = subparsers.add_parser('review-status', help='Show review infrastructure status')
    review_status_parser.set_defaults(func=cmd_review_status)

    # Review-results command
    review_results_parser = subparsers.add_parser('review-results', help='Show results of completed reviews')
    review_results_parser.add_argument('--json', action='store_true', help='Output as JSON')
    review_results_parser.set_defaults(func=cmd_review_results)

    # Review-retry command (CORE-026)
    review_retry_parser = subparsers.add_parser('review-retry', help='Retry failed reviews after fixing API keys')
    review_retry_parser.add_argument('--method', '-m', choices=['auto', 'cli', 'aider', 'api'],
                                     default='auto', help='Execution method (default: auto-detect)')
    review_retry_parser.add_argument('--no-fallback', action='store_true',
                                     help='Disable model fallback on transient failures (CORE-028b)')
    review_retry_parser.set_defaults(func=cmd_review_retry)

    # Setup-reviews command
    setup_reviews_parser = subparsers.add_parser('setup-reviews', help='Set up review infrastructure in a repository')
    setup_reviews_parser.add_argument('--dry-run', action='store_true', help='Show what would be created without writing')
    setup_reviews_parser.add_argument('--skip-actions', action='store_true', help='Skip GitHub Actions workflow creation')
    setup_reviews_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing files')
    setup_reviews_parser.set_defaults(func=cmd_setup_reviews)

    # Validate-adherence command (WF-034 Phase 2)
    validate_adherence_parser = subparsers.add_parser('validate-adherence',
        help='Validate workflow adherence (parallel execution, reviews, verification, etc.)')
    validate_adherence_parser.add_argument('--workflow', '-w', help='Workflow ID (default: current workflow)')
    validate_adherence_parser.add_argument('--json', action='store_true', help='Output as JSON')
    validate_adherence_parser.set_defaults(func=cmd_validate_adherence)

    # Setup command (auto-updates)
    setup_parser = subparsers.add_parser('setup', help='Enable automatic updates for this repo')
    setup_parser.add_argument('--dir', '-d', help='Target directory (default: current)')
    setup_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing setup')
    setup_parser.add_argument('--remove', action='store_true', help='Remove auto-updates from this repo')
    setup_parser.add_argument('--copy-secrets', action='store_true', help='Copy encrypted secrets from orchestrator repo')
    setup_parser.set_defaults(func=cmd_setup)

    # Enforce command (PRD-008: Zero-Config Workflow Enforcement)
    enforce_parser = subparsers.add_parser('enforce',
        help='Zero-config workflow enforcement (auto-start server, generate workflow.yaml)')
    enforce_parser.add_argument('task', help='Task description')
    enforce_parser.add_argument('--parallel', action='store_true',
        help='Use parallel execution mode (spawn multiple agents)')
    enforce_parser.add_argument('--sequential', action='store_true',
        help='Use sequential mode (single agent, default)')
    enforce_parser.add_argument('--port', type=int, default=8000,
        help='Orchestrator server port (default: 8000)')
    enforce_parser.add_argument('--json', action='store_true',
        help='Output JSON for programmatic parsing')
    enforce_parser.add_argument('--dir', '-d', help='Working directory (default: current)')
    enforce_parser.set_defaults(func=cmd_enforce)

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage orchestrator configuration')
    config_parser.add_argument('action', choices=['set', 'get', 'list'], help='Config action')
    config_parser.add_argument('key', nargs='?', help='Configuration key')
    config_parser.add_argument('value', nargs='?', help='Configuration value (for set)')
    config_parser.set_defaults(func=cmd_config)

    # Doctor command (CORE-025 Phase 4)
    doctor_parser = subparsers.add_parser('doctor', help='Check worktree health and perform cleanup')
    doctor_parser.add_argument('--cleanup', action='store_true',
                               help='Remove orphaned worktrees')
    doctor_parser.add_argument('--fix', action='store_true',
                               help='Fix session metadata for missing worktrees')
    doctor_parser.add_argument('--older-than', type=int, default=0,
                               help='Only cleanup worktrees older than N days (default: 0 = all orphaned)')
    doctor_parser.set_defaults(func=cmd_doctor)

    # Health command (V3 Phase 5)
    health_parser = subparsers.add_parser('health', help='Check orchestrator system health')
    health_parser.add_argument('--json', action='store_true',
                               help='Output as JSON')
    health_parser.add_argument('-d', '--dir', help='Working directory')
    health_parser.set_defaults(func=cmd_health)

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

    # Sessions command (CORE-024)
    sessions_parser = subparsers.add_parser('sessions', help='Manage session transcripts')
    sessions_parser.add_argument('action', choices=['list', 'show', 'clean', 'analyze'], help='Sessions action')
    sessions_parser.add_argument('session_id', nargs='?', help='Session ID (for show)')
    sessions_parser.add_argument('--limit', type=int, default=20, help='Max sessions to list (default: 20)')
    sessions_parser.add_argument('--older', type=int, default=30, help='Remove sessions older than N days (default: 30)')
    sessions_parser.add_argument('--days', type=int, default=30, help='Analyze sessions from last N days (default: 30)')
    sessions_parser.add_argument('--last', type=int, help='Analyze last N sessions')
    sessions_parser.add_argument('-d', '--dir', help='Working directory')
    sessions_parser.set_defaults(func=cmd_sessions)

    # Approval command (Parallel Agent Coordination)
    approval_parser = subparsers.add_parser('approval', help='Manage parallel agent approval requests')
    approval_parser.add_argument('approval_action',
                                 choices=['pending', 'approve', 'reject', 'approve-all', 'stats', 'cleanup', 'watch', 'summary'],
                                 help='Approval action')
    approval_parser.add_argument('request_id', nargs='?', help='Request ID (for approve/reject)')
    approval_parser.add_argument('--reason', help='Reason for approval/rejection')
    approval_parser.add_argument('--days', type=int, default=7, help='Cleanup records older than N days (default: 7)')
    approval_parser.add_argument('--once', action='store_true', help='Check once and exit (for watch)')
    approval_parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds (for watch)')
    approval_parser.add_argument('-d', '--dir', help='Working directory')
    approval_parser.set_defaults(func=cmd_approval)

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
    # check-backend (was check-squad)
    prd_check_backend = prd_subparsers.add_parser('check-backend', help='Check execution backend availability')
    prd_check_backend.set_defaults(func=cmd_prd_check_backend)

    # prd spawn
    prd_spawn = prd_subparsers.add_parser('spawn', help='Spawn next wave of tasks via Claude Squad')
    prd_spawn.add_argument('--prd-file', required=True, help='Path to PRD YAML file')
    prd_spawn.add_argument('--explain', action='store_true', help='Show wave groupings without spawning')
    prd_spawn.add_argument('--dry-run', action='store_true', help='Show what would be spawned without acting')
    prd_spawn.add_argument('--force', metavar='TASK_ID', help='Force spawn specific task (bypasses scheduler)')
    prd_spawn.add_argument('--no-approval-gate', action='store_true', help='Disable automatic approval gate injection in prompts')
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

    # Workflow session command (CORE-025 Phase 3)
    workflow_parser = subparsers.add_parser('workflow', help='Manage workflow sessions (CORE-025)')
    workflow_subparsers = workflow_parser.add_subparsers(dest='workflow_command', help='Workflow session commands')

    # workflow list
    workflow_list = workflow_subparsers.add_parser('list', help='List all workflow sessions')
    workflow_list.add_argument('-d', '--dir', help='Working directory')
    workflow_list.set_defaults(func=cmd_workflow_list)

    # workflow switch
    workflow_switch = workflow_subparsers.add_parser('switch', help='Switch to a different session')
    workflow_switch.add_argument('session_id', help='Session ID to switch to')
    workflow_switch.add_argument('-d', '--dir', help='Working directory')
    workflow_switch.set_defaults(func=cmd_workflow_switch)

    # workflow info
    workflow_info = workflow_subparsers.add_parser('info', help='Show session details')
    workflow_info.add_argument('session_id', nargs='?', help='Session ID (default: current)')
    workflow_info.add_argument('-d', '--dir', help='Working directory')
    workflow_info.set_defaults(func=cmd_workflow_info)

    # workflow cleanup
    workflow_cleanup = workflow_subparsers.add_parser('cleanup', help='Remove old sessions')
    workflow_cleanup.add_argument('--older-than', type=int, default=30, help='Days threshold (default: 30)')
    workflow_cleanup.add_argument('--status', choices=['abandoned', 'completed', 'all'], help='Filter by status')
    workflow_cleanup.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    workflow_cleanup.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')
    workflow_cleanup.add_argument('-d', '--dir', help='Working directory')
    workflow_cleanup.set_defaults(func=cmd_workflow_cleanup)

    workflow_parser.set_defaults(func=lambda args: workflow_parser.print_help() if not args.workflow_command else None)

    # Feedback command (WF-034 Phase 3a)
    feedback_parser = subparsers.add_parser('feedback', help='Capture workflow feedback')
    feedback_subparsers = feedback_parser.add_subparsers(dest='feedback_command', help='Feedback subcommands')

    # feedback capture (default subcommand)
    feedback_capture = feedback_subparsers.add_parser('capture', help='Capture workflow feedback (default)')
    feedback_capture.add_argument('--auto', action='store_true', help='Auto mode: infer from logs (default)')
    feedback_capture.add_argument('--interactive', action='store_true', help='Interactive mode: prompt questions')
    feedback_capture.add_argument('-d', '--dir', help='Working directory')
    feedback_capture.set_defaults(func=cmd_feedback_capture)

    # feedback review
    feedback_review = feedback_subparsers.add_parser('review', help='Review feedback patterns')
    feedback_review.add_argument('--days', type=int, default=7, help='Days to review (default: 7)')
    feedback_review.add_argument('--all', action='store_true', help='Review all feedback')
    feedback_review.add_argument('--suggest', action='store_true', help='Suggest roadmap items from patterns')
    feedback_review.add_argument('--tool', action='store_true', help='Review tool feedback only (anonymized)')
    feedback_review.add_argument('--process', action='store_true', help='Review process feedback only (private)')
    feedback_review.add_argument('-d', '--dir', help='Working directory')
    feedback_review.set_defaults(func=cmd_feedback_review)

    # feedback sync (Phase 3b)
    feedback_sync = feedback_subparsers.add_parser('sync', help='Upload anonymized tool feedback to GitHub Gist')
    feedback_sync.add_argument('--dry-run', action='store_true', help='Show what would be uploaded without uploading')
    feedback_sync.add_argument('--force', action='store_true', help='Re-sync all entries (remove synced_at timestamps)')
    feedback_sync.add_argument('--status', action='store_true', help='Show sync statistics')
    feedback_sync.add_argument('-d', '--dir', help='Working directory')
    feedback_sync.set_defaults(func=lambda args: cmd_feedback_sync(args))

    # Default to capture if no subcommand
    feedback_parser.set_defaults(func=lambda args: cmd_feedback_capture(args) if not args.feedback_command else None)

    # Task command (Issue #56)
    task_parser = subparsers.add_parser('task', help='Manage tasks/issues (Issue #56)')
    task_subparsers = task_parser.add_subparsers(dest='task_command', help='Task subcommands')

    # task list
    task_list = task_subparsers.add_parser('list', help='List tasks')
    task_list.add_argument('--status', '-s', choices=['open', 'in_progress', 'blocked', 'closed'],
                           help='Filter by status')
    task_list.add_argument('--priority', '-p', choices=['P0', 'P1', 'P2', 'P3'],
                           help='Filter by priority')
    task_list.add_argument('--provider', choices=['local', 'github'],
                           help='Task provider (default: local)')
    task_list.set_defaults(func=cmd_task_list)

    # task next
    task_next = task_subparsers.add_parser('next', help='Show highest priority open task')
    task_next.add_argument('--provider', choices=['local', 'github'],
                           help='Task provider (default: local)')
    task_next.set_defaults(func=cmd_task_next)

    # task add (quick add)
    task_add = task_subparsers.add_parser('add', help='Quick add a task')
    task_add.add_argument('title', help='Task title')
    task_add.add_argument('--description', '-d', help='Task description')
    task_add.add_argument('--priority', '-p', choices=['P0', 'P1', 'P2', 'P3'],
                          default='P2', help='Priority (default: P2)')
    task_add.add_argument('--labels', '-l', help='Comma-separated labels')
    task_add.add_argument('--provider', choices=['local', 'github'],
                          help='Task provider (default: local)')
    task_add.set_defaults(func=cmd_task_add)

    # task close
    task_close = task_subparsers.add_parser('close', help='Close a task')
    task_close.add_argument('task_id', help='Task ID to close')
    task_close.add_argument('--comment', '-c', help='Completion comment')
    task_close.add_argument('--provider', choices=['local', 'github'],
                            help='Task provider (default: local)')
    task_close.set_defaults(func=cmd_task_close)

    # task show
    task_show = task_subparsers.add_parser('show', help='Show task details')
    task_show.add_argument('task_id', help='Task ID to show')
    task_show.add_argument('--provider', choices=['local', 'github'],
                           help='Task provider (default: local)')
    task_show.set_defaults(func=cmd_task_show)

    task_parser.set_defaults(func=lambda args: task_parser.print_help() if not args.task_command else None)

    # Heal command (Self-Healing Phase 4)
    heal_parser = subparsers.add_parser('heal', help='Self-healing system commands (Phase 4)')
    heal_parser.add_argument('heal_action',
                             choices=['status', 'apply', 'ignore', 'unquarantine', 'explain', 'export', 'backfill'],
                             help='Heal action')
    heal_parser.add_argument('fix_id', nargs='?', help='Fix ID (for apply)')
    heal_parser.add_argument('fingerprint', nargs='?', help='Pattern fingerprint (for ignore/unquarantine/explain)')
    heal_parser.add_argument('--reason', help='Reason for ignore/unquarantine')
    heal_parser.add_argument('--force', action='store_true', help='Force apply (bypass safety checks)')
    heal_parser.add_argument('--dry-run', action='store_true', help='Preview without applying')
    heal_parser.add_argument('--format', choices=['yaml', 'json'], default='yaml', help='Export format')
    heal_parser.add_argument('--output', '-o', help='Output file for export')
    heal_parser.add_argument('--log-dir', help='Log directory for backfill')
    heal_parser.add_argument('--limit', type=int, help='Limit for backfill')
    heal_parser.add_argument('-d', '--dir', help='Working directory')
    heal_parser.set_defaults(func=cmd_heal)

    # Issues command (Self-Healing Phase 4)
    issues_parser = subparsers.add_parser('issues', help='Issue management commands (Phase 4)')
    issues_parser.add_argument('issues_action',
                               choices=['list', 'review'],
                               help='Issues action')
    issues_parser.add_argument('--status', choices=['open', 'resolved', 'ignored'], help='Filter by status')
    issues_parser.add_argument('--severity', choices=['high', 'medium', 'low'], help='Filter by severity')
    issues_parser.add_argument('--limit', type=int, default=20, help='Max results (default: 20)')
    issues_parser.add_argument('-d', '--dir', help='Working directory')
    issues_parser.set_defaults(func=cmd_issues)

    # Natural language command (Issue #60)
    if NL_AVAILABLE:
        add_nl_subcommand(subparsers, "orchestrator")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
