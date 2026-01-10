# Changelog

All notable changes to the workflow-orchestrator.

## [2.3.0] - 2026-01-10

### Added
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
