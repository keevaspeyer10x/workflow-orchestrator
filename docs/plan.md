# PRD-001: Claude Squad Integration - Implementation Plan

## Executive Summary

Integrate Workflow Orchestrator with [Claude Squad](https://github.com/smtg-ai/claude-squad) to enable:
- Managing multiple concurrent Claude Code sessions
- Persistent session state across orchestrator restarts
- Hybrid execution (interactive local + batch remote)
- Simplified backend architecture (5 files removed)

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude Squad CLI changes | Medium | High | Capability detection, version pinning, fallback strategies |
| tmux not available on system | Low | Medium | Clear error messages, manual fallback mode |
| Session state desync | Medium | Medium | Reconciliation on every operation, orphan detection |
| Machine reboot mid-task | Low | High | Persistent registry, automatic orphan cleanup |
| Session name collision | Low | Low | Unique prefix (wfo-), task ID sanitization |
| File lock contention | Low | Low | filelock library handles gracefully |
| Subprocess timeouts | Medium | Low | Configurable timeout, graceful error handling |

## Dependencies

**Required:**
- `filelock` - File-based locking for registry
- Claude Squad CLI installed (user responsibility)

**Optional:**
- GitHub Actions - For batch/remote execution
- tmux - Required by Claude Squad

## Implementation Order

### Phase 1: Core Components

#### 1.1 src/prd/session_registry.py (DONE)
- Persistent session storage in `.claude/squad_sessions.json`
- File locking via `filelock` for thread safety
- Session reconciliation with Claude Squad state
- Automatic cleanup of old sessions (>7 days)
- Status tracking: pending, running, completed, terminated, orphaned

#### 1.2 src/prd/squad_capabilities.py (DONE)
- Detect Claude Squad installation via `--version`
- Parse `--help` for command/flag support
- Validate minimum required capabilities
- Fail fast if incompatible
- Support alternative flag names (--dir/--directory)

#### 1.3 src/prd/squad_adapter.py (DONE)
- Main adapter using registry and capabilities
- Session name sanitization (alphanumeric only)
- Idempotent spawn operations (safe to retry)
- Robust output parsing with 3 fallback strategies
- Explicit session termination on completion

#### 1.4 src/prd/backend_selector.py (DONE)
- Hybrid mode selection (interactive/batch/manual)
- Auto-detect available backends
- Priority: Claude Squad > GitHub Actions > Manual

### Phase 2: CLI Commands

#### 2.1 Commands to Add
```bash
orchestrator prd check-squad    # Check compatibility
orchestrator prd spawn          # Spawn sessions for tasks
orchestrator prd sessions       # List active sessions
orchestrator prd attach <id>    # Attach to session
orchestrator prd done <id>      # Mark complete
orchestrator prd cleanup        # Clean orphaned sessions
```

### Phase 3: Integration

#### 3.1 Update executor.py
- Replace WorkerPool with BackendSelector
- Use ClaudeSquadAdapter for interactive mode
- Retain GitHubActionsBackend for batch mode

### Phase 4: Cleanup

#### 4.1 Files to Remove
- `src/prd/worker_pool.py` - Replaced by BackendSelector
- `src/prd/backends/local.py` - Claude Squad replaces local spawning
- `src/prd/backends/modal_worker.py` - Not needed (cloud)
- `src/prd/backends/render.py` - Not needed (cloud)
- `src/prd/backends/sequential.py` - Claude Squad handles this

#### 4.2 Files to Retain
- `src/prd/backends/github_actions.py` - For batch mode
- `src/prd/backends/manual.py` - Fallback
- `src/prd/backends/base.py` - Interface

### Phase 5: Testing

#### 5.1 Test Files
- `tests/prd/test_session_registry.py` (DONE)
- `tests/prd/test_squad_capabilities.py` (DONE)
- `tests/prd/test_squad_adapter.py` (DONE)
- `tests/prd/test_backend_selector.py` (TODO)

## Success Criteria

1. [ ] Claude Squad spawns sessions with one command
2. [ ] Sessions survive orchestrator restart
3. [ ] Orphaned sessions detected and cleaned up
4. [ ] Completed work integrates with existing merge flow
5. [ ] 5 deprecated backend files removed
6. [ ] All tests pass
7. [ ] Clear error if Claude Squad not installed

## Workflow Issues Identified

**Issue: Plan verification expects docs/plan.md**
- The orchestrator's PLAN phase verification expects a `docs/plan.md` file
- This isn't documented in CLAUDE.md or workflow.yaml
- **Recommendation:** Add to ROADMAP - make plan file path configurable or document requirement

## References

- Design: `docs/designs/claude_squad_integration_detailed.md`
- AI Reviews: GPT-5.2, Gemini 2.5 Pro, Grok 4
- Claude Squad: https://github.com/smtg-ai/claude-squad
