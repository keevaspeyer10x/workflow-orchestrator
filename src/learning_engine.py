"""
Learning Engine Module

Automatically generates learning reports at the end of workflows
and accumulates insights over time.

CORE-023-P3: Extended to detect conflict patterns and auto-suggest
ROADMAP items following source plan (lines 80-101).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

from .schema import WorkflowEvent, EventType, WorkflowState
from .analytics import WorkflowAnalytics


# ============================================================================
# CORE-023-P3: Conflict Pattern Data Classes
# ============================================================================

@dataclass
class ConflictPattern:
    """
    A detected conflict pattern.

    Used for analyzing which files conflict frequently across sessions.
    """
    file_path: str
    conflict_count: int
    session_count: int
    strategies_used: dict[str, int] = field(default_factory=dict)
    avg_resolution_time_ms: float = 0.0


@dataclass
class RoadmapSuggestion:
    """
    A suggestion to add to ROADMAP.md.

    Format from source plan (lines 91-97):
        #### AI-SUGGESTED: {title}
        **Status:** Suggested
        **Source:** AI analysis (LEARN phase, {date})
        **Evidence:** {evidence}

        **Recommendation:** {recommendation}
    """
    title: str
    evidence: str
    recommendation: str
    source_date: str


class LearningEngine:
    """
    Generates learning reports and manages the LEARNINGS.md file.
    """
    
    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)
        self.state_file = self.working_dir / ".workflow_state.json"
        self.log_file = self.working_dir / ".workflow_log.jsonl"
        self.learnings_file = self.working_dir / "LEARNINGS.md"
        self.analytics = WorkflowAnalytics(working_dir)
    
    def _load_state(self) -> Optional[WorkflowState]:
        """Load the current/last workflow state."""
        if not self.state_file.exists():
            return None
        with open(self.state_file, 'r') as f:
            data = json.load(f)
        return WorkflowState(**data)
    
    def _get_workflow_events(self, workflow_id: str) -> list[WorkflowEvent]:
        """Get all events for a specific workflow."""
        return self.analytics.get_workflow_events(workflow_id)
    
    def generate_learning_report(self, workflow_id: Optional[str] = None) -> str:
        """
        Generate a learning report for a specific workflow or the current one.
        """
        state = self._load_state()
        
        if not state and not workflow_id:
            return "No workflow found to generate learning report."
        
        wf_id = workflow_id or state.workflow_id
        events = self._get_workflow_events(wf_id)
        
        if not events:
            return f"No events found for workflow {wf_id}"
        
        # Analyze the workflow
        analysis = self._analyze_workflow(wf_id, events, state)
        
        # Generate the report
        return self._format_report(analysis)
    
    def _analyze_workflow(self, workflow_id: str, events: list[WorkflowEvent], state: Optional[WorkflowState]) -> dict:
        """Analyze a workflow's events and state."""
        analysis = {
            "workflow_id": workflow_id,
            "task": state.task_description if state else "Unknown",
            "project": state.project if state else None,
            "status": state.status if state else "unknown",
            "started_at": None,
            "completed_at": None,
            "duration_minutes": None,
            "phases_completed": [],
            "items_completed": [],
            "items_skipped": [],
            "items_failed": [],
            "verification_failures": [],
            "human_overrides": [],
            "timeline": []
        }
        
        # Process events
        for e in events:
            # Track timeline
            analysis["timeline"].append({
                "time": e.timestamp.strftime("%H:%M"),
                "event": e.event_type,
                "message": e.message
            })
            
            if e.event_type == EventType.WORKFLOW_STARTED:
                analysis["started_at"] = e.timestamp
            
            elif e.event_type == EventType.WORKFLOW_COMPLETED:
                analysis["completed_at"] = e.timestamp
            
            elif e.event_type == EventType.PHASE_COMPLETED:
                analysis["phases_completed"].append(e.phase_id)
            
            elif e.event_type == EventType.ITEM_COMPLETED:
                analysis["items_completed"].append(e.item_id)
            
            elif e.event_type == EventType.ITEM_SKIPPED:
                analysis["items_skipped"].append({
                    "item": e.item_id,
                    "reason": e.details.get("reason", "No reason provided")
                })
            
            elif e.event_type == EventType.ITEM_FAILED:
                analysis["items_failed"].append(e.item_id)
            
            elif e.event_type == EventType.VERIFICATION_FAILED:
                analysis["verification_failures"].append({
                    "item": e.item_id,
                    "message": e.message,
                    "details": e.details
                })
            
            elif e.event_type == EventType.HUMAN_OVERRIDE:
                analysis["human_overrides"].append({
                    "phase": e.phase_id,
                    "message": e.message
                })
        
        # Calculate duration
        if analysis["started_at"] and analysis["completed_at"]:
            duration = analysis["completed_at"] - analysis["started_at"]
            analysis["duration_minutes"] = round(duration.total_seconds() / 60, 1)
        
        return analysis
    
    def _format_report(self, analysis: dict) -> str:
        """Format the analysis into a readable report."""
        lines = [
            f"## Learning Report: {analysis['task']}",
            "",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Workflow ID:** {analysis['workflow_id']}",
            f"**Status:** {analysis['status']}",
        ]
        
        if analysis['duration_minutes']:
            lines.append(f"**Duration:** {analysis['duration_minutes']} minutes")
        
        if analysis['project']:
            lines.append(f"**Project:** {analysis['project']}")
        
        lines.extend(["", "### Summary", ""])
        
        # Completion summary
        lines.append(f"- **Phases completed:** {len(analysis['phases_completed'])}")
        lines.append(f"- **Items completed:** {len(analysis['items_completed'])}")
        lines.append(f"- **Items skipped:** {len(analysis['items_skipped'])}")
        lines.append(f"- **Verification failures:** {len(analysis['verification_failures'])}")
        
        # Skipped items detail
        if analysis['items_skipped']:
            lines.extend(["", "### Skipped Items", ""])
            for skip in analysis['items_skipped']:
                lines.append(f"- **{skip['item']}**: {skip['reason']}")
        
        # Verification failures detail
        if analysis['verification_failures']:
            lines.extend(["", "### Verification Failures", ""])
            for fail in analysis['verification_failures']:
                lines.append(f"- **{fail['item']}**: {fail['message']}")
        
        # Human overrides
        if analysis['human_overrides']:
            lines.extend(["", "### Human Interventions", ""])
            for override in analysis['human_overrides']:
                lines.append(f"- {override['message']}")
        
        # Suggestions
        lines.extend(["", "### Suggested Improvements", ""])
        suggestions = self._generate_suggestions(analysis)
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")
        
        # Action items
        lines.extend(["", "### Action Items", ""])
        action_items = self._generate_action_items(analysis)
        for item in action_items:
            lines.append(f"- [ ] {item}")
        
        lines.extend(["", "---", ""])
        
        return "\n".join(lines)
    
    def _generate_suggestions(self, analysis: dict) -> list[str]:
        """Generate improvement suggestions based on the analysis."""
        suggestions = []
        
        # Check for frequently skipped items
        if len(analysis['items_skipped']) > 2:
            suggestions.append(
                f"Multiple items were skipped ({len(analysis['items_skipped'])}). "
                "Review if these items are necessary or should be made optional."
            )
        
        # Check for verification failures
        if analysis['verification_failures']:
            suggestions.append(
                "Verification failures occurred. Consider if the verification "
                "criteria are appropriate or if clearer guidance is needed."
            )
        
        # Check duration
        if analysis['duration_minutes'] and analysis['duration_minutes'] > 120:
            suggestions.append(
                f"Workflow took {analysis['duration_minutes']} minutes. "
                "Consider breaking into smaller tasks or parallelizing work."
            )
        
        # Check for specific skip patterns
        skip_reasons = [s['reason'].lower() for s in analysis['items_skipped']]
        if any('simple' in r or 'trivial' in r for r in skip_reasons):
            suggestions.append(
                "Some items were skipped as 'simple/trivial'. Consider adding "
                "a task complexity tag that auto-adjusts required items."
            )
        
        if not suggestions:
            suggestions.append("Workflow completed smoothly. No specific improvements identified.")
        
        return suggestions
    
    def _generate_action_items(self, analysis: dict) -> list[str]:
        """Generate action items based on the analysis."""
        items = []
        
        # Review skipped items
        for skip in analysis['items_skipped']:
            items.append(f"Review if '{skip['item']}' skip was appropriate")
        
        # Address verification failures
        for fail in analysis['verification_failures']:
            items.append(f"Investigate verification failure for '{fail['item']}'")
        
        # General items
        if analysis['status'] == 'completed':
            items.append("Update workflow definition if improvements identified")
        elif analysis['status'] == 'abandoned':
            items.append("Document why workflow was abandoned to prevent recurrence")
        
        if not items:
            items.append("No specific action items - workflow completed successfully")
        
        return items
    
    def append_to_learnings_file(self, report: str):
        """Append a learning report to the LEARNINGS.md file."""
        # Create file with header if it doesn't exist
        if not self.learnings_file.exists():
            header = [
                "# Workflow Learnings",
                "",
                "This file accumulates learning reports from completed workflows.",
                "Use these insights to iterate and improve the workflow over time.",
                "",
                "---",
                ""
            ]
            with open(self.learnings_file, 'w') as f:
                f.write("\n".join(header))
        
        # Append the new report
        with open(self.learnings_file, 'a') as f:
            f.write(report)
            f.write("\n")
    
    def get_accumulated_insights(self) -> str:
        """
        Analyze all learning reports and generate accumulated insights.
        """
        summary = self.analytics.get_summary()
        suggestions = self.analytics.get_improvement_suggestions()
        
        lines = [
            "# Accumulated Workflow Insights",
            "",
            f"**Total Workflows Analyzed:** {summary.get('total_workflows', 0)}",
            f"**Completion Rate:** {summary.get('completion_rate', 'N/A')}",
            "",
            "## Key Patterns",
            ""
        ]
        
        # Most skipped items
        if summary.get('skipped_items'):
            lines.append("### Frequently Skipped Items")
            for item_id, data in sorted(
                summary['skipped_items'].items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )[:5]:
                lines.append(f"- {item_id}: {data['count']} times")
            lines.append("")
        
        # Verification issues
        if summary.get('verification_failures'):
            lines.append("### Verification Problem Areas")
            for item_id, count in sorted(
                summary['verification_failures'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]:
                lines.append(f"- {item_id}: {count} failures")
            lines.append("")
        
        # Improvement suggestions
        lines.append("## Recommended Improvements")
        lines.append("")
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")

        return "\n".join(lines)

    # ========================================================================
    # CORE-023-P3: Conflict Pattern Detection (source lines 80-101)
    # ========================================================================

    def get_conflict_patterns(self, session_window: int = 10) -> list[ConflictPattern]:
        """
        Analyze .workflow_log.jsonl for conflict patterns.

        From source plan (lines 84-87):
            LEARN phase detects:
              "src/cli.py conflicts in 4 of last 10 sessions"

        Args:
            session_window: Number of recent sessions to analyze

        Returns:
            List of ConflictPattern objects, sorted by conflict count descending
        """
        if not self.log_file.exists():
            return []

        # Parse all events from log
        events = []
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Identify workflow sessions (workflow_started -> workflow_completed)
        sessions = []
        current_session = None

        for event in events:
            event_type = event.get("event_type")
            workflow_id = event.get("workflow_id")

            if event_type == "workflow_started":
                current_session = {
                    "workflow_id": workflow_id,
                    "conflicts": [],
                }
            elif event_type == "workflow_completed" and current_session:
                sessions.append(current_session)
                current_session = None
            elif event_type == "conflict_resolved" and current_session:
                details = event.get("details", {})
                current_session["conflicts"].append({
                    "file": details.get("file"),
                    "strategy": details.get("strategy"),
                    "resolution_time_ms": details.get("resolution_time_ms", 0),
                })

        # Limit to recent sessions
        recent_sessions = sessions[-session_window:] if sessions else []
        session_count = len(recent_sessions)

        if session_count == 0:
            return []

        # Aggregate conflict data per file
        file_stats: dict[str, dict] = defaultdict(lambda: {
            "conflict_count": 0,
            "strategies": defaultdict(int),
            "total_time_ms": 0,
        })

        for session in recent_sessions:
            for conflict in session["conflicts"]:
                file_path = conflict["file"]
                if file_path:
                    file_stats[file_path]["conflict_count"] += 1
                    strategy = conflict.get("strategy", "unknown")
                    file_stats[file_path]["strategies"][strategy] += 1
                    file_stats[file_path]["total_time_ms"] += conflict.get("resolution_time_ms", 0)

        # Build ConflictPattern objects
        patterns = []
        for file_path, stats in file_stats.items():
            count = stats["conflict_count"]
            avg_time = stats["total_time_ms"] / count if count > 0 else 0

            patterns.append(ConflictPattern(
                file_path=file_path,
                conflict_count=count,
                session_count=session_count,
                strategies_used=dict(stats["strategies"]),
                avg_resolution_time_ms=avg_time,
            ))

        # Sort by conflict count descending
        patterns.sort(key=lambda p: p.conflict_count, reverse=True)
        return patterns

    def generate_roadmap_suggestions(
        self,
        conflict_threshold: int = 3,
    ) -> list[RoadmapSuggestion]:
        """
        Generate ROADMAP.md suggestions from conflict patterns.

        From source plan (lines 89-100): Only suggests for files
        conflicting >= threshold times.

        Args:
            conflict_threshold: Minimum conflicts to trigger suggestion

        Returns:
            List of RoadmapSuggestion objects
        """
        patterns = self.get_conflict_patterns()
        suggestions = []

        for pattern in patterns:
            if pattern.conflict_count >= conflict_threshold:
                # Generate suggestion in format from source plan
                title = f"Reduce {Path(pattern.file_path).name} conflicts"
                evidence = f"{pattern.file_path} conflicted in {pattern.conflict_count}/{pattern.session_count} sessions"

                # Generate recommendation based on file type
                file_name = Path(pattern.file_path).name
                if file_name.endswith(".py"):
                    recommendation = (
                        f"Consider extracting frequently-changing sections of {file_name} "
                        "to separate modules to reduce merge conflict surface area."
                    )
                else:
                    recommendation = (
                        f"Review {file_name} structure to identify sections that could be "
                        "split to reduce merge conflict frequency."
                    )

                suggestions.append(RoadmapSuggestion(
                    title=title,
                    evidence=evidence,
                    recommendation=recommendation,
                    source_date=datetime.now().strftime("%Y-%m-%d"),
                ))

        return suggestions

    def add_roadmap_suggestion(self, suggestion: RoadmapSuggestion) -> bool:
        """
        Add an AI-generated suggestion to ROADMAP.md.

        Format from source plan (lines 91-97):
            #### AI-SUGGESTED: {title}
            **Status:** Suggested
            **Source:** AI analysis (LEARN phase, {date})
            **Evidence:** {evidence}

            **Recommendation:** {recommendation}

        Args:
            suggestion: The suggestion to add

        Returns:
            True if added, False if similar suggestion already exists
        """
        roadmap_file = self.working_dir / "ROADMAP.md"

        # Read existing content or create new
        if roadmap_file.exists():
            content = roadmap_file.read_text()
        else:
            content = "# Roadmap\n\n## AI Suggestions\n\n"

        # Check for duplicate (same title)
        if f"AI-SUGGESTED: {suggestion.title}" in content:
            return False

        # Build suggestion block (exact format from source plan)
        suggestion_block = f"""
#### AI-SUGGESTED: {suggestion.title}
**Status:** Suggested
**Source:** AI analysis (LEARN phase, {suggestion.source_date})
**Evidence:** {suggestion.evidence}

**Recommendation:** {suggestion.recommendation}

"""

        # Find insertion point (after "## AI Suggestions" if exists, else at end)
        if "## AI Suggestions" in content:
            # Insert after the header
            idx = content.find("## AI Suggestions")
            end_of_line = content.find("\n", idx)
            content = content[:end_of_line + 1] + suggestion_block + content[end_of_line + 1:]
        else:
            # Add section and suggestion at end
            content += "\n## AI Suggestions\n" + suggestion_block

        roadmap_file.write_text(content)
        return True
