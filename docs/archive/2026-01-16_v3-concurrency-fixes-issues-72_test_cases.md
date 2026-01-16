# Test Cases: ai-tool.yaml Architecture

## Unit Tests (ai-tool-bridge)

### YAML Loader Tests (`tests/test_yaml_loader.py`)

| ID | Test Name | Input | Expected Output |
|----|-----------|-------|-----------------|
| YL-01 | test_load_valid_manifest | Valid ai-tool.yaml | Parsed dict with tool/commands |
| YL-02 | test_safe_load_used | YAML with Python tags | Raises error (not executed) |
| YL-03 | test_missing_schema_version | YAML without schema_version | ValidationError |
| YL-04 | test_missing_tool_name | YAML without tool.name | ValidationError |
| YL-05 | test_missing_commands | YAML without commands | ValidationError |
| YL-06 | test_duplicate_command_ids | YAML with duplicate IDs | ValidationError with message |
| YL-07 | test_empty_commands_list | YAML with commands: [] | Warning logged, valid parse |
| YL-08 | test_malformed_yaml | Invalid YAML syntax | YAMLError with line number |

### Scanner Tests (`tests/test_scanner.py`)

| ID | Test Name | Input | Expected Output |
|----|-----------|-------|-----------------|
| SC-01 | test_scan_single_dir | Dir with ai-tool.yaml | Returns 1 manifest |
| SC-02 | test_scan_recursive | Nested dirs with manifests | Returns all manifests |
| SC-03 | test_scan_empty_dir | Empty directory | Returns [] |
| SC-04 | test_scan_no_manifest | Dir without ai-tool.yaml | Returns [] |
| SC-05 | test_scan_multiple_paths | List of paths | Returns manifests from all |
| SC-06 | test_scan_partial_failure | 2 valid, 1 invalid | Returns 2, logs error for 1 |
| SC-07 | test_scan_strict_mode | 2 valid, 1 invalid, --strict | Raises error |
| SC-08 | test_scan_nonexistent_dir | Path that doesn't exist | Logs warning, continues |

### Aggregation Tests (`tests/test_aggregation.py`)

| ID | Test Name | Input | Expected Output |
|----|-----------|-------|-----------------|
| AG-01 | test_aggregate_single | 1 manifest | ai-tools.json with 1 tool |
| AG-02 | test_aggregate_multiple | 3 manifests | ai-tools.json with 3 tools |
| AG-03 | test_aggregate_command_namespacing | 2 manifests with "status" cmd | Commands namespaced correctly |
| AG-04 | test_aggregate_cross_tool_conflict | 2 tools with same namespaced ID | Error with clear message |
| AG-05 | test_aggregate_empty_input | No manifests | Valid JSON with empty tools |
| AG-06 | test_aggregate_preserves_all_fields | Full manifest | All fields in output |

## Integration Tests

### CLI Tests (`tests/test_cli_integration.py`)

| ID | Test Name | Command | Expected Output |
|----|-----------|---------|-----------------|
| CLI-01 | test_scan_command | `ai-tool-bridge scan <dir>` | Lists discovered tools |
| CLI-02 | test_build_command | `ai-tool-bridge build` | Creates ai-tools.json |
| CLI-03 | test_show_command | `ai-tool-bridge show` | Human-readable tool list |
| CLI-04 | test_scan_paths_flag | `ai-tool-bridge scan --paths a,b` | Scans specific paths |
| CLI-05 | test_build_output_flag | `ai-tool-bridge build --output x.json` | Creates x.json |
| CLI-06 | test_strict_flag | `ai-tool-bridge scan --strict` | Fails on any error |

### Full Flow Tests (`tests/test_integration.py`)

| ID | Test Name | Steps | Expected Result |
|----|-----------|-------|-----------------|
| INT-01 | test_scan_build_flow | 1. Scan dirs 2. Build | Valid ai-tools.json |
| INT-02 | test_three_tool_integration | Scan orchestrator, minds, vvs | All 3 in output |
| INT-03 | test_roundtrip | Build → Load → Validate | Schema valid |

## End-to-End Tests

### Fresh Environment Tests (`tests/test_e2e.py`)

| ID | Test Name | Scenario | Expected Result |
|----|-----------|----------|-----------------|
| E2E-01 | test_fresh_install | Run bootstrap.sh | Tools installed, ai-tools.json exists |
| E2E-02 | test_discover_after_install | Bootstrap → show | All tools listed |
| E2E-03 | test_cat_ai_tools_json | Bootstrap → cat ai-tools.json | Valid JSON output |

## Security Tests

| ID | Test Name | Input | Expected Result |
|----|-----------|-------|-----------------|
| SEC-01 | test_yaml_code_execution_blocked | YAML with !!python/object | Error, no execution |
| SEC-02 | test_install_url_validation | Invalid URL pattern | Warning logged |
| SEC-03 | test_cli_commands_not_executed | Manifest with cli_command | Command NOT run |

## Test Environment Setup

```bash
# Create test fixtures
mkdir -p tests/fixtures/valid
mkdir -p tests/fixtures/invalid
mkdir -p tests/fixtures/multi

# Valid manifest
cat > tests/fixtures/valid/ai-tool.yaml << 'EOF'
schema_version: "1.0"
tool:
  name: "test-tool"
  version: "1.0.0"
  description: "Test tool"
commands:
  - id: "test:cmd"
    description: "Test command"
    cli_command: "test cmd"
    triggers: ["run test"]
EOF

# Invalid manifest (missing required field)
cat > tests/fixtures/invalid/ai-tool.yaml << 'EOF'
tool:
  name: "broken-tool"
# Missing schema_version and commands
EOF
```

## Coverage Requirements

- Line coverage: >= 90%
- Branch coverage: >= 85%
- All security tests must pass
- All integration tests must pass before merge
