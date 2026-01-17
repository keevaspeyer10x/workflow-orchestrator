"""CLI commands for the healing system - Phase 4.

Provides the `orchestrator heal` command group:
- status: Show healing system status
- apply: Apply a suggested fix
- ignore: Permanently ignore a pattern
- unquarantine: Reset a quarantined pattern
- explain: Show why a fix wasn't auto-applied
- export: Export all patterns
- backfill: Process historical logs
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .environment import ENVIRONMENT, Environment
from .config import get_config
from .client import HealingClient, LookupResult
from .costs import get_cost_tracker
from .supabase_client import HealingSupabaseClient


def get_console():
    """Get Rich console if available, else simple print wrapper."""
    if RICH_AVAILABLE:
        return Console()

    class SimpleConsole:
        def print(self, *args, **kwargs):
            # Strip Rich markup for simple output
            text = " ".join(str(a) for a in args)
            # Remove common Rich markup
            import re
            text = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', text)
            print(text)

    return SimpleConsole()


console = get_console()


async def _get_healing_client() -> Optional[HealingClient]:
    """Get a configured healing client or None if unavailable."""
    import os

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    project_id = os.environ.get("HEALING_PROJECT_ID", "default")

    if not url or not key:
        return None

    try:
        supabase = HealingSupabaseClient(url, key, project_id)
        return HealingClient(supabase)
    except Exception:
        return None


async def _run_session_scan(
    working_dir: Path,
    healing_client: Optional[HealingClient],
) -> Optional["ScanSummary"]:
    """Run session-end scan for pattern learning.

    Called automatically at the end of cmd_finish to extract patterns
    from the current session's logs and files.

    Args:
        working_dir: Project root directory
        healing_client: Healing client for recording patterns

    Returns:
        ScanSummary if successful, None if skipped or failed
    """
    if healing_client is None:
        return None

    try:
        from .scanner import PatternScanner, ScanSummary

        scanner = PatternScanner(
            state_path=working_dir / ".orchestrator" / "scan_state.json",
            project_root=working_dir,
            healing_client=healing_client,
        )

        summary = await scanner.scan_all()
        return summary

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Session scan failed (non-blocking): {e}")
        return None


async def _check_crash_recovery(working_dir: Path) -> Optional["ScanSummary"]:
    """Check for and recover orphaned sessions from previous crashes.

    Called at the start of cmd_start to recover any learnings from
    sessions that didn't complete properly.

    Args:
        working_dir: Project root directory

    Returns:
        ScanSummary if recovery was performed, None otherwise
    """
    try:
        from .scanner import PatternScanner, ScanSummary

        scanner = PatternScanner(
            state_path=working_dir / ".orchestrator" / "scan_state.json",
            project_root=working_dir,
        )

        if scanner.has_orphaned_session():
            summary = await scanner.recover_orphaned()
            return summary

        return None

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Crash recovery check failed: {e}")
        return None


def heal_status() -> int:
    """Show healing system status.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    config = get_config()
    cost_tracker = get_cost_tracker()
    cost_status = cost_tracker.get_status()

    if RICH_AVAILABLE:
        table = Table(title="Healing Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Environment", ENVIRONMENT.value)
        table.add_row("Enabled", "Yes" if config.enabled else "[red]No[/red]")
        table.add_row(
            "Kill Switch",
            "[red]ACTIVE[/red]" if config.kill_switch_active else "Off"
        )
        table.add_row(
            "Today's Cost",
            f"${cost_status.daily_cost_usd:.2f} / ${cost_status.daily_limit_usd:.2f}"
        )
        table.add_row(
            "Validations",
            f"{cost_status.daily_validations} / {cost_status.validation_limit}"
        )

        # Try to get pattern count from Supabase
        client = asyncio.run(_get_healing_client())
        if client:
            try:
                stats = asyncio.run(client.get_stats())
                table.add_row("Patterns", str(stats.get("pattern_count", 0)))
            except Exception:
                table.add_row("Patterns", "[yellow]Unavailable[/yellow]")
        else:
            table.add_row("Supabase", "[yellow]Not configured[/yellow]")

        console.print(table)
    else:
        print(f"Environment: {ENVIRONMENT.value}")
        print(f"Enabled: {config.enabled}")
        print(f"Kill Switch: {'ACTIVE' if config.kill_switch_active else 'Off'}")
        print(f"Today's Cost: ${cost_status.daily_cost_usd:.2f} / ${cost_status.daily_limit_usd:.2f}")
        print(f"Validations: {cost_status.daily_validations} / {cost_status.validation_limit}")

    return 0


def heal_apply(fix_id: str, force: bool = False, dry_run: bool = False) -> int:
    """Apply a suggested fix.

    Args:
        fix_id: The fix ID to apply
        force: Bypass safety checks
        dry_run: Show preview without applying

    Returns:
        Exit code (0 for success, 1 for error)
    """
    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    if dry_run:
        console.print(f"[yellow]Dry run:[/yellow] Would apply fix {fix_id}")
        # TODO: Preview the fix details
        return 0

    if force:
        console.print("[yellow]Warning: Force mode - bypassing safety checks[/yellow]")

    # TODO: Implement actual fix application via FixApplicator
    console.print(f"[yellow]Fix application not yet implemented[/yellow]")
    console.print(f"Fix ID: {fix_id}")
    return 1


def heal_ignore(fingerprint: str, reason: str) -> int:
    """Permanently ignore an error pattern.

    Args:
        fingerprint: The error fingerprint to ignore
        reason: Why the pattern is being ignored

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if not reason:
        console.print("[red]Error: --reason is required[/red]")
        return 1

    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        # Quarantine the pattern with reason
        asyncio.run(client.supabase.quarantine_pattern(fingerprint, reason))
        console.print(f"[green]Pattern {fingerprint[:12]}... ignored[/green]")
        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


def heal_unquarantine(fingerprint: str, reason: str) -> int:
    """Reset a quarantined pattern.

    Args:
        fingerprint: The pattern fingerprint
        reason: Why the pattern is being unquarantined

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if not reason:
        console.print("[red]Error: --reason is required[/red]")
        return 1

    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        asyncio.run(client.supabase.unquarantine_pattern(fingerprint, reason))
        console.print(f"[green]Pattern {fingerprint[:12]}... unquarantined[/green]")
        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


def heal_explain(fingerprint: str) -> int:
    """Show why a fix wasn't auto-applied.

    Args:
        fingerprint: The error fingerprint to explain

    Returns:
        Exit code (0 for success, 1 for error)
    """
    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        # Look up the pattern
        pattern = asyncio.run(client.supabase.lookup_pattern(fingerprint))

        if not pattern:
            console.print(f"[yellow]Pattern {fingerprint[:12]}... not found[/yellow]")
            return 1

        console.print(f"\n[bold]Pattern:[/bold] {fingerprint[:16]}...")

        reasons = []
        suggestions = []

        # Check why it wasn't auto-applied
        if pattern.get("quarantined"):
            reasons.append(f"Pattern is quarantined: {pattern.get('quarantine_reason', 'No reason given')}")
            suggestions.append("Run `orchestrator heal unquarantine` to reset")

        safety = pattern.get("safety_category", "unknown")
        if safety == "risky":
            reasons.append("Pattern is categorized as RISKY - requires manual review")
            suggestions.append("Review and apply manually if safe")

        verified_count = pattern.get("verified_apply_count", 0)
        human_count = pattern.get("human_correction_count", 0)
        is_preseeded = pattern.get("is_preseeded", False)

        if not is_preseeded and verified_count < 5 and human_count < 1:
            reasons.append(f"No precedent established (verified: {verified_count}, human: {human_count})")
            suggestions.append("Apply fix manually to establish precedent")

        if not reasons:
            reasons.append("No specific blocking reason found")
            suggestions.append("Check validation pipeline for details")

        console.print("\n[bold]Why not auto-applied:[/bold]")
        for reason in reasons:
            console.print(f"  - {reason}")

        if suggestions:
            console.print("\n[bold]Suggestions:[/bold]")
            for suggestion in suggestions:
                console.print(f"  -> {suggestion}")

        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


def heal_export(format: str = "yaml", output: Optional[str] = None) -> int:
    """Export all patterns.

    Args:
        format: Output format (yaml or json)
        output: Output file path (stdout if None)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        # Get all patterns
        patterns = asyncio.run(client.supabase.get_all_patterns())

        if format == "json":
            data = json.dumps(patterns, indent=2, default=str)
        else:
            # YAML format
            try:
                import yaml
                data = yaml.dump(patterns, default_flow_style=False)
            except ImportError:
                console.print("[yellow]PyYAML not installed, using JSON[/yellow]")
                data = json.dumps(patterns, indent=2, default=str)

        if output:
            Path(output).write_text(data)
            console.print(f"[green]Exported {len(patterns)} patterns to {output}[/green]")
        else:
            print(data)

        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


def heal_backfill(
    log_dir: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    scan_only: bool = False,
    days: int = 30,
    no_github: bool = False,
) -> int:
    """Process historical workflow logs and other error sources.

    Args:
        log_dir: Directory containing workflow logs (defaults to current dir)
        dry_run: Preview without processing
        limit: Maximum number of logs to process
        scan_only: Only show recommendations, don't process
        days: Only scan files modified in the last N days
        no_github: Skip GitHub issue scanning

    Returns:
        Exit code (0 for success, 1 for error)
    """
    from .backfill import HistoricalBackfill
    from .scanner import PatternScanner

    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    log_path = Path(log_dir) if log_dir else Path(".")

    if not log_path.exists():
        console.print(f"[red]Error: Directory not found: {log_path}[/red]")
        return 1

    # Create scanner with options
    scanner = PatternScanner(
        state_path=log_path / ".orchestrator" / "scan_state.json",
        project_root=log_path,
        healing_client=client,
        include_github=not no_github,
    )

    # Scan-only mode: show recommendations
    if scan_only:
        recommendations = scanner.get_recommendations()
        if not recommendations:
            console.print("[yellow]No scannable sources found[/yellow]")
            return 0

        if RICH_AVAILABLE:
            table = Table(title="Scannable Sources")
            table.add_column("Source", style="cyan")
            table.add_column("Path", style="dim")
            table.add_column("Recommendation", style="green")

            for rec in recommendations:
                table.add_row(
                    rec["source"],
                    rec["path"],
                    rec["recommendation"],
                )
            console.print(table)
        else:
            console.print("Scannable Sources:")
            for rec in recommendations:
                console.print(f"  {rec['source']}: {rec['recommendation']}")
        return 0

    # Dry run mode: show what would be processed
    if dry_run:
        # Count logs without processing
        logs = list(log_path.glob("**/.workflow_log.jsonl"))
        if limit:
            logs = logs[:limit]
        console.print(f"[yellow]Dry run:[/yellow] Would process {len(logs)} log files")
        return 0

    # Use new scanner if --no-github or non-default days specified
    if no_github or days != 30:
        try:
            summary = asyncio.run(scanner.scan_all(days=days))
            console.print(f"[green]Scanned {summary.sources_scanned} sources, "
                         f"extracted {summary.errors_extracted} errors, "
                         f"created {summary.patterns_created} patterns[/green]")
            return 0
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return 1

    # Default behavior: use HistoricalBackfill for backward compatibility
    backfill = HistoricalBackfill(client)

    try:
        count = asyncio.run(backfill.backfill_workflow_logs(log_path, limit=limit))
        console.print(f"[green]Processed {count} errors from historical logs[/green]")
        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1
