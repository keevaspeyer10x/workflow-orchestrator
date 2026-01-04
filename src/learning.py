"""
Learning Engine Module

Automatically generates learning reports at the end of workflows
and accumulates insights over time.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

from .schema import WorkflowEvent, EventType, WorkflowState
from .analytics import WorkflowAnalytics


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
