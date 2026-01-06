# Changelog

All notable changes to the workflow-orchestrator.

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
