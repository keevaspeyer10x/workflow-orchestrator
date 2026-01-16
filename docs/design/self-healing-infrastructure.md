# Self-Healing Infrastructure Design Document

## Document Information

**Title:** Self-Learning, Self-Healing Infrastructure for Workflow Orchestrator
**Version:** 3.2 (Zero-Human Mode + Multi-Model Review Fixes)
**Status:** Ready for Implementation
**Author:** Architecture Design (Claude Opus 4.5 + Multi-Model Review)
**Date:** 2026-01-16
**Changes in 3.0:** Added User Journey, Issue Types, Issue Queue & Batching, Fix Application, Root Cause Investigation, and Learnings Architecture sections
**Changes in 3.1:** Replaced JSONL+keyword matching with Supabase backend (pgvector for RAG, recursive CTEs for graph, PostgreSQL for relational)
**Changes in 3.2:** Major revision based on 5-model review (Claude x2, GPT-5.2, Grok 4.1, DeepSeek V3.2):
- **Zero-Human Mode**: Replaced human precedent requirement with pre-seeded patterns + verified AI precedent (Section 4.5)
- **Fingerprinting Algorithm**: Added detailed fingerprinting with normalization rules and stability tests (Section 4.7)
- **Cost Controls**: Added daily limits, tiered validation, rate limiting (Section 4.8)
- **Local Fallback Cache**: Added SQLite cache for offline operation (Section 4.9)
- **Escape Hatches**: Added --force, --ignore, --unquarantine CLI commands (Section 4.10)
- **Simplified Quality Gates**: 8 sequential gates → 3 parallel phases (Section 7)
- **Simplified Lifecycle**: 6 states → 4 states with automatic graduation (Section 11.5)
- **Issue Types → Metadata**: Removed rigid enum, now descriptive metadata for analytics (Section 13)
- **Fixed Graph Causality**: Replaced broken substring matching with explicit causality edges (Section 17.4)
**Review:** Gemini 3 Pro, GPT-5.2, Grok 4.1, DeepSeek V3.2

---

## 1. Executive Summary

This document describes the architecture for a self-learning, self-healing infrastructure that enables the workflow orchestrator to automatically detect, learn from, and resolve errors with minimal human supervision while maintaining output quality equivalent to an experienced senior development team.

**Key Design Principles:**
- **Verification-first**: Only learn from fixes that pass the VERIFY phase
- **Multi-model validation**: Use different models for fixing vs judging (prevents blind spots)
- **Hard constraints**: Bounded diffs that LLM cannot override
- **Zero-human automation**: Pre-seeded patterns + verified AI precedent (no human bottleneck)
- **Fast iteration**: Aggressive phasing with automated safety gates
- **Rollback-ready**: Every auto-apply can be instantly reverted
- **Graceful degradation**: Local fallback when Supabase unavailable

---

## 2. Error & Learning Capture (How Errors Are Found)

### 2.1 Error Detection Sources

The system captures errors from **four sources**:

```
+------------------------------------------------------------------+
|                     ERROR DETECTION SOURCES                       |
+------------------------------------------------------------------+
|                                                                   |
|  1. WORKFLOW EVENT LOG (.workflow_log.jsonl)                     |
|     - item_failed events                                          |
|     - verification_failed events                                  |
|     - review_failed events                                        |
|     - error events with context                                   |
|     [ALREADY EXISTS - just need to parse]                        |
|                                                                   |
|  2. SESSION TRANSCRIPTS (.workflow_sessions/)                    |
|     - Parse for error patterns (stack traces, exit codes)        |
|     - Regex detection: ImportError, TypeError, etc.              |
|     - Natural language: "failed", "error", "exception"           |
|     [Issue #27 - LEARN-001]                                      |
|                                                                   |
|  3. SUBPROCESS INTERCEPTION                                      |
|     - Wrap CLI calls (pytest, npm, cargo, go test)               |
|     - Capture exit codes and stderr                               |
|     - Parse structured output (pytest --json, etc.)              |
|     [NEW - add to Bash/CLI execution layer]                      |
|                                                                   |
|  4. REAL-TIME HOOKS                                              |
|     - Phase transition failures                                   |
|     - Gate failures (build, test, lint)                          |
|     - Review rejections                                           |
|     [Extend existing workflow hooks]                             |
|                                                                   |
+------------------------------------------------------------------+
```

### 2.2 Error Detection Patterns

```python
# Patterns to detect in session transcripts (Issue #27)
ERROR_PATTERNS = {
    # Python exceptions
    r"^(\w+Error): (.+)$": "python_exception",
    r"^Traceback \(most recent call last\):": "python_traceback",

    # Exit codes
    r"exit code (\d+)": "exit_code",
    r"Command .+ failed": "command_failed",

    # Test failures
    r"FAILED (.+)::(.+)": "pytest_failure",
    r"(\d+) failed, (\d+) passed": "test_summary",

    # Build errors
    r"error\[E\d+\]": "rust_error",
    r"error TS\d+": "typescript_error",
    r"SyntaxError": "syntax_error",

    # Import/dependency errors
    r"ModuleNotFoundError: No module named '(.+)'": "missing_module",
    r"ImportError": "import_error",
    r"Cannot find module": "node_module_missing",
}
```

### 2.3 Learning Capture (How Learnings Are Found)

Learnings come from **three sources**:

| Source | What's Captured | When |
|--------|----------------|------|
| **LEARN Phase** | Explicit learnings from workflow completion | End of workflow |
| **Resolution Success** | What fix worked for what error | After VERIFY passes |
| **Pattern Analysis** | Cross-session patterns (Issue #27) | Periodic analysis |

```python
@dataclass
class LearningEvent:
    """Captured learning from any source."""

    learning_id: str
    source: Literal["learn_phase", "resolution_success", "pattern_analysis"]

    # What was learned
    error_fingerprint: str           # Which error this applies to
    successful_fix: Optional[str]    # The fix that worked (diff)
    context: dict                    # Phase, files, environment

    # Provenance
    learned_from_workflow_id: str
    learned_at: datetime
    human_authored: bool             # Critical for precedent requirement
```

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
+-----------------------------------------------------------------------------------+
|                          SELF-HEALING INFRASTRUCTURE v2                            |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +------------------+     +------------------+     +-------------------+           |
|  |  ERROR CAPTURE   |     |  PATTERN ENGINE  |     |  HEALING ENGINE   |          |
|  |  (4 Sources)     |     |  (Learning Core) |     |  (Resolution)     |          |
|  +------------------+     +------------------+     +-------------------+           |
|         |                        |                         |                       |
|         v                        v                         v                       |
|  +-------------+          +-------------+          +--------------+                |
|  | Workflow    |          | Fingerprint |          | Multi-Model  |               |
|  | Log Parser  |--------->| Matcher     |--------->| Validator    |               |
|  +-------------+          +-------------+          | (2+ models)  |               |
|         |                        |                 +--------------+                |
|  +-------------+          +-------------+                  |                       |
|  | Transcript  |          | Pattern     |          +--------------+                |
|  | Analyzer    |--------->| Memory      |          | Hard         |               |
|  | (Issue #27) |          | (Extended)  |          | Constraints  |               |
|  +-------------+          +-------------+          | (Unbendable) |               |
|         |                        |                 +--------------+                |
|  +-------------+          +-------------+                  |                       |
|  | Subprocess  |          | Strategy    |          +--------------+                |
|  | Interceptor |          | Tracker     |          | Rollback     |               |
|  +-------------+          +-------------+          | Engine       |               |
|         |                                          +--------------+                |
|  +-------------+                                           |                       |
|  | Real-time   |                                   +--------------+                |
|  | Hooks       |                                   | Kill Switch  |               |
|  +-------------+                                   | (.healing_   |               |
|                                                    |  lock file)  |               |
|                                                    +--------------+                |
+-----------------------------------------------------------------------------------+
```

### 3.2 Error Detection & Resolution Flow

```
    [ERROR OCCURS]
          |
          v
+-------------------+
| 1. DETECT         |  <-- From 4 sources (log, transcript, subprocess, hooks)
| Parse & Extract   |
+-------------------+
          |
          v
+-------------------+
| 2. FINGERPRINT    |  <-- Normalize: strip paths, UUIDs, timestamps, line numbers
| Create signature  |
+-------------------+
          |
          v
+-------------------+
| 3. PATTERN LOOKUP |  <-- Check pattern memory for known fix
+-------------------+
          |
    +-----+-----+
    |           |
[MATCH]    [NO MATCH]
    |           |
    v           v
+-------+   +--------+
| Check |   | Queue  |
| Human |   | for    |
| Prec. |   | Manual |
+-------+   +--------+
    |
    v (has human precedent)
+-------------------+
| 4. HARD LIMITS    |  <-- UNBENDABLE: max 2 files, max 30 lines, no deps
| Check constraints |
+-------------------+
    |
    v (within limits)
+-------------------+
| 5. MULTI-MODEL    |  <-- 2 of 3 models must approve (different from fixer)
| VALIDATION        |
| Gemini + GPT +    |
| Grok vote         |
+-------------------+
    |
    v (approved)
+-------------------+
| 6. APPLY FIX      |  <-- On branch, atomic, with rollback point
| (git branch)      |
+-------------------+
    |
    v
+-------------------+
| 7. VERIFY         |  <-- Build + Test + Lint (existing gates)
+-------------------+
    |
    +-----+-----+
    |           |
[PASS]      [FAIL]
    |           |
    v           v
+-------+   +--------+
| Learn |   | Revert |
| Pattern|  | Auto   |
+-------+   +--------+
    |
    v
+-------------------+
| 8. RECORD         |  <-- Update pattern memory, track provenance
| Update Memory     |
+-------------------+
```

---

## 4. Critical Safety Mechanisms (From Review)

### 4.1 Kill Switch

```python
# Global halt mechanism - check before ANY auto-apply
KILL_SWITCH_FILE = ".healing_lock"

def check_kill_switch() -> bool:
    """If this file exists, go to OBSERVE_ONLY mode."""
    return Path(KILL_SWITCH_FILE).exists()

# Usage:
# $ touch .healing_lock    # Instantly stops all auto-apply
# $ rm .healing_lock       # Resume auto-apply
```

### 4.2 Rollback Mechanism

```python
@dataclass
class RollbackPolicy:
    """Every auto-applied fix can be reverted."""

    # All fixes applied on branches, not main
    branch_prefix: str = "fix/auto-"

    # Auto-revert triggers
    auto_revert_triggers: list = field(default_factory=lambda: [
        "downstream_error_within_1h",    # Fix caused new errors
        "human_revert_detected",          # Someone manually reverted
        "verify_failed_after_merge",      # Late verification failure
    ])

    # Quarantine after revert
    quarantine_duration: timedelta = timedelta(days=7)

    def revert(self, resolution_id: str) -> None:
        """Revert a fix and quarantine the pattern."""
        # 1. git revert the commit
        # 2. Mark pattern as QUARANTINED
        # 3. Log to audit trail
        pass
```

### 4.3 Hard Constraints (LLM Cannot Override)

```python
@dataclass
class HardConstraints:
    """These limits are UNBENDABLE - no LLM score can bypass them."""

    # File limits
    max_files_changed: int = 2          # More files = not "safe"
    max_diff_lines: int = 30            # Larger diffs = risky

    # Dependency protection
    allow_new_dependencies: bool = False
    allow_dependency_removal: bool = False

    # Test protection (CRITICAL - from Gemini review)
    allow_test_deletion: bool = False
    allow_test_modification: bool = False  # Can add tests, not change
    allow_exception_swallowing: bool = False

    # Security
    forbidden_patterns: list = field(default_factory=lambda: [
        r"eval\(",                       # No dynamic eval
        r"exec\(",                       # No exec
        r"subprocess.*shell=True",       # No shell injection
        r"# type: ignore",               # No silencing type checker
        r"# noqa",                       # No silencing linter
        r"except:$",                     # No bare except
    ])

    def validate(self, diff: str, files: list[str]) -> tuple[bool, list[str]]:
        """Returns (passes, list of violations)."""
        violations = []

        if len(files) > self.max_files_changed:
            violations.append(f"Too many files: {len(files)} > {self.max_files_changed}")

        if len(diff.split('\n')) > self.max_diff_lines:
            violations.append(f"Diff too large: exceeds {self.max_diff_lines} lines")

        for pattern in self.forbidden_patterns:
            if re.search(pattern, diff):
                violations.append(f"Forbidden pattern: {pattern}")

        return len(violations) == 0, violations
```

### 4.4 Multi-Model Validation (Your Insight Was Correct)

```python
@dataclass
class MultiModelValidator:
    """
    Use DIFFERENT models for judging than for fixing.

    Prevents blind spots where a model approves its own bad patterns.
    """

    # Models used for review (different from the fixer)
    judge_models: list = field(default_factory=lambda: [
        "gemini-3-pro",
        "gpt-5.2",
        "grok-4.1",
    ])

    # Voting threshold
    min_approvals: int = 2              # 2 of 3 must approve

    # Score thresholds per model
    min_score_per_model: float = 0.7

    async def validate(self, fix: ResolutionRecord, error: ErrorEvent) -> ValidationResult:
        """Get multi-model consensus on fix quality."""

        votes = []
        for model in self.judge_models:
            result = await self._get_model_vote(model, fix, error)
            votes.append(result)

        approvals = sum(1 for v in votes if v.approved and v.score >= self.min_score_per_model)

        return ValidationResult(
            approved=approvals >= self.min_approvals,
            approvals=approvals,
            total_judges=len(self.judge_models),
            votes=votes,
            consensus_score=sum(v.score for v in votes) / len(votes),
        )
```

### 4.5 Automated Precedent (Zero-Human Mode)

The system establishes precedent through three mechanisms, eliminating the human bottleneck:

```python
def can_auto_apply(pattern: ErrorPattern) -> bool:
    """
    Zero-human automation: No human approval required.

    Precedent is established via:
    1. Pre-seeded universal patterns (ships with system)
    2. Verified AI precedent (5+ successful applies)
    3. Human corrections (highest-value signal when available)
    """

    # Check if pattern has ANY form of precedent
    if not pattern.has_precedent:
        return False  # New pattern - needs to build track record

    # Check verification requirements (automatic, no human gates)
    return (
        pattern.confidence >= 0.7 and
        pattern.success_rate >= 0.9 and
        pattern.verified_apply_count >= 5 and  # 5+ verified successes
        pattern.churn_rate < 0.1 and
        not pattern.quarantined
    )


@dataclass
class ErrorPattern:
    """Pattern with automated precedent tracking."""

    fingerprint: str
    safety_category: SafetyCategory

    # Precedent tracking (any of these establishes precedent)
    is_preseeded: bool = False          # Ships with system (universal patterns)
    verified_apply_count: int = 0       # Successful applies that passed VERIFY
    human_correction_count: int = 0     # Human corrections (highest value)

    @property
    def has_precedent(self) -> bool:
        """Precedent via pre-seeding, verified applies, or human corrections."""
        return (
            self.is_preseeded or
            self.verified_apply_count >= 5 or
            self.human_correction_count >= 1
        )

    # Stats
    confidence: float = 0.5
    success_rate: float = 0.0
    use_count: int = 0
    churn_rate: float = 0.0
    quarantined: bool = False


# ============================================
# PRE-SEEDED UNIVERSAL PATTERNS
# ============================================

PRESEEDED_PATTERNS = [
    # Import errors (SAFE - auto-apply eligible)
    {
        "fingerprint_regex": r"ModuleNotFoundError: No module named '(\w+)'",
        "fix_template": "pip install {captured_group_1}",
        "safety_category": "safe",
        "is_preseeded": True,
    },
    {
        "fingerprint_regex": r"ImportError: cannot import name '(\w+)' from '(\w+)'",
        "fix_template": "Check if {captured_group_1} exists in {captured_group_2}",
        "safety_category": "moderate",  # Needs verification
        "is_preseeded": True,
    },

    # Syntax errors (SAFE)
    {
        "fingerprint_regex": r"SyntaxError: f-string: single '\}' is not allowed",
        "fix_template": "Escape brace: }} → \\}",
        "safety_category": "safe",
        "is_preseeded": True,
    },
    {
        "fingerprint_regex": r"SyntaxError: invalid syntax",
        "fix_template": "Check for missing colons, brackets, or quotes",
        "safety_category": "moderate",
        "is_preseeded": True,
    },

    # Type errors (SAFE to MODERATE)
    {
        "fingerprint_regex": r"TypeError: '(\w+)' object is not (subscriptable|iterable|callable)",
        "fix_template": "Add None check before accessing {captured_group_1}",
        "safety_category": "safe",
        "is_preseeded": True,
    },
    {
        "fingerprint_regex": r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
        "fix_template": "Check if {captured_group_2} exists or handle None case",
        "safety_category": "moderate",
        "is_preseeded": True,
    },

    # Test framework errors (SAFE)
    {
        "fingerprint_regex": r"fixture '(\w+)' not found",
        "fix_template": "Add @pytest.fixture for {captured_group_1} or import from conftest",
        "safety_category": "safe",
        "is_preseeded": True,
    },

    # Node/JS errors (SAFE)
    {
        "fingerprint_regex": r"Cannot find module '(.+)'",
        "fix_template": "npm install {captured_group_1}",
        "safety_category": "safe",
        "is_preseeded": True,
    },

    # Go errors (SAFE)
    {
        "fingerprint_regex": r"cannot find package \"(.+)\"",
        "fix_template": "go get {captured_group_1}",
        "safety_category": "safe",
        "is_preseeded": True,
    },

    # Rust errors (SAFE)
    {
        "fingerprint_regex": r"error\[E0432\]: unresolved import `(\w+)`",
        "fix_template": "cargo add {captured_group_1}",
        "safety_category": "safe",
        "is_preseeded": True,
    },
]
```

**Precedent Hierarchy (highest to lowest value):**

| Precedent Type | How Established | Trust Level |
|----------------|-----------------|-------------|
| Human Correction | Human overrides AI suggestion | Highest |
| Pre-seeded | Ships with system (universal patterns) | High |
| Verified AI | 5+ successful applies passing VERIFY | Medium-High |
| Unverified | New pattern, no track record | None (no auto-apply) |

**Key Difference from Human-Required Model:**
- Old: Human must fix each error type first → bottleneck
- New: System ships with ~30 universal patterns → immediate value
- New: AI fixes that pass VERIFY 5+ times earn precedent automatically

### 4.6 Error Cascade Detection

```python
@dataclass
class CascadeDetector:
    """
    Detect when Fix A causes Error B.

    Prevents oscillating "ping-pong" fixes.
    """

    # Track files modified by healing engine
    file_heatmap: dict[str, list[datetime]] = field(default_factory=dict)

    # Thresholds
    max_modifications_per_hour: int = 3

    def record_modification(self, file_path: str) -> None:
        """Record that we modified a file."""
        if file_path not in self.file_heatmap:
            self.file_heatmap[file_path] = []
        self.file_heatmap[file_path].append(datetime.utcnow())

    def is_file_hot(self, file_path: str) -> bool:
        """Check if file has been modified too often (ping-pong risk)."""
        if file_path not in self.file_heatmap:
            return False

        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_mods = [t for t in self.file_heatmap[file_path] if t > one_hour_ago]

        return len(recent_mods) >= self.max_modifications_per_hour

    def check_cascade(self, new_error: ErrorEvent, recent_fixes: list[ResolutionRecord]) -> Optional[str]:
        """Check if new error was likely caused by a recent fix."""
        for fix in recent_fixes:
            # Check if error occurred in file we just modified
            if new_error.file_path in fix.files_modified:
                # Check timing (error occurred shortly after fix)
                if new_error.timestamp - fix.applied_at < timedelta(minutes=30):
                    return fix.resolution_id  # Likely caused by this fix
        return None
```

### 4.7 Fingerprinting Algorithm

**Critical**: The entire system hinges on stable, accurate fingerprinting. This section defines the exact algorithm.

```python
import hashlib
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class FingerprintConfig:
    """Configuration for error fingerprinting."""

    # Normalization rules (order matters)
    strip_patterns: list[tuple[str, str]] = field(default_factory=lambda: [
        # File paths: /home/user/project/foo.py → <path>/foo.py
        (r'/[\w/.-]+/([^/]+\.\w+)', r'<path>/\1'),

        # Line numbers: foo.py:123 → foo.py:<line>
        (r'(\.\w+):(\d+)', r'\1:<line>'),

        # UUIDs: abc123-def456-... → <uuid>
        (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>'),

        # Timestamps: 2026-01-16T14:30:00Z → <timestamp>
        (r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[Z\d:+-]*', '<timestamp>'),

        # Memory addresses: 0x7fff5fbff8c0 → <addr>
        (r'0x[0-9a-fA-F]+', '<addr>'),

        # Process IDs: pid=12345 → pid=<pid>
        (r'pid[=:]\s*\d+', 'pid=<pid>'),

        # Temp files: /tmp/pytest-123/... → <tmpdir>/...
        (r'/tmp/[\w.-]+/', '<tmpdir>/'),

        # Variable content in quotes: "user@example.com" → "<string>"
        (r'"[^"]{20,}"', '"<string>"'),  # Long strings only
    ])


class Fingerprinter:
    """
    Generate stable fingerprints for error deduplication.

    Design principles:
    1. Same root cause → same fingerprint (even with different paths/line numbers)
    2. Different root causes → different fingerprints (no false grouping)
    3. Hierarchical: coarse (error type) + fine (normalized message)
    """

    def __init__(self, config: FingerprintConfig = None):
        self.config = config or FingerprintConfig()

    def fingerprint(self, error: "ErrorEvent") -> str:
        """
        Generate a stable fingerprint from an error.

        Components (hashed together):
        1. Error type (e.g., "TypeError", "ImportError")
        2. Normalized message (paths/UUIDs/timestamps stripped)
        3. Top stack frame module + function (if available)
        """
        components = []

        # 1. Error type (most important for grouping)
        error_type = self._extract_error_type(error.error_type or error.description)
        components.append(f"type:{error_type}")

        # 2. Normalized message
        normalized = self._normalize(error.description or "")
        components.append(f"msg:{normalized[:200]}")  # Truncate for stability

        # 3. Top stack frame (if available)
        if error.stack_trace:
            top_frame = self._extract_top_frame(error.stack_trace)
            if top_frame:
                components.append(f"frame:{top_frame}")

        # Hash the components
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def fingerprint_coarse(self, error: "ErrorEvent") -> str:
        """
        Coarse fingerprint for broad grouping (just error type + category).

        Use for: "How many TypeError issues do we have?"
        """
        error_type = self._extract_error_type(error.error_type or error.description)
        return hashlib.sha256(f"coarse:{error_type}".encode()).hexdigest()[:8]

    def _extract_error_type(self, text: str) -> str:
        """Extract the error class name."""
        # Python: "TypeError: ..."
        match = re.match(r'^(\w+Error|\w+Exception|\w+Warning):', text)
        if match:
            return match.group(1)

        # Node: "Error: ..."
        if text.startswith("Error:"):
            return "Error"

        # Rust: "error[E0123]:"
        match = re.match(r'error\[(E\d+)\]', text)
        if match:
            return f"RustError_{match.group(1)}"

        # Go: "panic: ..."
        if text.startswith("panic:"):
            return "GoPanic"

        return "UnknownError"

    def _normalize(self, text: str) -> str:
        """Apply normalization rules to strip variable content."""
        result = text
        for pattern, replacement in self.config.strip_patterns:
            result = re.sub(pattern, replacement, result)
        return result.strip()

    def _extract_top_frame(self, stack_trace: str) -> Optional[str]:
        """Extract the top (most relevant) stack frame."""
        # Python traceback: File "foo.py", line 123, in bar
        match = re.search(r'File "([^"]+)", line \d+, in (\w+)', stack_trace)
        if match:
            filename = match.group(1).split('/')[-1]  # Just filename
            function = match.group(2)
            return f"{filename}:{function}"

        # Node.js: at functionName (file.js:123:45)
        match = re.search(r'at (\w+) \(([^)]+)\)', stack_trace)
        if match:
            function = match.group(1)
            filename = match.group(2).split('/')[-1].split(':')[0]
            return f"{filename}:{function}"

        return None


# Fingerprint clustering for semantic equivalence
@dataclass
class FingerprintCluster:
    """
    Group semantically equivalent fingerprints.

    Example: These are all "NoneType" errors that might need the same fix:
    - "TypeError: cannot unpack non-iterable NoneType object"
    - "TypeError: 'NoneType' object is not iterable"
    - "AttributeError: 'NoneType' object has no attribute 'items'"
    """

    canonical_fingerprint: str       # The "representative" fingerprint
    member_fingerprints: set[str]    # Variants that map to same fix
    semantic_label: str              # Human-readable: "NoneType handling"

    def matches(self, fingerprint: str) -> bool:
        """Check if a fingerprint belongs to this cluster."""
        return (
            fingerprint == self.canonical_fingerprint or
            fingerprint in self.member_fingerprints
        )
```

**Testing fingerprint stability:**
```python
def test_fingerprint_stability():
    """Same error produces same fingerprint across runs."""
    fp = Fingerprinter()

    # These should all produce the SAME fingerprint
    error1 = ErrorEvent(description="TypeError: 'NoneType' object is not subscriptable",
                        file_path="/home/alice/project/foo.py")
    error2 = ErrorEvent(description="TypeError: 'NoneType' object is not subscriptable",
                        file_path="/home/bob/work/foo.py")  # Different path

    assert fp.fingerprint(error1) == fp.fingerprint(error2)

    # These should produce DIFFERENT fingerprints
    error3 = ErrorEvent(description="ImportError: No module named 'foo'")
    assert fp.fingerprint(error1) != fp.fingerprint(error3)
```

### 4.8 Cost Controls

```python
@dataclass
class CostControls:
    """
    Prevent runaway spending on LLM validation and embeddings.

    All limits are automatic - no human approval required.
    """

    # Daily limits
    max_validations_per_day: int = 100
    max_embeddings_per_day: int = 500
    max_daily_cost_usd: float = 10.0

    # Per-operation limits
    max_validation_cost_usd: float = 0.50  # Per fix validation
    max_judges_for_safe: int = 1           # SAFE: 1 model
    max_judges_for_moderate: int = 2       # MODERATE: 2 models
    max_judges_for_risky: int = 3          # RISKY: 3 models (but no auto-apply)

    # Rate limiting
    max_auto_fixes_per_hour: int = 10
    cooldown_after_revert_minutes: int = 30

    # Tracking
    _daily_cost: float = 0.0
    _daily_validations: int = 0
    _daily_embeddings: int = 0
    _last_reset: datetime = field(default_factory=datetime.utcnow)

    def can_validate(self, safety_category: SafetyCategory) -> tuple[bool, str]:
        """Check if we can afford another validation."""
        self._maybe_reset_daily()

        if self._daily_cost >= self.max_daily_cost_usd:
            return False, f"Daily cost limit reached (${self._daily_cost:.2f})"

        if self._daily_validations >= self.max_validations_per_day:
            return False, f"Daily validation limit reached ({self._daily_validations})"

        return True, "OK"

    def record_cost(self, operation: str, cost_usd: float) -> None:
        """Record cost of an operation."""
        self._daily_cost += cost_usd
        if operation == "validation":
            self._daily_validations += 1
        elif operation == "embedding":
            self._daily_embeddings += 1

    def get_judge_count(self, safety_category: SafetyCategory) -> int:
        """Get number of judges for a safety category (cost-aware)."""
        if safety_category == SafetyCategory.SAFE:
            return self.max_judges_for_safe
        elif safety_category == SafetyCategory.MODERATE:
            return self.max_judges_for_moderate
        else:
            return self.max_judges_for_risky

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters if new day."""
        now = datetime.utcnow()
        if now.date() > self._last_reset.date():
            self._daily_cost = 0.0
            self._daily_validations = 0
            self._daily_embeddings = 0
            self._last_reset = now

    def get_status(self) -> dict:
        """Get current cost status for observability."""
        return {
            "daily_cost_usd": self._daily_cost,
            "daily_cost_limit_usd": self.max_daily_cost_usd,
            "daily_validations": self._daily_validations,
            "daily_validation_limit": self.max_validations_per_day,
            "budget_remaining_usd": self.max_daily_cost_usd - self._daily_cost,
        }
```

**Cost estimation per operation:**

| Operation | Estimated Cost | Notes |
|-----------|---------------|-------|
| Embedding (ada-002) | $0.0001/1K tokens | ~$0.0002 per error |
| Validation (1 model) | $0.02-0.10 | Depends on model |
| Validation (3 models) | $0.06-0.30 | Full multi-model |
| RAG query | Free | pgvector is local |

### 4.9 Local Fallback Cache

```python
import sqlite3
from pathlib import Path

@dataclass
class LocalFallbackCache:
    """
    SQLite cache for offline operation when Supabase unavailable.

    Ensures system continues working during:
    - Supabase outages (~1-2x/month)
    - Network issues
    - Rate limiting
    """

    cache_path: Path = Path(".claude/healing_cache.sqlite")

    def __post_init__(self):
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite schema."""
        conn = sqlite3.connect(self.cache_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patterns (
                fingerprint TEXT PRIMARY KEY,
                learning_id TEXT,
                fix_template TEXT,
                safety_category TEXT,
                success_rate REAL,
                use_count INTEGER,
                cached_at TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_writes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT,
                operation TEXT,  -- 'insert', 'update'
                payload TEXT,    -- JSON
                created_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_patterns_fingerprint
                ON patterns(fingerprint);
        """)
        conn.close()

    def lookup_pattern(self, fingerprint: str) -> dict | None:
        """Tier 1 lookup from local cache."""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute(
            "SELECT * FROM patterns WHERE fingerprint = ?",
            (fingerprint,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "fingerprint": row[0],
                "learning_id": row[1],
                "fix_template": row[2],
                "safety_category": row[3],
                "success_rate": row[4],
                "use_count": row[5],
            }
        return None

    def cache_pattern(self, pattern: dict) -> None:
        """Cache a pattern from Supabase for offline use."""
        conn = sqlite3.connect(self.cache_path)
        conn.execute("""
            INSERT OR REPLACE INTO patterns
            (fingerprint, learning_id, fix_template, safety_category, success_rate, use_count, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            pattern["fingerprint"],
            pattern.get("learning_id"),
            pattern.get("fix_template"),
            pattern.get("safety_category"),
            pattern.get("success_rate", 0.0),
            pattern.get("use_count", 0),
        ))
        conn.commit()
        conn.close()

    def queue_write(self, table: str, operation: str, payload: dict) -> None:
        """Queue a write for later sync to Supabase."""
        import json
        conn = sqlite3.connect(self.cache_path)
        conn.execute("""
            INSERT INTO pending_writes (table_name, operation, payload, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (table, operation, json.dumps(payload)))
        conn.commit()
        conn.close()

    def sync_pending_writes(self, supabase_client) -> int:
        """Sync queued writes to Supabase when connection restored."""
        import json
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute("SELECT id, table_name, operation, payload FROM pending_writes")
        rows = cursor.fetchall()

        synced = 0
        for row_id, table, operation, payload_json in rows:
            payload = json.loads(payload_json)
            try:
                if operation == "insert":
                    supabase_client.table(table).insert(payload).execute()
                elif operation == "update":
                    supabase_client.table(table).update(payload).eq("id", payload["id"]).execute()

                conn.execute("DELETE FROM pending_writes WHERE id = ?", (row_id,))
                synced += 1
            except Exception as e:
                # Keep in queue for retry
                pass

        conn.commit()
        conn.close()
        return synced


class HealingClient:
    """
    Unified client with automatic fallback.

    Tries Supabase first, falls back to local cache.
    """

    def __init__(self, supabase_client, local_cache: LocalFallbackCache):
        self.supabase = supabase_client
        self.cache = local_cache
        self._supabase_healthy = True

    def lookup_pattern(self, fingerprint: str) -> dict | None:
        """Lookup with automatic fallback."""
        # Try Supabase first
        if self._supabase_healthy:
            try:
                result = self.supabase.table("error_patterns")\
                    .select("*")\
                    .eq("fingerprint", fingerprint)\
                    .single()\
                    .execute()
                if result.data:
                    # Cache for offline use
                    self.cache.cache_pattern(result.data)
                    return result.data
            except Exception:
                self._supabase_healthy = False

        # Fallback to local cache
        return self.cache.lookup_pattern(fingerprint)

    def record_fix_result(self, fingerprint: str, success: bool) -> None:
        """Record fix result, queue if offline."""
        payload = {"fingerprint": fingerprint, "success": success}

        if self._supabase_healthy:
            try:
                self.supabase.rpc("update_pattern_stats", payload).execute()
                return
            except Exception:
                self._supabase_healthy = False

        # Queue for later sync
        self.cache.queue_write("pattern_stats", "update", payload)
```

### 4.10 Escape Hatches

```python
@dataclass
class EscapeHatches:
    """
    Manual overrides for when automation gets in the way.

    Philosophy: Trust the user, provide clear escape routes.
    """

    # CLI flags
    # --force: Bypass safety gates for emergencies
    # --ignore <fingerprint>: Permanently ignore an error pattern
    # --unquarantine <fingerprint>: Reset a quarantined pattern
    # --dry-run: Show what would happen without applying

    def force_apply(self, fix: "SuggestedFix", reason: str) -> "FixResult":
        """
        Force-apply a fix, bypassing safety gates.

        Usage: orchestrator heal apply --force --fix-id abc123 --reason "Emergency"

        Bypasses:
        - Safety category checks
        - Multi-model validation
        - Precedent requirements

        Does NOT bypass:
        - Kill switch (always respected)
        - Forbidden patterns (security)
        - Verification (still runs build/test)
        """
        if check_kill_switch():
            raise KillSwitchActive("Cannot force-apply while kill switch active")

        # Check forbidden patterns (security - never bypass)
        violations = hard_constraints.check_forbidden_patterns(fix.diff)
        if violations:
            raise SecurityViolation(f"Cannot force: {violations}")

        # Log the override
        audit_log.record({
            "action": "force_apply",
            "fix_id": fix.id,
            "reason": reason,
            "bypassed_gates": ["safety_category", "multi_model", "precedent"],
        })

        # Apply with verification only
        return apply_fix_with_verify_only(fix)

    def ignore_pattern(self, fingerprint: str, reason: str) -> None:
        """
        Permanently ignore an error pattern.

        Usage: orchestrator heal ignore --fingerprint xyz789 --reason "Expected behavior"

        The error will still be detected but will not:
        - Appear in issue queue
        - Trigger fix suggestions
        - Count toward metrics
        """
        pattern = pattern_memory.get(fingerprint)
        if not pattern:
            pattern = ErrorPattern(fingerprint=fingerprint)

        pattern.ignored = True
        pattern.ignored_reason = reason
        pattern.ignored_at = datetime.utcnow()

        pattern_memory.save(pattern)

        audit_log.record({
            "action": "ignore_pattern",
            "fingerprint": fingerprint,
            "reason": reason,
        })

    def unquarantine(self, fingerprint: str, reason: str) -> None:
        """
        Reset a quarantined pattern for another chance.

        Usage: orchestrator heal unquarantine --fingerprint xyz789 --reason "Root cause fixed"

        The pattern will:
        - Have quarantine flag removed
        - Keep historical stats (but can be used again)
        - Start fresh verification cycle
        """
        pattern = pattern_memory.get(fingerprint)
        if not pattern:
            raise PatternNotFound(fingerprint)

        pattern.quarantined = False
        pattern.quarantined_until = None
        pattern.verified_apply_count = 0  # Reset verification counter

        pattern_memory.save(pattern)

        audit_log.record({
            "action": "unquarantine",
            "fingerprint": fingerprint,
            "reason": reason,
        })

    def export_patterns(self, format: str = "yaml") -> str:
        """
        Export all patterns for manual review.

        Usage: orchestrator heal export --format yaml > patterns.yaml
        """
        patterns = pattern_memory.get_all()

        if format == "yaml":
            import yaml
            return yaml.dump([p.to_dict() for p in patterns], default_flow_style=False)
        elif format == "json":
            import json
            return json.dumps([p.to_dict() for p in patterns], indent=2)
        else:
            raise ValueError(f"Unknown format: {format}")
```

**CLI Commands:**
```bash
# Force a specific fix (bypass safety checks for emergencies)
orchestrator heal apply --force --fix-id abc123 --reason "Production emergency"

# Permanently ignore an error pattern
orchestrator heal ignore --fingerprint xyz789 --reason "Expected behavior"

# Reset a quarantined pattern
orchestrator heal unquarantine --fingerprint xyz789 --reason "Root cause fixed"

# Export all patterns for manual review
orchestrator heal export --format yaml > patterns.yaml

# Dry-run to see what would happen
orchestrator heal apply --dry-run --fix-id abc123

# Show why a fix wasn't auto-applied
orchestrator heal explain --fingerprint xyz789
```

---

## 5. Data Models (Simplified Per Review)

### 5.1 Safety Categories (Simplified from 6 to 3)

```python
class SafetyCategory(str, Enum):
    """Simplified categories per review feedback."""

    SAFE = "safe"           # Formatting, imports, types - auto-apply eligible
    MODERATE = "moderate"   # Logic fixes - high threshold auto-apply
    RISKY = "risky"         # Refactoring, API changes - never auto-apply
```

### 5.2 Provenance (Simplified to Binary)

```python
@dataclass
class ResolutionProvenance:
    """Simplified provenance - binary AI vs Human."""

    source: Literal["ai_generated", "human_authored"]
    author: str                        # Agent ID or "human"
    learned_at: datetime
```

### 5.3 Error Event Model

```python
@dataclass
class ErrorEvent:
    """Unified error event from any source."""

    # Identity
    error_id: str
    timestamp: datetime

    # Source
    source: Literal["workflow_log", "transcript", "subprocess", "hook"]

    # Classification
    error_type: str                    # Exception class or category
    severity: ErrorSeverity

    # Fingerprint (single level - medium)
    fingerprint: str                   # Normalized signature hash

    # Context
    workflow_id: Optional[str]
    phase_id: Optional[str]
    file_path: Optional[str]
    stack_trace: Optional[str]         # Scrubbed
    command: Optional[str]             # If subprocess
    exit_code: Optional[int]           # If subprocess

    # Resolution tracking
    resolution_id: Optional[str]
    resolution_status: ResolutionStatus
```

---

## 6. Staged Implementation (Aggressive Phasing)

### 6.1 Phase Overview (Fast Track)

| Phase | Duration | Focus | Autonomy Level |
|-------|----------|-------|----------------|
| Phase 0 | Day 1-3 | Detection infrastructure | Observe only |
| Phase 1 | Day 4-7 | Pattern matching + suggestions | Suggest, human confirms |
| Phase 2 | Week 2 | Safe auto-apply | Auto for SAFE category |
| Phase 3 | Week 3+ | Full auto-apply | Auto with all safety gates |

### 6.2 Phase 0: Detection (Days 1-3)

**Goal:** Get errors flowing into the system from all 4 sources.

**Deliverables:**
1. Workflow log parser (parse `.workflow_log.jsonl`)
2. Transcript analyzer (regex patterns from section 2.2)
3. Subprocess wrapper (capture exit codes, stderr)
4. Fingerprinting (normalize and hash)

**Success Criteria:**
- Errors from all sources captured
- Fingerprints are stable (same error = same fingerprint)
- Audit trail complete

### 6.3 Phase 1: Suggestions (Days 4-7)

**Goal:** Match errors to patterns and suggest fixes.

**Deliverables:**
1. Pattern memory extension (from conflict patterns to error patterns)
2. Human precedent tracking
3. Suggestion UI (show suggested fix, wait for confirmation)
4. Learning from confirmed fixes

**Success Criteria:**
- Suggestions generated for repeat errors
- Human confirms → pattern learned
- Zero auto-apply (all confirmed)

### 6.4 Phase 2: Safe Auto-Apply (Week 2)

**Goal:** Auto-apply SAFE category fixes with all safety gates.

**Prerequisites (Must Have Before Auto-Apply):**
- [x] Kill switch implemented
- [x] Rollback mechanism working
- [x] Hard constraints enforced
- [x] Multi-model validation active
- [x] Human precedent required

**Auto-Apply Rules:**

| Requirement | Threshold |
|-------------|-----------|
| Safety category | SAFE only |
| Human precedent | Required |
| Pattern confidence | >= 0.7 |
| Success rate | >= 0.9 |
| Use count | >= 3 |
| Multi-model approval | 2 of 3 |
| Hard constraints | All pass |

### 6.5 Phase 3: Full Auto-Apply (Week 3+)

**Goal:** Extend to MODERATE category with higher thresholds.

**Auto-Apply Rules for MODERATE:**

| Requirement | Threshold |
|-------------|-----------|
| Safety category | MODERATE |
| Human precedent | Required |
| Pattern confidence | >= 0.9 |
| Success rate | >= 0.95 |
| Use count | >= 10 |
| Multi-model approval | 3 of 3 (unanimous) |
| Hard constraints | All pass |

**Never Auto-Apply:**
- RISKY category (always requires confirmation)

---

## 7. Quality Gates (3-Phase Validation)

Simplified from 8 sequential gates to 3 logical phases. Phases run parallel where possible, reducing latency and cost.

```
                        FIX CANDIDATE
                              |
                +─────────────────────────────+
                │    PHASE 1: PRE-FLIGHT      │  ~10ms
                │    (parallel fast checks)   │
                +─────────────────────────────+
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   Kill Switch         Hard Constraints        Precedent
   (.healing_lock)     (files, lines, deps)    (verified)
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │ All must pass
                              ▼
                +─────────────────────────────+
                │   PHASE 2: VERIFICATION     │  ~30-60s
                │   (parallel build/test)     │
                +─────────────────────────────+
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
      Build                 Tests                 Lint
   (compile)           (related tests)        (ruff/eslint)
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │ All must pass
                              ▼
                +─────────────────────────────+
                │    PHASE 3: APPROVAL        │  ~5-15s
                │    (tiered by safety)       │
                +─────────────────────────────+
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
      SAFE               MODERATE                RISKY
   (1 judge)           (2 judges)           (no auto-apply)
   ~$0.03               ~$0.06                 (queue)
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                     [APPLY OR QUEUE]
```

### 7.1 Phase Details

```python
from dataclasses import dataclass
from enum import Enum
import asyncio

class ValidationPhase(Enum):
    PRE_FLIGHT = "pre_flight"
    VERIFICATION = "verification"
    APPROVAL = "approval"


@dataclass
class ValidationPipeline:
    """
    3-phase validation with parallel execution.

    Key improvements over 8-gate sequential:
    - Phase 1 checks run in parallel (~10ms total vs ~80ms sequential)
    - Phase 2 runs build/test/lint in parallel (~30s vs ~90s sequential)
    - Phase 3 is tiered by safety (1-3 judges vs always 3)
    """

    async def validate(self, fix: "SuggestedFix", error: "ErrorEvent") -> "ValidationResult":
        """Run all validation phases."""

        # PHASE 1: Pre-flight (parallel fast checks)
        preflight_results = await asyncio.gather(
            self._check_kill_switch(),
            self._check_hard_constraints(fix),
            self._check_precedent(fix.pattern_fingerprint),
            self._check_cascade(fix, error),
        )

        if not all(r.passed for r in preflight_results):
            failed = [r for r in preflight_results if not r.passed]
            return ValidationResult(
                approved=False,
                phase=ValidationPhase.PRE_FLIGHT,
                reason=failed[0].reason,
            )

        # PHASE 2: Verification (parallel build/test/lint)
        verify_results = await asyncio.gather(
            self._run_build(fix),
            self._run_tests(fix),
            self._run_lint(fix),
        )

        if not all(r.passed for r in verify_results):
            failed = [r for r in verify_results if not r.passed]
            return ValidationResult(
                approved=False,
                phase=ValidationPhase.VERIFICATION,
                reason=failed[0].reason,
            )

        # PHASE 3: Approval (tiered by safety category)
        approval = await self._get_approval(fix)
        return approval

    async def _get_approval(self, fix: "SuggestedFix") -> "ValidationResult":
        """Tiered approval based on safety category."""

        # RISKY: Never auto-apply, queue for review
        if fix.safety_category == SafetyCategory.RISKY:
            return ValidationResult(
                approved=False,
                phase=ValidationPhase.APPROVAL,
                reason="RISKY category - queued for review",
                queue_for_review=True,
            )

        # Get judge count based on safety + cost controls
        judge_count = cost_controls.get_judge_count(fix.safety_category)

        # Run judges (subset of full 3-model panel)
        judges = self._select_judges(judge_count)
        votes = await asyncio.gather(*[
            self._get_judge_vote(judge, fix)
            for judge in judges
        ])

        # Threshold: majority must approve
        approvals = sum(1 for v in votes if v.approved)
        threshold = (judge_count // 2) + 1  # Majority

        return ValidationResult(
            approved=approvals >= threshold,
            phase=ValidationPhase.APPROVAL,
            votes=votes,
            reason=f"{approvals}/{judge_count} judges approved" if approvals >= threshold else "Insufficient approvals",
        )

    def _select_judges(self, count: int) -> list[str]:
        """Select judges, prioritizing diversity."""
        all_judges = ["claude-opus-4-5", "gpt-5.2", "grok-4.1"]
        return all_judges[:count]
```

### 7.2 Phase Timing

| Phase | Sequential (old) | Parallel (new) | Savings |
|-------|------------------|----------------|---------|
| Pre-flight | ~80ms | ~10ms | 87% |
| Verification | ~90s | ~30s | 67% |
| Approval | ~15s (always 3) | ~5-15s (tiered) | 0-67% |
| **Total** | ~105s | ~35-55s | **50-67%** |

### 7.3 Automatic Pass-Through

Some fixes skip phases entirely based on category:

| Safety Category | Phase 1 | Phase 2 | Phase 3 |
|-----------------|---------|---------|---------|
| SAFE | ✓ | ✓ | 1 judge |
| MODERATE | ✓ | ✓ | 2 judges |
| RISKY | ✓ | ✓ | No auto-apply (queue) |

---

## 8. Metrics for Success

### 8.1 Primary Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| **Error Detection Rate** | 95%+ | Errors captured vs total errors |
| **Auto-Resolve Rate** | 50%+ by Week 3 | Errors resolved without human |
| **First-Fix Success Rate** | 90%+ | Auto-applies that pass VERIFY |
| **Churn Rate** | <5% | Fixes that get reverted |
| **Cascade Rate** | <1% | Fixes that cause new errors |
| **Time-to-Resolution** | <5 min | Detection to resolution |

### 8.2 Alert Thresholds

| Alert Level | Trigger | Action |
|-------------|---------|--------|
| CRITICAL | Churn rate > 15% | Activate kill switch |
| CRITICAL | Cascade detected | Revert + quarantine |
| CRITICAL | Kill switch active | All auto-apply halted |
| WARNING | Churn rate > 8% | Review recent patterns |
| WARNING | Multi-model disagreement > 30% | Review judge calibration |

---

## 9. File Structure

```
src/self_healing/
    __init__.py

    # Detection (Section 2)
    error_sources.py          # 4-source error detection
    transcript_analyzer.py    # Parse session transcripts (Issue #27)
    subprocess_wrapper.py     # Intercept CLI calls
    fingerprint.py            # Normalize and hash errors

    # Safety (Section 4)
    kill_switch.py            # Global halt mechanism
    rollback.py               # Revert fixes
    hard_constraints.py       # Unbendable limits
    multi_model_validator.py  # Multi-model voting
    human_precedent.py        # Track human fixes
    cascade_detector.py       # Detect error chains

    # Learning (Section 11)
    learning_schema.py        # Learning object schema
    learning_capture.py       # Extract learnings from workflows
    learning_lifecycle.py     # Graduation, expiration, pruning
    correction_capture.py     # Human correction events
    learning_to_pattern.py    # Convert learnings to patterns

    # Core
    pattern_memory.py         # Extended from conflict patterns
    staged_applicator.py      # Apply fixes on branches
    quality_gates.py          # 8-gate validation

    # Audit
    healing_audit.py          # Hash-chained logging

# Storage locations
.claude/
    learnings.jsonl           # Structured learnings (machine-readable)
    learnings_archive/        # Expired/deprecated learnings
    corrections.jsonl         # Human correction events
    learning_metrics.json     # Aggregated stats
```

---

## 10. Integration with Existing Infrastructure

| Component | Existing File | Integration |
|-----------|---------------|-------------|
| Error Detection | `src/audit.py` | Extend event types |
| Transcript Analysis | `src/transcript_logger.py` | Add error regex patterns |
| Pattern Memory | `src/learning/pattern_memory.py` | Extend for error patterns |
| Validation | `src/resolution/validator.py` | Add hard constraints |
| Multi-Model | `src/review/orchestrator.py` | Reuse model calling |

---

## 11. LEARN Phase Integration (Critical for Self-Healing)

The LEARN phase at the end of each workflow cycle is the **primary source of knowledge** for the self-healing system. Based on best practices from Netflix Chaos Engineering, Google SRE postmortems, GitHub Copilot correction learning, and Sentry's error grouping, we've designed a structured learning capture system.

### 11.1 Core Principle: Structure First, Prose Second

All models agreed: **treat learnings as code, not documents**. Machine-readable structure is the source of truth; human narrative is an attachment.

```
+------------------------------------------------------------------+
|                     LEARN PHASE FLOW                              |
+------------------------------------------------------------------+
|                                                                   |
|  Workflow Completes (VERIFY passed)                              |
|         |                                                         |
|         v                                                         |
|  +------------------+                                             |
|  | Capture Learning |  <-- Structured JSON, not freeform prose   |
|  +------------------+                                             |
|         |                                                         |
|         v                                                         |
|  +------------------+                                             |
|  | Deduplicate      |  <-- Fingerprint against existing learnings |
|  +------------------+                                             |
|         |                                                         |
|         v                                                         |
|  +------------------+                                             |
|  | Score & Rank     |  <-- priority = impact × recurrence × conf  |
|  +------------------+                                             |
|         |                                                         |
|         v                                                         |
|  +------------------+                                             |
|  | Store in         |  <-- .claude/learnings.jsonl               |
|  | Knowledge Base   |                                             |
|  +------------------+                                             |
|         |                                                         |
|         v                                                         |
|  +------------------+                                             |
|  | Check Automation |  <-- Should this become auto-remediation?  |
|  | Graduation       |                                             |
|  +------------------+                                             |
|                                                                   |
+------------------------------------------------------------------+
```

### 11.2 Learning Object Schema (Machine-Readable)

Based on multi-model consensus, every learning follows this structure:

```yaml
# Structured learning object
learning_id: "learn-uuid-123"
workflow_id: "wf-abc-789"
created_at: "2026-01-16T14:30:00Z"

# Classification
type: "error_resolution"  # detection_gap | remediation | prevention | process
category: "import_error"  # Specific error category

# The Core Learning (Atomic & Testable)
trigger:
  conditions:
    - metric: "error_type"
      operator: "=="
      value: "ModuleNotFoundError"
    - metric: "message_pattern"
      operator: "contains"
      value: "pytest_asyncio"
  context:
    - phase: "EXECUTE"
    - file_pattern: "tests/*.py"

# What action fixes this
action:
  type: "add_dependency"
  parameters:
    package: "pytest-asyncio"
    file: "requirements-dev.txt"
  validation:
    metric: "import_succeeds"
    expected: true

# Evidence (Quantified, Not Opinion)
evidence:
  occurrences: 3                # How many times seen
  success_rate: 1.0             # Resolution success rate
  time_saved_minutes: 12        # Estimated time saved
  files_involved:
    - "tests/test_async.py"
    - "requirements-dev.txt"

# Lifecycle & Scoring
confidence: 0.92                # Statistical confidence
lifecycle: "accepted"           # proposed | accepted | automated | deprecated
priority_score: 7.5             # impact × recurrence × confidence

# Provenance (Critical for Human Precedent)
provenance:
  source: "human_authored"      # ai_generated | human_authored
  author: "user@example.com"
  verified_by_workflow: "wf-xyz-456"

# Human-Readable Context (Attachment, Not Source)
narrative: |
  When running async tests, pytest-asyncio must be installed.
  The fixture `@pytest.mark.asyncio` requires this dependency.
  Adding to requirements-dev.txt resolves the import error.
```

### 11.3 Actionable vs Noise (Decision Criteria)

| Actionable Learning | Noise (Discard) |
|---------------------|-----------------|
| Specific trigger conditions ("If error X then Y") | Vague ("improve reliability") |
| Reproducible (≥3 occurrences or verified) | One-off incident |
| Clear validation metric | No way to verify success |
| Demonstrated success rate (>80%) | Unproven correlation |
| Low blast radius / reversible | High-risk changes |

```python
def is_actionable(learning: Learning) -> bool:
    """Filter noise from actionable learnings."""
    return (
        learning.trigger.conditions  # Has specific triggers
        and learning.evidence.occurrences >= 3  # Reproducible
        and learning.action.validation  # Has validation metric
        and learning.evidence.success_rate >= 0.8  # Proven effective
    )
```

### 11.4 Preventing Learning Bloat

Without aggressive lifecycle management, knowledge bases become unusable.

```python
@dataclass
class LearningLifecycleConfig:
    """Prevent learning bloat through aggressive curation."""

    # Deduplication
    similarity_threshold: float = 0.85  # Fingerprint similarity for dedup

    # Expiration
    unused_ttl_days: int = 90           # Remove if not used in 90 days
    deprecated_ttl_days: int = 30       # Remove deprecated after 30 days

    # Budget limits
    max_learnings_per_category: int = 50    # Top 50 per error category
    max_total_learnings: int = 1000         # Hard cap

    # Pruning criteria
    min_confidence_to_keep: float = 0.5     # Below this = prune
    min_success_rate_to_keep: float = 0.7   # Below this = prune

    def prune(self, learnings: list[Learning]) -> list[Learning]:
        """Remove low-value learnings."""
        # 1. Remove expired
        learnings = [l for l in learnings if not self._is_expired(l)]

        # 2. Remove low confidence
        learnings = [l for l in learnings if l.confidence >= self.min_confidence_to_keep]

        # 3. Remove low success rate
        learnings = [l for l in learnings if l.evidence.success_rate >= self.min_success_rate_to_keep]

        # 4. Keep top N per category
        learnings = self._keep_top_per_category(learnings)

        return learnings
```

### 11.5 Automation Graduation Path (Zero-Human)

Learnings progress through 4 stages with **fully automatic graduation** - no human gates:

```
    DRAFT → ACTIVE → AUTOMATED → DEPRECATED
      ↓        ↓         ↓            ↓
    New     Verified   Full auto   No longer
  pattern   working    applies      useful
```

**Key Change from Human-Gated Model:**
- Old: 6 stages with human approval required at multiple points
- New: 4 stages with automatic graduation based on verified outcomes

**Graduation Criteria (All Automatic):**

| Transition | Requirements | Automatic? |
|------------|--------------|------------|
| DRAFT → ACTIVE | Pattern verified 3+ times with >80% success | ✅ Yes |
| ACTIVE → AUTOMATED | 5+ verified applies, >90% success, no regressions | ✅ Yes |
| AUTOMATED → DEPRECATED | <50% success rate OR unused for 90+ days | ✅ Yes |
| Any → QUARANTINED | 2+ regressions OR cascade detected | ✅ Yes |

```python
from enum import Enum
from dataclasses import dataclass

class LifecycleState(Enum):
    """Simplified 4-state lifecycle (down from 6)."""
    DRAFT = "draft"           # New pattern, unverified
    ACTIVE = "active"         # Verified, eligible for suggestion/auto-apply
    AUTOMATED = "automated"   # Full auto-apply enabled
    DEPRECATED = "deprecated" # No longer used (but kept for history)
    # Note: QUARANTINED is a flag, not a state (can happen at any stage)


@dataclass
class LearningLifecycle:
    """Automatic lifecycle management."""

    state: LifecycleState = LifecycleState.DRAFT
    quarantined: bool = False

    # Metrics for automatic graduation
    verified_count: int = 0
    success_rate: float = 0.0
    regression_count: int = 0
    last_used: datetime = None

    def check_graduation(self) -> Optional[LifecycleState]:
        """Check if pattern should graduate to next state. Fully automatic."""

        # Quarantined patterns don't graduate
        if self.quarantined:
            return None

        if self.state == LifecycleState.DRAFT:
            # Graduate to ACTIVE after verification
            if self.verified_count >= 3 and self.success_rate >= 0.8:
                return LifecycleState.ACTIVE

        elif self.state == LifecycleState.ACTIVE:
            # Graduate to AUTOMATED after proven track record
            if (self.verified_count >= 5 and
                self.success_rate >= 0.9 and
                self.regression_count == 0):
                return LifecycleState.AUTOMATED

        elif self.state == LifecycleState.AUTOMATED:
            # Demote to DEPRECATED if no longer useful
            if self.success_rate < 0.5:
                return LifecycleState.DEPRECATED
            if self.last_used and (datetime.utcnow() - self.last_used).days > 90:
                return LifecycleState.DEPRECATED

        return None

    def check_quarantine(self) -> bool:
        """Check if pattern should be quarantined. Automatic safety."""
        return self.regression_count >= 2


# Shadow mode is now a flag, not a lifecycle state
@dataclass
class ShadowMode:
    """
    Track what would happen without actually applying.

    Used for new patterns to build confidence before auto-apply.
    """
    enabled: bool = True              # New patterns start in shadow
    shadow_applies: int = 0           # How many times we would have applied
    shadow_successes: int = 0         # How many would have succeeded
    shadow_outcomes: list[dict] = None  # Detailed outcomes for analysis

    def record_shadow(self, would_succeed: bool) -> None:
        """Record a shadow execution."""
        self.shadow_applies += 1
        if would_succeed:
            self.shadow_successes += 1

    def should_exit_shadow(self) -> bool:
        """Check if pattern is ready to exit shadow mode."""
        if self.shadow_applies < 5:
            return False
        shadow_rate = self.shadow_successes / self.shadow_applies
        return shadow_rate >= 0.9
```

**Lifecycle State Diagram:**

```
                     ┌──────────────┐
                     │    DRAFT     │  New pattern
                     │  (unverified)│
                     └──────┬───────┘
                            │ 3+ verified, >80% success
                            ▼
                     ┌──────────────┐
                     │    ACTIVE    │  Verified, working
    Quarantine ←─────│  (suggest)   │──────→ Quarantine
    (2+ regressions) └──────┬───────┘       (cascade detected)
                            │ 5+ verified, >90% success, 0 regressions
                            ▼
                     ┌──────────────┐
                     │  AUTOMATED   │  Full auto-apply
                     │  (auto-fix)  │
                     └──────┬───────┘
                            │ <50% success OR 90+ days unused
                            ▼
                     ┌──────────────┐
                     │  DEPRECATED  │  No longer used
                     │  (archived)  │
                     └──────────────┘
```

### 11.6 Integration with Self-Healing

The LEARN phase feeds directly into the self-healing pattern memory:

```python
def on_learn_phase_complete(workflow: Workflow) -> None:
    """Called when a workflow completes LEARN phase."""

    # 1. Extract structured learnings
    learnings = extract_learnings(workflow)

    # 2. Filter for actionable learnings
    actionable = [l for l in learnings if is_actionable(l)]

    # 3. Deduplicate against existing
    new_learnings = deduplicate(actionable, existing_learnings)

    # 4. Score and store
    for learning in new_learnings:
        learning.priority_score = compute_priority(learning)
        store_learning(learning)

    # 5. Update pattern memory for self-healing
    for learning in new_learnings:
        if learning.type == "error_resolution":
            # Convert learning to error pattern for self-healing
            pattern = learning_to_pattern(learning)
            pattern_memory.add_pattern(pattern)

    # 6. Check automation graduation
    for learning in get_all_learnings():
        new_stage = check_graduation(learning)
        if new_stage:
            graduate_learning(learning, new_stage)
```

### 11.7 Correction Capture (Copilot Pattern)

**Every human correction is the highest-value learning signal.** When a human overrides, rejects, or modifies an AI suggestion, capture it:

```python
@dataclass
class CorrectionEvent:
    """Capture when human corrects AI behavior."""

    correction_id: str
    timestamp: datetime

    # What was suggested
    ai_suggestion: str
    ai_pattern_hash: Optional[str]

    # What human did instead
    human_action: str
    human_diff: str

    # Context
    error_fingerprint: str
    workflow_id: str
    phase: str

    # Classification
    correction_type: Literal[
        "rejected",        # Human rejected AI suggestion entirely
        "modified",        # Human used AI suggestion but changed it
        "replaced",        # Human did something completely different
    ]

    # Learning opportunity
    implicit_learning: Optional[str]  # What we should learn from this
```

**Correction → Learning Pipeline:**

```
Human Correction → Capture Event → Analyze Pattern
                                        ↓
                        Is this a repeat correction?
                        (same fingerprint, same correction type)
                                        ↓
                        If ≥3 corrections: Create learning
                        "For error X, humans prefer action Y over AI suggestion Z"
                                        ↓
                        Update pattern memory to prefer human approach
```

### 11.8 Learning Storage

```
.claude/
├── learnings.jsonl           # Structured learnings (machine-readable)
├── learnings_archive/        # Expired/deprecated learnings
├── corrections.jsonl         # Human correction events
└── learning_metrics.json     # Aggregated stats
```

### 11.9 Learning Metrics Dashboard

Track these metrics to ensure learning quality:

| Metric | Target | Description |
|--------|--------|-------------|
| **Learning Actionability Rate** | >70% | % of captured learnings that are actionable |
| **Learning Dedup Rate** | >30% | % of learnings that dedupe against existing |
| **Automation Graduation Rate** | >20% | % of accepted learnings that reach automated |
| **Correction-to-Learning Rate** | >50% | % of corrections that generate learnings |
| **Learning Decay Rate** | <10%/month | % of learnings expiring unused |

---

## 12. User Journey & Process Flow

### 12.1 Day-by-Day Progression

The system starts conservative and becomes more autonomous as trust is established:

```
+------------------------------------------------------------------+
|                    USER JOURNEY TIMELINE                           |
+------------------------------------------------------------------+
|                                                                    |
|  DAY 1-3: PURE OBSERVATION                                        |
|  ┌─────────────────────────────────────────────────────────────┐  |
|  │ • Errors captured silently during workflow                   │  |
|  │ • Issues accumulate in queue (no mid-workflow interruptions) │  |
|  │ • End-of-session: "Found 5 issues this session"             │  |
|  │ • Human reviews and fixes manually                           │  |
|  │ • System learns from human fixes (builds precedent)          │  |
|  └─────────────────────────────────────────────────────────────┘  |
|                              ↓                                     |
|  DAY 4-7: SUGGESTIONS                                             |
|  ┌─────────────────────────────────────────────────────────────┐  |
|  │ • Errors detected, matched against learned patterns          │  |
|  │ • End-of-session: "Found 3 issues, 2 have known fixes"      │  |
|  │ • Suggested fixes shown (with confidence %)                  │  |
|  │ • Human confirms/rejects/modifies                            │  |
|  │ • Confirmations strengthen patterns                          │  |
|  └─────────────────────────────────────────────────────────────┘  |
|                              ↓                                     |
|  WEEK 2+: TRIVIAL AUTO-FIX                                        |
|  ┌─────────────────────────────────────────────────────────────┐  |
|  │ • SAFE category issues auto-fixed (imports, formatting)      │  |
|  │ • Non-trivial issues queued for batch review                 │  |
|  │ • End-of-session: "Auto-fixed 2, need review on 3"          │  |
|  │ • Human reviews non-trivial issues                           │  |
|  │ • Can batch-fix via orchestrator workflow                    │  |
|  └─────────────────────────────────────────────────────────────┘  |
|                              ↓                                     |
|  WEEK 3+: FULL AUTONOMY (with gates)                              |
|  ┌─────────────────────────────────────────────────────────────┐  |
|  │ • MODERATE category auto-fixed (higher threshold)            │  |
|  │ • RISKY always requires human review                         │  |
|  │ • Dashboard shows: "12 auto-fixes this week, 0 reverts"     │  |
|  │ • Kill switch available: `touch .healing_lock`              │  |
|  └─────────────────────────────────────────────────────────────┘  |
|                                                                    |
+------------------------------------------------------------------+
```

### 12.2 Session Flow (What Actually Happens)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TYPICAL WORKFLOW SESSION                          │
└─────────────────────────────────────────────────────────────────────┘

1. START SESSION
   $ orchestrator start "Implement feature X"

2. WORKFLOW EXECUTES (PLAN → EXECUTE → REVIEW → VERIFY)
   ┌────────────────────────────────────────────────────────────────┐
   │  During workflow, issues are SILENTLY CAPTURED:                 │
   │                                                                 │
   │  [Issue #1] TypeError in tests/test_api.py:45                  │
   │  [Issue #2] Process: Skipped security review (time pressure)   │
   │  [Issue #3] Missing error handling in src/api/login.py        │
   │                                                                 │
   │  ⚠️  NO NOTIFICATIONS OR INTERRUPTIONS                         │
   │  User focuses on their task                                     │
   └────────────────────────────────────────────────────────────────┘

3. LEARN PHASE TRIGGERS END-OF-SESSION REVIEW
   ┌────────────────────────────────────────────────────────────────┐
   │  $ orchestrator issues                                          │
   │                                                                 │
   │  ╭──────────────────────────────────────────────────────────╮  │
   │  │  SESSION ISSUES (3 found)                                 │  │
   │  ├──────────────────────────────────────────────────────────┤  │
   │  │                                                           │  │
   │  │  ✅ AUTO-FIXED (1):                                       │  │
   │  │     #1 [CODE] TypeError - missing return type             │  │
   │  │        Fixed: Added -> Optional[str] to function sig      │  │
   │  │                                                           │  │
   │  │  ⏳ NEED REVIEW (2):                                       │  │
   │  │     #2 [PROCESS] Security review skipped                  │  │
   │  │        Suggestion: Add to next session checklist          │  │
   │  │                                                           │  │
   │  │     #3 [CODE] Missing error handling (5 locations)        │  │
   │  │        Suggestion: Batch fix via orchestrator             │  │
   │  │        Confidence: 78% | Files: 3 | Est. lines: 45       │  │
   │  │                                                           │  │
   │  ╰──────────────────────────────────────────────────────────╯  │
   └────────────────────────────────────────────────────────────────┘

4. USER ACTIONS
   # Accept suggestions as-is
   $ orchestrator issues apply 1-2

   # Batch fix non-trivial issues via orchestrator (controlled)
   $ orchestrator issues fix --batch
   → Starts new orchestrator workflow for fixes
   → Root cause investigation in PLAN phase
   → Multi-model review before apply

   # Defer issues to next session
   $ orchestrator issues defer 3 --reason "Will address in refactor sprint"

   # Dismiss false positives
   $ orchestrator issues dismiss 4 --reason "Intentional behavior"
```

### 12.3 Key UX Principles

| Principle | Implementation |
|-----------|----------------|
| **No mid-workflow interruptions** | Issues queue silently, review at end |
| **Batch for efficiency** | Group related issues, fix together |
| **Orchestrator for control** | Non-trivial fixes run as full workflow |
| **Deferred issues carry over** | Unaddressed issues appear next session |
| **Always show confidence** | Users see why system is/isn't confident |
| **Human precedent visible** | "Based on 3 previous human fixes" |

---

## 13. Issue Metadata (Descriptive, Not Routing)

### 13.1 Issue Categories as Metadata

Issue types are captured as **descriptive metadata** for analytics and reporting, NOT as a routing mechanism. The system does NOT use a rigid enum because:

1. **Issue type doesn't determine fixability** - a CODE issue might be trivial or complex
2. **Routing by safety_category is more reliable** - based on the fix, not the error
3. **Freeform labels are more flexible** - auto-detected from error content

```python
# OLD approach (removed):
# class IssueType(str, Enum):
#     CODE = "code"
#     PROCESS = "process"
#     ...

# NEW approach: Descriptive metadata, auto-detected
@dataclass
class IssueMetadata:
    """Descriptive metadata for analytics (not routing)."""

    # Auto-detected from error content (freeform string)
    category: str  # e.g., "syntax_error", "import_missing", "test_failure"

    # Broader grouping for analytics dashboards
    group: str  # e.g., "code", "environment", "workflow"

    # Tags for flexible filtering
    tags: list[str]  # e.g., ["python", "tests", "ci"]


def auto_detect_metadata(error: ErrorEvent) -> IssueMetadata:
    """Auto-detect issue metadata from error content."""

    # Detect category from error type
    category = "unknown"
    if "import" in error.description.lower():
        category = "import_error"
    elif "syntax" in error.description.lower():
        category = "syntax_error"
    elif "test" in error.description.lower() or "assert" in error.description.lower():
        category = "test_failure"
    elif "permission" in error.description.lower():
        category = "permission_error"
    elif "connection" in error.description.lower():
        category = "connection_error"
    else:
        # Extract from error type if available
        category = error.error_type.lower() if error.error_type else "unknown"

    # Detect group
    group = "code"  # Default
    if category in ["import_error", "syntax_error", "type_error", "test_failure"]:
        group = "code"
    elif category in ["permission_error", "connection_error", "env_var_missing"]:
        group = "environment"
    elif "workflow" in error.source or "phase" in error.source:
        group = "workflow"

    # Auto-tag based on content
    tags = []
    if ".py" in (error.file_path or ""):
        tags.append("python")
    if ".ts" in (error.file_path or "") or ".js" in (error.file_path or ""):
        tags.append("javascript")
    if "test" in (error.file_path or "").lower():
        tags.append("tests")

    return IssueMetadata(category=category, group=group, tags=tags)
```

### 13.2 What Drives Routing (Not Issue Type)

Routing decisions are based on the **fix characteristics**, not the issue type:

| Routing Factor | What It Determines |
|----------------|-------------------|
| **safety_category** | SAFE/MODERATE/RISKY → judge count, auto-apply eligibility |
| **confidence** | Pattern match quality → suggest vs auto-apply threshold |
| **verified_count** | Track record → graduation to AUTOMATED state |
| **file_path** | Protected paths → always queue for review |

```python
def should_auto_apply(issue: IssueEvent, fix: SuggestedFix) -> tuple[bool, str]:
    """
    Determine if fix should auto-apply. Based on FIX properties, not issue type.

    OLD (removed): if issue.issue_type == IssueType.CODE: ...
    NEW: Route by safety_category + confidence + precedent
    """

    # Safety category determines judge count and eligibility
    if fix.safety_category == SafetyCategory.RISKY:
        return False, "RISKY category - queued for review"

    # Confidence must be high enough
    if fix.confidence < 0.7:
        return False, f"Low confidence ({fix.confidence:.2f})"

    # Pattern must have precedent (pre-seeded, verified AI, or human)
    if not fix.pattern.has_precedent:
        return False, "No precedent - pattern needs verification"

    # Protected paths never auto-apply
    if is_protected_path(issue.file_path):
        return False, f"Protected path: {issue.file_path}"

    return True, "Eligible for auto-apply"
```

### 13.3 Issue Groups for Analytics

The variety of issues is still captured for dashboards and reporting:

```
+------------------------------------------------------------------+
|                   ISSUE GROUPS (for analytics)                     |
+------------------------------------------------------------------+
|                                                                    |
|  CODE                               ENVIRONMENT                    |
|  ├── syntax_error                   ├── import_missing             |
|  ├── type_error                     ├── env_var_missing            |
|  ├── test_failure                   ├── permission_denied          |
|  ├── assertion_error                ├── connection_refused         |
|  └── runtime_error                  └── version_mismatch           |
|                                                                    |
|  WORKFLOW                           KNOWLEDGE                      |
|  ├── phase_skipped                  ├── convention_unknown         |
|  ├── review_bypassed                ├── api_undocumented           |
|  ├── test_coverage_low              └── context_missing            |
|  └── deadline_missed                                               |
|                                                                    |
+------------------------------------------------------------------+
```

**Analytics queries example:**
```sql
-- Issues by group (last 30 days)
SELECT
    metadata->>'group' as issue_group,
    COUNT(*) as count
FROM issues
WHERE created_at > now() - interval '30 days'
GROUP BY metadata->>'group';

-- Most common categories
SELECT
    metadata->>'category' as category,
    COUNT(*) as count,
    AVG(resolution_time_seconds) as avg_resolution
FROM issues
WHERE resolved_at IS NOT NULL
GROUP BY metadata->>'category'
ORDER BY count DESC
LIMIT 10;
```

### 13.4 Simplified IssueEvent

```python
@dataclass
class IssueEvent:
    """Unified issue event. Type is metadata, not routing logic."""

    issue_id: str
    timestamp: datetime
    workflow_id: str

    # Routing factors (used for decisions)
    severity: Severity              # critical, high, medium, low
    safety_category: SafetyCategory # SAFE, MODERATE, RISKY
    confidence: float               # 0.0 - 1.0

    # Detection source
    detected_from: Literal[
        "workflow_log",             # Phase/item failures
        "transcript",               # Session transcript parsing
        "subprocess",               # Command exit codes
        "hook",                     # Real-time workflow hooks
    ]

    # Issue details
    title: str                      # Short description
    description: str                # Full context
    file_path: Optional[str]        # For file-specific issues
    error_fingerprint: Optional[str]  # For deduplication

    # Metadata (for analytics, NOT routing)
    metadata: IssueMetadata         # Auto-detected category, group, tags

    # Suggested resolution
    suggested_fix: Optional[SuggestedFix]

    # Lifecycle
    status: IssueStatus             # new, reviewed, fixed, deferred, dismissed
    deferred_until: Optional[datetime]
    resolution_workflow_id: Optional[str]  # If fixed via orchestrator
```

### 13.4 Type-Specific Handling

| Issue Type | Auto-Fix Eligible | Typical Resolution | Review Required |
|------------|-------------------|-------------------|-----------------|
| CODE (SAFE) | ✅ Yes | Git branch commit | Multi-model |
| CODE (RISKY) | ❌ No | Orchestrator workflow | Human + multi-model |
| PROCESS | ❌ No | Workflow YAML update | Human |
| PROMPT | ❌ No | CLAUDE.md update | Human |
| ENVIRONMENT | ⚠️ Limited | Shell commands | Human for deps |
| KNOWLEDGE_GAP | ❌ No | Documentation update | Human |

---

## 14. Issue Queue & Batching

### 14.1 Silent Accumulation During Workflow

Issues are captured continuously but **never interrupt** the active workflow:

```python
class IssueQueue:
    """
    Accumulates issues during workflow, presents at end.

    Key principle: NEVER interrupt mid-workflow.
    Claude often abridges long notifications or scrolls past them.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.issues: list[IssueEvent] = []
        self._auto_fixed: list[IssueEvent] = []
        self._deferred_from_previous: list[IssueEvent] = []

    def add_issue(self, issue: IssueEvent) -> None:
        """Add issue silently - NO notification."""
        self.issues.append(issue)

        # Check if trivial auto-fix eligible
        if self._can_auto_fix(issue):
            self._attempt_auto_fix(issue)

    def _can_auto_fix(self, issue: IssueEvent) -> bool:
        """Check all gates for auto-fix eligibility."""
        return (
            issue.issue_type == IssueType.CODE and
            issue.suggested_fix and
            issue.suggested_fix.safety_category == SafetyCategory.SAFE and
            issue.confidence >= 0.7 and
            self._has_human_precedent(issue.error_fingerprint) and
            not check_kill_switch()
        )

    def get_session_summary(self) -> SessionIssueSummary:
        """Called at end of session (LEARN phase)."""
        return SessionIssueSummary(
            auto_fixed=self._auto_fixed,
            need_review=[i for i in self.issues if i.status == IssueStatus.NEW],
            deferred=self._deferred_from_previous,
            total=len(self.issues),
        )
```

### 14.2 End-of-Session Review

```
+------------------------------------------------------------------+
|                    END-OF-SESSION REVIEW                           |
+------------------------------------------------------------------+
|                                                                    |
|  Triggered by: LEARN phase completion                              |
|                                                                    |
|  $ orchestrator issues                                             |
|                                                                    |
|  ┌──────────────────────────────────────────────────────────────┐ |
|  │  SESSION SUMMARY                                              │ |
|  │  ═══════════════════════════════════════════════════════════ │ |
|  │                                                               │ |
|  │  This Session:                                                │ |
|  │    • Auto-fixed: 2 (imports, type hints)                     │ |
|  │    • Need review: 3                                           │ |
|  │    • Carried over: 1 (from previous session)                 │ |
|  │                                                               │ |
|  │  ───────────────────────────────────────────────────────────  │ |
|  │                                                               │ |
|  │  NEED REVIEW:                                                 │ |
|  │                                                               │ |
|  │  [1] CODE: Missing error handling in api/auth.py             │ |
|  │      Confidence: 82% | Files: 2 | Lines: ~25                 │ |
|  │      Pattern: "try/except for external calls"                │ |
|  │      Precedent: 5 human fixes for similar pattern            │ |
|  │                                                               │ |
|  │  [2] PROCESS: Security review skipped                        │ |
|  │      Recommendation: Add to next session checklist           │ |
|  │                                                               │ |
|  │  [3] KNOWLEDGE_GAP: Unknown caching behavior                 │ |
|  │      Recommendation: Document in ARCHITECTURE.md             │ |
|  │                                                               │ |
|  │  [4] CODE (carried over): Deprecated API usage              │ |
|  │      Deferred: 2 sessions ago                                 │ |
|  │      Recommendation: Batch with other modernization          │ |
|  │                                                               │ |
|  └──────────────────────────────────────────────────────────────┘ |
|                                                                    |
|  ACTIONS:                                                          |
|    orchestrator issues apply 1       # Apply single fix           |
|    orchestrator issues fix --batch   # Fix all via orchestrator   |
|    orchestrator issues defer 2-3     # Defer to next session      |
|    orchestrator issues dismiss 4     # Dismiss (false positive)   |
|                                                                    |
+------------------------------------------------------------------+
```

### 14.3 Issue Carry-Over Mechanism

Unaddressed issues persist across sessions:

```python
@dataclass
class IssueCarryOver:
    """Persist unaddressed issues to next session."""

    storage_file: Path = Path(".claude/issue_queue.jsonl")

    def defer_issue(
        self,
        issue: IssueEvent,
        reason: str,
        until: Optional[datetime] = None
    ) -> None:
        """Defer issue to future session."""
        issue.status = IssueStatus.DEFERRED
        issue.deferred_reason = reason
        issue.deferred_until = until or datetime.utcnow() + timedelta(days=7)
        issue.deferred_count = getattr(issue, 'deferred_count', 0) + 1
        self._persist(issue)

    def get_carried_over(self) -> list[IssueEvent]:
        """Get issues deferred from previous sessions."""
        issues = self._load_all()
        now = datetime.utcnow()
        return [
            i for i in issues
            if i.status == IssueStatus.DEFERRED
            and (i.deferred_until is None or i.deferred_until <= now)
        ]

    def escalate_stale_issues(self) -> list[IssueEvent]:
        """
        Flag issues deferred too many times.

        After 3 deferrals, issue becomes "stale" and gets highlighted.
        """
        issues = self._load_all()
        return [i for i in issues if i.deferred_count >= 3]
```

### 14.4 Batch Fix via Orchestrator

For non-trivial fixes, use orchestrator for control:

```bash
# Batch fix creates a new orchestrator workflow
$ orchestrator issues fix --batch

Starting batch fix workflow for 3 issues:
  [1] CODE: Missing error handling (api/auth.py, api/users.py)
  [2] CODE: Deprecated API usage (lib/cache.py)
  [3] CODE: Type inconsistencies (models/*.py)

Creating workflow: "Batch fix: error handling, API updates, type fixes"

→ PLAN phase: Root cause investigation for each issue
→ EXECUTE phase: Apply fixes on branch
→ REVIEW phase: Multi-model review of all changes
→ VERIFY phase: Build + test + lint
→ LEARN phase: Update patterns from successful fixes

Proceed? [Y/n]
```

### 14.5 CLI Commands

```bash
# List all issues (current session + carried over)
orchestrator issues

# Show detailed view of specific issue
orchestrator issues show 3

# Apply suggested fix for trivial issue
orchestrator issues apply 1

# Batch fix via orchestrator workflow (non-trivial)
orchestrator issues fix --batch
orchestrator issues fix --batch --include 1,2,5  # Specific issues

# Defer to next session
orchestrator issues defer 3 --reason "Will address in refactor"
orchestrator issues defer 3 --until "2026-01-20"  # Specific date

# Dismiss false positive
orchestrator issues dismiss 4 --reason "Intentional behavior"

# See stale issues (deferred 3+ times)
orchestrator issues stale

# Clear all issues (with confirmation)
orchestrator issues clear --confirm
```

---

## 15. How Fixes Are Applied

### 15.1 Fix Types by Issue Category

Different issue types require different fix mechanisms:

```
+------------------------------------------------------------------+
|                    FIX APPLICATION METHODS                         |
+------------------------------------------------------------------+
|                                                                    |
|  CODE ISSUES → Git Branch Commits                                  |
|  ┌────────────────────────────────────────────────────────────┐   |
|  │  1. Create branch: fix/auto-{fingerprint-short}            │   |
|  │  2. Apply code changes (via Edit tool)                     │   |
|  │  3. Run verification (build + test + lint)                 │   |
|  │  4. If pass → Merge to working branch                      │   |
|  │  5. If fail → Revert, log failure, quarantine pattern     │   |
|  └────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  ENVIRONMENT ISSUES → Shell Commands                               |
|  ┌────────────────────────────────────────────────────────────┐   |
|  │  1. Verify command safety (no rm -rf, etc.)               │   |
|  │  2. Execute command (pip install, npm install, etc.)       │   |
|  │  3. Verify success (exit code 0)                           │   |
|  │  4. Update requirements.txt/package.json if needed         │   |
|  │  5. Commit dependency changes                               │   |
|  └────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  PROCESS ISSUES → Workflow YAML Updates                            |
|  ┌────────────────────────────────────────────────────────────┐   |
|  │  1. Identify missing checklist items                        │   |
|  │  2. Propose workflow.yaml changes                           │   |
|  │  3. Human approves (always requires human)                  │   |
|  │  4. Update workflow.yaml                                     │   |
|  │  5. Commit changes                                           │   |
|  └────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  PROMPT ISSUES → CLAUDE.md / Workflow Prompt Updates               |
|  ┌────────────────────────────────────────────────────────────┐   |
|  │  1. Identify prompt causing poor output                     │   |
|  │  2. Propose updated prompt/instruction                      │   |
|  │  3. Human approves (always requires human)                  │   |
|  │  4. Update CLAUDE.md or workflow prompt template           │   |
|  │  5. Commit changes                                           │   |
|  └────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  KNOWLEDGE GAP ISSUES → Documentation Updates                      |
|  ┌────────────────────────────────────────────────────────────┐   |
|  │  1. Identify missing knowledge                              │   |
|  │  2. Draft documentation (LEARNINGS.md, ARCHITECTURE.md)    │   |
|  │  3. Human reviews and refines                               │   |
|  │  4. Add to appropriate documentation file                   │   |
|  │  5. Commit changes                                           │   |
|  └────────────────────────────────────────────────────────────┘   |
|                                                                    |
+------------------------------------------------------------------+
```

### 15.2 Code Fix Application (Detailed)

```python
@dataclass
class CodeFixApplicator:
    """Apply code fixes on isolated git branches."""

    branch_prefix: str = "fix/auto-"

    async def apply_fix(
        self,
        issue: IssueEvent,
        fix: SuggestedFix
    ) -> FixResult:
        """
        Apply a code fix with full safety gates.

        Returns FixResult with success/failure and details.
        """
        # 1. Pre-flight checks
        if check_kill_switch():
            return FixResult(success=False, reason="Kill switch active")

        violations = hard_constraints.validate(fix.diff, fix.files)
        if violations:
            return FixResult(success=False, reason=f"Constraint violation: {violations}")

        # 2. Create isolated branch
        branch_name = f"{self.branch_prefix}{issue.error_fingerprint[:8]}"
        run(f"git checkout -b {branch_name}")

        try:
            # 3. Apply changes
            for file_change in fix.file_changes:
                apply_edit(file_change.path, file_change.old, file_change.new)

            # 4. Run verification
            if not await self._verify(fix):
                raise VerificationFailed()

            # 5. Multi-model validation
            validation = await multi_model_validator.validate(fix, issue)
            if not validation.approved:
                raise ValidationFailed(validation)

            # 6. Commit and merge
            run(f"git add -A && git commit -m 'fix: {issue.title}'")
            run("git checkout - && git merge --no-ff {branch_name}")

            # 7. Record success in pattern memory
            pattern_memory.record_success(issue.error_fingerprint, fix)

            return FixResult(
                success=True,
                branch=branch_name,
                commit=get_commit_hash(),
                validation=validation,
            )

        except Exception as e:
            # Revert on any failure
            run("git checkout -")
            run(f"git branch -D {branch_name}")

            # Quarantine pattern if it keeps failing
            pattern_memory.record_failure(issue.error_fingerprint, str(e))

            return FixResult(success=False, reason=str(e))
```

### 15.3 Environment Fix Application

```python
@dataclass
class EnvironmentFixApplicator:
    """Apply environment/dependency fixes via shell commands."""

    # Safe commands that can be auto-executed
    safe_commands: set = field(default_factory=lambda: {
        "pip install",
        "npm install",
        "yarn add",
        "cargo add",
        "go get",
    })

    # Commands that require human approval
    dangerous_patterns: list = field(default_factory=lambda: [
        r"rm\s+-rf",
        r"sudo\s+",
        r"chmod\s+777",
        r">\s+/",
    ])

    def apply_fix(self, issue: IssueEvent, fix: SuggestedFix) -> FixResult:
        """Apply environment fix with safety checks."""

        command = fix.command

        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command):
                return FixResult(
                    success=False,
                    reason=f"Dangerous command pattern: {pattern}",
                    requires_human=True,
                )

        # Check if command is in safe list
        if not any(command.startswith(safe) for safe in self.safe_commands):
            return FixResult(
                success=False,
                reason="Command not in safe list",
                requires_human=True,
            )

        # Execute command
        result = subprocess.run(command, shell=True, capture_output=True)

        if result.returncode != 0:
            return FixResult(
                success=False,
                reason=f"Command failed: {result.stderr}",
            )

        return FixResult(success=True, output=result.stdout)
```

### 15.4 Fix Verification Pipeline

All fixes go through verification before being accepted:

```
FIX CANDIDATE
      |
      v
+-------------------+
| 1. BUILD CHECK    |  pytest/npm test/cargo build
+-------------------+
      |
      v
+-------------------+
| 2. TEST CHECK     |  Run related tests
+-------------------+
      |
      v
+-------------------+
| 3. LINT CHECK     |  ruff/eslint/clippy
+-------------------+
      |
      v
+-------------------+
| 4. TYPE CHECK     |  mypy/tsc
+-------------------+
      |
      v
+-------------------+
| 5. MULTI-MODEL    |  2/3 models approve
|    VALIDATION     |  (different from fixer)
+-------------------+
      |
      v
   [ACCEPT/REJECT]
```

---

## 16. Root Cause Investigation

### 16.1 When Does Investigation Happen?

Root cause investigation occurs in the **PLAN phase** of a fix workflow:

```
Issue Detected → Queued → Batch Fix Selected → PLAN Phase
                                                    ↓
                                          Root Cause Investigation
                                                    ↓
                                          Fix Strategy Decision
                                                    ↓
                                          EXECUTE → REVIEW → VERIFY
```

### 16.2 Investigation Process

```python
@dataclass
class RootCauseInvestigation:
    """
    Investigate root cause before fixing.

    Happens in PLAN phase of fix workflow.
    """

    async def investigate(self, issue: IssueEvent) -> InvestigationResult:
        """
        Determine root cause and best fix strategy.

        Returns:
            InvestigationResult with root_cause, confidence, and strategy
        """

        # 1. Gather context
        context = await self._gather_context(issue)

        # 2. Check pattern memory for similar issues
        similar = pattern_memory.find_similar(issue.error_fingerprint)

        # 3. Analyze based on issue type
        if issue.issue_type == IssueType.CODE:
            return await self._investigate_code_issue(issue, context, similar)
        elif issue.issue_type == IssueType.PROCESS:
            return await self._investigate_process_issue(issue, context)
        elif issue.issue_type == IssueType.PROMPT:
            return await self._investigate_prompt_issue(issue, context)
        # ... etc

    async def _investigate_code_issue(
        self,
        issue: IssueEvent,
        context: IssueContext,
        similar: list[PatternMatch]
    ) -> InvestigationResult:
        """Deep investigation of code issue."""

        # Determine if this is symptom or root cause
        questions = [
            "Is this error a symptom of a deeper issue?",
            "Are there similar errors in related files?",
            "Was this working before? What changed?",
            "Is this a type mismatch, logic error, or missing handling?",
        ]

        # Use code analysis
        analysis = await self._analyze_code(
            file=issue.file_path,
            error=issue.description,
            stack_trace=issue.stack_trace,
        )

        return InvestigationResult(
            root_cause=analysis.root_cause,
            confidence=analysis.confidence,
            is_symptom=analysis.is_symptom,
            related_issues=analysis.related,
            recommended_strategy=self._determine_strategy(analysis),
            investigation_notes=analysis.notes,
        )

    def _determine_strategy(self, analysis: CodeAnalysis) -> FixStrategy:
        """Determine the best fix strategy based on investigation."""

        if analysis.is_symptom:
            # Fix the root cause, not the symptom
            return FixStrategy.FIX_ROOT_CAUSE

        if len(analysis.related) > 3:
            # Multiple related issues - do batch refactor
            return FixStrategy.BATCH_REFACTOR

        if analysis.confidence < 0.6:
            # Low confidence - need human review
            return FixStrategy.HUMAN_REVIEW

        return FixStrategy.DIRECT_FIX
```

### 16.3 Investigation Output in PLAN Phase

When a batch fix workflow runs, the PLAN phase includes investigation:

```
$ orchestrator issues fix --batch

Starting batch fix workflow...

════════════════════════════════════════════════════════════════
PLAN PHASE: Root Cause Investigation
════════════════════════════════════════════════════════════════

Issue #1: TypeError in api/auth.py:45
┌────────────────────────────────────────────────────────────────┐
│ Investigation Results:                                          │
│                                                                 │
│ Root Cause: Missing Optional type annotation                   │
│ Confidence: 94%                                                │
│                                                                 │
│ Analysis:                                                       │
│   - Function returns None when user not found                  │
│   - Return type annotated as User (not Optional[User])        │
│   - Caller assumes non-null, causing TypeError                 │
│                                                                 │
│ Related Issues: None found                                      │
│                                                                 │
│ Recommended Strategy: DIRECT_FIX                               │
│   - Add Optional[User] return type                             │
│   - Update callers to handle None case                         │
│   - Est. changes: 2 files, 8 lines                             │
└────────────────────────────────────────────────────────────────┘

Issue #2: Deprecated API usage in lib/cache.py
┌────────────────────────────────────────────────────────────────┐
│ Investigation Results:                                          │
│                                                                 │
│ Root Cause: Using redis.StrictRedis (deprecated)              │
│ Confidence: 98%                                                │
│                                                                 │
│ Analysis:                                                       │
│   - StrictRedis deprecated in redis-py 4.0                    │
│   - Should use redis.Redis instead                             │
│   - Found 5 other files with same pattern                      │
│                                                                 │
│ Related Issues:                                                 │
│   - lib/session.py:23 (same pattern)                          │
│   - lib/rate_limit.py:45 (same pattern)                       │
│                                                                 │
│ Recommended Strategy: BATCH_REFACTOR                           │
│   - Update all 6 files together                                │
│   - Est. changes: 6 files, 12 lines                            │
└────────────────────────────────────────────────────────────────┘

Proceed with fixes? [Y/n/edit]
```

---

## 17. Learnings Architecture (Supabase: RAG + Graph + Relational)

### 17.1 Design Decision: Supabase as Unified Backend

We use **Supabase** (PostgreSQL) as a unified backend providing three capabilities:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SUPABASE ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │   RELATIONAL    │  │   VECTOR/RAG    │  │   GRAPH-LIKE    │     │
│  │   (Native PG)   │  │   (pgvector)    │  │ (Recursive CTE) │     │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘     │
│           │                    │                    │               │
│           └────────────────────┼────────────────────┘               │
│                                │                                     │
│                    ┌───────────▼───────────┐                        │
│                    │      PostgreSQL        │                        │
│                    │    (Single Source)     │                        │
│                    └───────────────────────┘                        │
│                                                                      │
│  Benefits:                                                           │
│  • Already in use ✓                                                 │
│  • No new infrastructure                                             │
│  • Row-Level Security (multi-project isolation)                     │
│  • Predictable cost (~$25/mo Pro tier)                              │
│  • Edge Functions for auto-embedding                                │
│  • Real-time subscriptions (live issue notifications)               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Why Supabase over alternatives:**

| Feature | MongoDB Atlas | Supabase | Our Choice |
|---------|---------------|----------|------------|
| Embedding Generation | Fully native | Edge Functions + triggers | Supabase ✓ |
| Reranking | Native Voyage AI | External (Cohere) | Supabase (simpler) |
| Security | RBAC | Row-Level Security (RLS) | Supabase ✓ (superior) |
| Graph Queries | $graphLookup | Recursive CTEs | Supabase ✓ |
| Pricing | Usage-based (scales high) | Predictable monthly | Supabase ✓ |
| Already Using | No | Yes | Supabase ✓ |

### 17.2 Database Schema

```sql
-- Enable pgvector extension
create extension if not exists vector;

-- ============================================
-- CORE TABLES
-- ============================================

-- Learnings with vector embeddings for RAG
create table learnings (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz default now(),
    updated_at timestamptz default now(),

    -- Identity
    project_id uuid references projects(id),  -- Multi-project support
    workflow_id text,

    -- Classification
    type text check (type in ('error_resolution', 'process', 'prevention', 'knowledge')),
    category text,  -- 'import_error', 'type_error', etc.

    -- The learning itself
    title text not null,
    description text,
    trigger_conditions jsonb,  -- Structured trigger definition
    action jsonb,              -- What to do when triggered

    -- RAG: Vector embedding for semantic search
    embedding vector(1536),    -- OpenAI ada-002 dimensions

    -- Evidence & scoring
    occurrences int default 1,
    success_rate float default 1.0,
    confidence float default 0.5,

    -- Lifecycle
    lifecycle text default 'proposed'
        check (lifecycle in ('proposed', 'accepted', 'shadow', 'automated', 'deprecated')),

    -- Provenance
    source text check (source in ('human', 'ai', 'correction')),
    has_human_precedent boolean default false
);

-- Index for vector similarity search
create index on learnings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- ============================================
-- ISSUE QUEUE
-- ============================================

create table issues (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz default now(),

    -- Identity
    project_id uuid references projects(id),
    workflow_id text,
    session_id text,

    -- Classification
    issue_type text check (issue_type in ('code', 'process', 'prompt', 'environment', 'knowledge_gap')),
    severity text check (severity in ('critical', 'high', 'medium', 'low')),

    -- Details
    title text not null,
    description text,
    file_path text,
    error_fingerprint text,

    -- For semantic search
    embedding vector(1536),

    -- Suggested fix (from pattern match or RAG)
    suggested_fix jsonb,
    confidence float,
    matched_learning_id uuid references learnings(id),

    -- Lifecycle
    status text default 'pending'
        check (status in ('pending', 'selected', 'in_progress', 'resolved', 'deferred', 'dismissed')),
    deferred_count int default 0,
    deferred_until timestamptz,
    resolution_notes text,

    -- Tracking
    detected_from text,  -- 'workflow_log', 'transcript', 'subprocess', 'hook'
    resolved_at timestamptz,
    resolved_by_workflow_id text
);

-- ============================================
-- ERROR PATTERNS (Fast exact-match lookup)
-- ============================================

create table error_patterns (
    id uuid primary key default gen_random_uuid(),

    -- The fingerprint for exact matching
    fingerprint text unique not null,

    -- Link to learning
    learning_id uuid references learnings(id),

    -- Stats for auto-apply decisions
    use_count int default 0,
    success_count int default 0,
    last_used_at timestamptz,

    -- Safety
    safety_category text check (safety_category in ('safe', 'moderate', 'risky')),
    has_human_precedent boolean default false,
    quarantined boolean default false,
    quarantined_until timestamptz
);

-- Fast fingerprint lookup
create index on error_patterns(fingerprint);

-- ============================================
-- GRAPH: Error → Change Relationships
-- ============================================

create table error_causes (
    id uuid primary key default gen_random_uuid(),

    error_fingerprint text not null,
    caused_by_file text not null,
    caused_by_change_type text,  -- 'added', 'modified', 'deleted'

    occurrence_count int default 1,
    confidence float default 0.5,

    created_at timestamptz default now(),
    last_seen_at timestamptz default now()
);

-- For graph traversal queries
create index on error_causes(error_fingerprint);
create index on error_causes(caused_by_file);

-- ============================================
-- CORRECTIONS (Human overrides - highest value signal)
-- ============================================

create table corrections (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz default now(),

    -- What AI suggested
    ai_suggestion jsonb,
    ai_pattern_fingerprint text,

    -- What human did instead
    human_action jsonb,
    human_diff text,

    -- Context
    error_fingerprint text,
    workflow_id text,

    -- Classification
    correction_type text check (correction_type in ('rejected', 'modified', 'replaced'))
);
```

### 17.3 Three-Tier Lookup Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THREE-TIER LOOKUP FLOW                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ERROR OCCURS                                                        │
│       │                                                              │
│       v                                                              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ TIER 1: Pattern Memory (exact fingerprint match)            │    │
│  │ Query: SELECT * FROM error_patterns WHERE fingerprint = $1  │    │
│  │ Latency: ~10ms                                              │    │
│  │ Use: Known errors with proven fixes                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│       │ No match?                                                    │
│       v                                                              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ TIER 2: RAG Semantic Search (pgvector)                      │    │
│  │ Query: SELECT * FROM learnings ORDER BY embedding <=> $1    │    │
│  │ Latency: ~100ms                                             │    │
│  │ Use: Similar-but-not-identical errors                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│       │ Found similar?                                               │
│       v                                                              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ TIER 3: Graph Causality (temporal + dependency analysis)    │    │
│  │ Query: Explicit causality edges, not string matching        │    │
│  │ Latency: ~50ms                                              │    │
│  │ Use: Root cause investigation in PLAN phase                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│       │                                                              │
│       v                                                              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ FIX APPLICATION                                              │    │
│  │ • Auto-apply if SAFE + verified precedent + confidence ≥0.7 │    │
│  │ • Queue RISKY category for review                           │    │
│  │ • Record result back to Supabase + local cache              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 17.4 Key Queries

**Tier 1: Fast exact-match lookup**
```sql
-- Check if we have a known fix for this fingerprint
-- Updated: Uses has_precedent (any type) instead of has_human_precedent
select
    ep.*,
    l.action,
    l.confidence,
    l.title
from error_patterns ep
join learnings l on l.id = ep.learning_id
where ep.fingerprint = $1
  and ep.quarantined = false
  and (ep.is_preseeded = true
       or ep.verified_apply_count >= 5
       or ep.human_correction_count >= 1)  -- Any form of precedent
  and (ep.success_count::float / nullif(ep.use_count, 0)) >= 0.9;
```

**Tier 2: RAG semantic search**
```sql
-- Find semantically similar learnings when no exact match
select
    id, title, description, action, confidence,
    1 - (embedding <=> $1) as similarity  -- $1 = embedding of current error
from learnings
where lifecycle in ('active', 'automated')  -- Updated lifecycle states
  and project_id = $2
order by embedding <=> $1
limit 5;
```

**Tier 3: Graph causality analysis (FIXED)**

The previous CTE used substring matching (`like '%' || cc.file || '%'`) which is NOT causality. Here's the correct approach using explicit causality edges:

```sql
-- Schema for explicit causality tracking
create table causality_edges (
    id uuid primary key default gen_random_uuid(),

    -- The error that occurred
    error_fingerprint text not null,
    error_timestamp timestamptz not null,

    -- The change that likely caused it
    causing_commit text not null,          -- Git commit hash
    causing_file text not null,            -- File that was changed
    causing_function text,                 -- Function if identifiable

    -- Evidence for causality (how we determined this link)
    evidence_type text check (evidence_type in (
        'temporal',     -- Error appeared within N commits of change
        'git_blame',    -- Git blame shows recent change at error location
        'dependency',   -- File imports/depends on changed file
        'cascade',      -- Fix A caused Error B (detected by CascadeDetector)
        'manual'        -- Human explicitly linked
    )),

    -- Confidence and tracking
    confidence float default 0.5,
    occurrence_count int default 1,
    last_seen timestamptz default now(),

    -- Constraints
    unique(error_fingerprint, causing_commit, causing_file)
);

create index on causality_edges(error_fingerprint);
create index on causality_edges(causing_file);
create index on causality_edges(causing_commit);
```

**Correct causality query:**
```sql
-- What changes typically cause this error?
-- Uses explicit causality edges, not string matching
with recursive cause_chain as (
    -- Level 0: Direct causes of this error
    select
        ce.causing_file as file,
        ce.causing_commit as commit,
        ce.evidence_type,
        ce.confidence,
        ce.occurrence_count,
        0 as depth
    from causality_edges ce
    where ce.error_fingerprint = $1

    union all

    -- Level 1+: What caused changes to those files? (transitive)
    select
        ce2.causing_file,
        ce2.causing_commit,
        ce2.evidence_type,
        ce2.confidence * 0.7,  -- Decay confidence with depth
        ce2.occurrence_count,
        cc.depth + 1
    from causality_edges ce2
    join cause_chain cc on ce2.error_fingerprint in (
        -- Find errors that occurred in the same file
        select distinct error_fingerprint
        from causality_edges
        where causing_file = cc.file
    )
    where cc.depth < 2  -- Limit transitive depth
)
select
    file,
    evidence_type,
    sum(occurrence_count) as total_occurrences,
    avg(confidence) as avg_confidence
from cause_chain
group by file, evidence_type
having sum(occurrence_count) >= 2  -- Only patterns seen multiple times
order by total_occurrences desc, avg_confidence desc
limit 10;
```

**Building causality edges (automatic):**
```python
def record_causality(error: ErrorEvent, recent_commits: list[Commit]) -> None:
    """
    Automatically build causality edges from git history.

    Called when an error is detected to link it to likely causes.
    """
    for commit in recent_commits:
        # Check temporal correlation (error within 1 hour of commit)
        if error.timestamp - commit.timestamp < timedelta(hours=1):
            for file in commit.files_changed:
                # Check if error occurred in this file or a file that imports it
                if is_related_file(error.file_path, file):
                    insert_causality_edge(
                        error_fingerprint=error.fingerprint,
                        causing_commit=commit.hash,
                        causing_file=file,
                        evidence_type="temporal",
                        confidence=0.6 if file == error.file_path else 0.4,
                    )

    # Also check git blame for the error location
    if error.file_path and error.line_number:
        blame_commit = git_blame(error.file_path, error.line_number)
        if blame_commit and is_recent(blame_commit):
            insert_causality_edge(
                error_fingerprint=error.fingerprint,
                causing_commit=blame_commit.hash,
                causing_file=error.file_path,
                evidence_type="git_blame",
                confidence=0.8,  # High confidence - direct blame
            )
```

**Analytics: Issue patterns**
```sql
-- Which issue types are we deferring most?
select
    issue_type,
    count(*) filter (where status = 'deferred') as deferred,
    count(*) filter (where status = 'resolved') as resolved,
    avg(deferred_count) as avg_deferrals
from issues
where created_at > now() - interval '30 days'
group by issue_type
order by deferred desc;
```

### 17.5 Auto-Embedding via Edge Function

```typescript
// supabase/functions/embed-learning/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

serve(async (req) => {
  const { record, type } = await req.json()

  // Generate embedding via OpenAI
  const embeddingResponse = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${Deno.env.get("OPENAI_API_KEY")}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-ada-002",
      input: `${record.title} ${record.description}`,
    }),
  })

  const { data } = await embeddingResponse.json()
  const embedding = data[0].embedding

  // Update the record with embedding
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
  )

  await supabase
    .from(type === 'learning' ? 'learnings' : 'issues')
    .update({ embedding })
    .eq('id', record.id)

  return new Response(JSON.stringify({ success: true }))
})
```

**Database trigger to auto-embed on insert:**
```sql
-- Trigger to auto-generate embeddings on insert
create or replace function trigger_embed_learning()
returns trigger as $$
begin
  perform net.http_post(
    url := current_setting('app.supabase_url') || '/functions/v1/embed-learning',
    body := jsonb_build_object('record', new, 'type', 'learning')
  );
  return new;
end;
$$ language plpgsql;

create trigger on_learning_insert
after insert on learnings
for each row execute function trigger_embed_learning();

-- Same for issues
create trigger on_issue_insert
after insert on issues
for each row execute function trigger_embed_learning();
```

### 17.6 Python Client Integration

```python
from dataclasses import dataclass
from supabase import create_client, Client
import os

@dataclass
class SupabaseLearningsClient:
    """Client for interacting with Supabase learnings backend."""

    def __init__(self):
        self.client: Client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"]
        )

    def lookup_pattern(self, fingerprint: str) -> dict | None:
        """Tier 1: Exact fingerprint match."""
        result = self.client.table("error_patterns")\
            .select("*, learnings(*)")\
            .eq("fingerprint", fingerprint)\
            .eq("quarantined", False)\
            .eq("has_human_precedent", True)\
            .single()\
            .execute()
        return result.data if result.data else None

    def semantic_search(self, error_text: str, project_id: str, limit: int = 5) -> list[dict]:
        """Tier 2: RAG semantic search using pgvector."""
        # First, get embedding for the error
        embedding = self._get_embedding(error_text)

        # Then search using Supabase's vector similarity
        result = self.client.rpc(
            "match_learnings",
            {
                "query_embedding": embedding,
                "match_threshold": 0.7,
                "match_count": limit,
                "filter_project_id": project_id
            }
        ).execute()
        return result.data

    def get_causality_chain(self, fingerprint: str) -> list[dict]:
        """Tier 3: Graph causality via recursive CTE."""
        result = self.client.rpc(
            "get_error_causes",
            {"error_fingerprint": fingerprint}
        ).execute()
        return result.data

    def record_learning(self, learning: dict) -> str:
        """Store a new learning (embedding auto-generated via trigger)."""
        result = self.client.table("learnings")\
            .insert(learning)\
            .execute()
        return result.data[0]["id"]

    def record_correction(self, correction: dict) -> None:
        """Record when human overrides AI suggestion."""
        self.client.table("corrections")\
            .insert(correction)\
            .execute()

    def update_pattern_stats(self, fingerprint: str, success: bool) -> None:
        """Update pattern statistics after use."""
        self.client.rpc(
            "update_pattern_stats",
            {
                "p_fingerprint": fingerprint,
                "p_success": success
            }
        ).execute()

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding from OpenAI."""
        import openai
        response = openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
```

### 17.7 Supabase RPC Functions

```sql
-- Match learnings by vector similarity
create or replace function match_learnings(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    filter_project_id uuid
)
returns table (
    id uuid,
    title text,
    description text,
    action jsonb,
    confidence float,
    similarity float
)
language sql stable
as $$
    select
        learnings.id,
        learnings.title,
        learnings.description,
        learnings.action,
        learnings.confidence,
        1 - (learnings.embedding <=> query_embedding) as similarity
    from learnings
    where
        learnings.project_id = filter_project_id
        and learnings.lifecycle in ('accepted', 'automated')
        and 1 - (learnings.embedding <=> query_embedding) > match_threshold
    order by learnings.embedding <=> query_embedding
    limit match_count;
$$;

-- Update pattern statistics
create or replace function update_pattern_stats(
    p_fingerprint text,
    p_success boolean
)
returns void
language plpgsql
as $$
begin
    update error_patterns
    set
        use_count = use_count + 1,
        success_count = success_count + case when p_success then 1 else 0 end,
        last_used_at = now()
    where fingerprint = p_fingerprint;
end;
$$;

-- Get error causes (graph traversal)
create or replace function get_error_causes(error_fingerprint text)
returns table (
    file text,
    change_type text,
    total_occurrences bigint
)
language sql stable
as $$
    with recursive cause_chain as (
        select
            caused_by_file as file,
            caused_by_change_type as change_type,
            occurrence_count,
            1 as depth
        from error_causes ec
        where ec.error_fingerprint = get_error_causes.error_fingerprint

        union all

        select
            ec.caused_by_file,
            ec.caused_by_change_type,
            ec.occurrence_count,
            cc.depth + 1
        from error_causes ec
        join cause_chain cc on ec.error_fingerprint like '%' || cc.file || '%'
        where cc.depth < 3
    )
    select file, change_type, sum(occurrence_count) as total_occurrences
    from cause_chain
    group by file, change_type
    order by total_occurrences desc;
$$;
```

### 17.8 Cost Estimate

| Component | Supabase Pro | Notes |
|-----------|--------------|-------|
| Database | Included | 8GB storage |
| pgvector | Included | No extra cost |
| Edge Functions | 500K/mo free | Auto-embedding |
| Realtime | 200 concurrent | Issue notifications |
| **Subtotal** | **~$25/mo** | Already paying this |
| OpenAI embeddings | ~$5/mo | ~$0.0001 per embedding |
| **Total** | **~$30/mo** | Minimal additional cost |

### 17.9 Bonus: Real-Time Issue Notifications

Supabase provides real-time subscriptions, enabling live issue notifications:

```typescript
// Subscribe to new issues in real-time
const channel = supabase
  .channel('issues')
  .on(
    'postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'issues' },
    (payload) => {
      console.log('New issue detected:', payload.new)
      // Could trigger desktop notification, Slack message, etc.
    }
  )
  .subscribe()
```

### 17.10 Migration from Local Files

For existing `.claude/learnings.jsonl` data:

```python
def migrate_jsonl_to_supabase(jsonl_path: str, client: SupabaseLearningsClient):
    """Migrate existing JSONL learnings to Supabase."""
    import json

    with open(jsonl_path) as f:
        for line in f:
            learning = json.loads(line)

            # Transform to Supabase schema
            supabase_learning = {
                "title": learning.get("title", learning.get("learning_id")),
                "description": learning.get("narrative"),
                "type": learning.get("type", "error_resolution"),
                "category": learning.get("category"),
                "trigger_conditions": learning.get("trigger"),
                "action": learning.get("action"),
                "confidence": learning.get("confidence", 0.5),
                "lifecycle": learning.get("lifecycle", "accepted"),
                "source": "human" if learning.get("provenance", {}).get("source") == "human_authored" else "ai",
                "has_human_precedent": learning.get("provenance", {}).get("source") == "human_authored",
            }

            client.record_learning(supabase_learning)

    print(f"Migrated learnings from {jsonl_path} to Supabase")

---

## 18. Appendix: Multi-Model Review Findings

### 18.1 Critical Additions (All 5 Models Agreed)

- [x] Rollback mechanism (auto-revert on regression)
- [x] Kill switch (`.healing_lock` file)
- [x] Hard constraints (unbendable limits)
- [x] Multi-model validation (different judges than fixers)
- [x] Human precedent requirement
- [x] Cascade detection

### 18.2 Unique Insights Incorporated

| Model | Insight | Incorporated |
|-------|---------|--------------|
| Claude | Never learn from AI-only fixes | Human precedent requirement |
| Gemini | Mandate reproduction test | Future: TDD for repairs |
| GPT | Promotion tiers not weeks | Metric-driven phasing |
| Grok | AST/diff anti-noise gate | Hard constraints on diff size |
| DeepSeek | Start with 3 error types | Focus on imports, syntax, types first |

### 18.3 Your Insight (Multi-Model Validation)

You correctly identified that cross-agent/multi-model validation IS valuable for top-tier models with CLI access. The design now uses **different models for judging than for fixing**, preventing the blind spot where a model approves its own patterns.
