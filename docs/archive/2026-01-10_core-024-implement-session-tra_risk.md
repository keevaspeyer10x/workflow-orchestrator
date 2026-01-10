# PRD-004 Risk Analysis

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| tmux not installed on target system | Medium | Low | Subprocess fallback handles this |
| tmux session name collisions | Low | Medium | Use unique prefix `wfo-{workflow_id}` |
| Orphaned tmux sessions on crash | Medium | Low | Cleanup command + reconciliation |
| Breaking existing tests | High | Medium | Update tests before merging |
| Claude --print behavior changes | Low | High | Pin to known-good behavior |
| Prompt file left on disk | Low | Low | Cleanup in done/cleanup commands |

## Detailed Analysis

### 1. tmux Availability
- **Risk:** tmux not installed in CI, containers, Windows
- **Mitigation:** SubprocessAdapter as automatic fallback
- **Detection:** `shutil.which("tmux")` returns None

### 2. Session Naming
- **Risk:** Multiple workflows create conflicting session names
- **Mitigation:** Include workflow ID in session name: `wfo-{wf_id}-main`
- **Already handled:** `_generate_session_name()` sanitizes task IDs

### 3. Orphaned Sessions
- **Risk:** Orchestrator crashes, tmux sessions keep running
- **Mitigation:**
  - `orchestrator prd cleanup` kills all wfo-* sessions
  - SessionRegistry marks orphaned on reconciliation
  - tmux sessions are visible (`tmux ls`) for manual cleanup

### 4. Test Breakage
- **Risk:** Existing squad_adapter tests fail
- **Mitigation:** Create new test file, deprecate old tests gradually
- **Approach:** Tests mock subprocess, don't need real tmux

### 5. Claude CLI Changes
- **Risk:** `claude --print` flag changes or removed
- **Mitigation:** Adapter abstraction allows quick fix
- **Detection:** Validate output on spawn

### 6. File Cleanup
- **Risk:** `.wfo_prompt_*.txt` files accumulate
- **Mitigation:** Delete in `kill_agent()` and `cleanup()`

## Security Considerations

| Concern | Assessment |
|---------|------------|
| Prompt injection via task_id | Low - sanitized with regex |
| tmux command injection | Low - using list args, not shell |
| Sensitive data in prompt files | Medium - files in working dir, user-controlled |
| Session hijacking | Low - requires local access |

## Rollback Plan

If issues discovered:
1. `backend_selector.py` can force `MANUAL` mode
2. Old `squad_adapter.py` remains (deprecated, not deleted)
3. SessionRegistry format unchanged - no migration needed
