# Implementation Plan: ai-tool.yaml Architecture

## Overview

Implement self-describing tool manifests (ai-tool.yaml) that ai-tool-bridge aggregates into a unified ai-tools.json, enabling seamless tool discovery across AI environments (Claude Code, Codex, Manus, etc.).

## Objective

Enable a seamless, invisible tool discovery experience where:
1. Each tool is self-describing via `ai-tool.yaml`
2. `ai-tool-bridge` aggregates manifests into `ai-tools.json`
3. AI environments read `ai-tools.json` for tool discovery
4. CLAUDE.md becomes a minimal fallback only

## Scope

**In Scope:**
- orchestrator (workflow-orchestrator repo)
- minds (multiminds repo)
- visual-verification-service

**Out of Scope:**
- ai-tool-bridge (aggregator, doesn't need its own manifest)
- quiet-ping-v6, keeva-devtools (can be added later)

## Architecture

```
Tool Repos                      ai-tool-bridge              AI Environment
┌─────────────────┐             ┌─────────────┐            ┌────────────────┐
│ orchestrator/   │             │             │            │                │
│  └─ai-tool.yaml │────┐        │   scan &    │            │  Read          │
├─────────────────┤    ├───────▶│  aggregate  │───────────▶│  ai-tools.json │
│ minds/          │    │        │             │            │                │
│  └─ai-tool.yaml │────┤        └─────────────┘            └────────────────┘
├─────────────────┤    │
│ vvs/            │    │
│  └─ai-tool.yaml │────┘
└─────────────────┘
```

## ai-tool.yaml Schema

```yaml
# ai-tool.yaml - Self-describing tool manifest
schema_version: "1.0"
tool:
  name: "orchestrator"
  version: "2.6.0"
  description: "Development workflow management for AI-assisted coding"
  homepage: "https://github.com/keevaspeyer10x/workflow-orchestrator"

install:
  pip: "git+https://github.com/keevaspeyer10x/workflow-orchestrator.git"
  check: "orchestrator --version"  # Command to verify installation

commands:
  - id: "orchestrator:status"
    description: "Show current workflow state"
    cli_command: "orchestrator status"
    triggers:
      - "check workflow status"
      - "what's the orchestrator status"
      - "workflow state"
    dangerous: false
    examples:
      - "orchestrator status"

  - id: "orchestrator:start"
    description: "Start a new workflow"
    cli_command: "orchestrator start"
    triggers:
      - "start workflow"
      - "begin workflow"
      - "use orchestrator to"
    parameters:
      - name: "task"
        type: "string"
        description: "Task description"
        required: true
        positional: true
    examples:
      - "orchestrator start 'Implement feature X'"

  # ... more commands

guidance:
  usage_patterns:
    - trigger: "Use orchestrator to X"
      action: "orchestrator start 'X' then follow the workflow phases"
    - trigger: "What's the status?"
      action: "orchestrator status"

  best_practices:
    - "Always check status before any action"
    - "Follow the current phase - don't skip ahead"
    - "Document everything with --notes"
```

## Security Constraints (from Plan Validation)

**YAML Safety (Critical):**
```python
# REQUIRED in yaml_loader.py - NEVER use yaml.load()
data = yaml.safe_load(file_content)
```

**Install URL Validation:**
- Install URLs must match allowlist: `github.com/keevaspeyer10x/*`
- `cli_command` fields are NEVER auto-executed by ai-tool-bridge
- Commands are executed by AI, not by the scanner

**Duplicate Command ID Handling:**
- Reject manifests with duplicate command IDs within same tool
- When aggregating, use `<tool_name>:<command_id>` namespace
- Error on cross-tool ID conflicts with clear message

**Fallback Behavior:**
1. If `ai-tools.json` exists → Read it directly (zero-latency)
2. If missing but tools installed → Run `ai-tool-bridge scan` to generate
3. If tools not installed → CLAUDE.md contains bootstrap instructions
4. CLAUDE.md minimal content:
   ```markdown
   ## AI Tools
   Run: `cat ai-tools.json` or `ai-tool-bridge show`

   If not installed: `curl -sSL .../bootstrap.sh | bash`
   ```

## ai-tools.json Output Schema

```json
{
  "$schema": "https://ai-tool-bridge.dev/schema/v1/ai-tools.json",
  "version": "1.0",
  "generated_at": "2026-01-16T12:00:00Z",
  "generator": "ai-tool-bridge/1.0.0",
  "tools": {
    "orchestrator": {
      "name": "orchestrator",
      "version": "2.6.0",
      "description": "...",
      "install": { "pip": "...", "check": "..." },
      "commands": [
        {
          "id": "orchestrator:status",
          "description": "...",
          "cli_command": "orchestrator status",
          "triggers": ["..."],
          "dangerous": false
        }
      ]
    }
  }
}
```

## Implementation Steps

### Phase 1: ai-tool-bridge Enhancement

**1.1 Add YAML manifest loading**
- File: `src/ai_tool_bridge/yaml_loader.py`
- Parse ai-tool.yaml files using `yaml.safe_load()` (CRITICAL: no yaml.load())
- Validate against schema (required fields: schema_version, tool.name, commands)
- Convert to internal CommandSpec objects
- Validate no duplicate command IDs within manifest

**1.2 Add directory scanning**
- File: `src/ai_tool_bridge/scanner.py`
- Scan directories for ai-tool.yaml files
- Support recursive scanning
- Support explicit path list
- **Edge cases:**
  - Empty manifest: Log warning, skip tool
  - Scan failure: Continue with other dirs, report failures at end
  - `--strict` flag: Fail on any error vs default partial-success

**1.3 Add CLI commands**
```bash
ai-tool-bridge scan <dir>           # Scan directory for manifests
ai-tool-bridge scan --paths <p1,p2> # Scan specific paths
ai-tool-bridge build                # Build aggregated ai-tools.json
ai-tool-bridge show                 # Show discovered tools
```

### Phase 2: Create Tool Manifests

**2.1 orchestrator (workflow-orchestrator)**
- Create `ai-tool.yaml` in repo root
- Commands: status, start, complete, skip, advance, finish, handoff, etc.
- Include guidance for common usage patterns

**2.2 minds (multiminds)**
- Create `ai-tool.yaml` in repo root
- Commands: ask, review, status
- Include guidance for code reviews and questions

**2.3 visual-verification-service**
- Create `ai-tool.yaml` in repo root
- Commands: verify, compare, capture
- Include guidance for visual testing

### Phase 3: Integration

**3.1 Update devtools bootstrap.sh**
```bash
# After installing tools, generate ai-tools.json
ai-tool-bridge build --output ai-tools.json
```

**3.2 Minimize CLAUDE.md**
Replace comprehensive instructions with:
```markdown
## AI Development Tools

For tool discovery: `cat ai-tools.json` or `ai-tool-bridge show`

If tools not installed:
```bash
curl -sSL .../bootstrap.sh | bash
```
```

### Phase 4: Testing

**4.1 Unit tests**
- Test YAML loading and validation
- Test directory scanning
- Test manifest aggregation

**4.2 Integration tests**
- Test full flow: scan → build → show
- Test with all three tool repos

**4.3 End-to-end test**
- Fresh environment simulation
- Install → discover → use flow

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Schema versioning conflicts | Low | Medium | Include schema_version field, validate on load |
| Missing ai-tool.yaml in tool repos | Medium | High | Fallback to CLAUDE.md, warn user |
| YAML parsing errors | Low | Medium | Validate schema, clear error messages |
| Install command failures | Medium | Medium | Include fallback pip commands |
| AI misinterprets triggers | Medium | Low | Test triggers, refine based on feedback |

## Success Criteria

1. `ai-tool-bridge scan` discovers all three tools (orchestrator, minds, vvs)
2. `ai-tool-bridge build` generates valid ai-tools.json (passes JSON schema validation)
3. `ai-tools.json` contains all commands from all 3 manifests with correct structure
4. Fresh Claude Code Web sandbox can install and discover tools via bootstrap
5. CLAUDE.md is minimal (~10 lines vs current ~50+)
6. All unit tests pass for yaml_loader, scanner, and aggregation

## Dependencies

- PyYAML >= 6.0 for YAML parsing (safe_load required)
- Python >= 3.9 (matches ai-tool-bridge requirements)
- Existing ai-tool-bridge infrastructure
- Git access to tool repos for manifest commits

## Test Cases

1. **Scan finds manifests**: `ai-tool-bridge scan /path/to/repos` returns 3 tools
2. **Invalid YAML rejected**: Malformed ai-tool.yaml produces clear error
3. **Missing fields rejected**: Required fields (name, commands) validated
4. **Aggregation works**: Multiple manifests merge into single ai-tools.json
5. **CLI works**: `ai-tool-bridge show` displays human-readable tool list
6. **Bootstrap generates**: After install, ai-tools.json exists
7. **Triggers match**: "use orchestrator to X" maps to orchestrator:start
8. **Fresh install works**: New environment can discover tools after bootstrap

## Parallel Execution Assessment

**Decision: Sequential execution**

**Reason:** The implementation has dependencies:
1. ai-tool-bridge must be enhanced BEFORE tool manifests can be tested
2. Tool manifests depend on finalized schema
3. Bootstrap update depends on ai-tool-bridge CLI

While the three ai-tool.yaml files could theoretically be created in parallel, they're simple enough that sequential creation is more efficient than coordination overhead. The ai-tool-bridge changes are the critical path.

## Timeline Notes

Implementation order:
1. ai-tool-bridge schema + loader (enables testing)
2. ai-tool-bridge scanner + CLI
3. orchestrator ai-tool.yaml
4. minds ai-tool.yaml
5. visual-verification-service ai-tool.yaml
6. devtools bootstrap update
7. CLAUDE.md minimization (all repos)
