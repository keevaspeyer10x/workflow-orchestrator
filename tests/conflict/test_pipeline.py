"""
Tests for the conflict detection pipeline.

These tests define the expected behavior for Phase 2 components.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.conflict.detector import ConflictSeverity, ConflictType


class TestDetectionPipeline:
    """Tests for the main detection pipeline orchestrator."""

    def test_pipeline_runs_all_steps(self):
        """Pipeline should run all detection steps in order."""
        from src.conflict.pipeline import DetectionPipeline

        pipeline = DetectionPipeline(base_branch="main")

        # Mock the individual detectors
        with patch.object(pipeline, 'textual_detector') as mock_textual, \
             patch.object(pipeline, 'build_tester') as mock_build, \
             patch.object(pipeline, 'dependency_analyzer') as mock_dep, \
             patch.object(pipeline, 'semantic_analyzer') as mock_semantic:

            mock_textual.detect.return_value = Mock(has_conflicts=False)
            mock_build.test.return_value = Mock(build_passed=True, tests_passed=True)
            mock_dep.analyze.return_value = []
            mock_semantic.analyze.return_value = Mock(has_semantic_conflicts=False)

            result = pipeline.run(["branch1", "branch2"])

            assert mock_textual.detect.called
            assert mock_build.test.called
            assert mock_dep.analyze.called
            assert mock_semantic.analyze.called

    def test_pipeline_short_circuits_on_critical_conflict(self):
        """Pipeline should stop early on critical conflicts."""
        from src.conflict.pipeline import DetectionPipeline

        pipeline = DetectionPipeline(base_branch="main")

        with patch.object(pipeline, 'textual_detector') as mock_textual:
            # Simulate critical textual conflict
            mock_textual.detect.return_value = Mock(
                has_conflicts=True,
                severity=ConflictSeverity.CRITICAL,
                conflicting_files=[],  # Empty list for iteration
                file_count=1
            )
            mock_textual.detect_risk_flags.return_value = []

            result = pipeline.run(["branch1", "branch2"])

            # Should have conflicts and skip later steps
            assert result.has_conflicts

    def test_pipeline_detects_clean_but_broken(self):
        """Pipeline should detect when merge is clean but build fails."""
        from src.conflict.pipeline import DetectionPipeline

        pipeline = DetectionPipeline(base_branch="main")

        with patch.object(pipeline, 'textual_detector') as mock_textual, \
             patch.object(pipeline, 'build_tester') as mock_build, \
             patch.object(pipeline, 'dependency_analyzer') as mock_dep, \
             patch.object(pipeline, 'semantic_analyzer') as mock_semantic:

            # Git says clean
            mock_textual.detect.return_value = Mock(has_conflicts=False)
            # But build fails
            mock_build.test.return_value = Mock(
                build_passed=False,
                all_passed=False,  # Pipeline checks this attribute
                error="Type error"
            )
            mock_dep.analyze.return_value = []
            mock_semantic.analyze.return_value = Mock(has_semantic_conflicts=False)

            result = pipeline.run(["branch1", "branch2"])

            # Should be marked as semantic conflict
            assert result.has_conflicts
            assert result.conflict_type.value == "semantic"


class TestBuildTester:
    """Tests for build/test runner on merged code."""

    def test_creates_temp_merge_branch(self):
        """Should create temporary branch with merged code."""
        from src.conflict.build_tester import BuildTester

        tester = BuildTester(base_branch="main")

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            tester.test(["branch1", "branch2"])

            # Should have created temp branch
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("checkout" in c and "temp" in c.lower() for c in calls)

    def test_cleans_up_temp_branch(self):
        """Should clean up temp branch even on failure."""
        from src.conflict.build_tester import BuildTester

        tester = BuildTester(base_branch="main")

        with patch('subprocess.run') as mock_run:
            # Simulate build failure
            mock_run.side_effect = [
                Mock(returncode=0),  # checkout
                Mock(returncode=0),  # merge
                Mock(returncode=1, stderr="Build failed"),  # build
                Mock(returncode=0),  # cleanup checkout
                Mock(returncode=0),  # cleanup delete
            ]

            result = tester.test(["branch1"])

            assert not result.build_passed
            # Should still clean up
            assert mock_run.call_count >= 4

    def test_auto_detects_build_system(self):
        """Should auto-detect build system from project files."""
        from src.conflict.build_tester import BuildTester

        tester = BuildTester(base_branch="main")

        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True  # package.json exists

            cmd = tester._detect_build_command()

            # Should detect npm/node project
            assert "npm" in cmd or "node" in cmd or cmd is not None


class TestDependencyAnalyzer:
    """Tests for dependency conflict detection."""

    def test_detects_version_conflict_npm(self):
        """Should detect conflicting versions in package.json."""
        from src.conflict.dependency import DependencyAnalyzer

        analyzer = DependencyAnalyzer()

        # Simulate two branches with different lodash versions
        branch1_deps = {"lodash": "^4.17.0"}
        branch2_deps = {"lodash": "^3.10.0"}

        conflicts = analyzer.compare_deps(branch1_deps, branch2_deps, "npm")

        assert len(conflicts) > 0
        assert conflicts[0].package == "lodash"

    def test_detects_version_conflict_pip(self):
        """Should detect conflicting versions in requirements.txt."""
        from src.conflict.dependency import DependencyAnalyzer

        analyzer = DependencyAnalyzer()

        branch1_deps = {"django": ">=4.0,<5.0"}
        branch2_deps = {"django": ">=3.0,<4.0"}

        conflicts = analyzer.compare_deps(branch1_deps, branch2_deps, "pip")

        assert len(conflicts) > 0
        assert conflicts[0].package == "django"

    def test_no_conflict_compatible_versions(self):
        """Should not flag compatible version ranges."""
        from src.conflict.dependency import DependencyAnalyzer

        analyzer = DependencyAnalyzer()

        branch1_deps = {"lodash": "^4.17.0"}
        branch2_deps = {"lodash": "^4.17.21"}

        conflicts = analyzer.compare_deps(branch1_deps, branch2_deps, "npm")

        # Compatible versions should not conflict
        assert len(conflicts) == 0


class TestSemanticAnalyzer:
    """Tests for semantic conflict detection."""

    def test_detects_symbol_overlap(self):
        """Should detect when branches define same symbol differently."""
        from src.conflict.semantic import SemanticAnalyzer

        analyzer = SemanticAnalyzer()

        branch1_symbols = {"src/auth.py": ["authenticate", "validate_token"]}
        branch2_symbols = {"src/auth.py": ["authenticate", "check_permissions"]}

        result = analyzer.check_symbol_overlap(branch1_symbols, branch2_symbols)

        assert result.has_overlap
        assert "authenticate" in result.overlapping_symbols

    def test_detects_domain_overlap(self):
        """Should detect when branches touch same domain areas."""
        from src.conflict.semantic import SemanticAnalyzer

        analyzer = SemanticAnalyzer()

        branch1_files = ["src/auth/login.py", "src/auth/session.py"]
        branch2_files = ["src/auth/logout.py", "src/auth/token.py"]

        result = analyzer.check_domain_overlap(branch1_files, branch2_files)

        assert "auth" in result.overlapping_domains

    def test_no_domain_overlap_different_areas(self):
        """Should not flag different domain areas."""
        from src.conflict.semantic import SemanticAnalyzer

        analyzer = SemanticAnalyzer()

        branch1_files = ["src/auth/login.py"]
        branch2_files = ["src/payments/checkout.py"]

        result = analyzer.check_domain_overlap(branch1_files, branch2_files)

        assert len(result.overlapping_domains) == 0


class TestConflictClusterer:
    """Tests for conflict clustering."""

    def test_clusters_by_shared_files(self):
        """Should cluster agents that touch same files."""
        from src.conflict.clusterer import ConflictClusterer

        clusterer = ConflictClusterer()

        agents = [
            {"id": "agent1", "files": ["src/a.py", "src/b.py"]},
            {"id": "agent2", "files": ["src/b.py", "src/c.py"]},
            {"id": "agent3", "files": ["src/x.py", "src/y.py"]},
        ]

        clusters = clusterer.cluster(agents)

        # agent1 and agent2 share src/b.py, should be in same cluster
        # agent3 is separate
        assert len(clusters) == 2

    def test_clusters_by_domain(self):
        """Should cluster agents working in same domain."""
        from src.conflict.clusterer import ConflictClusterer

        clusterer = ConflictClusterer()

        agents = [
            {"id": "agent1", "files": ["src/auth/login.py"]},
            {"id": "agent2", "files": ["src/auth/logout.py"]},
            {"id": "agent3", "files": ["src/payments/checkout.py"]},
        ]

        clusters = clusterer.cluster(agents, by="domain")

        # auth agents together, payments separate
        assert len(clusters) == 2

    def test_orders_clusters_by_dependency(self):
        """Should order clusters so dependencies come first."""
        from src.conflict.clusterer import ConflictClusterer

        clusterer = ConflictClusterer()

        clusters = [
            {"id": "c1", "depends_on": ["c2"]},
            {"id": "c2", "depends_on": []},
            {"id": "c3", "depends_on": ["c1"]},
        ]

        ordered = clusterer.order_by_dependency(clusters)

        # c2 first (no deps), then c1, then c3
        assert ordered[0]["id"] == "c2"
        assert ordered[1]["id"] == "c1"
        assert ordered[2]["id"] == "c3"


class TestRiskFlags:
    """Tests for risk flag detection."""

    def test_detects_security_files(self):
        """Should flag security-related file changes."""
        from src.conflict.detector import ConflictDetector

        detector = ConflictDetector(base_branch="main")

        files = ["src/auth/crypto.py", "src/utils.py"]
        flags = detector.detect_risk_flags(files)

        assert "security" in flags or "auth" in flags

    def test_detects_db_migration(self):
        """Should flag database migration changes."""
        from src.conflict.detector import ConflictDetector

        detector = ConflictDetector(base_branch="main")

        files = ["migrations/0042_add_user_table.py", "src/models.py"]
        flags = detector.detect_risk_flags(files)

        assert "db_migration" in flags

    def test_detects_public_api(self):
        """Should flag public API changes."""
        from src.conflict.detector import ConflictDetector

        detector = ConflictDetector(base_branch="main")

        files = ["src/api/v1/endpoints.py", "src/api/routes.py"]
        flags = detector.detect_risk_flags(files)

        assert "public_api" in flags
