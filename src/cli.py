#!/usr/bin/env python3
"""
Workflow Orchestrator CLI

Command-line interface for managing AI workflow enforcement.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engine import WorkflowEngine
from src.analytics import WorkflowAnalytics
from src.learning import LearningEngine
from src.dashboard import start_dashboard, generate_static_dashboard
from src.schema import WorkflowDef
from src.claude_integration import ClaudeCodeIntegration

VERSION = "1.0.0"


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
    engine = WorkflowEngine(args.dir or '.')
    
    yaml_path = Path(args.dir or '.') / (args.workflow or 'workflow.yaml')
    if not yaml_path.exists():
        print(f"Error: Workflow definition not found: {yaml_path}")
        sys.exit(1)
    
    try:
        state = engine.start_workflow(
            str(yaml_path),
            args.task,
            project=args.project
        )
        print(f"\n✓ Workflow started: {state.workflow_id}")
        print(f"  Task: {args.task}")
        print(f"  Phase: {state.current_phase_id}")
        print("\nRun 'orchestrator status' to see the checklist.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show current workflow status."""
    engine = get_engine(args)
    
    if args.json:
        print(json.dumps(engine.get_status(), indent=2, default=str))
    else:
        print(engine.get_recitation_text())


def cmd_complete(args):
    """Mark an item as complete."""
    engine = get_engine(args)
    
    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)
    
    try:
        success, message = engine.complete_item(
            args.item,
            notes=args.notes,
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
        success, message = engine.skip_item(args.item, args.reason)
        
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


def cmd_approve_item(args):
    """Approve a manual gate item."""
    engine = get_engine(args)
    
    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)
    
    try:
        success, message = engine.approve_item(args.item, notes=args.notes)
        
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


def cmd_advance(args):
    """Advance to the next phase."""
    engine = get_engine(args)
    
    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)
    
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
    
    success, message = engine.advance_phase(force=args.force)
    
    if success:
        print(f"✓ {message}")
        if not args.quiet:
            print("\n" + engine.get_recitation_text())
    else:
        print(f"✗ {message}")
        sys.exit(1)


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
    
    if args.abandon:
        if not args.reason:
            print("Error: --reason is required when abandoning")
            sys.exit(1)
        engine.abandon_workflow(args.reason)
        print("✓ Workflow abandoned")
    else:
        engine.complete_workflow(notes=args.notes)
        print("✓ Workflow completed")
        
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
    """Generate a handoff prompt for Claude Code or execute directly."""
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
    
    # Initialize Claude integration
    claude = ClaudeCodeIntegration(args.dir or '.')
    
    # Generate the handoff prompt
    prompt = claude.generate_handoff_prompt(
        task_description=engine.state.task_description,
        phase_name=phase_def.name if phase_def else engine.state.current_phase_id,
        checklist_items=pending_items,
        context_files=args.files.split(',') if args.files else None,
        constraints=args.constraints.split(',') if args.constraints else None,
        acceptance_criteria=args.criteria.split(',') if args.criteria else None
    )
    
    if args.execute:
        # Execute directly with Claude Code
        if not claude.is_available():
            print("Error: Claude Code CLI not available")
            print("Install with: npm install -g @anthropic-ai/claude-code")
            sys.exit(1)
        
        print("Executing with Claude Code...")
        print("="*60)
        
        success, output, details = claude.execute_prompt(prompt, timeout=args.timeout)
        
        print(output)
        print("="*60)
        
        if success:
            print("\n✓ Claude Code execution completed")
            
            # Parse and show completion report
            report = claude.parse_completion_report(output)
            if report['completed_items']:
                print("\nCompleted items:")
                for item in report['completed_items']:
                    print(f"  - {item}")
            
            if report['blockers']:
                print("\nBlockers encountered:")
                for blocker in report['blockers']:
                    print(f"  - {blocker}")
        else:
            print(f"\n✗ Claude Code execution failed: {details.get('error', 'unknown')}")
            sys.exit(1)
    else:
        # Just print the prompt for manual use
        print("=" * 60)
        print("CLAUDE CODE HANDOFF PROMPT")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        print("\nTo execute: orchestrator handoff --execute")
        print("Or copy the above prompt to Claude Code manually.")


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
    start_parser.set_defaults(func=cmd_start)
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show current workflow status')
    status_parser.add_argument('--json', action='store_true', help='Output as JSON')
    status_parser.set_defaults(func=cmd_status)
    
    # Complete command
    complete_parser = subparsers.add_parser('complete', help='Mark an item as complete')
    complete_parser.add_argument('item', help='Item ID to complete')
    complete_parser.add_argument('--notes', '-n', help='Notes about the completion')
    complete_parser.add_argument('--skip-verify', action='store_true', help='Skip verification')
    complete_parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')
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
    advance_parser.set_defaults(func=cmd_advance)
    
    # Approve command (for phase gates)
    approve_parser = subparsers.add_parser('approve', help='Approve a phase gate')
    approve_parser.add_argument('--phase', '-p', help='Phase ID (default: current)')
    approve_parser.set_defaults(func=cmd_approve)
    
    # Finish command
    finish_parser = subparsers.add_parser('finish', help='Complete or abandon the workflow')
    finish_parser.add_argument('--abandon', action='store_true', help='Abandon instead of complete')
    finish_parser.add_argument('--reason', '-r', help='Reason for abandoning')
    finish_parser.add_argument('--notes', '-n', help='Completion notes')
    finish_parser.add_argument('--skip-learn', action='store_true', help='Skip learning report')
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
    
    # Handoff command (NEW)
    handoff_parser = subparsers.add_parser('handoff', help='Generate or execute a Claude Code handoff')
    handoff_parser.add_argument('--execute', '-x', action='store_true', help='Execute with Claude Code directly')
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
    
    # Cleanup command (NEW)
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up abandoned workflows')
    cleanup_parser.add_argument('--search-dir', '-s', default='.', help='Directory to search (default: current)')
    cleanup_parser.add_argument('--max-age', '-a', type=int, default=7, help='Max age in days for active workflows (default: 7)')
    cleanup_parser.add_argument('--depth', '-d', type=int, default=3, help='Max search depth (default: 3)')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='Show what would be cleaned without doing it')
    cleanup_parser.set_defaults(func=cmd_cleanup)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
