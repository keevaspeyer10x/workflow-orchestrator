"""
Conflict Detection Module

Detects and classifies conflicts between agent branches.

Phase 1 (MVP): Basic textual conflict detection using git merge-tree
Phase 2: Full detection pipeline with semantic analysis, dependency
         conflicts, build testing, and conflict clustering
"""

# Phase 1: Basic detection
from .detector import (
    ConflictType,
    ConflictSeverity,
    ConflictFile,
    ConflictInfo,
    ConflictDetector,
    detect_conflicts,
)

# Phase 2: Full pipeline
from .pipeline import (
    PipelineResult,
    DetectionPipeline,
    run_detection_pipeline,
)

from .build_tester import (
    BuildTestResult,
    BuildTester,
)

from .dependency import (
    DependencyConflict,
    DependencyAnalyzer,
)

from .semantic import (
    SymbolOverlapResult,
    DomainOverlapResult,
    SemanticAnalysisResult,
    SemanticAnalyzer,
)

from .clusterer import (
    ConflictCluster,
    ConflictClusterer,
)

__all__ = [
    # Phase 1: Basic detection
    "ConflictType",
    "ConflictSeverity",
    "ConflictFile",
    "ConflictInfo",
    "ConflictDetector",
    "detect_conflicts",

    # Phase 2: Full pipeline
    "PipelineResult",
    "DetectionPipeline",
    "run_detection_pipeline",

    # Build testing
    "BuildTestResult",
    "BuildTester",

    # Dependency analysis
    "DependencyConflict",
    "DependencyAnalyzer",

    # Semantic analysis
    "SymbolOverlapResult",
    "DomainOverlapResult",
    "SemanticAnalysisResult",
    "SemanticAnalyzer",

    # Clustering
    "ConflictCluster",
    "ConflictClusterer",
]
