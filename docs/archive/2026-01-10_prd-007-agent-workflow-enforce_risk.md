# PRD-006: Risk Analysis

## Risk Assessment Summary
**Overall Risk Level: LOW**

This is a straightforward enhancement with minimal risk:
- No new dependencies
- No database changes
- No breaking API changes
- Purely additive (string concatenation)

## Risks Identified

### Risk 1: Prompt Size Inflation
**Severity: Low | Likelihood: Low**

The approval gate instructions add ~100 lines to each agent prompt. Could this cause issues?

**Analysis:**
- Claude Code handles large prompts well
- Instructions are ~2KB, negligible vs context window
- Prompt files already contain multi-page content

**Mitigation:** None needed. Monitor prompt file sizes if issues arise.

### Risk 2: Hardcoded db_path Mismatch
**Severity: Medium | Likelihood: Low**

If the db_path in instructions doesn't match where the approval queue actually looks, agents will submit to the wrong database.

**Analysis:**
- Both use `working_dir / ".workflow_approvals.db"`
- Pattern is consistent with existing code
- CLI also uses this path (cli.py:2732)

**Mitigation:** Use a constant or function for the default path rather than hardcoding in multiple places.

### Risk 3: Agent Ignores Instructions
**Severity: Medium | Likelihood: Medium**

LLM agents may not follow the injected instructions correctly:
- May not import the approval module
- May not call request_approval() at correct times
- May use wrong risk levels

**Analysis:**
- This is inherent to LLM-based systems
- Instructions are clear and include code examples
- Agents already receive many instructions they must follow

**Mitigation:**
- Clear, actionable instructions with code snippets
- Future: Add LEARN phase feedback if agents skip approvals

### Risk 4: Opt-out Flag Ignored in Certain Code Paths
**Severity: Low | Likelihood: Low**

The `--no-approval-gate` flag might not propagate correctly if there are multiple code paths to spawn_agent().

**Analysis:**
- Currently only PRDExecutor.spawn() calls adapter.spawn_agent()
- Direct TmuxAdapter usage would use TmuxConfig default
- SubprocessAdapter needs same pattern

**Mitigation:** Ensure all spawn paths respect the config. Add tests for opt-out.

## Dependencies
- ApprovalQueue must exist at the specified path (created by PRD-005)
- generate_approval_gate_instructions() must be accessible (exists in tmux_adapter.py)

## Rollback Plan
If issues arise:
1. Set `inject_approval_gate=False` in TmuxConfig default
2. Or use `--no-approval-gate` flag on all spawn commands
3. No data migration needed

## Conclusion
This is a low-risk change. The main consideration is ensuring consistency between TmuxAdapter and SubprocessAdapter implementations.
