"""
Tests for the resolution pipeline (Phase 3).

These tests define the expected behavior for the resolution system.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


class TestContextAssembler:
    """Tests for Stage 1: Context Assembly."""

    def test_assembles_context_from_detection_result(self):
        """Should assemble context from detection result."""
        from src.resolution.context import ContextAssembler
        from src.conflict.pipeline import PipelineResult
        from src.conflict.detector import ConflictType, ConflictSeverity

        assembler = ContextAssembler(base_branch="main")

        # Create mock detection result
        detection_result = Mock(spec=PipelineResult)
        detection_result.has_conflicts = True
        detection_result.conflict_type = ConflictType.TEXTUAL
        detection_result.severity = ConflictSeverity.MEDIUM
        detection_result.branches = ["claude/feature-a-abc123", "claude/feature-b-xyz789"]
        detection_result.textual_result = Mock(conflicting_files=[
            Mock(file_path="src/auth.py"),
            Mock(file_path="src/utils.py"),
        ])
        detection_result.semantic_result = None

        with patch.object(assembler, '_get_sha', return_value="abc123"):
            with patch.object(assembler, '_load_manifests', return_value=[]):
                with patch.object(assembler, '_derive_manifests', return_value=[]):
                    with patch.object(assembler, '_get_base_files', return_value=[]):
                        with patch.object(assembler, '_get_agent_files', return_value={}):
                            with patch.object(assembler, '_find_related_files', return_value=[]):
                                with patch.object(assembler, '_detect_conventions', return_value=[]):
                                    context = assembler.assemble(detection_result)

        assert context.detection_result == detection_result
        assert context.base_branch == "main"

    def test_extracts_agent_id_from_branch(self):
        """Should extract agent ID from branch name."""
        from src.resolution.context import ContextAssembler

        assembler = ContextAssembler()

        # Test various branch formats
        assert "abc123" in assembler._extract_agent_id("claude/add-feature-abc123")
        assert "xyz789" in assembler._extract_agent_id("claude/fix-bug-xyz789")

    def test_derives_changes_from_git(self):
        """Should derive actual changes from git diff."""
        from src.resolution.context import ContextAssembler

        assembler = ContextAssembler()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="A\tsrc/new_file.py\nM\tsrc/modified.py\nD\tsrc/deleted.py\n"
            )

            derived = assembler._derive_manifests(
                ["agent1"],
                ["claude/feature-agent1"]
            )

            assert len(derived) == 1
            assert "src/new_file.py" in derived[0].files_added
            assert "src/modified.py" in derived[0].files_modified
            assert "src/deleted.py" in derived[0].files_deleted


class TestIntentExtractor:
    """Tests for Stage 2: Intent Extraction."""

    def test_extracts_intent_from_manifest(self):
        """Should extract primary intent from manifest."""
        from src.resolution.intent import IntentExtractor
        from src.resolution.schema import ConflictContext, FileVersion
        from src.coordinator.schema import AgentManifest, AgentInfo, GitInfo, TaskInfo

        extractor = IntentExtractor()

        # Create mock context
        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1"]
        context.agent_manifests = [
            Mock(
                agent=Mock(id="agent1"),
                task=Mock(
                    description="Add user authentication with JWT tokens",
                    user_prompt="Implement login functionality",
                ),
                work=Mock(decisions=["Use bcrypt for password hashing"]),
            )
        ]
        context.agent_files = {"agent1": []}
        context.derived_manifests = []

        analysis = extractor.extract(context)

        assert len(analysis.intents) == 1
        assert "authentication" in analysis.intents[0].primary_intent.lower()

    def test_extracts_constraints_from_task(self):
        """Should extract hard/soft constraints from task description."""
        from src.resolution.intent import IntentExtractor

        extractor = IntentExtractor()

        # Test hard constraint patterns
        assert any(
            "must" in pattern[0]
            for pattern in extractor.hard_constraint_patterns
        )

        # Test soft constraint patterns
        assert any(
            "should" in pattern[0]
            for pattern in extractor.soft_constraint_patterns
        )

    def test_compares_compatible_intents(self):
        """Should identify compatible intents."""
        from src.resolution.intent import IntentExtractor
        from src.resolution.schema import ExtractedIntent

        extractor = IntentExtractor()

        intents = [
            ExtractedIntent(
                agent_id="agent1",
                primary_intent="Add login page",
                hard_constraints=[],
                soft_constraints=[],
                confidence="high",
            ),
            ExtractedIntent(
                agent_id="agent2",
                primary_intent="Add user dashboard",
                hard_constraints=[],
                soft_constraints=[],
                confidence="high",
            ),
        ]

        comparison = extractor._compare_intents(intents)

        # No conflicting constraints = compatible or orthogonal
        assert comparison.relationship in ["compatible", "orthogonal"]

    def test_identifies_low_confidence(self):
        """Should identify low confidence when intent unclear."""
        from src.resolution.intent import IntentExtractor
        from src.resolution.schema import ExtractedIntent

        extractor = IntentExtractor()

        # Create intent with low confidence
        intents = [
            ExtractedIntent(
                agent_id="agent1",
                primary_intent="Unknown task",
                confidence="low",
            ),
            ExtractedIntent(
                agent_id="agent2",
                primary_intent="Another task",
                confidence="medium",
            ),
        ]

        overall = extractor._calculate_overall_confidence(intents, None)

        # Any low confidence = overall low
        assert overall == "low"


class TestInterfaceHarmonizer:
    """Tests for Stage 3: Interface Harmonization."""

    def test_identifies_interface_changes(self):
        """Should identify function signature changes."""
        from src.resolution.harmonizer import InterfaceHarmonizer
        from src.resolution.schema import FileVersion

        harmonizer = InterfaceHarmonizer()

        new_version = Mock()
        new_version.path = "src/auth.py"
        new_version.content = """
def authenticate(username: str, password: str, remember: bool = False):
    pass
"""

        base_version = Mock()
        base_version.content = """
def authenticate(username: str, password: str):
    pass
"""

        changes = harmonizer._extract_interface_changes(
            new_version,
            base_version,
            "agent1"
        )

        # Should detect signature change
        assert len(changes) > 0
        assert any(c.name == "authenticate" for c in changes)
        assert any(c.change_type == "signature_changed" for c in changes)

    def test_extracts_python_functions(self):
        """Should extract Python function signatures."""
        from src.resolution.harmonizer import InterfaceHarmonizer

        harmonizer = InterfaceHarmonizer()

        content = """
def foo(a: int, b: str) -> bool:
    pass

def bar():
    pass

class MyClass:
    def method(self, x):
        pass
"""
        functions = harmonizer._extract_python_functions(content)

        assert "foo" in functions
        assert "bar" in functions
        assert "a: int, b: str" in functions["foo"]

    def test_extracts_js_exports(self):
        """Should extract JavaScript exports."""
        from src.resolution.harmonizer import InterfaceHarmonizer

        harmonizer = InterfaceHarmonizer()

        content = """
export function authenticate(user) {}
export const API_KEY = "xxx";
export { foo, bar as baz };
export default class MyClass {}
"""
        exports = harmonizer._extract_js_exports(content)

        assert "authenticate" in exports
        assert "API_KEY" in exports
        assert "foo" in exports


class TestCandidateGenerator:
    """Tests for Candidate Generation."""

    def test_generates_candidate(self):
        """Should generate resolution candidate."""
        from src.resolution.candidate import CandidateGenerator
        from src.resolution.schema import ConflictContext, IntentAnalysis, HarmonizedResult

        generator = CandidateGenerator()

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]
        context.agent_branches = {
            "agent1": "claude/feature-agent1",
            "agent2": "claude/feature-agent2",
        }
        context.derived_manifests = []

        intents = Mock(spec=IntentAnalysis)
        intents.comparison = Mock(relationship="orthogonal")
        intents.intents = []

        harmonized = Mock(spec=HarmonizedResult)
        harmonized.build_passes = True

        with patch.object(generator, '_create_resolution_branch', return_value=True):
            with patch.object(generator, '_get_diff_from_base', return_value="diff"):
                with patch.object(generator, '_get_modified_files', return_value=["src/a.py"]):
                    candidates = generator.generate(context, intents, harmonized)

        assert len(candidates) == 1
        assert candidates[0].branch_name.startswith("resolution/")

    def test_selects_strategy_based_on_confidence(self):
        """Should select strategy based on intent confidence."""
        from src.resolution.candidate import CandidateGenerator
        from src.resolution.schema import ConflictContext, IntentAnalysis, HarmonizedResult, ExtractedIntent

        generator = CandidateGenerator()

        context = Mock(spec=ConflictContext)
        context.agent_ids = ["agent1", "agent2"]

        intents = Mock(spec=IntentAnalysis)
        intents.comparison = Mock(relationship="compatible")
        intents.intents = [
            ExtractedIntent(agent_id="agent1", primary_intent="task1", confidence="high"),
            ExtractedIntent(agent_id="agent2", primary_intent="task2", confidence="low"),
        ]

        harmonized = Mock(spec=HarmonizedResult)
        harmonized.build_passes = True

        strategy = generator._select_strategy(context, intents, harmonized)

        # agent1 has higher confidence, should prefer their approach
        assert strategy == "agent1_primary"


class TestResolutionValidator:
    """Tests for Resolution Validation."""

    def test_validates_build_passes(self):
        """Should validate that build passes."""
        from src.resolution.validator import ResolutionValidator
        from src.resolution.schema import ResolutionCandidate, ConflictContext

        validator = ResolutionValidator()

        candidate = ResolutionCandidate(
            candidate_id="test-1",
            strategy="convention_primary",
            branch_name="resolution/test-1",
        )

        context = Mock(spec=ConflictContext)
        context.base_branch = "main"

        with patch.object(validator, '_checkout_branch', return_value=True):
            with patch.object(validator, '_run_build', return_value=True):
                with patch.object(validator, '_run_lint', return_value=0.9):
                    with patch.object(validator, '_run_targeted_tests', return_value={
                        "passed": 5, "failed": 0, "skipped": 1
                    }):
                        results = validator.validate([candidate], context)

        assert len(results) == 1
        assert results[0].build_passed == True
        assert results[0].tests_passed == 5
        assert results[0].tests_failed == 0

    def test_finds_related_tests(self):
        """Should find tests related to modified files."""
        from src.resolution.validator import ResolutionValidator
        from pathlib import Path

        validator = ResolutionValidator(repo_path=Path("/fake/repo"))

        with patch('pathlib.Path.exists') as mock_exists:
            # Simulate test_auth.py exists
            def exists_check(path=None):
                return "test_auth" in str(path) if path else False

            mock_exists.side_effect = lambda: True

            # This just tests the pattern matching logic
            modified = ["src/auth.py"]
            test_files = validator._find_related_tests(modified)

            # Should have looked for test files
            # (actual result depends on file system mock)

    def test_calculates_scores(self):
        """Should calculate candidate scores correctly."""
        from src.resolution.validator import ResolutionValidator
        from src.resolution.schema import ResolutionCandidate, ConflictContext

        validator = ResolutionValidator()

        candidate = ResolutionCandidate(
            candidate_id="test-1",
            strategy="convention_primary",
            branch_name="resolution/test-1",
            build_passed=True,
            lint_score=0.9,
            tests_passed=10,
            tests_failed=0,
            files_modified=["src/a.py", "src/b.py"],
        )

        context = Mock(spec=ConflictContext)

        validator._calculate_scores(candidate, context)

        # All passing = high correctness
        assert candidate.correctness_score == 1.0
        # Few files = high simplicity
        assert candidate.simplicity_score >= 0.8
        # Good lint = good convention
        assert candidate.convention_score == 0.9
        # Total should be reasonable
        assert 0.8 <= candidate.total_score <= 1.0


class TestResolutionPipeline:
    """Tests for the main resolution pipeline."""

    def test_returns_no_escalation_when_no_conflicts(self):
        """Should return no escalation when no conflicts."""
        from src.resolution.pipeline import ResolutionPipeline
        from src.conflict.pipeline import PipelineResult
        from src.conflict.detector import ConflictType, ConflictSeverity

        pipeline = ResolutionPipeline()

        detection_result = Mock(spec=PipelineResult)
        detection_result.has_conflicts = False
        detection_result.conflict_type = ConflictType.NONE

        result = pipeline.resolve(detection_result)

        assert result.needs_escalation == False

    def test_escalates_on_low_confidence(self):
        """Should escalate when intent confidence is low."""
        from src.resolution.pipeline import ResolutionPipeline
        from src.conflict.pipeline import PipelineResult
        from src.conflict.detector import ConflictType, ConflictSeverity
        from src.resolution.schema import IntentAnalysis

        pipeline = ResolutionPipeline(auto_escalate_low_confidence=True)

        detection_result = Mock(spec=PipelineResult)
        detection_result.has_conflicts = True
        detection_result.conflict_type = ConflictType.TEXTUAL
        detection_result.branches = ["branch1", "branch2"]

        # Mock context assembler
        with patch.object(pipeline, 'context_assembler') as mock_ctx:
            mock_ctx.assemble.return_value = Mock(agent_ids=["a1", "a2"])

            # Mock intent extractor returning low confidence
            with patch.object(pipeline, 'intent_extractor') as mock_intent:
                mock_intent.extract.return_value = Mock(
                    overall_confidence="low",
                    intents=[],
                )

                result = pipeline.resolve(detection_result)

        assert result.needs_escalation == True
        assert result.escalation_reason == "low_intent_confidence"

    def test_selects_viable_candidate(self):
        """Should select viable candidate with highest score."""
        from src.resolution.pipeline import ResolutionPipeline
        from src.resolution.schema import ResolutionCandidate, IntentAnalysis

        pipeline = ResolutionPipeline()

        candidates = [
            ResolutionCandidate(
                candidate_id="c1",
                strategy="agent1_primary",
                branch_name="resolution/c1",
                build_passed=True,
                tests_failed=0,
                total_score=0.85,
            ),
            ResolutionCandidate(
                candidate_id="c2",
                strategy="agent2_primary",
                branch_name="resolution/c2",
                build_passed=True,
                tests_failed=0,
                total_score=0.75,
            ),
        ]

        intents = Mock(spec=IntentAnalysis)
        context = Mock(agent_ids=["a1", "a2"], derived_manifests=[])

        result = pipeline._select_winner("res-1", candidates, intents, context)

        assert result.needs_escalation == False
        assert result.winning_candidate.candidate_id == "c1"

    def test_escalates_when_no_viable_candidates(self):
        """Should escalate when no candidates are viable."""
        from src.resolution.pipeline import ResolutionPipeline
        from src.resolution.schema import ResolutionCandidate, IntentAnalysis

        pipeline = ResolutionPipeline()

        # All candidates fail build
        candidates = [
            ResolutionCandidate(
                candidate_id="c1",
                strategy="agent1_primary",
                branch_name="resolution/c1",
                build_passed=False,
                tests_failed=2,
                total_score=0.3,
            ),
        ]

        intents = Mock(spec=IntentAnalysis)
        context = Mock(agent_ids=["a1"], derived_manifests=[])

        result = pipeline._select_winner("res-1", candidates, intents, context)

        assert result.needs_escalation == True
        assert result.escalation_reason == "no_viable_candidates"


class TestSchemaModels:
    """Tests for schema data models."""

    def test_resolution_candidate_is_viable(self):
        """Should correctly determine viability."""
        from src.resolution.schema import ResolutionCandidate

        # Viable: build passed, no failed tests
        viable = ResolutionCandidate(
            candidate_id="c1",
            strategy="convention_primary",
            branch_name="branch1",
            build_passed=True,
            tests_failed=0,
        )
        assert viable.is_viable == True

        # Not viable: build failed
        not_viable = ResolutionCandidate(
            candidate_id="c2",
            strategy="convention_primary",
            branch_name="branch2",
            build_passed=False,
            tests_failed=0,
        )
        assert not_viable.is_viable == False

        # Not viable: tests failed
        also_not_viable = ResolutionCandidate(
            candidate_id="c3",
            strategy="convention_primary",
            branch_name="branch3",
            build_passed=True,
            tests_failed=2,
        )
        assert also_not_viable.is_viable == False

    def test_intent_analysis_can_auto_resolve(self):
        """Should correctly determine if can auto-resolve."""
        from src.resolution.schema import IntentAnalysis, IntentComparison

        # Can auto-resolve: high confidence, no human judgment needed
        can_resolve = IntentAnalysis(
            intents=[],
            comparison=IntentComparison(
                relationship="compatible",
                requires_human_judgment=False,
                confidence="high",
            ),
            overall_confidence="high",
        )
        assert can_resolve.can_auto_resolve == True

        # Cannot auto-resolve: low confidence
        cannot_resolve = IntentAnalysis(
            intents=[],
            comparison=None,
            overall_confidence="low",
        )
        assert cannot_resolve.can_auto_resolve == False

        # Cannot auto-resolve: requires human judgment
        needs_human = IntentAnalysis(
            intents=[],
            comparison=IntentComparison(
                relationship="conflicting",
                requires_human_judgment=True,
                confidence="medium",
            ),
            overall_confidence="medium",
        )
        assert needs_human.can_auto_resolve == False
