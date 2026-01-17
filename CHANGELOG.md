# Changelog

All notable changes to the workflow-orchestrator.

## [Unreleased]

### Added
- **V4.2 Phase 2: Token Budget System** (Issue #102)
  - `src/v4/budget/`: New module for token budget tracking and enforcement
  - Provider-specific token counting:
    - `ClaudeTokenCounter`: Uses Anthropic's count_tokens API
    - `OpenAITokenCounter`: Uses tiktoken library
    - `EstimationTokenCounter`: Fallback (~4 chars/token)
  - `AtomicBudgetTracker`: Thread-safe budget tracking with SQLite persistence
    - Atomic reserve/commit/rollback pattern for token management
    - BEGIN IMMEDIATE locking for concurrency safety
    - Reservation timeout with automatic cleanup
  - Budget events integration with event store (BUDGET_CREATED, TOKENS_RESERVED, etc.)
  - 51 new tests covering concurrency, provider counting, and event sourcing

- **Control Inversion V4** (Issue #100): Orchestrator-driven workflow execution
  - New `orchestrator run` command for V4 workflow execution
  - `src/v4/models.py`: Complete data models (PhaseType, GateType, WorkflowStatus, gates, phases, state)
  - `src/v4/state.py`: State persistence with file locking and atomic writes
  - `src/v4/parser.py`: YAML workflow parsing with validation
  - `src/v4/gate_engine.py`: Programmatic gate validation (file_exists, command, no_pattern, json_valid)
  - `src/runners/base.py`: AgentRunner interface
  - `src/runners/claude_code.py`: Claude Code subprocess runner
  - `src/executor.py`: Core WorkflowExecutor with control inversion loop
  - `workflows/default_v4.yaml`: Default 5-phase V4 workflow
  - 17 new tests for executor, gates, state, and parser
  - Key principle: Orchestrator drives execution, LLM cannot skip phases or bypass gates

- **Self-Healing Infrastructure Phase 7b**: CLI Scanner Integration
  - `src/healing/cli_heal.py`: New helper functions for CLI integration
    - `_run_session_scan()`: Session-end scan helper for cmd_finish
    - `_check_crash_recovery()`: Crash recovery helper for cmd_start
    - Enhanced `heal_backfill()` with new parameters:
      - `--scan-only`: Show recommendations without processing
      - `--days N`: Limit scan to files modified in last N days (default: 30)
      - `--no-github`: Skip GitHub issue scanning
  - `src/healing/scanner.py`: Added `include_github` parameter to PatternScanner
  - `src/cli.py`: Added new CLI flags for heal backfill command
  - Non-blocking error handling (scanner failures don't block workflow completion)
  - 11 new tests for CLI scanner integration

- **Self-Healing Infrastructure Phase 7**: Intelligent File Scanning for Backfill
  - Session-end hook architecture (multi-model consensus from Claude, GPT, Gemini, Grok, DeepSeek)
  - `src/healing/scanner.py`: Main scanner module
    - `ScanState`: Persisted state tracking with file hashes, GitHub watermark, session tracking
    - `ScanResult` / `ScanSummary`: Data classes for scan results
    - `PatternScanner`: Incremental hash-based file scanning
      - `scan_all()`: Scan all sources with configurable days filter
      - `get_recommendations()`: Get recommendations for scannable sources
      - `has_orphaned_session()` / `recover_orphaned()`: Crash recovery
    - Sources: `.workflow_log.jsonl`, `LEARNINGS.md`, `.wfo_logs/`, `.orchestrator/sessions/`
    - Error extraction from text and JSONL formats using existing detector patterns
  - `src/healing/github_parser.py`: GitHub closed issues parser
    - `GitHubIssueParser`: Fetches closed issues via `gh` CLI
    - Filters by bug-related labels (bug, error, fix, crash, exception, failure)
    - Extracts error patterns from issue bodies (Python, Node, Rust, Go)
    - Watermark-based incremental fetching with date filtering
  - Deduplication via fingerprinting (existing infrastructure)
  - 34 new tests for scanner and GitHub parser
  - Designed for seamless integration at `orchestrator finish`

- **Self-Healing Infrastructure Phase 6**: Intelligent Pattern Filtering
  - Cross-project pattern relevance scoring with Wilson score
  - `src/healing/context_extraction.py`: Context extraction module
    - `detect_language()`: Detects Python, JavaScript, Go, Rust from error patterns/file paths
    - `detect_error_category()`: Classifies errors (dependency, syntax, runtime, network, permission)
    - `detect_framework()`: Detects React, Django, pytest, express, etc.
    - `wilson_score()`: Wilson score lower bound for success rate confidence
    - `calculate_recency_score()`: Exponential decay scoring (30-day half-life)
    - `calculate_context_overlap()`: Hierarchical context matching
    - `calculate_relevance_score()`: Combined scoring with all factors
    - `is_eligible_for_cross_project()`: Guardrails (3+ projects, 5+ successes, 0.7+ Wilson)
    - `extract_context()`: Main function to extract PatternContext from errors
  - `src/healing/supabase_client.py`: New scoring methods
    - `lookup_patterns_scored()`: RPC call for scored pattern lookup
    - `record_pattern_application()`: Per-project usage tracking
    - `get_pattern_project_ids()`: List projects using a pattern
    - `get_project_share_setting()`: Check opt-out status
  - `src/healing/client.py`: Phase 6 integration
    - `_lookup_scored()`: Scored lookup with tiered matching (same-project 0.6, cross-project 0.75)
    - `SAME_PROJECT_THRESHOLD` and `CROSS_PROJECT_THRESHOLD` constants
    - Updated `record_fix_result()` to pass context for per-project tracking
  - All 4 detectors (workflow_log, subprocess, transcript, hook) now extract context
  - Backfill module updated to extract context for historical errors
  - Project opt-out support: `share_patterns: false` in healing_config
  - 62 new tests for context extraction and scored lookup

- **Self-Healing Infrastructure Phase 4**: CLI & Workflow Integration
  - `src/healing/cli_heal.py`: CLI commands for healing system
    - `orchestrator heal status`: Show healing system status (environment, kill switch, costs, patterns)
    - `orchestrator heal apply <fix-id>`: Apply a fix with optional `--dry-run`
    - `orchestrator heal ignore <fingerprint>`: Mark error as false positive
    - `orchestrator heal unquarantine <fingerprint>`: Remove from quarantine list
    - `orchestrator heal explain <fingerprint>`: Explain error and fix rationale
    - `orchestrator heal export`: Export patterns/fixes to JSON/YAML/CSV
    - `orchestrator heal backfill`: Backfill historical logs into pattern database
  - `src/healing/cli_issues.py`: CLI commands for issue management
    - `orchestrator issues list`: List accumulated issues with filters
    - `orchestrator issues review`: Interactive review of pending issues
  - `src/healing/hooks.py`: HealingHooks for workflow integration
    - `on_phase_complete()`: Hook for phase completion events
    - `on_subprocess_complete()`: Hook for command execution events
    - `on_workflow_complete()`: Hook for workflow completion
    - `on_learn_phase_complete()`: Hook for LEARN phase learnings capture
  - CLI integrated into `src/cli.py` with argparse subparsers
  - 11 unit tests for CLI commands in `tests/healing/test_cli_heal.py`

- **Self-Healing Infrastructure Phase 5**: Observability & Hardening
  - `src/healing/circuit_breaker.py`: Circuit breaker pattern for fix safety
    - CircuitState enum: CLOSED (normal), OPEN (blocked), HALF_OPEN (testing)
    - Trips after 2 reverts within 1 hour, 30-minute cooldown
    - State persistence to Supabase via `load_state()`/`save_state()`
    - Global instance via `get_circuit_breaker()`/`reset_circuit_breaker()`
  - `src/healing/metrics.py`: Metrics collection and dashboard
    - DashboardMetrics dataclass: detection_rate, auto_fix_rate, success_rate
    - HealingMetrics class: `get_dashboard_data()` for metrics retrieval
    - Cost tracking, pattern counts, top errors
  - `src/healing/flakiness.py`: Flakiness detection for intermittent errors
    - FlakinessDetector class: variance-based analysis of error timing
    - FlakinessResult dataclass with determinism_score (0.0=flaky, 1.0=deterministic)
    - Configurable variance threshold (default: 1 hour) and min occurrences (3)
  - `src/healing/cache_optimizer.py`: Cache warming for pattern pre-loading
    - CacheOptimizer class: `warm_cache()` for LOCAL environment
    - Configurable cache limit and TTL (24 hours default)
  - `src/healing/backfill.py`: Historical log backfill
    - HistoricalBackfill class: `backfill_workflow_logs()` for .workflow_log.jsonl
    - Processes error events and records to Supabase
  - `src/healing/supabase_client.py`: Extended with 15+ new methods
    - Pattern methods: `get_all_patterns()`, `get_top_patterns()`, `get_pattern_counts()`, `get_pattern_growth()`
    - Issue methods: `list_issues()`, `get_error_counts()`, `get_fix_counts()`
    - Cost methods: `get_cost_data()`, `get_daily_costs()`
    - Circuit breaker: `get_circuit_state()`, `save_circuit_state()`
    - Flakiness: `get_error_occurrences()`
    - Backfill: `record_historical_error()`
  - 19 unit tests in `tests/healing/test_circuit_breaker.py`
  - 7 unit tests in `tests/healing/test_flakiness.py`
  - All 376 healing tests pass (Phases 0-5 complete)

### Fixed
- **State file integrity warnings (#94)**: Fixed false-positive integrity check warnings
  - Root cause: `_version` field included in checksum on save but removed before verification on load
  - Fix: Added `_version` to excluded fields in `compute_state_checksum`
  - Added 6 unit tests for checksum computation in `tests/test_state_version.py`

### Added
- **Self-Healing Infrastructure Phase 3**: Validation & Fix Application
  - `src/healing/safety.py`: SafetyCategorizer for diff analysis
    - Categories: SAFE (whitespace, imports, comments), MODERATE (error handling, conditionals), RISKY (DB ops, security, function sigs)
    - Protected paths: migrations, .env, secrets, CI configs
    - Methods: `categorize()`, `categorize_diff()`
  - `src/healing/costs.py`: CostTracker for API cost management
    - Daily budgets, per-validation limits
    - Operation cost tracking (embeddings, judges)
    - Methods: `record()`, `can_validate()`, `estimate_cost()`
  - `src/healing/cascade.py`: CascadeDetector for hot file detection
    - Prevents fix ping-pong on frequently modified files
    - Hot file threshold: 3+ modifications/hour
    - Methods: `is_file_hot()`, `record_fix()`, `check_cascade()`
  - `src/healing/judges.py`: MultiModelJudge for consensus voting
    - Models: Claude Opus, Gemini Pro, GPT-5.2, Grok
    - Tiered judging: 1 judge (SAFE), 2 (MODERATE), 3 (RISKY)
    - Methods: `judge()`, `_get_vote()`, `_parse_vote()`
  - `src/healing/validation.py`: ValidationPipeline with 3 phases
    - Phase 1 PRE_FLIGHT: Kill switch, constraints, precedent, cascade, cost budget
    - Phase 2 VERIFICATION: Parallel build/test/lint
    - Phase 3 APPROVAL: Multi-model consensus voting
    - Methods: `validate()`, convenience function `validate_fix()`
  - `src/healing/context.py`: ContextRetriever for file context
    - Retrieves files for error location and fix action
    - Related file detection by language (Python, JS, Go)
    - Methods: `get_context()`, `get_related_files()`
  - `src/healing/applicator.py`: FixApplicator with environment awareness
    - Action types: diff, command, file_edit, multi_step
    - Command allowlist for safety (pip, npm, yarn, go, cargo, etc.)
    - Environment-aware: LOCAL (direct merge), CLOUD (PR creation)
    - Build/test verification before merge
    - Methods: `apply()`, `rollback()`, `_verify()`
  - 99 unit tests for Phase 3 components
  - All 339 healing tests pass (147 Phase 1 + 93 Phase 2 + 99 Phase 3)

- **Self-Healing Infrastructure Phase 2**: Pattern Memory, Lookup & Security
  - `src/healing/security.py`: SecurityScrubber removes secrets/PII before storage
    - 13 regex patterns: API keys, bearer tokens, passwords, AWS keys, PEM, connection strings, emails, GitHub/Slack tokens
    - Methods: `scrub()`, `scrub_error()`, `scrub_dict()`
  - `src/healing/embeddings.py`: OpenAI embedding service for RAG semantic search
    - Uses `text-embedding-ada-002` model (1536 dimensions)
    - Graceful degradation when API key unavailable
  - `src/healing/preseeded_patterns.py`: 30 pre-built patterns for common errors
    - Python: ModuleNotFoundError, SyntaxError, ImportError, PermissionError, FileNotFoundError, AssertionError, pytest, type errors
    - Node.js: Cannot find module, ENOENT, EACCES, SyntaxError, TypeError
    - Go: undefined, cannot find package, permission denied
    - Rust: cannot find, unresolved import, mismatched types, borrow checker
    - `match_preseeded()` for local pattern matching
  - `src/healing/supabase_client.py`: HealingSupabaseClient for pattern storage
    - Tier 1: Exact fingerprint lookup with project_id filtering
    - Tier 2: RAG semantic search via `match_learnings` RPC (0.7 threshold)
    - Tier 3: Causality traversal via `get_error_causes` RPC (depth parameter)
    - Methods: `lookup_pattern()`, `lookup_similar()`, `get_causes()`, `record_pattern()`, `record_fix_result()`, `audit_log()`
  - `src/healing/pattern_generator.py`: LLM-based pattern generation
    - Uses Claude Sonnet for fix extraction from diffs
    - Methods: `generate_from_diff()`, `extract_from_transcript()`
  - `src/healing/client.py`: Unified HealingClient with three-tier lookup
    - `LookupResult` dataclass with tier, pattern, source, causes
    - Cascade: Cache → Supabase exact → RAG semantic → Causality
    - 0.85 similarity threshold for RAG matches
  - `migrations/001_healing_schema.sql`: Supabase schema
    - Tables: `healing_config`, `error_patterns`, `learnings`, `causality_edges`, `healing_audit`
    - pgvector for semantic search with IVFFlat index
    - RPC functions: `match_learnings`, `get_error_causes`, `increment_pattern_stat`
    - Row Level Security policies
  - 93 unit tests for Phase 2 components
  - All 240 healing tests pass (147 Phase 1 + 93 Phase 2)
- **Self-Healing Infrastructure Phase 1**: Detection, Fingerprinting & Config
  - `src/healing/config.py`: HealingConfig from environment variables (Supabase in Phase 2)
    - Kill switch support, cost controls, protected paths, timeouts
  - `src/healing/models.py`: ErrorEvent unified error model, FixAction schema
  - `src/healing/fingerprint.py`: Stable fingerprinting for error deduplication
    - Normalizes paths, line numbers, UUIDs, timestamps, memory addresses
    - Extracts error types from Python, Node, Rust, Go
    - Fine-grained (16 hex) and coarse (8 hex) fingerprints
  - `src/healing/detectors/`: 4 error detectors
    - `WorkflowLogDetector`: Parses .workflow_log.jsonl
    - `SubprocessDetector`: Parses command stdout/stderr
    - `TranscriptDetector`: Parses conversation transcripts
    - `HookDetector`: Parses hook output
  - `src/healing/accumulator.py`: Session-level error deduplication
  - 147 unit tests for Phase 1 components
  - Observation-only (no fixes applied) - Phase 2 adds pattern matching
- **Self-Healing Infrastructure Phase 0**: Abstraction layer for cross-environment operations
  - `src/healing/environment.py`: Environment detection (LOCAL/CLOUD/CI)
  - `src/healing/adapters/`: Abstract interfaces and implementations
    - `StorageAdapter`: File operations (LocalStorageAdapter, GitHubStorageAdapter)
    - `GitAdapter`: Git operations (LocalGitAdapter, GitHubAPIAdapter)
    - `CacheAdapter`: Caching (LocalSQLiteCache, InMemoryCache)
    - `ExecutionAdapter`: Command execution (LocalExecutionAdapter, GitHubActionsAdapter)
  - `AdapterFactory`: Creates appropriate adapters based on detected environment
  - Foundation layer for self-healing features in future phases
  - 76 unit tests for full adapter coverage
- **Zero-Human Mode with Minds Proxy (#39)**: Multi-model consensus for autonomous gate decisions
  - `MindsGateProxy` class orchestrates multi-model voting for gate decisions
  - Weighted voting: ChatGPT/Claude (2.0), Gemini (1.5), Grok (1.0), DeepSeek (0.5)
  - Re-deliberation feature: dissenting models see other reasoning before final vote
  - Certainty-based escalation: high certainty (>=0.95) proceeds even on CRITICAL
  - Full decision audit trail with rollback commands in `minds_decisions.jsonl`
  - Configurable via `workflow.yaml` supervision settings
- **Model Fallback on Quota Exhaustion (#89)**: Automatic fallback to alternative models
  - Quota errors now trigger fallback chain instead of permanent failure
  - `ReviewResult.fallbacks_tried` tracks attempted models
  - Moved quota patterns to transient errors in `retry.py`
- **Automated Design Validation (#91)**: Compare implementation against plan
  - `DesignValidationResult` with status: PASS, PASS_WITH_NOTES, NEEDS_REVISION, SKIP
  - Lenient mode (default): only flags major scope creep, not minor additions
  - Tracks: planned items implemented, unplanned additions, deviations
  - Uses LLM fallback chain for resilience
- **Plan Validation Review (#88)**: Pre-implementation review in PLAN phase
  - Reviews `docs/plan.md` BEFORE implementation to catch flawed designs while changes are cheap
  - 10 checkpoints: Request Completeness, Requirements Alignment, Security & Compliance,
    Risk Mitigation, Objective-Driven Optimality, Dependencies & Integration, Edge Cases,
    Testing & Success Criteria, Implementability, Operational Readiness
  - 5 verdicts: APPROVED, APPROVED_WITH_NOTES, NEEDS_REVISION (with fixes), BLOCKED, ESCALATE
  - Request completeness check ensures nothing from original request is missing
  - Objective-driven optimality validates solution is optimal for underlying goal
  - "Fix-not-flag" approach: provides actual fixes, not just problem descriptions
  - Skip conditions with concrete definitions (trivial_change, simple_bug_fix, well_understood_pattern)
  - Never-skip scenarios: security-sensitive, data migrations, breaking API, multi-system impact
  - Complements Design Validation Review (#82) which validates post-implementation
  - Designed with multi-model input (Claude, GPT, Grok, DeepSeek consensus via /minds)
- **Design Validation Review (#82)**: New 6th review type in REVIEW phase
  - Validates implementation matches design goals from `docs/plan.md`
  - Checks: requirements traceability, scope control, parameter alignment
  - Skippable when: no plan exists, simple bug fix, trivial change
  - Prompt designed with multi-model input (Claude, GPT, Grok, DeepSeek consensus)

### Security
- **TOCTOU Fix in Stale Lock Cleanup (#73)**: Use atomic rename pattern in `_clean_stale_lock()`
  - Previously: check-then-delete pattern had race condition vulnerability
  - Now: atomically rename to `.removing` before delete, preventing lock bypass
  - Gracefully handles concurrent removal attempts
- **Directory fsync for State Durability (#80)**: Add directory fsync after atomic rename
  - `save_state_with_integrity()` now fsyncs parent directory after rename
  - Ensures rename is durable on crash (especially on ext4)
  - Uses `O_DIRECTORY` flag when available, with graceful fallback
- **Timing Attack Prevention (#71)**: Use `hmac.compare_digest` for hash comparisons
  - `verify_integrity()` now uses constant-time comparison
  - `check_audit_integrity()` uses constant-time comparison for chain verification
- **Audit Hash Verification (#74)**: `check_audit_integrity()` now recomputes and verifies hashes
  - Previously only checked chain linkage (prev_hash)
  - Now detects tampered entries by recomputing expected hash

### Performance
- **Audit Log Memory Fix (#79)**: `_load_last_hash()` uses seek-from-end approach
  - Previously read entire file into memory (potential DoS)
  - Now reads only last 4KB chunk
- **File Detection Optimization (#87)**: `_auto_detect_important_files()` optimized
  - Tries `git ls-files` first (faster for git repos)
  - Falls back to rglob with depth limit
  - Excludes common artifact directories (node_modules, __pycache__, etc.)

### Fixed
- **orchestrator finish silently ignores uncommitted changes (#92)**: Auto-commit uncommitted changes before sync
  - `orchestrator finish` now auto-commits all uncommitted changes with message "Complete workflow: <task>"
  - Prevents silent data loss when workflow completes but changes aren't pushed
  - Use `--no-push` to skip both commit and push
- Fixed `test_sanitize_paths` asserting on wrong field (`entries[0].get('path')` → `entries[0]['data']['path']`)

### Added
- **V3 Hybrid Orchestration Phase 5: CLI Integration**
  - `orchestrator health` command for system health checks
    - JSON output with `--json` flag
    - Checks state file, locks, and checkpoints
  - Mode detection at workflow start via `detect_operator_mode()`
    - Logs to audit trail with operator mode and confidence
    - Stored in workflow state metadata
  - Audit logging for key operations
    - Logs: `workflow_start`, `workflow_finish`, `phase_transition`
    - Stored in `.orchestrator/audit.jsonl`
  - State integrity checks with v3 version/checksum
    - State files now include `_version`, `_checksum`, `_updated_at`
    - Integrity verified on load with warning if tampered
  - Gate enforcement in `orchestrator complete`
    - Validates `file_exists` and `command` gates before completion
    - Clear error messages when gate fails
  - 15 new CLI integration tests in `tests/test_cli_v3_integration.py`

- **V3 Hybrid Orchestration Phase 4: Integration & Hardening**
  - `src/audit.py`: Tamper-evident audit logging system
    - `AuditLogger` class with chained SHA256 hashes for integrity
    - Log operations: checkpoint create/restore, mode changes, workflow state changes
    - Path sanitization to prevent sensitive data leakage
    - `verify_integrity()` for tamper detection
    - `AuditTamperError` exception for tamper alerts
  - `src/health.py`: Health check system for orchestrator components
    - `HealthChecker` class with component-level health reports
    - Checks: state file integrity, lock state, checkpoint directory
    - Structured JSON output for automation
  - `StateIntegrityError` exception in `src/state_version.py`
  - 25 new tests across 4 test files:
    - `tests/test_audit_v3.py`: 6 audit logging tests
    - `tests/test_health_v3.py`: 7 health check tests
    - `tests/test_integration_v3.py`: 5 end-to-end tests
    - `tests/test_adversarial_v3.py`: 6 adversarial tests (concurrency, malformed input, resource limits)

### Security
- **CommandGate**: Eliminated shell=True to prevent shell injection
  - Shell builtins (true, false, exit) now emulated in Python
  - Injection attempts like "true; rm -rf /" are now rejected
- **ArtifactGate**: Fixed path traversal and symlink attacks
  - Absolute paths now blocked with clear error
  - Path resolution with containment check (resolve + relative_to)
  - Symlink attacks through parent directories now caught
- **FileLock**: Cross-platform support and fd leak prevention
  - Windows support via msvcrt.locking (Unix uses fcntl)
  - File descriptors properly cleaned up on all failure paths
  - Close-on-exec flag for child process safety
- **LockManager**: Fixed race conditions and symlink attacks
  - Thread lock no longer held while yielding (prevents deadlock)
  - Cross-platform PID checking via psutil
  - Lock path validation prevents symlink attacks
  - Cycle detection in checkpoint chain traversal

- **V3 Hybrid Orchestration Phase 3: Checkpointing & Concurrency**
  - `FileLock` class: File-based locking using fcntl for concurrent access control
    - Exclusive (write) and shared (read) lock modes
    - Timeout-based acquisition with `LockTimeoutError`
    - Context manager support for automatic lock release
  - `LockManager` class: Named resource locking with stale lock detection
    - Reentrant locks (same thread can acquire multiple times safely)
    - Automatic cleanup on process exit via atexit handler
    - Stale lock detection (checks if PID is still running)
  - Checkpoint chaining via `parent_checkpoint_id` field
  - `get_checkpoint_chain()` method to retrieve full checkpoint lineage
  - Fixed checkpoint ID collision with microseconds + random suffix
  - `tests/test_checkpoint_v3.py`: 11 comprehensive tests for new features

- **V3 Hybrid Orchestration Phase 2: Artifact-Based Gates**
  - `src/gates.py`: Gate validation system for workflow item completion
    - `ArtifactGate`: File existence and content validation (with path traversal & symlink protection)
    - `CommandGate`: Command execution with exit code validation (shell injection safe via shlex)
    - `HumanApprovalGate`: Manual approval gate for human checkpoints
    - `CompositeGate`: AND/OR logic for combining multiple gates
  - Built-in validators: `exists`, `not_empty` (default), `min_size`, `json_valid`, `yaml_valid`
  - Security measures: path traversal blocking, symlink attack prevention, shell injection safety
  - `tests/test_gates.py`: 18 comprehensive tests including adversarial input tests

- **V3 Hybrid Orchestration Phase 1: Phase Types & Tool Scoping**
  - `PhaseType` enum (STRICT, GUIDED, AUTONOMOUS) for phase autonomy levels
  - `phase_type` field in PhaseDef (defaults to GUIDED for backward compatibility)
  - `intended_tools` field in PhaseDef (documentation only, not enforced)
  - 11 new tests in `tests/test_phase_types.py`

- **V3 Hybrid Orchestration Phase 0: Foundation**
  - `src/mode_detection.py`: Operator mode detection (human vs LLM)
    - `OperatorMode` enum (HUMAN, LLM) for type-safe mode handling
    - `ModeDetectionResult` dataclass with mode, reason, and confidence
    - `detect_operator_mode()` with priority-based detection: emergency override → explicit mode → CLAUDECODE → TTY
    - `is_llm_mode()` convenience function for simple boolean checks
    - `log_mode_detection()` for audit logging
  - `src/state_version.py`: State file versioning with integrity checks
    - `STATE_VERSION = "3.0"` constant for version identification
    - `.orchestrator/v3/` isolated state directory (doesn't conflict with v2)
    - SHA256 checksums for tamper detection
    - Atomic writes with fsync for corruption prevention
    - Version verification prevents v2/v3 state confusion
  - `tests/test_mode_detection.py`: 18 comprehensive tests
    - 10 mode detection tests (emergency override, explicit mode, CLAUDECODE, TTY)
    - 5 state integrity tests (round-trip, tamper detection, version check)
    - 3 state versioning tests (directory path, checksum exclusion, content sensitivity)

- **Issue #58: CORE-028b Model Fallback Execution Chain**
  - API reviews now automatically retry with fallback models on transient failures (rate limits, 503s, timeouts)
  - New `src/review/retry.py` module with `is_retryable_error()`, `is_permanent_error()`, and `retry_with_backoff()` functions
  - Added `execute_with_fallback()` method to `APIExecutor` for fallback chain execution
  - Fallback chains configurable in `workflow.yaml` under `settings.reviews.fallback_chains`
  - Added `--no-fallback` CLI flag to `orchestrator review` and `orchestrator review-retry` commands
  - CLI output now shows `[fallback]` indicator and fallback reason when alternative model is used
  - Permanent errors (401, 403, invalid API key) fail immediately without retry or fallback
  - Default fallback chains: gemini→flash→sonnet, codex→gpt-5.1→sonnet, grok→grok-3→sonnet
  - Comprehensive test coverage in `tests/test_review_fallback.py` (23 tests)

### Fixed
- **Issue #64: Default task_provider to 'github' when gh CLI available**
  - Task commands (list, add, next, close, show) now auto-detect provider instead of defaulting to 'local'
  - If gh CLI is installed and authenticated, GitHub Issues backend is used automatically
  - Falls back to local JSON storage when gh CLI unavailable
  - Explicit `--provider local` flag still overrides auto-detection

- **Issue #63: commit_and_sync shows "Skipped" when auto-sync actually pushes**
  - In zero_human mode, commit_and_sync item now shows "Completed" after successful auto-sync
  - Previously showed misleading "Skipped" even though CORE-031 auto-sync pushed changes
  - Notes indicate "Auto-completed via CORE-031 sync" for clarity

- **Issue #65: vibe_coding review type not exposed in CLI choices**
  - CLI `review` command now dynamically uses `get_all_review_types()` from registry
  - Previously hardcoded list `['security', 'consistency', 'quality', 'holistic', 'all']` missing `vibe_coding`
  - Added regression tests in `tests/test_cli_reviews.py::TestCLIReviewChoices`

### Changed
- **Issue #66: Model version DRY refactor (Phase 1)**
  - `src/review/api_executor.py`: Now uses `model_registry.get_latest_model()` instead of hardcoded `OPENROUTER_MODELS` dict
  - `src/review/config.py`: API model defaults now call `_get_default_api_model()` which uses registry
  - CLI models remain tool-specific (different naming scheme) - deferred to future phase if needed
  - Added regression tests in `tests/test_model_registry.py::TestModelRegistryIntegration`

- **Upgraded to GPT-5.2-Codex** (released December 2025)
  - Updated model_registry.py: 5.2-codex-max now preferred for code reviews
  - Updated workflow.yaml and src/default_workflow.yaml: CLI and API model references
  - Updated src/review/models.py: Added 5.2-codex model mappings and NO_TEMPERATURE_MODELS
  - Updated src/review/api_executor.py: Default codex model now openai/gpt-5.2
  - Updated src/providers/openrouter.py: Added 5.2 models to FUNCTION_CALLING_MODELS
  - Updated src/schema.py: Default fallback chain now uses 5.2
  - Maintains backward compatibility with 5.1 models as fallback

### Fixed
- **Issue #61: CLI Hanging in Non-Interactive Mode**
  - Added `is_interactive()` helper function to detect non-TTY environments
  - Added `confirm()` helper for prompts with fail-fast in non-interactive mode
  - Fixed `orchestrator advance` - uses `--yes` flag instead of hanging on critique prompt
  - Fixed `orchestrator init` - uses `--force` flag instead of hanging on overwrite prompt
  - Fixed `orchestrator resolve` - exits with suggestion to use `--strategy` instead of hanging
  - Fixed `orchestrator workflow cleanup` - uses `--yes` flag instead of hanging on confirmation
  - Fixed `orchestrator feedback review --suggest` - gracefully skips ROADMAP prompt in non-interactive mode
  - Added 14 new tests in `tests/test_cli_noninteractive.py`

## [2.10.2] - 2026-01-14

### Changed
- **WF-030 Phase 4: Git Worktree Isolation marked COMPLETED**
  - Updated ROADMAP.md to reflect full implementation status
  - All MVP tasks verified: WorktreeManager, --isolated flag, worktree merge/cleanup, orchestrator doctor
  - V2 features also complete: Human-readable naming (YYYYMMDD-adjective-noun-sessionid), auto-cleanup (7d)

## [2.10.1] - 2026-01-14

### Added
- **CORE-026-E1 & E2: Complete Error Classification**
  - `_classify_exception()` in api_executor.py - classifies HTTP status codes and request exceptions
  - `_classify_error()` in cli_executor.py - classifies CLI error messages
  - `_ping_api()` in router.py - lightweight /models endpoint tests for API key validation
  - `ping=True` option on `validate_api_keys()` to test keys with real API calls
  - 15 new tests (10 executor classification, 5 ping validation)

## [2.10.0] - 2026-01-14

### Added
- **CORE-026: Review Failure Resilience & API Key Recovery**
  - **ReviewErrorType enum**: Typed error classification (KEY_MISSING, KEY_INVALID, RATE_LIMITED, NETWORK_ERROR, TIMEOUT, PARSE_ERROR, REVIEW_FAILED)
  - **classify_http_error()**: Maps HTTP status codes to error types (401/403 → KEY_INVALID, 429 → RATE_LIMITED, 500+ → NETWORK_ERROR)
  - **validate_api_keys()**: Proactive API key validation before running reviews
  - **recovery.py module**: Model-specific recovery instructions with SOPS reload guidance
  - **required_reviews in workflow.yaml**: Configurable required reviews per workflow (not hardcoded)
  - **get_required_reviews()**: Engine method to read required reviews from workflow definition
  - **get_failed_reviews()**: Engine method returning failed reviews with error type for targeted retry
  - **review-retry command**: CLI command to retry failed reviews after fixing API keys
  - **30 new tests**: Comprehensive coverage in `tests/test_review_resilience.py`

### Changed
- **PhaseDef schema**: Added `required_reviews: list[str]` field for workflow-level review requirements

## [2.9.0] - 2026-01-13

### Added
- **CORE-025 Phase 1: Multi-Repo Containment Strategy Foundation**
  - **OrchestratorPaths class**: Centralized path resolution for all orchestrator files (`src/path_resolver.py`)
    - Auto-detects repo root by walking up to `.git/` or `workflow.yaml`
    - Session-aware paths: `.orchestrator/sessions/<session-id>/`
    - Legacy path detection for backward compatibility
    - Supports normal (gitignored) vs portable (committed) modes
  - **SessionManager class**: Session lifecycle management (`src/session_manager.py`)
    - 8-character UUID session IDs
    - Session metadata with creation timestamp and repo root
    - Current session pointer (`.orchestrator/current` file)
    - Session listing and switching
  - **34 new unit tests**: Full coverage for PathResolver and SessionManager
  - **filelock dependency**: Added for concurrent access safety (Phase 1.4)

### Changed
- pyproject.toml now includes `filelock>=3.0` dependency

### Technical Details
- New directory structure: `.orchestrator/sessions/<session-id>/state.json`, `log.jsonl`, etc.
- Dual-read pattern ready: New paths preferred, legacy paths as fallback
- Phase 2 (WorkflowEngine integration) deferred to keep Phase 1 focused

## [2.8.1] - 2026-01-12

### Added
- **WF-035 Phases 3-5: Review Fallback Foundation** (Continues WF-035 zero-human mode)
  - **ReviewResult fallback tracking**: `was_fallback` and `fallback_reason` fields track when fallback models are used
  - **ReviewThresholdError exception**: Raised when insufficient reviews complete (used by `on_insufficient_reviews: block`)
  - **16 new unit tests**: `tests/test_review_fallbacks.py` covering fallback fields, threshold logic, and settings validation

### Fixed
- **Critique module attribute error**: Fixed `'ReviewResult' object has no attribute 'content'` error in `critique.py`
  - Changed `result.content` to `result.raw_output` (correct attribute name)
  - Error appeared on every phase advance since critique runs between phases

### Changed
- **LEARN phase**: Added `session_error_review` step as first item in LEARN phase
  - Prompts agent to search session transcript for errors, warnings, and failures
  - Helps catch bugs like the critique.py error before workflow completion
  - Includes search patterns and example of how errors map to bugs

### Notes
- Phases 3 (Visual Regression) and 5 (Gate Skipping) were already implemented in previous PR
- Full fallback chain execution (try primary → fallback1 → fallback2) deferred to follow-up task
- Schema and tracking foundation now in place for graceful degradation

## [2.8.0] - 2026-01-11

### Added
- **WF-035: Zero-Human Mode - Supervision Mode Configuration** (Phases 1-2 of 6)
  - **SupervisionMode enum**: `supervised` (default), `zero_human`, `hybrid` in `src/schema.py`
  - **WorkflowSettings model**: Typed settings with `supervision_mode`, `smoke_test_command`, `test_command`, `build_command`
  - **ReviewSettings model**: Configurable review fallbacks with `minimum_required`, `fallbacks`, `on_insufficient_reviews`
  - **Gate skipping logic**: `should_skip_gate()` in `src/engine.py` auto-skips manual gates in `zero_human` mode
  - **Warning logging**: Skipped gates logged with `[ZERO-HUMAN MODE]` prefix for audit trail
  - **34 new unit tests**: Comprehensive coverage for supervision mode and gate skipping
  - **100% backward compatible**: Default `supervised` mode maintains existing behavior

### Changed
- WorkflowEngine now accepts optional `settings` parameter for typed configuration
- Manual gates respect `supervision_mode` setting when determining whether to block

### Deferred (Follow-up PR)
- WF-035 Phases 3-6: Smoke testing framework, visual regression docs, review fallbacks, integration tests

## [2.7.0] - 2026-01-11

### Added
- **WF-034 Phase 3b: Two-Tier Feedback System**: Split feedback into tool metrics (shareable) vs process context (private)
  - **Two-file architecture**: `.workflow_tool_feedback.jsonl` (anonymized) + `.workflow_process_feedback.jsonl` (full context)
  - **Anonymization with allowlist approach**: Only explicitly safe fields kept (prevents future PII leakage)
  - **Salted SHA256 hashing**: workflow_id → 16-char hash (prevents rainbow table attacks)
  - **Nested PII protection**: Phase dict keys validated (only PLAN, EXECUTE, etc. allowed)
  - **Automatic migration**: Phase 3a single-file feedback migrated to two-tier on first run
  - **Transaction-safe migration**: Atomic rename with rollback and crash recovery
  - **Sync command**: `orchestrator feedback sync` uploads anonymized tool feedback to GitHub Gist
  - **Review filters**: `orchestrator feedback review --tool` / `--process` for targeted analysis
  - **22 unit tests** covering security, atomicity, and anonymization
  - **Multi-model validation**: 5 AI models (Claude, GPT, Gemini, Grok, DeepSeek) reviewed for security

### Security
- **Salt management documentation**: Added comprehensive security guidance in CLAUDE.md
  - Default salt for single-user installations
  - Custom salt generation for teams (`openssl rand -base64 32`)
  - Warnings about salt storage, rotation, and version control
- **Allowlist-based PII filtering**: Future schema changes cannot leak PII by default
- **Deep copy protection**: Nested data structures safely handled

## [2.6.0] - 2026-01-11

### Added
- **PRD-008: Zero-Config Workflow Enforcement**: Single command workflow setup for AI agents
  - **`orchestrator enforce` command**: Auto-detects server, generates workflow, and provides agent instructions
  - **Server Auto-Discovery** (`src/orchestrator/auto_setup.py`): Checks ports 8000-8002 for running servers
  - **Server Auto-Start**: Spawns daemon process if no server found, with health check verification
  - **Repository Analysis** (`src/orchestrator/workflow_generator.py`): Detects language and test framework
    - Python (pytest), JavaScript (jest/mocha), Go (go test), Rust (cargo test)
    - Auto-detects project structure (src/, tests/, etc.)
  - **Workflow YAML Generation**: Creates `.orchestrator/agent_workflow.yaml` from template
    - 5-phase workflow (PLAN → TDD → IMPL → REVIEW → VERIFY)
    - Language-specific test commands and tool restrictions
  - **Agent Context Formatting** (`src/orchestrator/agent_context.py`): Generates SDK usage instructions
    - Markdown format with code examples
    - Sequential vs parallel execution mode support
    - Outputs to stdout for AI consumption + backup file
  - **Cross-Platform Support**: Windows and Unix daemon process management
  - **81 comprehensive unit tests** with 100% pass rate

## [2.5.0] - 2026-01-11

### Added
- **WF-029: Tradeoff Analysis in LEARN Phase**: Mandatory complexity vs benefit analysis for roadmap items
  - Added tradeoff analysis requirements to `propose_actions` workflow step
  - Requires categorization: ✅ RECOMMEND / ⚠️ DEFER / 🔍 EXPLORATORY
  - Includes YAGNI check and evidence evaluation (production data, user requests, bottlenecks)
  - Prevents roadmap bloat from low-value items without implementation evidence
  - Applied to both workflow.yaml and src/default_workflow.yaml
- **WF-030: Session Isolation** - Documented multi-workflow limitation in roadmap (planned feature)

### Changed
- **CLAUDE.md**: Added comprehensive "Automatic Updates" section explaining auto-update behavior
  - What gets auto-updated (orchestrator code) vs what doesn't (workflow.yaml)
  - How to get new workflow features in existing projects
  - Recent workflow improvements (WF-029 tradeoff analysis)
  - Verification commands for checking versions

### Added
- **PRD-007: Agent Workflow Enforcement System (Days 14-20)**: Complete orchestration server for multi-agent workflows
  - **State Management** (`src/orchestrator/state.py`): Thread-safe task tracking with JSON persistence
    - Task registration and phase tracking
    - Dependency management and completion tracking
    - Blocker recording and state snapshots
    - Concurrent operation support with lock-based protection
  - **Event Bus** (`src/orchestrator/events.py`): Pub/sub pattern for agent coordination
    - 6 standard event types (task claimed, transitioned, completed, tool executed, gate blocked/passed)
    - Event history for debugging and audit trails
    - Thread-safe subscriber management
  - **Configuration System** (`src/orchestrator/config.py`): Multi-source configuration management
    - Defaults → YAML file → Environment variables (priority order)
    - 9 configuration classes (Server, Security, State, Event, Audit, Retry, CircuitBreaker, Logging, Orchestrator)
    - Runtime updates and validation
    - Thread-safe operations
  - **Error Handling** (`src/orchestrator/error_handling.py`): Production-grade reliability
    - RetryHandler with exponential backoff and jitter
    - CircuitBreaker with 3-state pattern (CLOSED/OPEN/HALF_OPEN)
    - FallbackHandler for graceful degradation
    - ErrorHandler combining retry + circuit breaker + fallback
    - Custom exception hierarchy (RetryableError, NonRetryableError, CircuitBreakerOpenError)
  - **Agent SDK** (`src/agent_sdk/`): Simple Python client for agents
    - Automatic token management and refresh
    - Convenience methods (claim_task, advance_phase, execute_tool)
    - Context manager support
    - Comprehensive error handling
  - **API Integration**: StateManager and EventBus integrated into FastAPI endpoints
    - Task claim tracking
    - Phase transition events
    - Tool execution events
    - State snapshots
  - **Testing**: 102 new tests (100% pass rate)
    - 13 StateManager tests (registration, phases, completion, dependencies, persistence, thread safety)
    - 12 EventBus tests (subscribers, publishing, history, error handling, thread safety)
    - 28 integration tests (state + events coordination)
    - 11 E2E workflow tests (complete workflows, multi-agent, gates, permissions)
    - 32 configuration tests (loading, overrides, validation, priority)
    - 31 error handling tests (retry, circuit breaker, fallback, thread safety)
    - 21 Agent SDK tests
  - **Documentation** (125+ pages total):
    - `docs/AGENT_SDK_GUIDE.md` (40+ pages): Complete SDK user guide with API reference, examples, best practices
    - `docs/WORKFLOW_SPEC.md` (35+ pages): Workflow YAML specification with schema, validation, examples
    - `docs/DEPLOYMENT_GUIDE.md` (50+ pages): Production deployment (systemd, Docker, Kubernetes, monitoring, security)
    - Implementation summaries: `docs/DAYS_13_20_SUMMARY.md`, `docs/DAYS_14_16_SUMMARY.md`, `docs/DAYS_17_20_SUMMARY.md`
  - **Production Ready**:
    - Security: JWT authentication, permission enforcement, audit logging
    - Reliability: Retry logic, circuit breakers, graceful degradation
    - Scalability: Stateless API, horizontal scaling, thread-safe operations
    - Observability: Comprehensive logging, health checks, event tracking
    - Deployment: Systemd, Docker, Kubernetes manifests provided

### Changed
- API endpoints now publish events and track state through StateManager and EventBus

## [2.4.0] - 2026-01-10

### Added
- **CORE-023-P1: Conflict Resolution - Core**: Fast conflict detection and resolution without LLM
  - `orchestrator resolve` command with preview and `--apply` modes
  - Conflict detection for merge and rebase operations
  - 3-way merge via `git merge-file`
  - Git `rerere` integration for resolution caching
  - Interactive escalation with ours/theirs/both/editor options
  - Status integration with conflict warnings
  - Files: `src/git_conflict_resolver.py`, CLI in `src/cli.py`

- **CORE-023-P2: Conflict Resolution - LLM Integration**: Intelligent resolution for complex conflicts
  - `--use-llm` flag for `orchestrator resolve` command
  - Intent extraction with structured JSON output
  - Multi-provider support: OpenAI, Gemini, OpenRouter
  - Confidence-based escalation (HIGH=auto, MEDIUM=ask, LOW=escalate)
  - Tiered validation: conflict markers, syntax, JSON, YAML
  - Sensitive file protection (skips .env, secrets, keys)
  - Context-aware with CLAUDE.md conventions and token budgets
  - 36 unit tests covering all functionality
  - Files: `src/resolution/llm_resolver.py`

- **WF-027: Workflow Finish Summary Archival**: Automatic persistence of completion summaries
  - Saves full `orchestrator finish` output to `docs/archive/YYYY-MM-DD_<task-slug>_summary.md`
  - Includes phase summaries, skipped items, external reviews, learnings
  - Solves terminal truncation and enables later reference
  - Displays save location confirmation

- **PRD-005: ApprovalGate + TmuxAdapter Integration**: Human-in-the-loop for parallel agents
  - Automatic pause at workflow gates for human approval
  - `ApprovalGate.get_decision_log()` tracks decisions with rationale
  - `ApprovalQueue.decision_summary()` groups by auto/human decisions
  - `orchestrator approval watch` with tmux bell notifications
  - `orchestrator approval summary` for decision analysis
  - 50 new tests; 21 in `tests/test_approval_gate.py`
  - Files: `src/approval_gate.py`, `src/approval_queue.py`, `src/prd/tmux_adapter.py`

- **PRD-006: Auto-Inject ApprovalGate in spawn_agent()**: Zero-config approval system
  - Automatic injection of approval gate instructions during agent spawning
  - Added `inject_approval_gate: bool = True` to TmuxConfig/SubprocessConfig
  - `--no-approval-gate` CLI flag for opt-out
  - 13 new tests (8 TmuxAdapter, 5 SubprocessAdapter)
  - Maintains backward compatibility

- **Parallel Agent Approval System**: Coordinate multiple Claude Code agents with approval gates
  - `ApprovalQueue`: SQLite-backed queue with WAL mode for concurrent agent access
  - `ApprovalGate`: Agent-side interface with exponential backoff polling (2s → 10s → 30s)
  - State machine: PENDING → APPROVED/REJECTED → CONSUMED (consume-once semantics)
  - Risk-based auto-approval: LOW auto-approves, CRITICAL always requires human
  - Heartbeat tracking + TTL expiration for stuck agent detection
  - CLI commands: `approval pending`, `approve`, `reject`, `approve-all`, `stats`, `cleanup`
  - 29 new tests covering queue operations, concurrency, and maintenance

### Changed
- **CLAUDE.md**: Added documentation for approval commands in Key Commands table

## [2.3.0] - 2026-01-10

### Added
- **PRD-001: Claude Squad Integration Phase 1**: Architecture simplification for agent spawning
  - Replaced complex multi-backend spawning with Claude Squad integration
  - New files: `src/prd/squad_adapter.py`, `src/prd/squad_capabilities.py`, `src/prd/session_registry.py`
  - CLI commands: `prd check-squad`, `prd spawn`, `prd sessions`, `prd attach`, `prd done`
  - Persistent session state registry
  - Capability-aware agent selection
  - Removed: Modal/Render/local subprocess backends (`worker_pool.py`, `backends/local.py`, `backends/modal_worker.py`, `backends/render.py`)
  - Retained: GitHub Actions batch execution, branch management, conflict resolution

- **PRD-004: Direct tmux Agent Management**: Replaced broken Claude Squad integration with direct tmux session management
  - `TmuxAdapter`: Spawns Claude Code agents in tmux windows for interactive sessions
  - `SubprocessAdapter`: Fire-and-forget fallback when tmux unavailable
  - `BackendSelector`: Auto-detects tmux, falls back to subprocess
  - Happy integration via `CLAUDE_BINARY=happy` config
  - 57 new tests covering both adapters

### Changed
- **CLI prd commands**: Now use new adapters instead of broken ClaudeSquadAdapter
  - `prd sessions`: Lists active agent sessions
  - `prd attach`: Attaches to tmux session (tmux only)
  - `prd done`: Marks task complete and terminates session
  - `prd cleanup`: Cleans up all sessions
- **ExecutionMode**: Added `SUBPROCESS` mode for non-tmux environments

### Fixed
- **Stale learnings in finish summary**: `orchestrator finish` now generates learning report BEFORE displaying summary, so current workflow learnings are shown instead of previous workflow's content

### Deprecated
- `ClaudeSquadAdapter` and `squad_capabilities.py` - kept for reference but no longer used

## [2.2.2] - 2026-01-10

### Fixed
- **Smarter API Key Check**: Now warns only when NO review API keys are set (was warning if ANY key missing)
  - At least one key (GEMINI, OPENAI, OPENROUTER, or XAI) enables reviews
  - Empty strings treated as missing
  - Less noisy UX for vibe coders
- **default_test Bug**: Fixed `check_project_mismatch` using wrong default (`npm run build` → `npm test`)
- **sops Command Syntax**: Fixed invalid bash syntax in API key loading instructions (now uses `yq`)

### Changed
- **Skip Summary Enhancement**: Now shows `item_id: description` format for better traceability
- **Gate Bypass Highlighting**: Force-skipped gate items now show `⚠️ GATE BYPASSED:` prefix in finish summary

### Added
- 4 new tests for API key check behavior (`TestAPIKeyCheck` class)

## [2.2.1] - 2026-01-08

### Added
- **Auto-Run Third-Party Reviews (WF-010)**: Automatically runs third-party model reviews when completing REVIEW phase items
  - `security_review` → runs security review via Codex
  - `quality_review` → runs quality review via Codex
  - `architecture_review` → runs holistic review via Gemini
  - Blocks completion if review fails or finds blocking issues
  - Captures review results in completion notes
  - `--skip-auto-review` flag available (not recommended)
  - Guides users to `skip --reason` if review infrastructure unavailable

## [2.2.0] - 2026-01-07

### Added
- **OpenRouter Streaming Support (CORE-012)**: Real-time response streaming
  - `execute_streaming()` method yields chunks as they arrive
  - `stream_to_console()` convenience method for interactive use
  - Handles stream interruption gracefully

- **Visual Verification Enhancements (VV-001 through VV-006)**:
  - **VV-001**: Auto-load style guide - `style_guide_path` parameter auto-loads and includes style guide in all verifications
  - **VV-002**: Workflow step integration - `run_all_visual_tests()` wires into workflow's `visual_regression_test` item
  - **VV-003**: Visual test discovery - `discover_visual_tests()` scans `tests/visual/*.md` files with YAML frontmatter
  - **VV-004**: Baseline management - `save_baseline()`, `get_baseline()`, `compare_with_baseline()` with hash-based comparison
  - **VV-006**: Cost tracking - `UsageInfo` dataclass with token counts and estimated cost from service

- **Model Selection Guidance (WF-003)**: `get_latest_model(category)` in model registry
  - Categories: `codex`, `gemini`, `claude` and aliases (`security`, `quality`, `consistency`, `holistic`)
  - Returns latest available model for review routing

- **Changelog/Roadmap Automation**: New `update_changelog_roadmap` item in LEARN phase
  - Prompts to move completed roadmap items to changelog
  - Configurable `roadmap_file` and `changelog_file` settings in workflow.yaml

- **CLI Enhancements**:
  - `visual-verify-all` command for running all visual tests in a directory
  - `--device` flag for device presets (e.g., `iphone-14`, `desktop`)
  - `--show-cost` flag for cost/token display
  - `--save-baseline` flag for baseline screenshot management

### Changed
- Visual verification client now returns `VerificationResult` dataclass instead of dict
- Mobile viewport updated to iPhone 14 dimensions (390x844)
- API key is now optional for visual verification (for unprotected services)

### Integration
- Updated `visual-verification-service` with cost tracking (`usage` field in response)

## [2.1.0] - 2026-01-06

### Added
- **Global Installation (CORE-018)**: pip-installable package with bundled default workflow
  - `pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git`
  - `orchestrator init` command to create local workflow.yaml
  - Config discovery: local workflow.yaml > bundled default
  - Works in Claude Code Web, Manus, and local environments

- **TDD-Enforced Test Ordering (WF-005)**: EXECUTE phase now enforces tests-first
  - `write_tests` (RED) before `implement_code` (GREEN)
  - Operating notes explain TDD rationale

- **Improved LEARN Phase (WF-006)**: Explicit action approval before applying
  - `propose_actions` → `approve_actions` → `apply_approved_actions`
  - User must approve specific changes before they're embedded

- **Commit and Sync Step (WF-007)**: Final workflow item prompts to commit
  - Auto-generates commit message from task description and changes
  - Prompts user before committing and pushing to main

- **Auto-Setup Hook Commands (CORE-019)**: Easy setup for Claude Code sessions
  - `orchestrator install-hook` - Installs SessionStart hook for auto-setup
  - `orchestrator uninstall-hook` - Removes the hook
  - Always gets latest version with `--upgrade`
  - Works in Claude Code CLI and Claude Code Web

### Changed
- EXECUTE phase item order: write_tests now comes before implement_code
- LEARN phase restructured for explicit action approval
- Version bumped to 2.0.0 in CLI

## [2.0.0] - 2026-01-06

### Added
- **Multi-Model Review Routing (CORE-016)**: Route reviews to different AI models
  - Security/Quality → Codex
  - Consistency/Holistic → Gemini
  - CLI mode (Codex/Gemini CLIs) or API mode (OpenRouter)
  - `setup-reviews` command for GitHub Actions bootstrap

- **Provider Abstraction (CORE-001)**: Generic provider interface
  - OpenRouter, Claude Code, Manual providers
  - `--provider` and `--model` CLI flags

- **Environment Detection (CORE-002)**: Auto-detect Claude Code, Manus, Standalone

- **Operating Notes (CORE-003)**: `notes` field on phases and items
  - Categories: `[tip]`, `[caution]`, `[learning]`, `[context]`

- **Task Constraints (CORE-004)**: `--constraints` flag on start command

- **Checkpoint/Resume (CORE-005)**: Save and restore workflow state
  - `orchestrator checkpoint`, `orchestrator resume`
  - Auto-checkpoint on phase transitions

- **Visual Verification**: AI-powered UAT testing
  - `visual-verify`, `visual-template` commands
  - Desktop and mobile viewport testing
  - Style guide integration

- **SOPS Secrets Management**: Backported from quiet-ping-v6

## [1.0.0] - 2026-01-05

### Added
- Core workflow engine with phase/item state machine
- YAML-based workflow definitions
- Active verification (file_exists, command, manual_gate)
- Claude Code CLI integration
- Analytics and learning engine
- Web dashboard
- Security hardening (injection protection, path traversal)
- Version-locked workflow definitions in state
- Template variable substitution
