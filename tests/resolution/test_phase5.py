"""
Tests for Phase 5: Advanced Resolution.

Tests for:
- MultiCandidateGenerator: Generates 3 candidates with distinct strategies
- DiversityChecker: Ensures candidates are diverse
- TieredValidator: Tiered validation with early elimination
- FlakyTestHandler: Flaky test detection and retry
- SelfCritic: LLM-based critique (optional)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json
import tempfile


# ============================================================================
# MultiCandidateGenerator Tests
# ============================================================================

class TestMultiCandidateGenerator:
    """Tests for multi-candidate generation."""

    def test_generates_three_candidates_by_default(self):
        """Should generate 3 candidates using distinct strategies."""
        from src.resolution.multi_candidate import MultiCandidateGenerator
        from src.resolution.schema import ConflictContext, IntentAnalysis, HarmonizedResult

        generator = MultiCandidateGenerator()

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]
        context.agent_branches = {
            "agent1": "claude/feature-agent1",
            "agent2": "claude/feature-agent2",
        }

        intents = Mock(spec=IntentAnalysis)
        intents.comparison = Mock(relationship="compatible")
        intents.intents = []

        harmonized = Mock(spec=HarmonizedResult)
        harmonized.build_passes = True

        with patch.object(generator, '_generate_single_candidate') as mock_gen:
            mock_gen.return_value = Mock(candidate_id="test", strategy="test")
            candidates = generator.generate(context, intents, harmonized)

        # Should attempt to generate 3 candidates
        assert mock_gen.call_count == 3

    def test_uses_configured_strategies(self):
        """Should use strategies from config."""
        from src.resolution.multi_candidate import MultiCandidateGenerator

        strategies = ["agent1_primary", "convention_primary"]
        generator = MultiCandidateGenerator(strategies=strategies)

        assert generator.strategies == strategies

    def test_generates_with_distinct_strategies(self):
        """Each candidate should use a different strategy."""
        from src.resolution.multi_candidate import MultiCandidateGenerator
        from src.resolution.schema import ConflictContext, IntentAnalysis, HarmonizedResult

        generator = MultiCandidateGenerator()

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]
        context.agent_branches = {"agent1": "branch1", "agent2": "branch2"}

        intents = Mock(spec=IntentAnalysis)
        intents.comparison = Mock(relationship="orthogonal")
        intents.intents = []

        harmonized = Mock(spec=HarmonizedResult)

        with patch.object(generator, '_create_resolution_branch', return_value=True):
            with patch.object(generator, '_get_diff_from_base', return_value="diff"):
                with patch.object(generator, '_get_modified_files', return_value=[]):
                    candidates = generator.generate(context, intents, harmonized)

        # Each candidate should have different strategy
        strategies = [c.strategy for c in candidates]
        assert len(strategies) == len(set(strategies))

    def test_respects_max_candidates_config(self):
        """Should respect max_candidates configuration."""
        from src.resolution.multi_candidate import MultiCandidateGenerator

        generator = MultiCandidateGenerator(max_candidates=2)
        assert generator.max_candidates == 2

    def test_handles_generation_failure_gracefully(self):
        """Should handle individual candidate generation failures."""
        from src.resolution.multi_candidate import MultiCandidateGenerator
        from src.resolution.schema import ConflictContext, IntentAnalysis, HarmonizedResult

        generator = MultiCandidateGenerator()

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]
        context.agent_branches = {"agent1": "branch1", "agent2": "branch2"}

        intents = Mock(spec=IntentAnalysis)
        intents.comparison = Mock(relationship="compatible")
        intents.intents = []  # Add missing attribute
        harmonized = Mock(spec=HarmonizedResult)

        # First call succeeds, second fails, third succeeds
        with patch.object(generator, '_generate_single_candidate') as mock_gen:
            mock_gen.side_effect = [
                Mock(candidate_id="c1"),
                None,  # Failure
                Mock(candidate_id="c3"),
            ]
            candidates = generator.generate(context, intents, harmonized)

        # Should still return the 2 successful candidates
        assert len(candidates) == 2


# ============================================================================
# DiversityChecker Tests
# ============================================================================

class TestDiversityChecker:
    """Tests for candidate diversity checking."""

    def test_calculates_pairwise_diversity(self):
        """Should calculate diversity between pairs of candidates."""
        from src.resolution.diversity import DiversityChecker
        from src.resolution.schema import ResolutionCandidate

        checker = DiversityChecker()

        # Use proper diff format with +/- prefixes
        c1 = Mock()
        c1.diff_from_base = "+line1\n+line2\n+line3"
        c1.candidate_id = "c1"

        c2 = Mock()
        c2.diff_from_base = "+line1\n+line4\n+line5"
        c2.candidate_id = "c2"

        diversity = checker.calculate_pairwise_diversity(c1, c2)

        # Should be between 0 and 1
        assert 0.0 <= diversity <= 1.0
        # Different diffs = some diversity
        assert diversity > 0.0

    def test_identical_diffs_have_zero_diversity(self):
        """Identical diffs should have zero diversity."""
        from src.resolution.diversity import DiversityChecker

        checker = DiversityChecker()

        c1 = Mock()
        c1.diff_from_base = "+same\n+content\n+here"
        c1.candidate_id = "c1"

        c2 = Mock()
        c2.diff_from_base = "+same\n+content\n+here"
        c2.candidate_id = "c2"

        diversity = checker.calculate_pairwise_diversity(c1, c2)
        assert diversity == 0.0

    def test_completely_different_diffs_have_high_diversity(self):
        """Completely different diffs should have high diversity."""
        from src.resolution.diversity import DiversityChecker

        checker = DiversityChecker()

        c1 = Mock()
        c1.diff_from_base = "+aaa\n+bbb\n+ccc"
        c1.candidate_id = "c1"

        c2 = Mock()
        c2.diff_from_base = "+xxx\n+yyy\n+zzz"
        c2.candidate_id = "c2"

        diversity = checker.calculate_pairwise_diversity(c1, c2)
        assert diversity >= 0.8

    def test_checks_minimum_diversity(self):
        """Should check if candidates meet minimum diversity threshold."""
        from src.resolution.diversity import DiversityChecker

        checker = DiversityChecker(min_diversity=0.3)

        c1 = Mock()
        c1.diff_from_base = "+aaa\n+bbb"
        c1.candidate_id = "c1"

        c2 = Mock()
        c2.diff_from_base = "+aaa\n+ccc"
        c2.candidate_id = "c2"

        c3 = Mock()
        c3.diff_from_base = "+aaa\n+ddd"
        c3.candidate_id = "c3"

        result = checker.check_diversity([c1, c2, c3])

        # Result is a DiversityResult dataclass
        assert hasattr(result, "meets_threshold")
        assert hasattr(result, "min_diversity")
        assert hasattr(result, "pairwise_scores")

    def test_flags_low_diversity(self):
        """Should flag when candidates are too similar."""
        from src.resolution.diversity import DiversityChecker

        checker = DiversityChecker(min_diversity=0.5)

        # Very similar candidates
        c1 = Mock()
        c1.diff_from_base = "+same line"
        c1.candidate_id = "c1"

        c2 = Mock()
        c2.diff_from_base = "+same line"
        c2.candidate_id = "c2"

        result = checker.check_diversity([c1, c2])
        assert result.meets_threshold == False


# ============================================================================
# TieredValidator Tests
# ============================================================================

class TestTieredValidator:
    """Tests for tiered validation."""

    def test_tier1_smoke_runs_build_only(self):
        """Tier 1 (smoke) should only run build."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier
        from src.resolution.schema import ResolutionCandidate

        validator = TieredValidator()

        candidate = Mock(spec=ResolutionCandidate)
        candidate.branch_name = "test-branch"
        candidate.candidate_id = "test-1"

        with patch.object(validator, '_checkout_branch', return_value=True):
            with patch.object(validator, '_run_build', return_value=True) as mock_build:
                with patch.object(validator, '_run_lint') as mock_lint:
                    with patch.object(validator, '_run_targeted_tests') as mock_targeted:
                        with patch.object(validator, '_run_full_test_suite') as mock_full:
                            result = validator.validate_tier(candidate, ValidationTier.SMOKE)

        mock_build.assert_called_once()
        mock_lint.assert_not_called()
        mock_targeted.assert_not_called()
        mock_full.assert_not_called()

    def test_tier2_lint_runs_build_and_lint(self):
        """Tier 2 (lint) should run build and lint."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier

        validator = TieredValidator()

        candidate = Mock(branch_name="test-branch")

        with patch.object(validator, '_checkout_branch', return_value=True):
            with patch.object(validator, '_run_build', return_value=True):
                with patch.object(validator, '_run_lint', return_value=0.9) as mock_lint:
                    with patch.object(validator, '_run_targeted_tests') as mock_targeted:
                        with patch.object(validator, '_run_full_test_suite') as mock_full:
                            result = validator.validate_tier(candidate, ValidationTier.LINT)

        mock_lint.assert_called_once()
        mock_targeted.assert_not_called()
        mock_full.assert_not_called()

    def test_tier3_targeted_runs_related_tests(self):
        """Tier 3 (targeted) should run tests for modified files only."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier

        validator = TieredValidator()

        candidate = Mock(branch_name="test-branch", files_modified=["src/auth.py"])

        with patch.object(validator, '_checkout_branch', return_value=True):
            with patch.object(validator, '_run_build', return_value=True):
                with patch.object(validator, '_run_lint', return_value=0.9):
                    with patch.object(validator, '_run_targeted_tests') as mock_tests:
                        mock_tests.return_value = {"passed": 5, "failed": 0, "skipped": 0}
                        result = validator.validate_tier(candidate, ValidationTier.TARGETED)

        mock_tests.assert_called_once()

    def test_tier4_comprehensive_runs_full_suite(self):
        """Tier 4 (comprehensive) should run full test suite."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier

        validator = TieredValidator()

        candidate = Mock(branch_name="test-branch", files_modified=["src/auth.py"])

        with patch.object(validator, '_checkout_branch', return_value=True):
            with patch.object(validator, '_run_build', return_value=True):
                with patch.object(validator, '_run_lint', return_value=0.9):
                    with patch.object(validator, '_run_full_test_suite') as mock_tests:
                        mock_tests.return_value = {"passed": 50, "failed": 0, "skipped": 5}
                        result = validator.validate_tier(candidate, ValidationTier.COMPREHENSIVE)

        mock_tests.assert_called_once()

    def test_early_elimination_on_build_failure(self):
        """Should eliminate candidates that fail build early."""
        from src.resolution.validation_tiers import TieredValidator
        from src.resolution.schema import ResolutionCandidate

        validator = TieredValidator()

        candidates = [
            Mock(branch_name="branch1", build_passed=False),
            Mock(branch_name="branch2", build_passed=True),
            Mock(branch_name="branch3", build_passed=False),
        ]

        # Simulate tier 1 results already set
        for c in candidates:
            c.build_passed = c.build_passed  # Already set in mock

        surviving = validator.filter_viable(candidates, require_build=True)

        assert len(surviving) == 1
        assert surviving[0].branch_name == "branch2"

    def test_determines_appropriate_tier_for_high_risk(self):
        """Should use tier 4 for high-risk files."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier

        validator = TieredValidator()

        # Security file = high risk = tier 4
        tier = validator.determine_tier(["src/auth/login.py"])
        assert tier == ValidationTier.COMPREHENSIVE

        # API file = high risk = tier 4
        tier = validator.determine_tier(["src/api/endpoints.py"])
        assert tier == ValidationTier.COMPREHENSIVE

    def test_determines_tier3_for_normal_files(self):
        """Should use tier 3 for normal files."""
        from src.resolution.validation_tiers import TieredValidator, ValidationTier

        validator = TieredValidator()

        tier = validator.determine_tier(["src/utils/helpers.py"])
        assert tier == ValidationTier.TARGETED


# ============================================================================
# FlakyTestHandler Tests
# ============================================================================

class TestFlakyTestHandler:
    """Tests for flaky test handling."""

    def test_tracks_test_outcomes(self):
        """Should track pass/fail history for tests."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json")

            handler.record_outcome("test_auth.py::test_login", passed=True)
            handler.record_outcome("test_auth.py::test_login", passed=True)
            handler.record_outcome("test_auth.py::test_login", passed=False)

            history = handler.get_history("test_auth.py::test_login")
            assert len(history) == 3
            assert history[-1] == False  # Last outcome

    def test_calculates_flakiness_score(self):
        """Should calculate flakiness score from history."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json")

            # Record alternating results (very flaky)
            test_name = "test_flaky.py::test_sometimes_fails"
            for i in range(10):
                handler.record_outcome(test_name, passed=(i % 2 == 0))

            score = handler.get_flakiness_score(test_name)

            # Alternating = very flaky
            assert score >= 0.4

    def test_stable_test_has_zero_flakiness(self):
        """Stable tests should have zero flakiness."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json")

            test_name = "test_stable.py::test_always_passes"
            for _ in range(10):
                handler.record_outcome(test_name, passed=True)

            score = handler.get_flakiness_score(test_name)
            assert score == 0.0

    def test_retries_flaky_tests(self):
        """Should retry known flaky tests."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json", max_retries=3)

            # Mark test as flaky
            test_name = "test_flaky.py::test_sometimes"
            for i in range(5):
                handler.record_outcome(test_name, passed=(i % 2 == 0))

            # Check if should retry
            should_retry = handler.should_retry(test_name, current_attempt=1)
            assert should_retry == True

    def test_respects_max_retries(self):
        """Should not retry beyond max attempts."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json", max_retries=3)

            test_name = "test_flaky.py::test_sometimes"
            for i in range(5):
                handler.record_outcome(test_name, passed=(i % 2 == 0))

            # Should not retry after max attempts
            should_retry = handler.should_retry(test_name, current_attempt=3)
            assert should_retry == False

    def test_adjusts_score_for_flaky_failures(self):
        """Flaky test failures should have reduced weight in scoring."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FlakyTestHandler(db_path=Path(tmpdir) / "flaky.json")

            # Mark as flaky
            test_name = "test_flaky.py::test_sometimes"
            for i in range(10):
                handler.record_outcome(test_name, passed=(i % 2 == 0))

            weight = handler.get_failure_weight(test_name)

            # Flaky = lower weight
            assert weight < 1.0

    def test_persists_to_disk(self):
        """Should persist flaky data to disk."""
        from src.resolution.flaky_handler import FlakyTestHandler

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "flaky.json"

            # First handler writes
            handler1 = FlakyTestHandler(db_path=db_path)
            handler1.record_outcome("test_x", passed=True)
            handler1.save()

            # Second handler reads
            handler2 = FlakyTestHandler(db_path=db_path)
            handler2.load()

            history = handler2.get_history("test_x")
            assert len(history) == 1


# ============================================================================
# SelfCritic Tests
# ============================================================================

class TestSelfCritic:
    """Tests for LLM self-critique."""

    def test_critiques_candidate(self):
        """Should critique a resolution candidate."""
        from src.resolution.self_critic import SelfCritic
        from src.resolution.schema import ResolutionCandidate, ConflictContext

        critic = SelfCritic()

        candidate = Mock(spec=ResolutionCandidate)
        candidate.diff_from_base = "def login(user):\n    return True"
        candidate.strategy = "convention_primary"

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]

        with patch.object(critic, '_invoke_llm') as mock_llm:
            mock_llm.return_value = "APPROVED"
            result = critic.critique(candidate, context)

        assert result.approved == True

    def test_detects_security_issues(self):
        """Should detect security issues in code."""
        from src.resolution.self_critic import SelfCritic

        critic = SelfCritic()

        candidate = Mock()
        candidate.diff_from_base = """
def authenticate(user, password):
    query = f"SELECT * FROM users WHERE password = '{password}'"
    return db.execute(query)
"""
        candidate.strategy = "convention_primary"
        context = Mock()
        context.agent_ids = ["a1"]
        context.agent_manifests = []

        with patch.object(critic, '_invoke_llm') as mock_llm:
            mock_llm.return_value = "ISSUES:\n- SQL injection vulnerability detected"
            result = critic.critique(candidate, context)

        assert result.approved == False
        assert result.has_security_issues == True

    def test_blocks_on_critical_issues(self):
        """Critical issues should block delivery."""
        from src.resolution.self_critic import SelfCritic, CritiqueResult

        critic = SelfCritic()

        result = CritiqueResult(
            approved=False,
            issues=["SQL injection"],
            has_security_issues=True,
            has_critical_bugs=False,
        )

        assert critic.should_block(result) == True

    def test_does_not_block_on_minor_issues(self):
        """Minor issues should not block delivery."""
        from src.resolution.self_critic import SelfCritic, CritiqueResult

        critic = SelfCritic()

        result = CritiqueResult(
            approved=False,
            issues=["Consider adding docstring"],
            has_security_issues=False,
            has_critical_bugs=False,
        )

        assert critic.should_block(result) == False

    def test_can_be_disabled(self):
        """Self-critique should be disableable."""
        from src.resolution.self_critic import SelfCritic

        critic = SelfCritic(enabled=False)

        candidate = Mock()
        context = Mock()

        result = critic.critique(candidate, context)

        # When disabled, should auto-approve
        assert result.approved == True


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhase5Integration:
    """Integration tests for Phase 5 components."""

    def test_pipeline_generates_multiple_candidates(self):
        """Resolution pipeline should generate multiple candidates."""
        from src.resolution.pipeline import ResolutionPipeline
        from src.conflict.pipeline import PipelineResult
        from src.conflict.detector import ConflictType

        # This tests that Phase 5 components integrate properly
        # Full implementation will be tested after components are built
        pass

    def test_diversity_check_triggers_regeneration(self):
        """Low diversity should trigger candidate regeneration."""
        # Test that diversity check integrates with generator
        pass

    def test_tiered_validation_with_flaky_handling(self):
        """Tiered validation should use flaky test handler."""
        # Test that flaky handler integrates with validator
        pass
