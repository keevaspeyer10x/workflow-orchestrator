# Test Cases: Issue #88 - Plan Validation Review

## Test Cases

### TC1: YAML Validity
**Objective**: Verify default_workflow.yaml remains valid after adding plan_validation
**Steps**:
1. Run `python3 -c "import yaml; yaml.safe_load(open('src/default_workflow.yaml'))"`
2. Expect: No errors, YAML parses successfully

### TC2: Item Position
**Objective**: Verify plan_validation is positioned correctly in PLAN phase
**Steps**:
1. Parse workflow YAML
2. Find PLAN phase items
3. Verify order: risk_analysis < plan_validation < define_test_cases < user_approval
**Expected**: plan_validation appears after risk_analysis and before user_approval

### TC3: Required Fields Present
**Objective**: Verify plan_validation has all required fields
**Steps**:
1. Parse workflow YAML
2. Find plan_validation item
3. Check for: id, name, description, required, skippable, skip_conditions, notes
**Expected**: All required fields present

### TC4: Skip Conditions Defined
**Objective**: Verify skip conditions are properly defined
**Steps**:
1. Parse plan_validation item
2. Check skip_conditions list
3. Verify contains: trivial_change, simple_bug_fix, well_understood_pattern
**Expected**: All three skip conditions present

### TC5: Existing Tests Pass
**Objective**: Verify no regressions introduced
**Steps**:
1. Run `pytest`
2. Expect: All tests pass

### TC6: Checkpoints in Description
**Objective**: Verify all 10 checkpoints are in the description
**Steps**:
1. Read plan_validation description
2. Check for keywords: "Request Completeness", "Requirements Alignment", "Security", "Risk Mitigation", "Objective-Driven Optimality", "Dependencies", "Edge Cases", "Testing", "Implementability", "Operational Readiness"
**Expected**: All 10 checkpoint topics present

### TC7: Verdicts in Description
**Objective**: Verify all 5 verdicts are defined
**Steps**:
1. Read plan_validation description
2. Check for: APPROVED, APPROVED_WITH_NOTES, NEEDS_REVISION, BLOCKED, ESCALATE
**Expected**: All 5 verdicts present
