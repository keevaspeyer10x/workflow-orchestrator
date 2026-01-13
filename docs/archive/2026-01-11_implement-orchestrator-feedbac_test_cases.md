# PRD-008: Zero-Config Workflow Enforcement - Test Cases

**Status:** Planning Phase
**Coverage Target:** 85%+ overall, 90%+ for critical paths

## Test Organization

```
tests/
├── test_auto_setup.py              # Unit tests for server management
├── test_workflow_generator.py      # Unit tests for YAML generation
├── test_agent_context.py           # Unit tests for instruction formatting
├── integration/
│   └── test_enforce_command.py     # End-to-end integration tests
└── manual/
    └── test_enforce_dogfooding.md  # Manual testing checklist
```

---

## Unit Tests

### 1. Server Auto-Setup (`tests/test_auto_setup.py`)

#### 1.1 Health Check Tests
**Test:** `test_check_server_health_success()`
- **Setup:** Mock httpx.get() to return 200 OK
- **Action:** Call `check_server_health("http://localhost:8000")`
- **Assert:** Returns True

**Test:** `test_check_server_health_failure()`
- **Setup:** Mock httpx.get() to raise ConnectionError
- **Action:** Call `check_server_health("http://localhost:8000")`
- **Assert:** Returns False

**Test:** `test_check_server_health_timeout()`
- **Setup:** Mock httpx.get() to timeout
- **Action:** Call `check_server_health("http://localhost:8000")`
- **Assert:** Returns False after timeout

---

#### 1.2 Server Discovery Tests
**Test:** `test_find_running_server_on_default_port()`
- **Setup:** Mock health check to succeed on port 8000
- **Action:** Call `find_running_server()`
- **Assert:** Returns "http://localhost:8000"

**Test:** `test_find_running_server_on_alternate_port()`
- **Setup:** Mock health check to fail on 8000, succeed on 8001
- **Action:** Call `find_running_server()`
- **Assert:** Returns "http://localhost:8001"

**Test:** `test_find_running_server_none_found()`
- **Setup:** Mock health check to fail on all ports (8000, 8001, 8002)
- **Action:** Call `find_running_server()`
- **Assert:** Returns None

---

#### 1.3 Daemon Start Tests
**Test:** `test_start_orchestrator_daemon_success()`
- **Setup:** Mock subprocess.Popen(), mock health check success
- **Action:** Call `start_orchestrator_daemon(port=8000)`
- **Assert:**
  - Returns "http://localhost:8000"
  - PID written to `.orchestrator/server.pid`
  - Subprocess called with correct arguments

**Test:** `test_start_orchestrator_daemon_health_check_timeout()`
- **Setup:** Mock subprocess.Popen(), mock health check never succeeds
- **Action:** Call `start_orchestrator_daemon(port=8000)`
- **Assert:**
  - Raises TimeoutError after 10 seconds
  - Process is killed
  - PID file is cleaned up

**Test:** `test_start_orchestrator_daemon_port_in_use()`
- **Setup:** Mock subprocess.Popen() to raise OSError (port in use)
- **Action:** Call `start_orchestrator_daemon(port=8000)`
- **Assert:**
  - Raises RuntimeError with clear message
  - Suggests trying different port

**Test:** `test_start_orchestrator_daemon_creates_log_file()`
- **Setup:** Mock subprocess.Popen()
- **Action:** Call `start_orchestrator_daemon(port=8000)`
- **Assert:**
  - `.orchestrator/server.log` file exists
  - Subprocess stdout/stderr redirected to log

---

#### 1.4 Ensure Server Running Tests
**Test:** `test_ensure_orchestrator_running_already_running()`
- **Setup:** Mock find_running_server() to return URL
- **Action:** Call `ensure_orchestrator_running()`
- **Assert:**
  - Returns existing server URL
  - Does NOT start new server

**Test:** `test_ensure_orchestrator_running_needs_start()`
- **Setup:**
  - Mock find_running_server() to return None
  - Mock start_orchestrator_daemon() to succeed
- **Action:** Call `ensure_orchestrator_running()`
- **Assert:**
  - Starts new server
  - Returns new server URL

**Test:** `test_ensure_orchestrator_running_start_fails()`
- **Setup:**
  - Mock find_running_server() to return None
  - Mock start_orchestrator_daemon() to raise RuntimeError
- **Action:** Call `ensure_orchestrator_running()`
- **Assert:**
  - Raises clear error message
  - Suggests manual start as fallback

---

### 2. Workflow Generator (`tests/test_workflow_generator.py`)

#### 2.1 Repo Analysis Tests
**Test:** `test_analyze_repo_python_pytest()`
- **Setup:** Create temp dir with:
  - `requirements.txt` with pytest
  - `tests/test_*.py` files
  - `src/` directory
- **Action:** Call `analyze_repo(temp_dir)`
- **Assert:**
  - `language == "python"`
  - `test_framework == "pytest"`
  - `test_command == "pytest"`

**Test:** `test_analyze_repo_javascript_jest()`
- **Setup:** Create temp dir with:
  - `package.json` with jest
  - `__tests__/` directory
  - `src/` directory
- **Action:** Call `analyze_repo(temp_dir)`
- **Assert:**
  - `language == "javascript"`
  - `test_framework == "jest"`
  - `test_command == "npm test"`

**Test:** `test_analyze_repo_go_project()`
- **Setup:** Create temp dir with:
  - `go.mod` file
  - `*_test.go` files
- **Action:** Call `analyze_repo(temp_dir)`
- **Assert:**
  - `language == "go"`
  - `test_framework == "go test"`
  - `test_command == "go test ./..."`

**Test:** `test_analyze_repo_rust_cargo()`
- **Setup:** Create temp dir with:
  - `Cargo.toml` file
  - `src/` directory
  - `tests/` directory
- **Action:** Call `analyze_repo(temp_dir)`
- **Assert:**
  - `language == "rust"`
  - `test_framework == "cargo test"`
  - `test_command == "cargo test"`

**Test:** `test_analyze_repo_unknown_type()`
- **Setup:** Create temp dir with no recognizable structure
- **Action:** Call `analyze_repo(temp_dir)`
- **Assert:**
  - `language == "unknown"`
  - `test_framework == "unknown"`
  - Falls back to generic configuration

---

#### 2.2 Workflow Generation Tests
**Test:** `test_generate_workflow_yaml_python()`
- **Setup:** Create RepoAnalysis for Python/pytest
- **Action:** Call `generate_workflow_yaml("Add login", analysis)`
- **Assert:** YAML contains:
  - `task: "Add login"`
  - `language: "python"`
  - `test_framework: "pytest"`
  - 5 phases (PLAN, TDD, IMPL, REVIEW, VERIFY)
  - Allowed tools include: `read_files`, `write_files`, `edit_files`, `bash`
  - Gates reference pytest

**Test:** `test_generate_workflow_yaml_javascript()`
- **Setup:** Create RepoAnalysis for JavaScript/jest
- **Action:** Call `generate_workflow_yaml("Add feature", analysis)`
- **Assert:** YAML contains:
  - `language: "javascript"`
  - `test_framework: "jest"`
  - Gates reference jest
  - Allowed tools appropriate for JS

**Test:** `test_generate_workflow_yaml_embeds_task()`
- **Setup:** Create RepoAnalysis
- **Action:** Call `generate_workflow_yaml("Very specific task description", analysis)`
- **Assert:**
  - YAML metadata includes full task description
  - Task is embedded in workflow for agent reference

---

#### 2.3 Workflow Save Tests
**Test:** `test_save_workflow_yaml_creates_directory()`
- **Setup:** Temp dir without .orchestrator/
- **Action:** Call `save_workflow_yaml(content, temp_dir)`
- **Assert:**
  - `.orchestrator/` directory created
  - `agent_workflow.yaml` written
  - `.orchestrator/.gitignore` created

**Test:** `test_save_workflow_yaml_existing_directory()`
- **Setup:** Temp dir with existing .orchestrator/
- **Action:** Call `save_workflow_yaml(content, temp_dir)`
- **Assert:**
  - Workflow written successfully
  - Existing files not affected

**Test:** `test_save_workflow_yaml_gitignore_contents()`
- **Setup:** Temp dir
- **Action:** Call `save_workflow_yaml(content, temp_dir)`
- **Assert:** `.orchestrator/.gitignore` contains:
  - `*.pid`
  - `*.log`
  - `server.log`
  - `enforce.log`

---

### 3. Agent Context Generation (`tests/test_agent_context.py`)

#### 3.1 Instruction Generation Tests
**Test:** `test_generate_agent_instructions_basic()`
- **Setup:** Basic parameters (task, server URL, workflow path, mode)
- **Action:** Call `generate_agent_instructions(...)`
- **Assert:** Markdown contains:
  - Task description
  - Server URL
  - Workflow file path
  - SDK import example
  - Phase instructions (PLAN phase)
  - Allowed/forbidden tools

**Test:** `test_generate_agent_instructions_sequential_mode()`
- **Setup:** mode="sequential"
- **Action:** Call `generate_agent_instructions(..., mode="sequential")`
- **Assert:** Instructions mention:
  - "Sequential mode (single agent)"
  - No references to parallel coordination

**Test:** `test_generate_agent_instructions_parallel_mode()`
- **Setup:** mode="parallel"
- **Action:** Call `generate_agent_instructions(..., mode="parallel")`
- **Assert:** Instructions mention:
  - "Parallel mode (multiple agents)"
  - Coordination through orchestrator

**Test:** `test_generate_agent_instructions_includes_sdk_example()`
- **Setup:** Standard parameters
- **Action:** Call `generate_agent_instructions(...)`
- **Assert:** Contains complete Python code snippet:
  ```python
  from src.agent_sdk.client import AgentClient
  client = AgentClient(...)
  task = client.claim_task(...)
  ```

---

#### 3.2 Prompt Formatting Tests
**Test:** `test_format_agent_prompt_structure()`
- **Setup:** Generate instructions
- **Action:** Call `format_agent_prompt(instructions, server_url, mode)`
- **Assert:** Output contains:
  - Header with `===` borders
  - "AGENT WORKFLOW READY" message
  - Server URL highlighted
  - Task description
  - SDK code snippet
  - Footer

**Test:** `test_format_agent_prompt_includes_quick_start()`
- **Setup:** Generate instructions
- **Action:** Call `format_agent_prompt(...)`
- **Assert:** Contains quick-start section with:
  - Current phase (PLAN)
  - Allowed tools list
  - Forbidden tools list
  - Next steps

---

#### 3.3 File Save Tests
**Test:** `test_save_agent_instructions_creates_file()`
- **Setup:** Generate instructions, temp dir
- **Action:** Call `save_agent_instructions(content, temp_dir)`
- **Assert:**
  - `.orchestrator/agent_instructions.md` created
  - Content matches input
  - File is readable

**Test:** `test_save_agent_instructions_overwrites_existing()`
- **Setup:** Existing old `agent_instructions.md`
- **Action:** Call `save_agent_instructions(new_content, temp_dir)`
- **Assert:**
  - Old content replaced
  - New content written

---

## Integration Tests

### 4. Enforce Command End-to-End (`tests/integration/test_enforce_command.py`)

#### 4.1 Fresh Repo Tests
**Test:** `test_enforce_fresh_repo_complete_flow()`
- **Setup:**
  - Create temp repo with Python/pytest structure
  - No server running
  - No workflow.yaml exists
- **Action:** Run `orchestrator enforce "Add login feature"`
- **Assert:**
  - Server starts successfully (PID file created)
  - `agent_workflow.yaml` generated
  - `agent_instructions.md` created
  - Stdout contains formatted prompt
  - All files in `.orchestrator/` directory

**Test:** `test_enforce_fresh_repo_port_conflict()`
- **Setup:**
  - Start dummy server on port 8000
  - Create temp repo
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Detects port 8000 in use
  - Tries port 8001
  - Server starts on 8001
  - Success message indicates port 8001

---

#### 4.2 Existing Server Tests
**Test:** `test_enforce_with_running_server()`
- **Setup:**
  - Start orchestrator server on 8000
  - Create temp repo
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Detects existing server
  - Does NOT start duplicate
  - Uses existing server at port 8000
  - Workflow and instructions created

**Test:** `test_enforce_respects_existing_workflow()`
- **Setup:**
  - Create temp repo
  - Manually create `agent_workflow.yaml` with custom content
  - Server running
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Existing workflow.yaml NOT overwritten
  - Custom content preserved
  - Instructions reference existing workflow

---

#### 4.3 Command Options Tests
**Test:** `test_enforce_with_port_flag()`
- **Setup:** Create temp repo
- **Action:** Run `orchestrator enforce "Task" --port 8002`
- **Assert:**
  - Server starts on port 8002
  - Instructions reference port 8002

**Test:** `test_enforce_with_json_output()`
- **Setup:** Create temp repo, start server
- **Action:** Run `orchestrator enforce "Task" --json`
- **Assert:**
  - Output is valid JSON
  - Contains: server_url, workflow_path, instructions_path, mode, task
  - No formatted text output

**Test:** `test_enforce_sequential_mode_explicit()`
- **Setup:** Create temp repo
- **Action:** Run `orchestrator enforce "Task" --sequential`
- **Assert:**
  - Instructions mention sequential mode
  - Workflow generated for single agent

**Test:** `test_enforce_parallel_mode()`
- **Setup:** Create temp repo
- **Action:** Run `orchestrator enforce "Task" --parallel`
- **Assert:**
  - Instructions mention parallel mode
  - Workflow includes coordination gates

---

#### 4.4 Error Handling Tests
**Test:** `test_enforce_invalid_repo_structure()`
- **Setup:** Create empty temp dir (no recognizable structure)
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Falls back to generic workflow template
  - Warning printed: "Could not detect project type, using generic workflow"
  - Workflow still generated

**Test:** `test_enforce_server_start_fails()`
- **Setup:**
  - Mock server start to fail (all ports in use)
  - Create temp repo
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Clear error message
  - Suggests manual server start
  - Suggests alternative ports
  - Exit code non-zero

---

#### 4.5 Language Detection Tests
**Test:** `test_enforce_python_project()`
- **Setup:** Create temp repo with:
  - `requirements.txt`
  - `tests/test_*.py`
  - `pytest.ini`
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Generated workflow has `language: python`
  - Test framework is pytest
  - Appropriate allowed_tools

**Test:** `test_enforce_javascript_project()`
- **Setup:** Create temp repo with:
  - `package.json`
  - `jest.config.js`
  - `__tests__/`
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Generated workflow has `language: javascript`
  - Test framework is jest
  - NPM commands in workflow

**Test:** `test_enforce_go_project()`
- **Setup:** Create temp repo with:
  - `go.mod`
  - `*_test.go` files
- **Action:** Run `orchestrator enforce "Task"`
- **Assert:**
  - Generated workflow has `language: go`
  - Test framework is `go test`
  - Go-specific tools

---

## Manual Testing

### 5. Dogfooding Tests (`tests/manual/test_enforce_dogfooding.md`)

These tests are performed manually by a human with an AI agent to validate the entire user experience.

#### 5.1 Fresh Repo - Python Project
**Test:** Use `orchestrator enforce` in a new Python project
- [ ] Clone a sample Python project
- [ ] Run `orchestrator enforce "Add feature X"`
- [ ] Verify server starts
- [ ] Verify workflow generated
- [ ] Share instructions with Claude Code agent
- [ ] Verify agent understands instructions
- [ ] Verify agent can use SDK
- [ ] Verify agent completes PLAN phase

**Success Criteria:**
- Agent requires zero human intervention beyond initial prompt
- Agent successfully uses SDK
- Workflow enforcement works

---

#### 5.2 Existing Workflow - Custom Project
**Test:** Use `orchestrator enforce` in project with custom workflow
- [ ] Create custom `agent_workflow.yaml` with non-standard phases
- [ ] Run `orchestrator enforce "Task"`
- [ ] Verify custom workflow is preserved
- [ ] Verify instructions reference custom workflow
- [ ] Verify agent can work with custom phases

**Success Criteria:**
- Custom workflow respected
- Agent adapts to custom phases

---

#### 5.3 Parallel Mode - Multi-Agent
**Test:** Use `orchestrator enforce --parallel`
- [ ] Run `orchestrator enforce "Large task" --parallel`
- [ ] Spawn multiple agents via `orchestrator prd spawn`
- [ ] Verify agents coordinate through orchestrator
- [ ] Verify no conflicts

**Success Criteria:**
- Multiple agents work in parallel
- State coordination works

---

#### 5.4 Error Recovery - Port Conflicts
**Test:** Handle port conflicts gracefully
- [ ] Manually start server on port 8000
- [ ] Run `orchestrator enforce "Task"`
- [ ] Verify it detects existing server
- [ ] Verify it does NOT start duplicate

**Success Criteria:**
- No duplicate servers
- Clear messaging

---

#### 5.5 Cross-Platform - Windows Test
**Test:** Run on Windows 11
- [ ] Install orchestrator on Windows
- [ ] Run `orchestrator enforce "Task"` in PowerShell
- [ ] Verify server starts (or clear error)
- [ ] Verify paths use correct separators
- [ ] Verify workflow generation works

**Success Criteria:**
- Works on Windows OR provides clear unsupported message

---

## Performance Tests

### 6. Performance Benchmarks

#### 6.1 Server Startup Time
**Test:** Measure server startup latency
- **Action:** Time from `start_orchestrator_daemon()` to health check success
- **Target:** < 3 seconds
- **Assert:** Average startup time under target

#### 6.2 Workflow Generation Time
**Test:** Measure workflow generation latency
- **Action:** Time `generate_workflow_yaml()` with repo analysis
- **Target:** < 1 second
- **Assert:** Generation time under target

#### 6.3 Server Resource Usage
**Test:** Measure server memory and CPU
- **Action:** Monitor server process for 5 minutes idle
- **Target:** < 100MB RAM, < 2% CPU (idle)
- **Assert:** Resource usage under target

---

## Test Coverage Goals

| Component | Target Coverage | Critical Paths Coverage |
|-----------|----------------|-------------------------|
| `auto_setup.py` | 90% | 100% (server start, health check) |
| `workflow_generator.py` | 85% | 95% (repo analysis, YAML gen) |
| `agent_context.py` | 85% | 90% (instruction gen, formatting) |
| `cli.py` (enforce command) | 80% | 90% (argument parsing, flow) |
| Integration tests | N/A | 100% (all critical flows) |

**Overall Target:** 85%+ coverage

---

## Test Execution Plan

### Phase 1: Unit Tests
1. Write tests for `auto_setup.py`
2. Write tests for `workflow_generator.py`
3. Write tests for `agent_context.py`
4. Run with `pytest --cov` to verify coverage

### Phase 2: Integration Tests
1. Write integration tests for `enforce` command
2. Test all language detections
3. Test all error scenarios
4. Run in isolated test environments

### Phase 3: Manual Testing
1. Dogfooding in real repos
2. Test with actual AI agents
3. Cross-platform testing (Linux, Mac, Windows)
4. Performance benchmarking

### Phase 4: Regression Testing
1. Run full existing test suite
2. Verify no regressions
3. Update any affected tests

---

## Test Data

### Sample Test Repos
- **Python/pytest:** Repo with requirements.txt, tests/, src/
- **JavaScript/jest:** Repo with package.json, __tests__/, src/
- **Go:** Repo with go.mod, *_test.go files
- **Rust:** Repo with Cargo.toml, tests/
- **Unknown:** Empty directory with no structure

### Mocked Responses
- HTTP health check responses (200, 500, timeout)
- Subprocess spawn results (success, failure, OSError)
- File system operations (success, permission errors)

---

## Acceptance Criteria

For PRD-008 to pass testing:
- [ ] All unit tests pass (90%+ coverage on critical paths)
- [ ] All integration tests pass (100% of defined scenarios)
- [ ] Manual dogfooding succeeds with Claude Code agent
- [ ] Cross-platform tests pass on Linux and Mac (Windows nice-to-have)
- [ ] Performance benchmarks meet targets
- [ ] Zero regressions in existing functionality
- [ ] Test documentation complete

---

## Notes

- Tests should be independent (can run in any order)
- Use temp directories for all file operations
- Clean up resources (servers, files) after tests
- Mock external dependencies (httpx, subprocess)
- Use fixtures for common setup patterns
- Tag tests: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
