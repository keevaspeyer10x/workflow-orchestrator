# PRD-008: Zero-Config Workflow Enforcement Implementation Plan

**Status:** Planning
**Priority:** HIGH - Required for PRD-007 usability
**Complexity:** Medium
**Estimated Effort:** 5 days

## Executive Summary

Implement `orchestrator enforce` command that provides zero-configuration workflow enforcement for AI agents. This makes PRD-007 (Agent Workflow Enforcement System) actually usable by eliminating manual setup steps.

## Problem Statement

PRD-007 built a complete Agent Workflow Enforcement System, but using it requires:
1. Manually starting orchestrator server
2. Manually creating agent_workflow.yaml
3. Manually importing and using Agent SDK
4. Reading 125 pages of documentation

This defeats the purpose for vibe-coding workflows. Agents should just work.

## Solution Overview

Single command that auto-configures everything:
```bash
orchestrator enforce "Implement user authentication"
```

This will:
- Auto-detect or auto-start orchestrator server
- Auto-generate agent_workflow.yaml from repo analysis
- Output agent-ready instructions to stdout
- Create .orchestrator/agent_instructions.md as backup reference

## Design Decisions

### 1. Server Auto-Start
**Decision:** Auto-start with `--daemon` if not running
**Rationale:** Zero-config UX, graceful fallback if port in use

### 2. Workflow Generation
**Decision:** Template-based with repo detection (language, test framework)
**Rationale:** Fast, predictable, good enough for most projects. Avoid LLM complexity.

### 3. Agent Context Injection
**Decision:** Output to stdout + generate .orchestrator/agent_instructions.md
**Rationale:**
- AI agent sees stdout directly (zero human intervention)
- Backup file for reference/debugging
- Self-contained (works in any repo)
- Portable (doesn't rely on repo's CLAUDE.md)

### 4. Execution Mode Default
**Decision:** Sequential (single agent) by default, --parallel opt-in
**Rationale:** PRD-007 just completed, multi-agent needs validation. Proven workflow first.

### 5. Workflow Path
**Decision:** Check .orchestrator/agent_workflow.yaml → ./agent_workflow.yaml → auto-generate
**Rationale:** Hidden by default (clean), but users can override in root if they want version control

### 6. Command Structure
**Decision:** New `orchestrator enforce` subcommand
**Rationale:** Clear separation from regular orchestrator workflow, signals agent-specific enforcement

## Implementation Plan

### Phase 1: Core Auto-Setup Infrastructure (Days 1-3)

#### 1.1 Server Discovery & Auto-Start (`src/orchestrator/auto_setup.py`)
**Functions:**
- `check_server_health(url: str) -> bool` - HTTP health check
- `find_running_server() -> Optional[str]` - Check ports 8000-8002
- `start_orchestrator_daemon(port: int) -> str` - Background subprocess
  - Save PID to .orchestrator/server.pid
  - Wait for health confirmation
- `ensure_orchestrator_running() -> str` - Main entry point

**Testing:**
- Mock httpx for health checks
- Mock subprocess for daemon start
- Test port conflicts
- Test PID file creation

**Estimated:** 150 lines + 200 lines tests

---

#### 1.2 Workflow Generator (`src/orchestrator/workflow_generator.py`)
**Functions:**
- `analyze_repo(path: Path) -> RepoAnalysis` - Detect:
  - Language (Python/JS/Go/Rust)
  - Test framework (pytest/jest/go test)
  - Project structure
- `generate_workflow_yaml(task: str, analysis: RepoAnalysis) -> str`
  - 5-phase template: PLAN → TDD → IMPL → REVIEW → VERIFY
  - Customize allowed_tools by language
  - Customize gates by test framework
- `save_workflow_yaml(content: str, path: Path) -> Path`
  - Save to .orchestrator/agent_workflow.yaml
  - Create .gitignore

**Template:** `src/orchestrator/templates/workflow_template.yaml`
- 5 phases with standard gates
- Placeholders for customization
- Task metadata embedded

**Testing:**
- Test repo detection for each language
- Test YAML generation with different configurations
- Test file creation and gitignore

**Estimated:** 300 lines + 200 lines template + 250 lines tests

---

#### 1.3 Agent Instructions Generator (`src/orchestrator/agent_context.py`)
**Functions:**
- `generate_agent_instructions(task, server_url, workflow_path, mode) -> str`
  - Markdown with:
    - Task description
    - Setup confirmation
    - SDK usage example
    - Phase-specific guidance
    - Docs links
- `save_agent_instructions(content: str, path: Path) -> Path`
- `format_agent_prompt(instructions: str, server_url: str, mode: str) -> str`
  - Rich terminal output with boxes
  - Quick-start code snippet
  - Current phase tools

**Testing:**
- Test markdown generation
- Test formatting variations
- Test file save

**Estimated:** 200 lines + 150 lines tests

---

### Phase 2: CLI Integration (Day 4)

#### 2.1 Add `enforce` Command (`src/cli.py`)

**Command Signature:**
```bash
orchestrator enforce <task> [--parallel] [--sequential] [--port PORT] [--json]
```

**Implementation:**
```python
def cmd_enforce(args):
    # 1. Ensure server running
    server_url = ensure_orchestrator_running(port=args.port)

    # 2. Find or generate workflow
    workflow_path = find_or_generate_workflow(args.task)

    # 3. Generate instructions
    instructions = generate_agent_instructions(...)
    instructions_path = save_agent_instructions(...)

    # 4. Output prompt
    if args.json:
        print(json.dumps({...}))
    else:
        print(format_agent_prompt(...))
```

**Argument Parser:**
- `task` - Required task description
- `--parallel` - Use parallel mode (opt-in)
- `--sequential` - Use sequential mode (default)
- `--port` - Server port (default 8000)
- `--json` - Machine-readable output

**Testing:** `tests/integration/test_enforce_command.py`
- Test fresh repo (no server, no workflow)
- Test existing server (reuse)
- Test existing workflow (don't overwrite)
- Test --json output
- Test --parallel mode
- Test port conflicts

**Estimated:** 150 lines CLI + 300 lines integration tests

---

### Phase 3: Documentation Updates (Day 5)

#### 3.1 Update Existing Docs
- `CLAUDE.md` - Add agent context section
  - "If .orchestrator/agent_instructions.md exists, read it"
  - How to use `orchestrator enforce`
- `README.md` - Add Quick Start section
  - One-command setup example
- `docs/AGENT_SDK_GUIDE.md` - Add Zero-Config section
  - Point to `orchestrator enforce`

#### 3.2 Create New Docs
- `docs/ENFORCE_COMMAND.md` - Comprehensive guide
  - What it does
  - How it works
  - Usage examples
  - Language-specific notes
  - Troubleshooting

**Estimated:** 200 lines docs

---

## File Summary

### New Files (8)
1. `src/orchestrator/auto_setup.py` (~150 lines)
2. `src/orchestrator/workflow_generator.py` (~300 lines)
3. `src/orchestrator/agent_context.py` (~200 lines)
4. `src/orchestrator/templates/workflow_template.yaml` (~200 lines)
5. `tests/test_auto_setup.py` (~200 lines)
6. `tests/test_workflow_generator.py` (~250 lines)
7. `tests/integration/test_enforce_command.py` (~300 lines)
8. `docs/ENFORCE_COMMAND.md` (~150 lines)

### Modified Files (3)
1. `src/cli.py` (+150 lines)
2. `CLAUDE.md` (+20 lines)
3. `README.md` (+30 lines)

### Total
- **New Code:** ~1,950 lines
- **Modified Code:** ~200 lines
- **Test Code:** ~750 lines (38% of total)

## Risk Analysis

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Server port conflicts | Medium | Medium | Check multiple ports, clear error messages |
| Subprocess management issues | High | Low | PID tracking, health checks, cleanup on exit |
| Workflow template not fitting all projects | Low | Medium | Start simple, iterate based on feedback |
| AI agent misinterpreting stdout instructions | Medium | Low | Format with clear structure, provide examples |

### Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Users confused by auto-started server | Low | Low | Clear console output, health check endpoint |
| .orchestrator/ directory clutter | Low | Medium | Add to .gitignore by default |
| Different repos have different needs | Medium | High | Allow manual workflow.yaml override |

## Success Criteria

### Functional
✅ `orchestrator enforce "task"` works in fresh repo with zero setup
✅ Server auto-starts if not running
✅ Workflow.yaml auto-generates with correct language detection
✅ AI agent receives clear, actionable instructions
✅ Works in Python, JavaScript, Go, Rust repos

### Quality
✅ 85%+ test coverage
✅ All unit tests pass
✅ All integration tests pass
✅ Zero regressions in existing functionality

### User Experience
✅ Zero human intervention required
✅ Clear error messages for edge cases
✅ Works for other users (not just this repo)
✅ Documentation explains everything

## Dependencies

### Internal
- PRD-007 (Agent Workflow Enforcement) - ✅ Complete
- `src/orchestrator/api.py` - ✅ Exists
- `src/agent_sdk/client.py` - ✅ Exists

### External
- `httpx` - ✅ Already installed
- `fastapi` - ✅ Already installed
- `uvicorn` - ✅ Already installed

## Timeline

**Day 1:** `auto_setup.py` + tests (server management)
**Day 2:** `workflow_generator.py` + tests (YAML generation)
**Day 3:** `agent_context.py` + tests (instruction formatting)
**Day 4:** CLI integration + integration tests
**Day 5:** Documentation + manual testing + polish

**Total:** 5 days

## Open Questions

None - all design decisions confirmed with user.

## Acceptance Criteria

### For User Approval
- [ ] Implementation plan is clear and complete
- [ ] Design decisions are sound
- [ ] Risk analysis covers key concerns
- [ ] Timeline is realistic

### For Implementation Complete
- [ ] All 8 new files created and tested
- [ ] All 3 modified files updated
- [ ] 85%+ test coverage achieved
- [ ] All integration tests pass
- [ ] Documentation complete
- [ ] Manual testing in fresh repo succeeds
- [ ] Zero regressions in existing features

## Next Steps

After approval:
1. Create branch: `feature/prd-008-zero-config-enforcement`
2. Implement Phase 1 (auto_setup.py)
3. Implement Phase 2 (workflow_generator.py)
4. Implement Phase 3 (agent_context.py)
5. Implement Phase 4 (CLI integration)
6. Implement Phase 5 (Documentation)
7. Manual testing + polish
8. Create PR with comprehensive review
