"""
Feedback loop for bidirectional communication with agents.

This module provides the FeedbackLoop class which manages agent feedback
collection and proactive guidance generation based on historical data.

Usage:
    loop = FeedbackLoop()
    loop.collect_feedback("agent-1", feedback)
    guidance = loop.generate_guidance("agent-1", task_context)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .feedback_schema import (
    AgentFeedback,
    FeedbackType,
    FeedbackSeverity,
    GuidanceMessage,
    GuidanceType,
    GuidanceUrgency,
)
from .pattern_memory import ConflictPatternMemory
from .strategy_tracker import StrategyTracker


def _serialize_feedback(feedback: AgentFeedback) -> dict:
    """Serialize AgentFeedback to dict for JSON storage."""
    data = asdict(feedback)
    # Convert datetime to ISO string
    if data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()
    return data


def _deserialize_feedback(data: dict) -> AgentFeedback:
    """Deserialize dict to AgentFeedback."""
    from .feedback_schema import ConflictHint, PatternSuggestion

    # Make a copy to avoid mutating the original
    data = dict(data)

    # Convert ISO string back to datetime
    if data.get("created_at") and isinstance(data["created_at"], str):
        data["created_at"] = datetime.fromisoformat(data["created_at"])
    # Convert enum string to enum
    if data.get("feedback_type") and isinstance(data["feedback_type"], str):
        data["feedback_type"] = FeedbackType(data["feedback_type"])
    if data.get("severity") and isinstance(data["severity"], str):
        data["severity"] = FeedbackSeverity(data["severity"])

    # Handle nested dataclasses
    if data.get("conflict_hint") and isinstance(data["conflict_hint"], dict):
        data["conflict_hint"] = ConflictHint(**data["conflict_hint"])
    if data.get("pattern_suggestion") and isinstance(data["pattern_suggestion"], dict):
        data["pattern_suggestion"] = PatternSuggestion(**data["pattern_suggestion"])

    return AgentFeedback(**data)

logger = logging.getLogger(__name__)


# Default storage path
DEFAULT_FEEDBACK_PATH = Path(".claude/feedback_history.json")

# How many recent feedbacks to keep per agent
MAX_HISTORY_PER_AGENT = 100


@dataclass
class FeedbackHistory:
    """Persistent feedback history."""

    # Feedback by agent ID
    by_agent: dict[str, list[dict]] = field(default_factory=dict)

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize history to dictionary."""
        return {
            "by_agent": self.by_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeedbackHistory":
        """Deserialize history from dictionary."""
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            by_agent=data.get("by_agent", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


class FeedbackLoop:
    """
    Manages bidirectional communication with agents.

    Collects feedback from agents about resolutions and generates
    proactive guidance based on historical patterns and strategies.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        pattern_memory: Optional[ConflictPatternMemory] = None,
        strategy_tracker: Optional[StrategyTracker] = None,
    ):
        """
        Initialize the feedback loop.

        Args:
            storage_path: Path to feedback storage file
            pattern_memory: Pattern memory for context-aware guidance
            strategy_tracker: Strategy tracker for recommendation guidance
        """
        self.storage_path = storage_path or DEFAULT_FEEDBACK_PATH
        self._history: Optional[FeedbackHistory] = None
        self._pattern_memory = pattern_memory
        self._strategy_tracker = strategy_tracker

    def _load_history(self) -> FeedbackHistory:
        """Load history from disk or create new."""
        if self._history is not None:
            return self._history

        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                self._history = FeedbackHistory.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load feedback history: {e}")
                self._history = FeedbackHistory(created_at=datetime.now(timezone.utc))
        else:
            self._history = FeedbackHistory(created_at=datetime.now(timezone.utc))

        return self._history

    def _save_history(self) -> None:
        """Save history to disk."""
        if self._history is None:
            return

        self._history.updated_at = datetime.now(timezone.utc)

        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.storage_path, 'w') as f:
            json.dump(self._history.to_dict(), f, indent=2)

    def collect_feedback(self, agent_id: str, feedback: AgentFeedback) -> None:
        """
        Collect feedback from an agent.

        Args:
            agent_id: ID of the agent providing feedback
            feedback: The feedback to record
        """
        history = self._load_history()

        if agent_id not in history.by_agent:
            history.by_agent[agent_id] = []

        # Add feedback
        history.by_agent[agent_id].append(_serialize_feedback(feedback))

        # Trim history to max size
        if len(history.by_agent[agent_id]) > MAX_HISTORY_PER_AGENT:
            history.by_agent[agent_id] = history.by_agent[agent_id][-MAX_HISTORY_PER_AGENT:]

        self._save_history()
        logger.debug(f"Collected feedback from agent {agent_id}: {feedback.feedback_type}")

    def get_agent_history(self, agent_id: str) -> list[AgentFeedback]:
        """
        Get feedback history for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            List of AgentFeedback objects
        """
        history = self._load_history()

        if agent_id not in history.by_agent:
            return []

        return [
            _deserialize_feedback(fb)
            for fb in history.by_agent[agent_id]
        ]

    def generate_guidance(
        self,
        agent_id: str,
        task_context: Optional[dict] = None,
    ) -> list[GuidanceMessage]:
        """
        Generate guidance messages for an agent.

        Args:
            agent_id: ID of the agent to guide
            task_context: Context about the current task

        Returns:
            List of GuidanceMessage objects
        """
        guidance = []

        # Get agent's history
        agent_history = self.get_agent_history(agent_id)

        # Generate guidance based on agent's past feedback
        guidance.extend(self._guidance_from_agent_history(agent_id, agent_history))

        # Generate guidance from pattern memory
        if self._pattern_memory and task_context:
            guidance.extend(self._guidance_from_patterns(agent_id, task_context))

        # Generate guidance from strategy tracker
        if self._strategy_tracker and task_context:
            guidance.extend(self._guidance_from_strategies(agent_id, task_context))

        return guidance

    def _guidance_from_agent_history(
        self,
        agent_id: str,
        history: list[AgentFeedback],
    ) -> list[GuidanceMessage]:
        """Generate guidance based on agent's own history."""
        guidance = []

        if not history:
            return guidance

        # Look for recent failures
        recent_failures = [
            fb for fb in history[-10:]  # Last 10
            if fb.feedback_type == FeedbackType.APPROACH_FAILED
        ]

        if len(recent_failures) >= 2:
            guidance.append(GuidanceMessage(
                guidance_id=f"guidance-{uuid.uuid4().hex[:8]}",
                target_agent_id=agent_id,
                guidance_type=GuidanceType.CONFLICT_WARNING,
                title="Recent Failures Detected",
                message=f"You've had {len(recent_failures)} recent resolution failures. Consider trying a different approach.",
                urgency=GuidanceUrgency.MEDIUM,
                reason=f"{len(recent_failures)} failures in last 10 attempts",
            ))

        # Look for pattern suggestions from this agent
        pattern_suggestions = [
            fb for fb in history
            if fb.feedback_type == FeedbackType.PATTERN_SUGGESTION
        ]

        if pattern_suggestions:
            latest = pattern_suggestions[-1]
            if latest.pattern_suggestion:
                guidance.append(GuidanceMessage(
                    guidance_id=f"guidance-{uuid.uuid4().hex[:8]}",
                    target_agent_id=agent_id,
                    guidance_type=GuidanceType.USE_PATTERN,
                    title="Previously Suggested Pattern",
                    message=f"You previously suggested: {latest.pattern_suggestion.description[:100]}",
                    urgency=GuidanceUrgency.LOW,
                    reason="Based on your previous pattern suggestion",
                    pattern_suggestion=latest.pattern_suggestion,
                ))

        return guidance

    def _guidance_from_patterns(
        self,
        agent_id: str,
        task_context: dict,
    ) -> list[GuidanceMessage]:
        """Generate guidance from pattern memory."""
        guidance = []

        # This would use pattern memory to suggest resolutions
        # Implementation depends on ConflictPatternMemory interface
        conflict_type = task_context.get("conflict_type", "")
        files = task_context.get("files", [])

        if conflict_type and self._pattern_memory:
            suggestion = self._pattern_memory.suggest_resolution(
                conflict_type=conflict_type,
                files_involved=files,
                intent_categories=task_context.get("intents", []),
            )

            if suggestion and suggestion.confidence >= 0.5:
                guidance.append(GuidanceMessage(
                    guidance_id=f"guidance-{uuid.uuid4().hex[:8]}",
                    target_agent_id=agent_id,
                    guidance_type=GuidanceType.USE_PATTERN,
                    title="Similar Pattern Found",
                    message=f"Similar conflict resolved with '{suggestion.strategy}' strategy ({suggestion.confidence*100:.0f}% confidence)",
                    urgency=GuidanceUrgency.MEDIUM,
                    reason=f"Pattern hash: {suggestion.pattern_hash}",
                    workflow_id=task_context.get("workflow_id"),
                    related_task=task_context.get("conflict_id"),
                ))

        return guidance

    def _guidance_from_strategies(
        self,
        agent_id: str,
        task_context: dict,
    ) -> list[GuidanceMessage]:
        """Generate guidance from strategy tracker."""
        guidance = []

        if not self._strategy_tracker:
            return guidance

        # Build context for recommendation
        context = {}
        if task_context.get("language"):
            context["language"] = task_context["language"]
        if task_context.get("framework"):
            context["framework"] = task_context["framework"]
        if task_context.get("conflict_type"):
            context["conflict_type"] = task_context["conflict_type"]

        # Get recommendation
        rec = self._strategy_tracker.recommend(context)

        if rec.is_medium_confidence:
            guidance.append(GuidanceMessage(
                guidance_id=f"guidance-{uuid.uuid4().hex[:8]}",
                target_agent_id=agent_id,
                guidance_type=GuidanceType.USE_PATTERN,  # Use USE_PATTERN for strategy hints
                title="Strategy Recommendation",
                message=f"Recommended strategy: '{rec.strategy.value}' ({rec.confidence*100:.0f}% confidence). {rec.reasoning}",
                urgency=GuidanceUrgency.MEDIUM if rec.is_high_confidence else GuidanceUrgency.LOW,
                reason=f"Based on {rec.sample_size} historical uses",
                workflow_id=task_context.get("workflow_id"),
                related_task=task_context.get("conflict_id"),
            ))

            # Include alternatives for lower confidence recommendations
            if not rec.is_high_confidence and rec.alternatives:
                alt_strs = [f"{a[0].value} ({a[1]*100:.0f}%)" for a in rec.alternatives[:2]]
                guidance.append(GuidanceMessage(
                    guidance_id=f"guidance-{uuid.uuid4().hex[:8]}",
                    target_agent_id=agent_id,
                    guidance_type=GuidanceType.CONTEXT_UPDATE,
                    title="Alternative Strategies",
                    message=f"Alternative strategies: {', '.join(alt_strs)}",
                    urgency=GuidanceUrgency.LOW,
                    reason="Lower confidence - consider alternatives",
                    workflow_id=task_context.get("workflow_id"),
                    related_task=task_context.get("conflict_id"),
                ))

        return guidance

    def clear(self) -> None:
        """Clear all feedback history."""
        self._history = FeedbackHistory(created_at=datetime.now(timezone.utc))
        if self.storage_path.exists():
            self.storage_path.unlink()
