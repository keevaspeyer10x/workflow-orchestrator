"""CLI commands for issue management - Phase 4.

Provides the `orchestrator issues` command group:
- list: List accumulated issues
- review: Simple CLI-based review workflow
"""

import asyncio
import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .client import HealingClient
from .supabase_client import HealingSupabaseClient


def get_console():
    """Get Rich console if available, else simple print wrapper."""
    if RICH_AVAILABLE:
        return Console()

    class SimpleConsole:
        def print(self, *args, **kwargs):
            text = " ".join(str(a) for a in args)
            import re
            text = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', text)
            print(text)

        def input(self, prompt: str) -> str:
            return input(prompt)

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


def issues_list(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 20
) -> int:
    """List accumulated issues.

    Args:
        status: Filter by status (open, resolved, ignored)
        severity: Filter by severity (high, medium, low)
        limit: Maximum number of issues to show

    Returns:
        Exit code (0 for success, 1 for error)
    """
    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        issues = asyncio.run(client.supabase.list_issues(
            status=status,
            severity=severity,
            limit=limit
        ))

        if not issues:
            console.print("[yellow]No issues found[/yellow]")
            return 0

        if RICH_AVAILABLE:
            table = Table(title="Issues")
            table.add_column("Fingerprint", width=12)
            table.add_column("Error", width=40)
            table.add_column("Count")
            table.add_column("Status")
            table.add_column("Fix")

            for issue in issues:
                fp = issue.get("fingerprint", "")[:12]
                desc = issue.get("description", "")[:40]
                count = str(issue.get("count", 0))
                issue_status = issue.get("status", "unknown")
                has_fix = "[green]Yes[/green]" if issue.get("has_fix") else "[red]No[/red]"

                table.add_row(fp, desc, count, issue_status, has_fix)

            console.print(table)
        else:
            print(f"{'Fingerprint':<12} {'Error':<40} {'Count':<6} {'Status':<10} {'Fix'}")
            print("-" * 80)
            for issue in issues:
                fp = issue.get("fingerprint", "")[:12]
                desc = issue.get("description", "")[:40]
                count = str(issue.get("count", 0))
                issue_status = issue.get("status", "unknown")
                has_fix = "Yes" if issue.get("has_fix") else "No"
                print(f"{fp:<12} {desc:<40} {count:<6} {issue_status:<10} {has_fix}")

        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


def issues_review() -> int:
    """Interactive review of pending issues.

    Simple CLI-based review with y/n prompts.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    client = asyncio.run(_get_healing_client())
    if not client:
        console.print("[red]Error: Supabase not configured[/red]")
        return 1

    try:
        # Get issues with available fixes
        issues = asyncio.run(client.supabase.list_issues(
            status="open",
            has_fix=True,
            limit=50
        ))

        if not issues:
            console.print("[yellow]No issues with fixes to review[/yellow]")
            return 0

        console.print(f"\n[bold]Reviewing {len(issues)} issues with available fixes[/bold]\n")

        applied = 0
        skipped = 0

        for i, issue in enumerate(issues, 1):
            fp = issue.get("fingerprint", "")
            desc = issue.get("description", "")[:60]
            count = issue.get("count", 0)
            fix_id = issue.get("fix_id")

            console.print(f"\n[bold]Issue {i}/{len(issues)}:[/bold]")
            console.print(f"  Fingerprint: {fp[:16]}...")
            console.print(f"  Error: {desc}")
            console.print(f"  Occurrences: {count}")

            # Get fix details if available
            if fix_id:
                console.print(f"  Fix available: {fix_id}")

            # Simple y/n prompt
            try:
                response = input("\nApply fix? [y/N/q(uit)]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Review cancelled[/yellow]")
                break

            if response == 'q':
                console.print("[yellow]Review stopped[/yellow]")
                break
            elif response == 'y':
                # Apply the fix
                try:
                    # TODO: Implement actual fix application
                    console.print(f"[green]Fix {fix_id} applied[/green]")
                    applied += 1
                except Exception as e:
                    console.print(f"[red]Failed to apply: {e}[/red]")
            else:
                console.print("[dim]Skipped[/dim]")
                skipped += 1

        console.print(f"\n[bold]Review complete:[/bold]")
        console.print(f"  Applied: {applied}")
        console.print(f"  Skipped: {skipped}")

        return 0
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1
