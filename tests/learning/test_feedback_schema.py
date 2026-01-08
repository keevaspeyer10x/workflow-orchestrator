"""
Tests for the learning module feedback schema.

These tests define the expected behavior for the agent feedback
and proactive guidance system.
"""

import pytest
from datetime import datetime, timezone, timedelta


class TestFeedbackType:
    """Tests for FeedbackType enum."""

    def test_feedback_types_exist(self):
        """Should have all expected feedback types."""
        from src.learning.feedback_schema import FeedbackType

        # Resolution feedback
        assert FeedbackType.CONFLICT_HINT == "conflict_hint"
        assert FeedbackType.PATTERN_SUGGESTION == "pattern_suggestion"
        assert FeedbackType.RESOLUTION_OUTCOME == "resolution_outcome"

        # Work feedback
        assert FeedbackType.APPROACH_WORKED == "approach_worked"
        assert FeedbackType.APPROACH_FAILED == "approach_failed"

        # Context feedback
        assert FeedbackType.MISSING_CONTEXT == "missing_context"
        assert FeedbackType.UNCLEAR_INTENT == "unclear_intent"

        # System feedback
        assert FeedbackType.TOOLING_ISSUE == "tooling_issue"
        assert FeedbackType.TIMING_ISSUE == "timing_issue"


class TestFeedbackSeverity:
    """Tests for FeedbackSeverity enum."""

    def test_severity_levels(self):
        """Should have all severity levels."""
        from src.learning.feedback_schema import FeedbackSeverity

        assert FeedbackSeverity.INFO == "info"
        assert FeedbackSeverity.WARNING == "warning"
        assert FeedbackSeverity.CRITICAL == "critical"


class TestConflictHint:
    """Tests for ConflictHint dataclass."""

    def test_creates_conflict_hint(self):
        """Should create conflict hint with required fields."""
        from src.learning.feedback_schema import ConflictHint

        hint = ConflictHint(
            files=["src/auth.py", "src/users.py"],
            description="Both agents modified authentication logic",
        )

        assert hint.files == ["src/auth.py", "src/users.py"]
        assert "authentication" in hint.description
        assert hint.conflict_type == "textual"  # default

    def test_conflict_hint_with_all_fields(self):
        """Should create conflict hint with all optional fields."""
        from src.learning.feedback_schema import ConflictHint

        hint = ConflictHint(
            files=["src/api.py"],
            description="Interface change conflict",
            other_agent_id="agent-xyz",
            conflict_type="interface",
            evidence="def foo(a) vs def foo(a, b)",
            suggested_resolution="Use optional parameter with default",
        )

        assert hint.other_agent_id == "agent-xyz"
        assert hint.conflict_type == "interface"
        assert hint.evidence != ""
        assert hint.suggested_resolution != ""


class TestPatternSuggestion:
    """Tests for PatternSuggestion dataclass."""

    def test_creates_pattern_suggestion(self):
        """Should create pattern suggestion with required fields."""
        from src.learning.feedback_schema import PatternSuggestion

        pattern = PatternSuggestion(
            pattern_name="Repository Pattern",
            description="Use repository classes for data access",
            context="When implementing database operations",
        )

        assert pattern.pattern_name == "Repository Pattern"
        assert "data access" in pattern.description
        assert pattern.confidence == "medium"  # default

    def test_pattern_suggestion_with_example(self):
        """Should include example code."""
        from src.learning.feedback_schema import PatternSuggestion

        pattern = PatternSuggestion(
            pattern_name="Dependency Injection",
            description="Inject dependencies rather than instantiate",
            context="Service layer classes",
            example_code="def __init__(self, repo: Repository):",
            source_files=["src/services/user_service.py"],
            confidence="high",
        )

        assert "def __init__" in pattern.example_code
        assert len(pattern.source_files) == 1
        assert pattern.confidence == "high"


class TestAgentFeedback:
    """Tests for AgentFeedback dataclass."""

    def test_creates_basic_feedback(self):
        """Should create feedback with required fields."""
        from src.learning.feedback_schema import (
            AgentFeedback,
            FeedbackType,
            FeedbackSeverity,
        )

        feedback = AgentFeedback(
            feedback_id="fb-001",
            agent_id="agent-abc123",
            feedback_type=FeedbackType.APPROACH_WORKED,
        )

        assert feedback.feedback_id == "fb-001"
        assert feedback.agent_id == "agent-abc123"
        assert feedback.feedback_type == FeedbackType.APPROACH_WORKED
        assert feedback.severity == FeedbackSeverity.INFO
        assert isinstance(feedback.created_at, datetime)

    def test_feedback_with_what_worked(self):
        """Should track what worked."""
        from src.learning.feedback_schema import AgentFeedback, FeedbackType

        feedback = AgentFeedback(
            feedback_id="fb-002",
            agent_id="agent-def456",
            feedback_type=FeedbackType.RESOLUTION_OUTCOME,
            what_worked=["Using adapter pattern", "Adding retry logic"],
            what_didnt_work=[],
        )

        assert len(feedback.what_worked) == 2
        assert "adapter pattern" in feedback.what_worked[0]
        assert len(feedback.what_didnt_work) == 0

    def test_feedback_with_suggestions(self):
        """Should include improvement suggestions."""
        from src.learning.feedback_schema import AgentFeedback, FeedbackType

        feedback = AgentFeedback(
            feedback_id="fb-003",
            agent_id="agent-ghi789",
            feedback_type=FeedbackType.APPROACH_FAILED,
            suggested_improvements=[
                "Check for existing implementations first",
                "Coordinate with other agents on shared files",
            ],
        )

        assert len(feedback.suggested_improvements) == 2

    def test_feedback_with_conflict_hint(self):
        """Should include conflict hint."""
        from src.learning.feedback_schema import (
            AgentFeedback,
            FeedbackType,
            ConflictHint,
        )

        hint = ConflictHint(
            files=["src/models.py"],
            description="Schema conflict detected",
        )

        feedback = AgentFeedback(
            feedback_id="fb-004",
            agent_id="agent-jkl012",
            feedback_type=FeedbackType.CONFLICT_HINT,
            conflict_hint=hint,
        )

        assert feedback.conflict_hint is not None
        assert feedback.conflict_hint.files == ["src/models.py"]

    def test_feedback_with_pattern_suggestion(self):
        """Should include pattern suggestion."""
        from src.learning.feedback_schema import (
            AgentFeedback,
            FeedbackType,
            PatternSuggestion,
        )

        pattern = PatternSuggestion(
            pattern_name="Factory Pattern",
            description="Use factory for object creation",
            context="Creating polymorphic objects",
        )

        feedback = AgentFeedback(
            feedback_id="fb-005",
            agent_id="agent-mno345",
            feedback_type=FeedbackType.PATTERN_SUGGESTION,
            pattern_suggestion=pattern,
        )

        assert feedback.pattern_suggestion is not None
        assert feedback.pattern_suggestion.pattern_name == "Factory Pattern"

    def test_has_actionable_insights_true(self):
        """Should detect actionable insights."""
        from src.learning.feedback_schema import (
            AgentFeedback,
            FeedbackType,
            PatternSuggestion,
        )

        feedback = AgentFeedback(
            feedback_id="fb-006",
            agent_id="agent-pqr678",
            feedback_type=FeedbackType.APPROACH_WORKED,
            suggested_improvements=["Do X instead of Y"],
        )

        assert feedback.has_actionable_insights == True

    def test_has_actionable_insights_false(self):
        """Should return false when no actionable insights."""
        from src.learning.feedback_schema import AgentFeedback, FeedbackType

        feedback = AgentFeedback(
            feedback_id="fb-007",
            agent_id="agent-stu901",
            feedback_type=FeedbackType.TOOLING_ISSUE,
            # No suggestions, hints, or patterns
        )

        assert feedback.has_actionable_insights == False

    def test_is_success_feedback(self):
        """Should identify success feedback."""
        from src.learning.feedback_schema import AgentFeedback, FeedbackType

        # Success case
        success = AgentFeedback(
            feedback_id="fb-008",
            agent_id="agent-vwx234",
            feedback_type=FeedbackType.APPROACH_WORKED,
            what_worked=["Everything went smoothly"],
        )
        assert success.is_success_feedback == True

        # Failure case
        failure = AgentFeedback(
            feedback_id="fb-009",
            agent_id="agent-yza567",
            feedback_type=FeedbackType.APPROACH_FAILED,
            what_didnt_work=["Build failed"],
        )
        assert failure.is_success_feedback == False

        # Mixed case (not pure success)
        mixed = AgentFeedback(
            feedback_id="fb-010",
            agent_id="agent-bcd890",
            feedback_type=FeedbackType.RESOLUTION_OUTCOME,
            what_worked=["Tests passed"],
            what_didnt_work=["Lint issues"],
        )
        assert mixed.is_success_feedback == False

    def test_summary_generation(self):
        """Should generate readable summary."""
        from src.learning.feedback_schema import (
            AgentFeedback,
            FeedbackType,
            FeedbackSeverity,
        )

        feedback = AgentFeedback(
            feedback_id="fb-011",
            agent_id="agent-efg123",
            feedback_type=FeedbackType.CONFLICT_HINT,
            severity=FeedbackSeverity.WARNING,
            what_worked=["Quick detection"],
            what_didnt_work=["Initial approach failed"],
            suggested_improvements=["Try X", "Try Y", "Try Z"],
        )

        summary = feedback.summary()

        assert "conflict_hint" in summary
        assert "warning" in summary
        assert "Worked:" in summary
        assert "Failed:" in summary
        assert "Suggestions: 3" in summary


class TestGuidanceType:
    """Tests for GuidanceType enum."""

    def test_guidance_types_exist(self):
        """Should have all expected guidance types."""
        from src.learning.feedback_schema import GuidanceType

        # Conflict prevention
        assert GuidanceType.CONFLICT_WARNING == "conflict_warning"
        assert GuidanceType.FILE_LOCK_HINT == "file_lock_hint"
        assert GuidanceType.COORDINATION_HINT == "coordination_hint"

        # Pattern guidance
        assert GuidanceType.USE_PATTERN == "use_pattern"
        assert GuidanceType.AVOID_PATTERN == "avoid_pattern"

        # Context sharing
        assert GuidanceType.CONTEXT_UPDATE == "context_update"
        assert GuidanceType.TASK_CLARIFICATION == "task_clarification"

        # Priority/scheduling
        assert GuidanceType.PRIORITY_UPDATE == "priority_update"
        assert GuidanceType.SEQUENCE_HINT == "sequence_hint"


class TestGuidanceUrgency:
    """Tests for GuidanceUrgency enum."""

    def test_urgency_levels(self):
        """Should have all urgency levels."""
        from src.learning.feedback_schema import GuidanceUrgency

        assert GuidanceUrgency.LOW == "low"
        assert GuidanceUrgency.MEDIUM == "medium"
        assert GuidanceUrgency.HIGH == "high"
        assert GuidanceUrgency.BLOCKING == "blocking"


class TestGuidanceMessage:
    """Tests for GuidanceMessage dataclass."""

    def test_creates_basic_guidance(self):
        """Should create guidance with required fields."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-001",
            target_agent_id="agent-abc",
            guidance_type=GuidanceType.CONFLICT_WARNING,
            title="Potential Conflict Detected",
            message="Agent xyz is working on the same file",
        )

        assert guidance.guidance_id == "guide-001"
        assert guidance.target_agent_id == "agent-abc"
        assert guidance.guidance_type == GuidanceType.CONFLICT_WARNING
        assert "Conflict" in guidance.title

    def test_guidance_with_conflict_details(self):
        """Should include conflict-specific details."""
        from src.learning.feedback_schema import (
            GuidanceMessage,
            GuidanceType,
            GuidanceUrgency,
            ConflictHint,
        )

        hint = ConflictHint(
            files=["src/api.py"],
            description="Both agents modifying API routes",
        )

        guidance = GuidanceMessage(
            guidance_id="guide-002",
            target_agent_id="agent-def",
            guidance_type=GuidanceType.COORDINATION_HINT,
            urgency=GuidanceUrgency.HIGH,
            title="Coordinate on API Changes",
            message="Suggest coordinating with agent-xyz on API routes",
            conflict_hint=hint,
            files_to_avoid=["src/api.py", "src/routes.py"],
            agents_to_coordinate=["agent-xyz"],
        )

        assert guidance.urgency == GuidanceUrgency.HIGH
        assert guidance.conflict_hint is not None
        assert len(guidance.files_to_avoid) == 2
        assert "agent-xyz" in guidance.agents_to_coordinate

    def test_guidance_with_pattern(self):
        """Should include pattern suggestions."""
        from src.learning.feedback_schema import (
            GuidanceMessage,
            GuidanceType,
            PatternSuggestion,
        )

        pattern = PatternSuggestion(
            pattern_name="Error Handling",
            description="Use try-except with specific exceptions",
            context="API endpoint handlers",
        )

        guidance = GuidanceMessage(
            guidance_id="guide-003",
            target_agent_id="agent-ghi",
            guidance_type=GuidanceType.USE_PATTERN,
            title="Recommended Error Handling Pattern",
            message="Consider using established error handling pattern",
            pattern_suggestion=pattern,
        )

        assert guidance.pattern_suggestion is not None
        assert guidance.pattern_suggestion.pattern_name == "Error Handling"

    def test_is_active_returns_true_when_not_expired(self):
        """Should be active when not expired or applied."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-004",
            target_agent_id="agent-jkl",
            guidance_type=GuidanceType.CONTEXT_UPDATE,
            title="Context Update",
            message="New information available",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        assert guidance.is_active == True

    def test_is_active_returns_false_when_expired(self):
        """Should be inactive when expired."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-005",
            target_agent_id="agent-mno",
            guidance_type=GuidanceType.CONTEXT_UPDATE,
            title="Expired Update",
            message="Old information",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert guidance.is_active == False

    def test_is_active_returns_false_when_applied(self):
        """Should be inactive when already applied."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-006",
            target_agent_id="agent-pqr",
            guidance_type=GuidanceType.USE_PATTERN,
            title="Applied Pattern",
            message="Already applied",
            applied=True,
        )

        assert guidance.is_active == False

    def test_is_conflict_related(self):
        """Should identify conflict-related guidance."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        conflict_types = [
            GuidanceType.CONFLICT_WARNING,
            GuidanceType.FILE_LOCK_HINT,
            GuidanceType.COORDINATION_HINT,
        ]

        for gtype in conflict_types:
            guidance = GuidanceMessage(
                guidance_id="guide-007",
                target_agent_id="agent-stu",
                guidance_type=gtype,
                title="Test",
                message="Test",
            )
            assert guidance.is_conflict_related == True

        non_conflict = GuidanceMessage(
            guidance_id="guide-008",
            target_agent_id="agent-vwx",
            guidance_type=GuidanceType.USE_PATTERN,
            title="Pattern",
            message="Pattern suggestion",
        )
        assert non_conflict.is_conflict_related == False

    def test_acknowledge(self):
        """Should track acknowledgment."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-009",
            target_agent_id="agent-yza",
            guidance_type=GuidanceType.PRIORITY_UPDATE,
            title="Priority Change",
            message="Task priority increased",
        )

        assert guidance.acknowledged == False
        guidance.acknowledge()
        assert guidance.acknowledged == True
        assert guidance.acknowledged_at is not None

    def test_mark_applied(self):
        """Should track application."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-010",
            target_agent_id="agent-bcd",
            guidance_type=GuidanceType.AVOID_PATTERN,
            title="Avoid Anti-pattern",
            message="Don't use this pattern",
        )

        assert guidance.applied == False
        guidance.mark_applied()
        assert guidance.applied == True
        assert guidance.applied_at is not None

    def test_mark_ignored(self):
        """Should track ignored with reason."""
        from src.learning.feedback_schema import GuidanceMessage, GuidanceType

        guidance = GuidanceMessage(
            guidance_id="guide-011",
            target_agent_id="agent-efg",
            guidance_type=GuidanceType.SEQUENCE_HINT,
            title="Sequence Suggestion",
            message="Consider different task order",
        )

        guidance.mark_ignored("Not applicable to current task")
        assert guidance.applied == False
        assert guidance.ignored_reason == "Not applicable to current task"


class TestFeedbackBatch:
    """Tests for FeedbackBatch dataclass."""

    def test_creates_empty_batch(self):
        """Should create empty batch."""
        from src.learning.feedback_schema import FeedbackBatch

        batch = FeedbackBatch(batch_id="batch-001")

        assert batch.batch_id == "batch-001"
        assert len(batch.feedback_items) == 0

    def test_groups_by_type(self):
        """Should group feedback by type."""
        from src.learning.feedback_schema import (
            FeedbackBatch,
            AgentFeedback,
            FeedbackType,
        )

        batch = FeedbackBatch(
            batch_id="batch-002",
            feedback_items=[
                AgentFeedback(
                    feedback_id="fb-a",
                    agent_id="agent-1",
                    feedback_type=FeedbackType.CONFLICT_HINT,
                ),
                AgentFeedback(
                    feedback_id="fb-b",
                    agent_id="agent-2",
                    feedback_type=FeedbackType.CONFLICT_HINT,
                ),
                AgentFeedback(
                    feedback_id="fb-c",
                    agent_id="agent-1",
                    feedback_type=FeedbackType.APPROACH_WORKED,
                ),
            ],
        )

        by_type = batch.by_type

        assert FeedbackType.CONFLICT_HINT in by_type
        assert len(by_type[FeedbackType.CONFLICT_HINT]) == 2
        assert FeedbackType.APPROACH_WORKED in by_type
        assert len(by_type[FeedbackType.APPROACH_WORKED]) == 1

    def test_groups_by_agent(self):
        """Should group feedback by agent."""
        from src.learning.feedback_schema import (
            FeedbackBatch,
            AgentFeedback,
            FeedbackType,
        )

        batch = FeedbackBatch(
            batch_id="batch-003",
            feedback_items=[
                AgentFeedback(
                    feedback_id="fb-x",
                    agent_id="agent-A",
                    feedback_type=FeedbackType.TOOLING_ISSUE,
                ),
                AgentFeedback(
                    feedback_id="fb-y",
                    agent_id="agent-B",
                    feedback_type=FeedbackType.TIMING_ISSUE,
                ),
                AgentFeedback(
                    feedback_id="fb-z",
                    agent_id="agent-A",
                    feedback_type=FeedbackType.APPROACH_FAILED,
                ),
            ],
        )

        by_agent = batch.by_agent

        assert "agent-A" in by_agent
        assert len(by_agent["agent-A"]) == 2
        assert "agent-B" in by_agent
        assert len(by_agent["agent-B"]) == 1

    def test_filters_actionable_items(self):
        """Should filter actionable items."""
        from src.learning.feedback_schema import (
            FeedbackBatch,
            AgentFeedback,
            FeedbackType,
        )

        batch = FeedbackBatch(
            batch_id="batch-004",
            feedback_items=[
                AgentFeedback(
                    feedback_id="fb-1",
                    agent_id="agent-1",
                    feedback_type=FeedbackType.APPROACH_WORKED,
                    suggested_improvements=["Do this better"],
                ),
                AgentFeedback(
                    feedback_id="fb-2",
                    agent_id="agent-2",
                    feedback_type=FeedbackType.TOOLING_ISSUE,
                    # No suggestions
                ),
            ],
        )

        actionable = batch.actionable_items

        assert len(actionable) == 1
        assert actionable[0].feedback_id == "fb-1"


class TestGuidanceBatch:
    """Tests for GuidanceBatch dataclass."""

    def test_creates_empty_batch(self):
        """Should create empty batch."""
        from src.learning.feedback_schema import GuidanceBatch

        batch = GuidanceBatch(batch_id="gbatch-001")

        assert batch.batch_id == "gbatch-001"
        assert len(batch.guidance_messages) == 0

    def test_groups_by_agent(self):
        """Should group guidance by target agent."""
        from src.learning.feedback_schema import (
            GuidanceBatch,
            GuidanceMessage,
            GuidanceType,
        )

        batch = GuidanceBatch(
            batch_id="gbatch-002",
            guidance_messages=[
                GuidanceMessage(
                    guidance_id="g-1",
                    target_agent_id="agent-A",
                    guidance_type=GuidanceType.USE_PATTERN,
                    title="Pattern A",
                    message="Use pattern A",
                ),
                GuidanceMessage(
                    guidance_id="g-2",
                    target_agent_id="agent-B",
                    guidance_type=GuidanceType.AVOID_PATTERN,
                    title="Avoid B",
                    message="Avoid pattern B",
                ),
                GuidanceMessage(
                    guidance_id="g-3",
                    target_agent_id="agent-A",
                    guidance_type=GuidanceType.CONTEXT_UPDATE,
                    title="Update A",
                    message="Context update for A",
                ),
            ],
        )

        by_agent = batch.by_agent

        assert "agent-A" in by_agent
        assert len(by_agent["agent-A"]) == 2
        assert "agent-B" in by_agent
        assert len(by_agent["agent-B"]) == 1

    def test_filters_urgent_messages(self):
        """Should filter high/blocking urgency messages."""
        from src.learning.feedback_schema import (
            GuidanceBatch,
            GuidanceMessage,
            GuidanceType,
            GuidanceUrgency,
        )

        batch = GuidanceBatch(
            batch_id="gbatch-003",
            guidance_messages=[
                GuidanceMessage(
                    guidance_id="g-low",
                    target_agent_id="agent-1",
                    guidance_type=GuidanceType.USE_PATTERN,
                    urgency=GuidanceUrgency.LOW,
                    title="Low Priority",
                    message="Low priority",
                ),
                GuidanceMessage(
                    guidance_id="g-high",
                    target_agent_id="agent-1",
                    guidance_type=GuidanceType.CONFLICT_WARNING,
                    urgency=GuidanceUrgency.HIGH,
                    title="High Priority",
                    message="High priority",
                ),
                GuidanceMessage(
                    guidance_id="g-blocking",
                    target_agent_id="agent-2",
                    guidance_type=GuidanceType.FILE_LOCK_HINT,
                    urgency=GuidanceUrgency.BLOCKING,
                    title="Blocking",
                    message="Blocking issue",
                ),
            ],
        )

        urgent = batch.urgent_messages

        assert len(urgent) == 2
        assert any(m.guidance_id == "g-high" for m in urgent)
        assert any(m.guidance_id == "g-blocking" for m in urgent)

    def test_filters_conflict_related(self):
        """Should filter conflict-related messages."""
        from src.learning.feedback_schema import (
            GuidanceBatch,
            GuidanceMessage,
            GuidanceType,
        )

        batch = GuidanceBatch(
            batch_id="gbatch-004",
            guidance_messages=[
                GuidanceMessage(
                    guidance_id="g-pattern",
                    target_agent_id="agent-1",
                    guidance_type=GuidanceType.USE_PATTERN,
                    title="Pattern",
                    message="Use pattern",
                ),
                GuidanceMessage(
                    guidance_id="g-conflict",
                    target_agent_id="agent-2",
                    guidance_type=GuidanceType.CONFLICT_WARNING,
                    title="Conflict",
                    message="Potential conflict",
                ),
                GuidanceMessage(
                    guidance_id="g-coord",
                    target_agent_id="agent-3",
                    guidance_type=GuidanceType.COORDINATION_HINT,
                    title="Coordinate",
                    message="Coordinate with others",
                ),
            ],
        )

        conflict_related = batch.conflict_related

        assert len(conflict_related) == 2
        assert any(m.guidance_id == "g-conflict" for m in conflict_related)
        assert any(m.guidance_id == "g-coord" for m in conflict_related)


class TestModuleImports:
    """Test that the module exports are correct."""

    def test_imports_from_learning_module(self):
        """Should be able to import from learning module."""
        from src.learning import (
            FeedbackType,
            FeedbackSeverity,
            AgentFeedback,
            GuidanceType,
            GuidanceMessage,
            ConflictHint,
            PatternSuggestion,
        )

        # Verify they're the correct types
        assert FeedbackType.CONFLICT_HINT == "conflict_hint"
        assert GuidanceType.CONFLICT_WARNING == "conflict_warning"
