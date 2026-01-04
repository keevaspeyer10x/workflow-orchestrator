"""
Workflow Analytics Module

Analyzes workflow history to identify patterns, bottlenecks, and improvement opportunities.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from .schema import WorkflowEvent, EventType


class WorkflowAnalytics:
    """
    Analyzes workflow logs to provide insights for iteration and improvement.
    """
    
    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)
        self.log_file = self.working_dir / ".workflow_log.jsonl"
        self.events: list[WorkflowEvent] = []
        self._load_events()
    
    def _load_events(self):
        """Load all events from the log file."""
        if not self.log_file.exists():
            return
        
        with open(self.log_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        # Handle datetime parsing
                        if 'timestamp' in data and isinstance(data['timestamp'], str):
                            data['timestamp'] = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                        self.events.append(WorkflowEvent(**data))
                    except Exception as e:
                        pass  # Skip malformed lines
    
    def get_workflow_ids(self) -> list[str]:
        """Get all unique workflow IDs."""
        return list(set(e.workflow_id for e in self.events))
    
    def get_workflow_events(self, workflow_id: str) -> list[WorkflowEvent]:
        """Get all events for a specific workflow."""
        return [e for e in self.events if e.workflow_id == workflow_id]
    
    def get_summary(self) -> dict:
        """Get a comprehensive analytics summary."""
        if not self.events:
            return {"status": "no_data", "message": "No workflow history found"}
        
        workflow_ids = self.get_workflow_ids()
        
        # Count workflow outcomes
        completed = 0
        abandoned = 0
        active = 0
        
        for wf_id in workflow_ids:
            wf_events = self.get_workflow_events(wf_id)
            event_types = [e.event_type for e in wf_events]
            
            if EventType.WORKFLOW_COMPLETED in event_types:
                completed += 1
            elif EventType.WORKFLOW_ABANDONED in event_types:
                abandoned += 1
            else:
                active += 1
        
        # Analyze skipped items
        skipped_items = defaultdict(list)
        for e in self.events:
            if e.event_type == EventType.ITEM_SKIPPED:
                reason = e.details.get('reason', 'No reason')
                skipped_items[e.item_id].append(reason)
        
        # Analyze verification failures
        verification_failures = defaultdict(int)
        for e in self.events:
            if e.event_type == EventType.VERIFICATION_FAILED:
                verification_failures[e.item_id] += 1
        
        # Calculate phase durations
        phase_durations = self._calculate_phase_durations()
        
        # Find most common blockers
        blockers = []
        for e in self.events:
            if e.event_type == EventType.ERROR or 'blocker' in e.message.lower():
                blockers.append(e.message)
        
        return {
            "total_workflows": len(workflow_ids),
            "completed": completed,
            "abandoned": abandoned,
            "active": active,
            "completion_rate": f"{(completed / len(workflow_ids) * 100):.1f}%" if workflow_ids else "N/A",
            "skipped_items": {
                item_id: {
                    "count": len(reasons),
                    "reasons": reasons
                }
                for item_id, reasons in skipped_items.items()
            },
            "verification_failures": dict(verification_failures),
            "phase_durations": phase_durations,
            "total_events": len(self.events)
        }
    
    def _calculate_phase_durations(self) -> dict:
        """Calculate average duration for each phase."""
        phase_times = defaultdict(list)
        
        for wf_id in self.get_workflow_ids():
            wf_events = self.get_workflow_events(wf_id)
            
            phase_starts = {}
            for e in wf_events:
                if e.event_type == EventType.PHASE_STARTED and e.phase_id:
                    phase_starts[e.phase_id] = e.timestamp
                elif e.event_type == EventType.PHASE_COMPLETED and e.phase_id:
                    if e.phase_id in phase_starts:
                        duration = e.timestamp - phase_starts[e.phase_id]
                        phase_times[e.phase_id].append(duration.total_seconds())
        
        return {
            phase_id: {
                "avg_minutes": f"{sum(times) / len(times) / 60:.1f}",
                "count": len(times)
            }
            for phase_id, times in phase_times.items()
        }
    
    def get_report(self) -> str:
        """Generate a human-readable analytics report."""
        summary = self.get_summary()
        
        if summary.get("status") == "no_data":
            return "No workflow history found. Complete some workflows to see analytics."
        
        lines = [
            "=" * 60,
            "WORKFLOW ANALYTICS REPORT",
            "=" * 60,
            "",
            "## Overview",
            f"Total Workflows: {summary['total_workflows']}",
            f"  - Completed: {summary['completed']}",
            f"  - Abandoned: {summary['abandoned']}",
            f"  - Active: {summary['active']}",
            f"Completion Rate: {summary['completion_rate']}",
            "",
        ]
        
        # Skipped items analysis
        if summary['skipped_items']:
            lines.append("## Most Skipped Items")
            sorted_skipped = sorted(
                summary['skipped_items'].items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )
            for item_id, data in sorted_skipped[:5]:
                lines.append(f"  - {item_id}: {data['count']} times")
                # Show top reasons
                reason_counts = defaultdict(int)
                for r in data['reasons']:
                    reason_counts[r[:50]] += 1
                for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])[:3]:
                    lines.append(f"      \"{reason}\" ({count}x)")
            lines.append("")
        
        # Verification failures
        if summary['verification_failures']:
            lines.append("## Verification Failures")
            sorted_failures = sorted(
                summary['verification_failures'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for item_id, count in sorted_failures[:5]:
                lines.append(f"  - {item_id}: {count} failures")
            lines.append("")
        
        # Phase durations
        if summary['phase_durations']:
            lines.append("## Average Phase Durations")
            for phase_id, data in summary['phase_durations'].items():
                lines.append(f"  - {phase_id}: {data['avg_minutes']} min (n={data['count']})")
            lines.append("")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def get_improvement_suggestions(self) -> list[str]:
        """Generate actionable improvement suggestions based on analytics."""
        summary = self.get_summary()
        suggestions = []
        
        if summary.get("status") == "no_data":
            return ["Complete some workflows to get improvement suggestions."]
        
        # Check for frequently skipped items
        for item_id, data in summary.get('skipped_items', {}).items():
            if data['count'] >= 3:
                suggestions.append(
                    f"Item '{item_id}' is frequently skipped ({data['count']} times). "
                    f"Consider making it optional or removing it from the workflow."
                )
        
        # Check for verification failures
        for item_id, count in summary.get('verification_failures', {}).items():
            if count >= 2:
                suggestions.append(
                    f"Item '{item_id}' has {count} verification failures. "
                    f"Review if the verification criteria are too strict or if the item needs clearer instructions."
                )
        
        # Check completion rate
        if summary['total_workflows'] >= 3:
            completed = summary['completed']
            total = summary['total_workflows']
            rate = completed / total
            if rate < 0.7:
                suggestions.append(
                    f"Workflow completion rate is {rate*100:.0f}%. "
                    f"Consider simplifying the workflow or identifying common abandonment causes."
                )
        
        # Check for long phases
        for phase_id, data in summary.get('phase_durations', {}).items():
            avg_min = float(data['avg_minutes'])
            if avg_min > 60:
                suggestions.append(
                    f"Phase '{phase_id}' takes an average of {avg_min:.0f} minutes. "
                    f"Consider breaking it into smaller phases or parallelizing items."
                )
        
        if not suggestions:
            suggestions.append("No specific improvements identified. Keep iterating!")
        
        return suggestions
