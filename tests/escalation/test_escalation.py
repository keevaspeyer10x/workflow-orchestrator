"""
Tests for the escalation system (Phase 4).

These tests define the expected behavior for the human escalation system.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta


class TestEscalationSchema:
    """Tests for escalation schema and data models."""

    def test_escalation_age_calculation(self):
        """Should correctly calculate escalation age."""
        from src.escalation.schema import Escalation

        # Create escalation 5 hours ago
        five_hours_ago = datetime.now(timezone.utc) - timedelta(hours=5)

        escalation = Escalation(
            escalation_id="test-1",
            created_at=five_hours_ago,
        )

        # Age should be approximately 5 hours
        assert 4.9 <= escalation.age_in_hours <= 5.1

    def test_escalation_timeout_policy_selection(self):
        """Should select correct timeout policy based on priority."""
        from src.escalation.schema import (
            Escalation,
            EscalationPriority,
            TIMEOUT_POLICIES,
        )

        critical = Escalation(
            escalation_id="crit-1",
            priority=EscalationPriority.CRITICAL,
        )
        assert critical.timeout_policy.auto_select == False
        assert critical.timeout_policy.timeout_hours == 24

        low = Escalation(
            escalation_id="low-1",
            priority=EscalationPriority.LOW,
        )
        assert low.timeout_policy.auto_select == True
        assert low.timeout_policy.timeout_hours == 168  # 1 week

    def test_has_risk_flag(self):
        """Should correctly identify risk flags."""
        from src.escalation.schema import Escalation, EscalationTrigger

        escalation = Escalation(
            escalation_id="test-1",
            triggers=[
                EscalationTrigger.SECURITY_SENSITIVE,
                EscalationTrigger.AUTH_CHANGES,
            ],
        )

        assert escalation.has_risk_flag("security")
        assert escalation.has_risk_flag("auth")
        assert not escalation.has_risk_flag("payment")


class TestIssueCreator:
    """Tests for GitHub issue creation."""

    def test_generates_title_with_priority_emoji(self):
        """Should generate title with priority-appropriate emoji."""
        from src.escalation.issue_creator import IssueCreator
        from src.escalation.schema import Escalation, EscalationPriority, EscalationTrigger

        creator = IssueCreator()

        critical = Escalation(
            escalation_id="crit-1",
            priority=EscalationPriority.CRITICAL,
            triggers=[EscalationTrigger.SECURITY_SENSITIVE],
        )
        title = creator._generate_title(critical)
        assert "🚨" in title  # Critical emoji

        standard = Escalation(
            escalation_id="std-1",
            priority=EscalationPriority.STANDARD,
            triggers=[EscalationTrigger.LOW_INTENT_CONFIDENCE],
        )
        title = creator._generate_title(standard)
        assert "🤔" in title  # Standard emoji

    def test_generates_body_with_options(self):
        """Should generate body with all options."""
        from src.escalation.issue_creator import IssueCreator
        from src.escalation.schema import Escalation, EscalationOption

        creator = IssueCreator()

        escalation = Escalation(
            escalation_id="test-1",
            options=[
                EscalationOption(
                    option_id="A",
                    title="Option A",
                    description="First option",
                    is_recommended=True,
                ),
                EscalationOption(
                    option_id="B",
                    title="Option B",
                    description="Second option",
                ),
            ],
            recommendation="A",
        )

        body = creator._generate_body(escalation)

        # Should contain both options
        assert "[A]" in body
        assert "[B]" in body
        assert "Option A" in body
        assert "Option B" in body
        assert "Recommended" in body

    def test_generates_labels(self):
        """Should generate appropriate labels."""
        from src.escalation.issue_creator import IssueCreator
        from src.escalation.schema import Escalation, EscalationPriority, EscalationTrigger

        creator = IssueCreator()

        escalation = Escalation(
            escalation_id="test-1",
            priority=EscalationPriority.HIGH,
            triggers=[EscalationTrigger.AUTH_CHANGES],
        )

        labels = creator._generate_labels(escalation)

        assert "claude-escalation" in labels
        assert "priority:high" in labels


class TestResponseHandler:
    """Tests for response handling."""

    def test_handles_option_selection(self):
        """Should handle option selection (A, B, C)."""
        from src.escalation.response_handler import ResponseHandler
        from src.escalation.schema import Escalation, EscalationOption, EscalationStatus

        handler = ResponseHandler()

        escalation = Escalation(
            escalation_id="test-1",
            options=[
                EscalationOption(option_id="A", title="Option A", description="First"),
                EscalationOption(option_id="B", title="Option B", description="Second"),
            ],
        )

        with patch.object(handler, '_post_selection_confirmation'):
            result = handler.process_response(escalation, "A")

        assert result.resolved == True
        assert result.winner.option_id == "A"
        assert escalation.status == EscalationStatus.RESOLVED

    def test_handles_explain_request(self):
        """Should handle explain request."""
        from src.escalation.response_handler import ResponseHandler
        from src.escalation.schema import Escalation, EscalationStatus

        handler = ResponseHandler()

        escalation = Escalation(
            escalation_id="test-1",
            issue_number=123,
        )

        with patch.object(handler.issue_creator, 'add_comment'):
            result = handler.process_response(escalation, "explain")

        assert result.resolved == False
        assert result.awaiting_response == True
        assert escalation.status == EscalationStatus.AWAITING_INFO

    def test_handles_custom_preference(self):
        """Should handle custom: prefix."""
        from src.escalation.response_handler import ResponseHandler
        from src.escalation.schema import Escalation

        handler = ResponseHandler()

        escalation = Escalation(
            escalation_id="test-1",
            issue_number=123,
        )

        with patch.object(handler.issue_creator, 'add_comment'):
            result = handler.process_response(escalation, "custom: use React instead")

        assert result.custom == True
        assert result.custom_preference == "use React instead"

    def test_parses_github_comment(self):
        """Should parse various GitHub comment formats."""
        from src.escalation.response_handler import parse_github_comment

        # Direct option
        assert parse_github_comment("A") == "A"
        assert parse_github_comment("b") == "B"

        # Explain
        assert parse_github_comment("explain") == "explain"

        # Custom
        assert parse_github_comment("custom: my preference").startswith("custom:")

        # Option in sentence
        assert parse_github_comment("I'll go with option B") == "B"


class TestTimeoutHandler:
    """Tests for timeout handling."""

    def test_sends_reminder_at_threshold(self):
        """Should send reminder when reminder_hours reached."""
        from src.escalation.timeout_handler import TimeoutHandler
        from src.escalation.schema import Escalation, EscalationPriority

        handler = TimeoutHandler()

        # Create escalation that's past reminder threshold
        old_time = datetime.now(timezone.utc) - timedelta(hours=30)
        escalation = Escalation(
            escalation_id="test-1",
            priority=EscalationPriority.STANDARD,  # 24h reminder
            created_at=old_time,
        )

        with patch.object(handler, '_send_reminder') as mock_remind:
            handler.check_timeout(escalation)
            mock_remind.assert_called_once()

    def test_auto_selects_on_timeout(self):
        """Should auto-select when timeout reached and allowed."""
        from src.escalation.timeout_handler import TimeoutHandler
        from src.escalation.schema import (
            Escalation,
            EscalationOption,
            EscalationPriority,
            EscalationStatus,
        )

        handler = TimeoutHandler()

        # Create escalation past timeout threshold
        old_time = datetime.now(timezone.utc) - timedelta(hours=100)
        escalation = Escalation(
            escalation_id="test-1",
            priority=EscalationPriority.STANDARD,  # 72h timeout, auto_select=True
            created_at=old_time,
            options=[
                EscalationOption(option_id="A", title="Recommended", description="Best", is_recommended=True),
            ],
            recommendation="A",
        )

        with patch.object(handler, '_post_auto_select_notification'):
            result = handler.check_timeout(escalation)

        assert result is not None
        assert result.resolved == True
        assert result.auto_selected == True
        assert escalation.status == EscalationStatus.AUTO_SELECTED

    def test_does_not_auto_select_critical(self):
        """Should NOT auto-select critical escalations."""
        from src.escalation.timeout_handler import TimeoutHandler
        from src.escalation.schema import (
            Escalation,
            EscalationOption,
            EscalationPriority,
            EscalationStatus,
        )

        handler = TimeoutHandler()

        # Critical escalation past timeout
        old_time = datetime.now(timezone.utc) - timedelta(hours=50)
        escalation = Escalation(
            escalation_id="crit-1",
            priority=EscalationPriority.CRITICAL,  # auto_select=False
            created_at=old_time,
            options=[
                EscalationOption(option_id="A", title="Option", description="Desc"),
            ],
        )

        # Mock the notification methods, not the whole _send_urgent_escalation
        with patch.object(handler, '_send_urgent_github_notice'):
            with patch.object(handler, '_send_urgent_slack_notice'):
                with patch.object(handler, '_send_urgent_email_notice'):
                    result = handler.check_timeout(escalation)

        # Status should be TIMEOUT (not auto-selected)
        assert escalation.status == EscalationStatus.TIMEOUT
        # Should not be resolved (awaiting human)
        assert result.resolved == False


class TestFeaturePorter:
    """Tests for feature porting."""

    def test_identifies_unique_features(self):
        """Should identify files unique to loser candidate."""
        from src.escalation.feature_porter import FeaturePorter
        from src.resolution.schema import ResolutionCandidate

        porter = FeaturePorter()

        winner = ResolutionCandidate(
            candidate_id="w1",
            strategy="agent1_primary",
            branch_name="winner",
            files_modified=["src/a.py", "src/b.py"],
        )

        loser = ResolutionCandidate(
            candidate_id="l1",
            strategy="agent2_primary",
            branch_name="loser",
            files_modified=["src/b.py", "src/c.py", "src/d.py"],
        )

        unique = porter._identify_unique_features(winner, loser)

        # src/c.py and src/d.py are unique to loser
        assert "src/c.py" in unique
        assert "src/d.py" in unique
        assert "src/b.py" not in unique  # Shared

    def test_excludes_test_files(self):
        """Should not port test files."""
        from src.escalation.feature_porter import FeaturePorter

        porter = FeaturePorter()

        assert porter._is_test_or_config("tests/test_foo.py") == True
        assert porter._is_test_or_config("src/foo.spec.ts") == True
        assert porter._is_test_or_config("src/foo.py") == False

    def test_excludes_config_files(self):
        """Should not port config files."""
        from src.escalation.feature_porter import FeaturePorter

        porter = FeaturePorter()

        assert porter._is_test_or_config(".env") == True
        assert porter._is_test_or_config("config/settings.yaml") == True
        assert porter._is_test_or_config("pyproject.toml") == True
        assert porter._is_test_or_config("src/main.py") == False


class TestEscalationManager:
    """Tests for the main escalation manager."""

    def test_creates_escalation_from_resolution(self):
        """Should create escalation from resolution failure."""
        from src.escalation.manager import EscalationManager
        from src.resolution.schema import Resolution, ResolutionCandidate

        manager = EscalationManager()

        resolution = Resolution(
            resolution_id="res-1",
            needs_escalation=True,
            escalation_reason="low_intent_confidence",
            all_candidates=[
                ResolutionCandidate(
                    candidate_id="c1",
                    strategy="agent1_primary",
                    branch_name="branch1",
                    build_passed=True,
                    total_score=0.75,
                ),
            ],
        )

        with patch.object(manager.issue_creator, 'create_issue', return_value=(123, "url")):
            escalation = manager.create_escalation(resolution)

        assert escalation is not None
        assert len(escalation.options) > 0
        assert escalation.issue_number == 123

    def test_determines_priority_from_triggers(self):
        """Should determine priority based on triggers."""
        from src.escalation.manager import EscalationManager
        from src.escalation.schema import EscalationTrigger, EscalationPriority

        manager = EscalationManager()

        # Security = Critical
        triggers = [EscalationTrigger.SECURITY_SENSITIVE]
        assert manager._determine_priority(triggers, None) == EscalationPriority.CRITICAL

        # Auth = High
        triggers = [EscalationTrigger.AUTH_CHANGES]
        assert manager._determine_priority(triggers, None) == EscalationPriority.HIGH

        # Similar candidates = Low
        triggers = [EscalationTrigger.CANDIDATES_TOO_SIMILAR]
        assert manager._determine_priority(triggers, None) == EscalationPriority.LOW

    def test_generates_options_from_candidates(self):
        """Should generate options from resolution candidates."""
        from src.escalation.manager import EscalationManager
        from src.resolution.schema import ResolutionCandidate

        manager = EscalationManager()

        candidates = [
            ResolutionCandidate(
                candidate_id="c1",
                strategy="agent1_primary",
                branch_name="b1",
                summary="Agent 1 approach",
            ),
            ResolutionCandidate(
                candidate_id="c2",
                strategy="agent2_primary",
                branch_name="b2",
                summary="Agent 2 approach",
            ),
        ]

        options = manager._generate_options(candidates)

        assert len(options) == 2
        assert options[0].option_id == "A"
        assert options[1].option_id == "B"

    def test_processes_response_and_ports_features(self):
        """Should process response and port features."""
        from src.escalation.manager import EscalationManager
        from src.escalation.schema import (
            Escalation,
            EscalationOption,
        )
        from src.resolution.schema import ResolutionCandidate

        manager = EscalationManager()

        # Create an escalation
        escalation = Escalation(
            escalation_id="test-1",
            options=[
                EscalationOption(
                    option_id="A",
                    title="Option A",
                    description="First",
                    candidate=ResolutionCandidate(
                        candidate_id="c1",
                        strategy="agent1_primary",
                        branch_name="b1",
                    ),
                ),
                EscalationOption(
                    option_id="B",
                    title="Option B",
                    description="Second",
                    candidate=ResolutionCandidate(
                        candidate_id="c2",
                        strategy="agent2_primary",
                        branch_name="b2",
                    ),
                ),
            ],
        )
        manager._escalations["test-1"] = escalation

        with patch.object(manager.response_handler, '_post_selection_confirmation'):
            with patch.object(manager.feature_porter, 'port_features', return_value=[]):
                with patch.object(manager.issue_creator, 'close_issue'):
                    result = manager.process_response("test-1", "A")

        assert result.resolved == True
        assert result.winner.option_id == "A"


class TestAlwaysEscalateTriggers:
    """Tests for always-escalate triggers."""

    def test_security_triggers_always_escalate(self):
        """Security triggers should be in ALWAYS_ESCALATE."""
        from src.escalation.schema import (
            EscalationTrigger,
            ALWAYS_ESCALATE_TRIGGERS,
        )

        assert EscalationTrigger.SECURITY_SENSITIVE in ALWAYS_ESCALATE_TRIGGERS
        assert EscalationTrigger.AUTH_CHANGES in ALWAYS_ESCALATE_TRIGGERS
        assert EscalationTrigger.DB_MIGRATIONS in ALWAYS_ESCALATE_TRIGGERS

    def test_quality_triggers_always_escalate(self):
        """Quality triggers should be in ALWAYS_ESCALATE."""
        from src.escalation.schema import (
            EscalationTrigger,
            ALWAYS_ESCALATE_TRIGGERS,
        )

        assert EscalationTrigger.TESTS_REMOVED in ALWAYS_ESCALATE_TRIGGERS
        assert EscalationTrigger.TESTS_WEAKENED in ALWAYS_ESCALATE_TRIGGERS
