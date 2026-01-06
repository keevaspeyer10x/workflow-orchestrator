# Test Cases: Global Installation (Method C)

## Unit Tests

### Config Discovery Tests

#### TC-CFG-001: Find Local Workflow
**Component:** `src/config.py`
**Description:** Finds workflow.yaml in current directory
**Input:** Directory with workflow.yaml present
**Expected:** Returns path to local workflow.yaml
**Priority:** High

#### TC-CFG-002: Fallback to Bundled Workflow
**Component:** `src/config.py`
**Description:** Falls back to bundled when no local workflow
**Input:** Directory without workflow.yaml
**Expected:** Returns path to bundled default_workflow.yaml
**Priority:** High

#### TC-CFG-003: Get Bundled Workflow Path
**Component:** `src/config.py`
**Description:** Returns correct path to package data
**Input:** N/A
**Expected:** Path exists and points to valid YAML file
**Priority:** High

#### TC-CFG-004: Get Default Workflow Content
**Component:** `src/config.py`
**Description:** Returns bundled workflow as string
**Input:** N/A
**Expected:** Valid YAML content with 5 phases
**Priority:** Medium

### Init Command Tests

#### TC-INIT-001: Init Creates Workflow
**Component:** `src/cli.py`
**Description:** Creates workflow.yaml in current directory
**Setup:** Empty directory
**Input:** `orchestrator init`
**Expected:** workflow.yaml created, matches bundled content
**Priority:** High

#### TC-INIT-002: Init Prompts on Existing File
**Component:** `src/cli.py`
**Description:** Prompts before overwriting existing workflow
**Setup:** Directory with existing workflow.yaml
**Input:** `orchestrator init` (simulate 'y' response)
**Expected:** Prompts user, creates backup, overwrites
**Priority:** High

#### TC-INIT-003: Init Creates Backup
**Component:** `src/cli.py`
**Description:** Backs up existing file before overwrite
**Setup:** Directory with workflow.yaml containing custom content
**Input:** `orchestrator init --force`
**Expected:** workflow.yaml.bak created with original content
**Priority:** High

#### TC-INIT-004: Init Aborts on No
**Component:** `src/cli.py`
**Description:** Does not overwrite when user says no
**Setup:** Directory with existing workflow.yaml
**Input:** `orchestrator init` (simulate 'n' response)
**Expected:** Original file unchanged, no backup created
**Priority:** Medium

#### TC-INIT-005: Init Force Flag
**Component:** `src/cli.py`
**Description:** --force skips prompt
**Setup:** Directory with existing workflow.yaml
**Input:** `orchestrator init --force`
**Expected:** Creates backup and overwrites without prompt
**Priority:** Medium

### Engine Workflow Loading Tests

#### TC-ENG-001: Engine Uses Local Workflow
**Component:** `src/engine.py`
**Description:** Engine loads local workflow.yaml when present
**Setup:** Directory with custom workflow.yaml
**Input:** `WorkflowEngine(".")` then `load_workflow()`
**Expected:** Loaded workflow matches local file content
**Priority:** High

#### TC-ENG-002: Engine Falls Back to Bundled
**Component:** `src/engine.py`
**Description:** Engine uses bundled when no local workflow
**Setup:** Empty directory
**Input:** `WorkflowEngine(".")` then `load_workflow()`
**Expected:** Loaded workflow matches bundled default
**Priority:** High

#### TC-ENG-003: Engine Reports Workflow Source
**Component:** `src/engine.py`
**Description:** Engine logs which workflow is being used
**Input:** Any workflow load
**Expected:** Log message indicates source path
**Priority:** Medium

### Import Tests

#### TC-IMP-001: Package Import Works
**Component:** `src/__init__.py`
**Description:** Can import package after pip install
**Setup:** `pip install -e .`
**Input:** `from src import WorkflowEngine`
**Expected:** Import succeeds
**Priority:** High

#### TC-IMP-002: Main Entry Point Works
**Component:** `src/__main__.py`
**Description:** `python -m src` runs CLI
**Setup:** `pip install -e .`
**Input:** `python -m src --help`
**Expected:** Shows help text
**Priority:** High

#### TC-IMP-003: Entry Point Script Works
**Component:** pyproject.toml entry point
**Description:** `orchestrator` command available after install
**Setup:** `pip install -e .`
**Input:** `orchestrator --help`
**Expected:** Shows help text
**Priority:** High

## Integration Tests

### TC-INT-001: Fresh Install and Run
**Description:** Full workflow from install to status check
**Setup:** Fresh virtual environment
**Steps:**
1. `pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git`
2. `cd /tmp/test-dir`
3. `orchestrator status`
**Expected:** Shows status using bundled workflow
**Priority:** High

### TC-INT-002: Init Then Start Workflow
**Description:** Init workflow then start a task
**Setup:** Fresh directory
**Steps:**
1. `orchestrator init`
2. `orchestrator start "Test task"`
3. `orchestrator status`
**Expected:** Workflow running in PLAN phase
**Priority:** High

### TC-INT-003: Local Workflow Override
**Description:** Local workflow takes precedence over bundled
**Setup:** Directory with custom 2-phase workflow.yaml
**Steps:**
1. `orchestrator start "Test"`
2. Check loaded workflow
**Expected:** Uses custom workflow, not bundled
**Priority:** High

### TC-INT-004: Backward Compat - Bash Script
**Description:** Existing bash script still works
**Setup:** Clone repo
**Steps:**
1. `cd workflow-orchestrator`
2. `./orchestrator --help`
**Expected:** Shows help (same as before)
**Priority:** High

### TC-INT-005: Editable Install Works
**Description:** `pip install -e .` for development
**Setup:** Clone repo
**Steps:**
1. `pip install -e .`
2. `orchestrator --help`
3. Edit src/cli.py (add comment)
4. `orchestrator --help` (should reflect change)
**Expected:** Changes reflected without reinstall
**Priority:** Medium

## CLI Command Tests

### TC-CLI-001: Status Without Workflow
**Component:** `src/cli.py`
**Description:** Status with bundled workflow (no local file)
**Input:** `orchestrator status` (in empty dir)
**Expected:** Shows status or helpful message
**Priority:** High

### TC-CLI-002: Start Without Workflow
**Component:** `src/cli.py`
**Description:** Start works with bundled workflow
**Input:** `orchestrator start "Task"` (in empty dir)
**Expected:** Starts workflow using bundled definition
**Priority:** High

### TC-CLI-003: Init Output
**Component:** `src/cli.py`
**Description:** Init shows helpful next steps
**Input:** `orchestrator init`
**Expected:** Message includes "workflow.yaml created" and next steps
**Priority:** Medium

### TC-CLI-004: Version Flag
**Component:** `src/cli.py`
**Description:** Shows version from package
**Input:** `orchestrator --version`
**Expected:** Shows version number
**Priority:** Low

## Error Handling Tests

### TC-ERR-001: Missing Package Data
**Component:** `src/config.py`
**Description:** Clear error if bundled workflow missing
**Setup:** Corrupted install without package data
**Input:** Try to access bundled workflow
**Expected:** Clear error message with recovery steps
**Priority:** Medium

### TC-ERR-002: Invalid Local Workflow
**Component:** `src/engine.py`
**Description:** Error on malformed workflow.yaml
**Setup:** workflow.yaml with invalid YAML
**Input:** `orchestrator status`
**Expected:** Parse error with file path and line number
**Priority:** Medium

### TC-ERR-003: Init in Read-Only Directory
**Component:** `src/cli.py`
**Description:** Clear error when can't write
**Setup:** Directory without write permission
**Input:** `orchestrator init`
**Expected:** Permission error with explanation
**Priority:** Low

## Existing Test Compatibility

### TC-COMPAT-001: All Existing Tests Pass
**Description:** No regressions from package restructure
**Input:** `pytest tests/`
**Expected:** All tests pass
**Priority:** High

### TC-COMPAT-002: Test Imports Updated
**Description:** Tests use correct import paths
**Input:** Run tests after import changes
**Expected:** No import errors
**Priority:** High

## Coverage Requirements

- Minimum 80% coverage for new code in `src/config.py`
- 100% coverage for init command logic
- All error paths must be tested
- Integration tests can be marked `@pytest.mark.integration` and skipped in CI
