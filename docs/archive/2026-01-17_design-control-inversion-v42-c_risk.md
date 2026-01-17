# Control Inversion V4 - Risk Analysis

## Risk Assessment Matrix

| Risk | Severity | Likelihood | Mitigation | Residual Risk |
|------|----------|------------|------------|---------------|
| CLI integration conflicts | Medium | Low | Add new command without modifying existing commands | Low |
| State file conflicts with existing .orchestrator/ | Medium | Low | Use separate `.orchestrator/v4/` directory | Low |
| Import errors from circular dependencies | Medium | Medium | Follow strict dependency order in implementation | Low |
| Test failures due to spec deviations | Medium | Medium | Follow spec exactly, debug incrementally | Low |
| CommandGate security (shell injection) | High | Low | Use controlled inputs, defer allowlist to V4.2/Issue #75 | Medium |
| File locking failures on non-Unix | Medium | Low | fcntl is Unix-only; document limitation | Low |
| Claude Code subprocess timeout | Low | Medium | Configurable timeout with sensible default (1 hour) | Low |

## Detailed Analysis

### 1. CLI Integration Conflicts
**Risk:** The existing cli.py is large (~270KB). Adding a new command could conflict with existing code.

**Mitigation:**
- Add `cmd_run` as a new function (no modification to existing functions)
- Add parser registration at the end of the subparsers section
- No changes to existing command behavior

### 2. State File Conflicts
**Risk:** The existing orchestrator uses `.orchestrator/` directory for various state files.

**Mitigation:**
- V4 state lives in `.orchestrator/v4/state_{workflow_id}.json`
- Completely separate from existing V3 state files
- Both can coexist without interference

### 3. Import Errors
**Risk:** The new modules have dependencies on each other.

**Mitigation:**
- Follow strict creation order: models.py → state.py → parser.py → gate_engine.py → runners/ → executor.py → cli.py
- Test imports after each module creation

### 4. CommandGate Security
**Risk:** The CommandGate executes shell commands which could be exploited.

**Mitigation:**
- Commands come from YAML workflow files (not user input)
- Workflow files are controlled by repository owner
- Timeout limits prevent runaway processes
- Issue #75 tracks allowlist approach for additional security (V4.2)

### 5. Platform Compatibility
**Risk:** Uses `fcntl` for file locking which is Unix-only.

**Mitigation:**
- Document as Unix-only feature
- Windows users won't get file locking protection
- Not a blocking issue for initial release

## Impact Assessment

### Positive Impacts
1. **Reliability:** LLM cannot forget to complete workflow
2. **Consistency:** Gates validated programmatically
3. **Auditability:** Clear state tracking with checkpoints
4. **Extensibility:** Clean architecture for V4.2 additions

### Negative Impacts
1. **Learning curve:** Users need to learn `orchestrator run` command
2. **Backward compatibility:** Doesn't replace existing passive mode (yet)
3. **Platform limitation:** File locking Unix-only

## Acceptance

This risk analysis is acceptable. The primary risks are mitigated and the benefits outweigh the residual risks.
