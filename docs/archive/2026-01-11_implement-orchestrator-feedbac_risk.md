# PRD-008: Zero-Config Workflow Enforcement - Risk Analysis

**Date:** 2026-01-11
**Status:** Planning Phase

## Executive Summary

PRD-008 has **MEDIUM overall risk**. Primary concerns are subprocess management and portability across environments. Mitigation strategies are well-defined and testable.

## Risk Categories

### 1. Technical Risks

#### 1.1 Server Port Conflicts
**Severity:** MEDIUM | **Probability:** MEDIUM | **Impact:** Service disruption

**Description:**
Auto-starting orchestrator server may fail if port 8000 already in use by another service.

**Scenarios:**
- User already running orchestrator manually
- Another service bound to port 8000 (common dev port)
- Multiple `orchestrator enforce` calls in parallel

**Mitigation:**
1. **Port scanning:** Check ports 8000, 8001, 8002 in sequence
2. **Health check first:** Always check if server is reachable before starting
3. **Clear error messages:** "Port 8000 in use. Try --port 8001 or stop existing server."
4. **PID file tracking:** Store `.orchestrator/server.pid` to detect our own servers
5. **Graceful fallback:** Allow `--port` flag for manual override

**Testing:**
- Unit test: Mock port binding errors
- Integration test: Start server on 8000, verify `enforce` detects it
- Integration test: Force port conflict, verify fallback to 8001

**Residual Risk:** LOW (after mitigation)

---

#### 1.2 Subprocess Management & Daemon Cleanup
**Severity:** HIGH | **Probability:** LOW | **Impact:** Resource leaks, zombie processes

**Description:**
Background server processes may not clean up properly if `orchestrator enforce` crashes or user kills terminal.

**Scenarios:**
- User Ctrl+C during server startup
- Terminal crashes during daemon spawn
- Multiple orphaned orchestrator processes accumulate
- PID file points to dead process or wrong process

**Mitigation:**
1. **PID file management:**
   - Write PID immediately after spawn
   - Check PID validity before reusing (process exists + is our server)
   - Delete PID file on clean shutdown
2. **Health check confirmation:**
   - Wait up to 10 seconds for server to respond to /health
   - If health check fails, kill process and clean up PID file
3. **Daemon detachment:**
   - Use `subprocess.Popen()` with proper detach flags
   - Redirect stdout/stderr to `.orchestrator/server.log`
   - Close stdin to prevent blocking
4. **Cleanup command:**
   - Add `orchestrator cleanup` to kill orphaned servers
   - Document in error messages
5. **Process ownership check:**
   - Verify PID in PID file belongs to orchestrator process
   - Check process command line matches expected

**Testing:**
- Unit test: Mock subprocess failures
- Integration test: Kill orchestrator during startup, verify cleanup
- Integration test: Multiple sequential starts, verify no duplicates
- Manual test: Verify daemon survives terminal close

**Residual Risk:** MEDIUM (requires thorough testing)

---

#### 1.3 Workflow Template Inadequacy
**Severity:** LOW | **Probability:** MEDIUM | **Impact:** User frustration, manual editing

**Description:**
Auto-generated workflow.yaml may not fit all project types. Template might be too rigid or miss important project-specific requirements.

**Scenarios:**
- Unusual test frameworks (Mocha, pytest-bdd, etc.)
- Multi-language projects (Python + JS frontend)
- Custom build systems (Bazel, Buck, etc.)
- Projects without tests (documentation, infrastructure)

**Mitigation:**
1. **Start simple, iterate:**
   - Launch with support for Python/pytest, JS/jest, Go/go test, Rust/cargo test
   - Add more frameworks based on user feedback
2. **Manual override:**
   - Check for existing `agent_workflow.yaml` first
   - Users can create custom workflow and it will be used
   - Document customization in `docs/ENFORCE_COMMAND.md`
3. **Graceful degradation:**
   - If repo type undetected, use generic template
   - Template should work for most projects (read/write/test)
4. **Clear messaging:**
   - Print "Generated workflow for Python/pytest. Edit .orchestrator/agent_workflow.yaml to customize."

**Testing:**
- Unit test: Test detection for each supported language
- Unit test: Test fallback for unknown project types
- Integration test: Verify custom workflow.yaml is respected

**Residual Risk:** LOW (user has full control)

---

#### 1.4 Agent Instruction Misinterpretation
**Severity:** MEDIUM | **Probability:** LOW | **Impact:** Agent confused, workflow fails

**Description:**
AI agent might misunderstand stdout instructions or fail to use Agent SDK correctly.

**Scenarios:**
- Agent doesn't see stdout output (terminal issue)
- Agent misparses instruction format
- Agent tries to use SDK without importing correctly
- Agent skips reading `.orchestrator/agent_instructions.md`

**Mitigation:**
1. **Structured output:**
   - Use clear section headers with `===` borders
   - Include executable code snippets
   - Highlight key information (SERVER URL, TASK)
2. **Dual delivery:**
   - Print to stdout (AI sees immediately)
   - Write to `.orchestrator/agent_instructions.md` (backup reference)
3. **Examples over explanation:**
   - Show complete code snippet for SDK usage
   - Include actual values (server URL, task description)
   - Avoid abstract instructions
4. **Testing with real agents:**
   - Manual test with Claude Code
   - Verify agent can follow instructions end-to-end
5. **Fallback instructions:**
   - If agent confused, user can say "Read .orchestrator/agent_instructions.md"

**Testing:**
- Manual test: Run `orchestrator enforce` and verify output clarity
- Integration test: Verify `.orchestrator/agent_instructions.md` created correctly
- Dogfooding: Use it for real tasks, iterate on format

**Residual Risk:** LOW (dual delivery + examples)

---

### 2. Operational Risks

#### 2.1 Hidden Server Processes
**Severity:** LOW | **Probability:** LOW | **Impact:** User confusion, resource usage

**Description:**
Users may not realize orchestrator server is running in background, leading to confusion or resource concerns.

**Scenarios:**
- User forgets server is running, tries to start manually
- Multiple projects spawn multiple servers
- User concerned about CPU/memory usage
- User doesn't know how to stop server

**Mitigation:**
1. **Clear messaging:**
   - Print "✓ Orchestrator running on http://localhost:8000 (PID: 12345)"
   - Include in error messages: "Server already running at..."
2. **Status command:**
   - `orchestrator status` shows if server running
   - `orchestrator ps` lists all running servers (if multiple projects)
3. **Stop command:**
   - Document `orchestrator stop` or `kill $(cat .orchestrator/server.pid)`
   - Add to `orchestrator cleanup` command
4. **Resource monitoring:**
   - Server should be lightweight (<50MB RAM, <1% CPU idle)
   - Log warnings if resource usage high
5. **Auto-shutdown option:**
   - Consider `--timeout` flag to auto-stop server after inactivity
   - Document in help: "Server runs until you stop it or reboot"

**Testing:**
- Manual test: Verify clear messaging
- Performance test: Measure server resource usage

**Residual Risk:** VERY LOW (informational issue)

---

#### 2.2 .orchestrator/ Directory Clutter
**Severity:** LOW | **Probability:** MEDIUM | **Impact:** User annoyance, repo clutter

**Description:**
.orchestrator/ directory may accumulate files (workflows, logs, PIDs) that users don't want in their repo.

**Scenarios:**
- Multiple workflow.yaml versions created
- Server logs grow large
- PID files from old servers remain
- User doesn't know what's safe to delete

**Mitigation:**
1. **Default gitignore:**
   - Create `.orchestrator/.gitignore` on first run
   - Ignore: `*.pid`, `*.log`, `server.log`, `enforce.log`
   - Don't ignore: `agent_workflow.yaml` (user might want to version control)
2. **Cleanup command:**
   - `orchestrator cleanup` removes old PIDs, logs
   - Document safe cleanup practices
3. **Log rotation:**
   - Limit server.log to 10MB
   - Keep only last 5 log files
4. **Clear documentation:**
   - Explain .orchestrator/ contents in `docs/ENFORCE_COMMAND.md`
   - Document what's safe to delete, what's important

**Testing:**
- Unit test: Verify .gitignore creation
- Integration test: Verify cleanup command works

**Residual Risk:** VERY LOW (standard practice)

---

#### 2.3 Cross-Platform Compatibility
**Severity:** MEDIUM | **Probability:** MEDIUM | **Impact:** Windows/Mac users can't use feature

**Description:**
Subprocess management, daemon spawning, PID files may behave differently on Windows vs Linux/Mac.

**Scenarios:**
- Windows doesn't support Unix-style daemon detach
- PID file paths use wrong separator (\ vs /)
- Process management commands differ (ps vs tasklist)
- Health check timing differs

**Mitigation:**
1. **Use Python's platform-agnostic APIs:**
   - `pathlib.Path` for all paths (handles separators)
   - `subprocess.Popen()` works on all platforms
   - `psutil` library for cross-platform process management
2. **Platform-specific code:**
   - Detect OS with `sys.platform`
   - Windows: Use `CREATE_NEW_PROCESS_GROUP` flag
   - Linux/Mac: Use `os.setsid()` for daemon detach
3. **Testing on all platforms:**
   - CI runs tests on Linux, Mac, Windows
   - Manual testing on Windows
4. **Fallback for Windows:**
   - If daemon spawn fails, run server in foreground
   - Warn user: "Windows: Server running in foreground. Don't close this terminal."

**Testing:**
- CI: Run integration tests on Linux, Mac, Windows
- Manual test: Verify on Windows 11

**Residual Risk:** MEDIUM (Windows complexity)

---

### 3. Security Risks

#### 3.1 Arbitrary Code Execution via Auto-Start
**Severity:** LOW | **Probability:** VERY LOW | **Impact:** Security vulnerability

**Description:**
Auto-starting orchestrator server executes code (`python -m src.orchestrator.api`). If malicious code injected into repo, it could execute.

**Scenarios:**
- User clones malicious repo with modified `src/orchestrator/api.py`
- Attacker compromises repo, adds malicious code
- User runs `orchestrator enforce` without reviewing code

**Mitigation:**
1. **This is not a new risk:**
   - User already trusts repo by using orchestrator
   - Running tests/builds also executes repo code
   - Not specific to auto-start feature
2. **Standard security practices:**
   - Review code before using in new repos
   - Use virtual environments
   - Run in containers for untrusted code
3. **Documentation:**
   - Document trust model in README
   - Recommend code review for new repos

**Residual Risk:** VERY LOW (no worse than existing risk)

---

#### 3.2 PID File Race Conditions
**Severity:** LOW | **Probability:** VERY LOW | **Impact:** Wrong process killed

**Description:**
If PID file is stale and PID reused by different process, `orchestrator stop` could kill wrong process.

**Scenarios:**
- Orchestrator crashes, PID file not cleaned up
- PID in file reused by different process
- User runs `orchestrator stop`, kills unrelated process

**Mitigation:**
1. **Process verification:**
   - Check process command line matches expected
   - Verify process owner is current user
   - Use `psutil` for robust process inspection
2. **Stale PID detection:**
   - If PID exists but command doesn't match, warn user
   - Don't auto-kill without verification
3. **Atomic PID file operations:**
   - Write PID atomically with file lock
   - Delete PID file before starting new server

**Testing:**
- Unit test: Mock stale PID scenarios
- Integration test: Verify safe handling of stale PIDs

**Residual Risk:** VERY LOW (careful verification)

---

### 4. User Experience Risks

#### 4.1 Unclear Error Messages
**Severity:** LOW | **Probability:** MEDIUM | **Impact:** User frustration, support burden

**Description:**
If auto-setup fails, error messages might not guide user to fix the issue.

**Scenarios:**
- Port conflict error doesn't suggest solution
- Repo analysis fails, doesn't explain why
- Server health check timeout, no context

**Mitigation:**
1. **Actionable error messages:**
   - Bad: "Server failed to start"
   - Good: "Server failed to start on port 8000 (already in use). Try: orchestrator enforce --port 8001"
2. **Include context:**
   - Show what was attempted
   - Suggest specific fix
   - Link to docs if complex
3. **Logging for debugging:**
   - Write detailed logs to `.orchestrator/enforce.log`
   - Error message says: "See .orchestrator/enforce.log for details"
4. **Common issues documented:**
   - Troubleshooting section in `docs/ENFORCE_COMMAND.md`

**Testing:**
- Unit test: Verify error messages are clear
- Manual test: Force errors, verify user can fix them

**Residual Risk:** LOW (good practices)

---

#### 4.2 Portability Across Repos
**Severity:** LOW | **Probability:** LOW | **Impact:** Feature doesn't work in other projects

**Description:**
Feature might only work in workflow-orchestrator repo, not in arbitrary user repos.

**Scenarios:**
- Assumes orchestrator is installed in PATH (might not be)
- Assumes workflow-orchestrator repo is in specific location
- Hard-coded paths break in other repos

**Mitigation:**
1. **Installation requirement:**
   - User must install orchestrator via `install.sh`
   - This adds orchestrator to PATH
   - Document clearly in README
2. **Relative paths only:**
   - All paths relative to current repo
   - No assumptions about repo location
3. **Testing in different repos:**
   - Create test repos in /tmp
   - Verify `orchestrator enforce` works
4. **Documentation:**
   - Show examples in different repos
   - Document installation requirement

**Testing:**
- Integration test: Test in temporary directory
- Manual test: Test in different repo

**Residual Risk:** VERY LOW (if tested properly)

---

## Risk Summary Matrix

| Risk | Severity | Probability | Impact | Residual Risk |
|------|----------|-------------|--------|---------------|
| Server port conflicts | Medium | Medium | Service disruption | LOW |
| Subprocess management | High | Low | Resource leaks | MEDIUM |
| Workflow template inadequacy | Low | Medium | User frustration | LOW |
| Agent instruction misinterpretation | Medium | Low | Workflow fails | LOW |
| Hidden server processes | Low | Low | User confusion | VERY LOW |
| .orchestrator/ clutter | Low | Medium | Repo clutter | VERY LOW |
| Cross-platform compatibility | Medium | Medium | Windows users affected | MEDIUM |
| Arbitrary code execution | Low | Very Low | Security risk | VERY LOW |
| PID file race conditions | Low | Very Low | Wrong process killed | VERY LOW |
| Unclear error messages | Low | Medium | User frustration | LOW |
| Portability across repos | Low | Low | Feature limited | VERY LOW |

## Overall Risk Assessment

**Overall Risk Level:** MEDIUM

**Primary Concerns:**
1. Subprocess management and cleanup (HIGH severity, LOW probability)
2. Cross-platform compatibility on Windows (MEDIUM severity, MEDIUM probability)

**Secondary Concerns:**
3. Port conflicts (MEDIUM severity, MEDIUM probability)
4. Agent instruction clarity (MEDIUM severity, LOW probability)

**All risks have defined mitigation strategies and test plans.**

## Risk Acceptance

### Acceptable Risks
- Workflow template may not fit all projects → Users can customize
- .orchestrator/ directory may accumulate files → Standard practice with gitignore
- Server runs in background → Clear messaging, status commands
- Windows daemon spawning complexity → Fallback to foreground mode

### Risks Requiring Extra Testing
- Subprocess management → Extensive integration tests
- Cross-platform compatibility → CI on all platforms
- PID file handling → Mock various failure scenarios

### Risks to Monitor Post-Launch
- Agent instruction format effectiveness → Dogfooding feedback
- Workflow template coverage → User feedback on supported frameworks
- Server resource usage → Monitor in production use

## Mitigation Checklist

- [x] Port conflict handling designed
- [ ] Port conflict tests written
- [ ] Subprocess management designed
- [ ] Subprocess cleanup tests written
- [ ] Cross-platform code paths designed
- [ ] CI configured for Linux/Mac/Windows
- [ ] Error messages reviewed for clarity
- [ ] Troubleshooting docs written
- [ ] PID file verification implemented
- [ ] Integration tests in temp repos
- [ ] Manual dogfooding test plan created

## Contingency Plans

### If subprocess management proves unreliable:
**Fallback:** Require user to start server manually
- Remove auto-start feature
- `orchestrator enforce` checks for running server, fails if not found
- Error message: "Start server with: orchestrator serve --daemon"
- Still provides workflow generation and instruction output

### If Windows compatibility is problematic:
**Fallback:** Document Linux/Mac only for v1
- Add Windows support in v1.1
- Provide Docker workaround for Windows users
- Most users are on Linux/Mac development environments

### If agent instruction format doesn't work:
**Fallback:** Interactive setup mode
- `orchestrator enforce` prompts user for information
- Generates workflow based on answers
- User manually shares setup with agent
- Less "zero-config" but still better than manual YAML creation

## Success Metrics

To validate risks are mitigated:

1. **Subprocess reliability:** Zero orphaned processes in 100 test runs
2. **Cross-platform:** All integration tests pass on Linux, Mac, Windows
3. **Agent clarity:** 90%+ success rate in dogfooding (agent follows instructions correctly)
4. **Error messages:** Users can fix errors without asking for help (qualitative feedback)
5. **Portability:** Works in 5 different test repos without modifications

## Next Steps

1. Implement with all mitigations in place
2. Write comprehensive tests for high-risk areas
3. Manual testing on all platforms
4. Dogfooding with real tasks
5. Monitor feedback and iterate
