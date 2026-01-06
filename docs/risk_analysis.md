# Risk Analysis: OpenRouter Function Calling for Interactive Repo Context

## Executive Summary

This feature adds function calling support to the OpenRouter provider, allowing models to interactively request file/code context. Overall risk is **LOW to MEDIUM** due to read-only operations and graceful fallback design.

---

## Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|------------|--------|----------|------------|
| R1: Path traversal | Medium | High | **Medium** | Validate paths, sandbox to working_dir |
| R2: Large file memory issues | Low | Medium | **Low** | Soft warning at 2MB, stream large files |
| R3: Infinite tool call loop | Low | Medium | **Low** | Soft warning at 50 calls, model decides |
| R4: API cost explosion | Medium | Medium | **Medium** | Log call counts, user visibility |
| R5: Breaking existing behavior | Low | High | **Medium** | Auto-detect, preserve fallback path |
| R6: Model compatibility issues | Medium | Low | **Low** | Maintain fallback, test major models |

---

## Detailed Risk Analysis

### R1: Path Traversal Attacks

**Description:** A malicious or confused model could request files outside the working directory (e.g., `../../etc/passwd`).

**Likelihood:** Medium - Models may generate unexpected paths.

**Impact:** High - Could expose sensitive system files.

**Mitigation:**
1. Resolve all paths relative to `working_dir`
2. Validate resolved path is within `working_dir` using `Path.resolve()`
3. Return error for paths outside sandbox
4. Never use user/model input directly in file operations

**Implementation:**
```python
def safe_read_file(path: str, working_dir: Path) -> str:
    resolved = (working_dir / path).resolve()
    if not resolved.is_relative_to(working_dir):
        return {"error": "Path outside working directory", "path": path}
    # ... proceed with read
```

---

### R2: Large File Memory Issues

**Description:** Reading very large files (multi-GB) could exhaust memory.

**Likelihood:** Low - Most code files are small; 2MB warning catches edge cases.

**Impact:** Medium - Process crash, poor UX.

**Mitigation:**
1. Soft warning at 2MB (log, don't block)
2. For files >10MB, consider streaming/chunking
3. Return file size in response so model can decide
4. Truncate extremely large files (>50MB) with clear message

**Implementation:**
```python
def execute_read_file(path: str, working_dir: Path) -> dict:
    file_size = file_path.stat().st_size
    if file_size > 2 * 1024 * 1024:  # 2MB
        logger.warning(f"Large file ({file_size / 1024 / 1024:.1f}MB): {path}")
    if file_size > 50 * 1024 * 1024:  # 50MB
        return {"content": "(file too large - 50MB limit)", "truncated": True}
    # ... read file
```

---

### R3: Infinite Tool Call Loop

**Description:** Model keeps calling tools without producing final output.

**Likelihood:** Low - Modern models handle tool loops well.

**Impact:** Medium - Wasted API costs, hung execution.

**Mitigation:**
1. Soft warning at 50 calls (log, don't block)
2. Hard limit at 200 calls as safety net
3. Include call count in final result metadata
4. Log each tool call for debugging

**Implementation:**
```python
MAX_TOOL_CALLS = 200  # Hard safety limit

while call_count < MAX_TOOL_CALLS:
    if call_count == 50:
        logger.warning("50+ tool calls - consider optimizing prompt")
    # ... execute tool
else:
    return ExecutionResult(
        success=False,
        error=f"Exceeded maximum tool calls ({MAX_TOOL_CALLS})"
    )
```

---

### R4: API Cost Explosion

**Description:** Many tool calls = many API round-trips = high costs.

**Likelihood:** Medium - Complex tasks may need many file reads.

**Impact:** Medium - Unexpected bills for users.

**Mitigation:**
1. Log total tool calls prominently in output
2. Include token usage in ExecutionResult metadata
3. Document expected costs in user guide
4. Consider adding `--max-tools` CLI flag (future enhancement)

---

### R5: Breaking Existing Behavior

**Description:** Changes to `execute()` could break existing workflows.

**Likelihood:** Low - Design preserves existing code path.

**Impact:** High - User workflows fail unexpectedly.

**Mitigation:**
1. Auto-detection: only use tools if model supports it
2. Preserve `_execute_basic()` as unchanged fallback
3. Extensive testing of both paths
4. Clear logging of which path is used

**Implementation:**
```python
def execute(self, prompt: str, model: str = None) -> ExecutionResult:
    if self._supports_function_calling(model):
        logger.info(f"Using function calling with {model}")
        return self.execute_with_tools(prompt, model)
    else:
        logger.info(f"Using basic execution with {model}")
        return self._execute_basic(prompt, model)
```

---

### R6: Model Compatibility Issues

**Description:** Different models may have different function calling formats/behaviors.

**Likelihood:** Medium - OpenRouter normalizes, but edge cases exist.

**Impact:** Low - Falls back gracefully.

**Mitigation:**
1. Start with known-good models (GPT-4+, Claude 3+, Gemini Pro)
2. Maintain allowlist of tested models
3. Fallback to basic execution on any tool-related errors
4. Log model-specific issues for improvement

---

## Security Considerations

### What We're NOT Doing (Intentionally)

| Capability | Status | Reason |
|------------|--------|--------|
| Shell command execution | **Excluded** | High risk, not needed for context |
| File writing | **Excluded** | Out of scope, security risk |
| Network requests | **Excluded** | Out of scope, security risk |
| Environment variables | **Excluded** | Could leak secrets |

### Defense in Depth

1. **Path sandboxing**: All file operations restricted to working_dir
2. **Read-only**: No write operations exposed
3. **No execution**: No shell/command capabilities
4. **Graceful failures**: Errors return messages, never crash

---

## Rollback Plan

If issues discovered post-deployment:

1. **Immediate**: Set `ORCHESTRATOR_DISABLE_TOOLS=1` env var to disable
2. **Quick fix**: Pin to models known to work
3. **Full rollback**: Revert to previous version (git revert)

---

## Monitoring & Observability

Add logging for:
- Each tool call (tool name, parameters, result size)
- Total tool calls per execution
- Execution time with vs without tools
- Fallback triggers (why basic mode was used)

---

## Conclusion

The feature is **LOW to MEDIUM risk** overall:
- Read-only operations limit blast radius
- Path sandboxing prevents traversal
- Graceful fallbacks preserve existing behavior
- Soft limits future-proof without blocking valid use cases

**Recommendation:** Proceed with implementation, with emphasis on:
1. Path validation (R1)
2. Good logging for cost visibility (R4)
3. Comprehensive testing of both code paths (R5)
