# Workflow Efficiency Telemetry & Risk-Adaptive Verification

**Issue Type:** Feature
**Priority:** HIGH
**Complexity:** MEDIUM
**Related:** WF-024 (Risk-Based Multi-AI Phase Reviews), WF-035 (Zero-Human Mode)

## Problem Statement

We lack data on workflow step efficiency. Concerns include:
- Running 2000 tests for a 2-line change (potentially wasteful)
- No visibility into time/cost per phase
- No way to evaluate "value added" vs "gold plating"
- No test impact analysis to run only relevant tests

However, as a **zero-human-review vibe coding platform** building complex tools, thoroughness may be justified. We need **data before optimizing**.

## Multi-Model Consensus (Claude, GPT-5.2, Grok 4.1, DeepSeek V3.2)

All 4 models strongly agreed on the approach:

### 1. Implement Test Impact Analysis (Highest Priority)
- Map which tests cover which files/modules
- For each change, run only tests that exercise modified code
- Expand to broader suites only when risk score is high
- *"You'll likely find <50 of those 2000 tests are relevant"*

### 2. Risk-Based Verification Tiers
| Risk Level | Scope | Verification |
|------------|-------|--------------|
| **Low** | Config, docs, typos | Lint + targeted unit tests only |
| **Medium** | Isolated logic changes | Affected tests + some integration |
| **High** | Core libs, security | Full relevant suite + security scans |
| **Critical** | Data migrations, APIs | Full suite + staged deployment |

### 3. Gold Plating Detection Criteria
- Changes not traceable to PLAN requirements or VERIFY failures
- High cost with no measurable quality improvement
- Refactoring working code without defect reduction
- Expanding scope beyond specification

## Proposed Telemetry Schema

```yaml
workflow_trace:
  trace_id: uuid
  workflow_id: string

  change_context:
    lines_changed: int
    files_touched: list[string]
    risk_score: float  # 1-10
    risk_tier: low|medium|high|critical
    change_type: feature|bugfix|refactor|docs|config

  phases:
    - phase: PLAN|EXECUTE|REVIEW|VERIFY|LEARN
      duration_ms: int
      cost_usd: float
      tokens: {input: int, output: int}
      iterations: int  # retries/loops
      outcome: pass|fail|partial
      items_completed: int
      items_skipped: int

  verification:
    tests_total: int           # Total tests in suite
    tests_selected: int        # By impact analysis
    tests_run: int             # Actually executed
    tests_passed: int
    tests_failed: int
    selection_method: impact_analysis|full_suite|risk_based|manual
    defects_found: int
    test_duration_ms: int

  reviews:
    models_attempted: list[string]
    models_succeeded: list[string]
    review_cost_usd: float
    issues_found: int
    issues_by_severity: {critical: int, high: int, medium: int, low: int}

  value_assessment:
    aligned_to_plan: boolean
    justified_by_failure: boolean
    gold_plating_flag: boolean

  derived_metrics:
    cost_per_line_changed: float
    tests_per_line_changed: float
    verification_proportionality: float  # tests_run / (lines_changed × risk_score)
```

## Relationship to WF-024 (Risk-Based Reviews)

WF-024 proposed risk-based review intensity at different phases. This issue extends that concept to **all verification activities**:

| WF-024 Focus | This Issue Extends To |
|--------------|----------------------|
| Review model tier (economy/standard/premium) | Test selection strategy |
| Risk level per EXECUTE item | Risk scoring for entire change |
| PLAN review before implementation | Verification scope before running tests |

**Recommendation:** Merge the risk-scoring mechanism. A single `risk_score` should drive:
1. Review intensity (WF-024)
2. Test selection scope (this issue)
3. Phase duration expectations

## Implementation Phases

### Phase 1: Instrumentation (Data Collection)
- [ ] Add `workflow_trace` schema to state tracking
- [ ] Capture phase start/end timestamps
- [ ] Log test counts (total, run, passed, failed)
- [ ] Track API costs per phase (token counts × model pricing)
- [ ] Store in `.workflow_telemetry.jsonl` (like feedback files)

### Phase 2: Risk Scoring in PLAN Phase
- [ ] Add `risk_score` field to workflow state
- [ ] Auto-calculate based on: files touched, modules affected, change type
- [ ] Display risk tier in `orchestrator status`
- [ ] Allow manual override: `orchestrator start "task" --risk high`

### Phase 3: Test Impact Analysis
- [ ] Integrate with pytest coverage mapping (if available)
- [ ] Build file→test mapping from previous runs
- [ ] Select tests based on changed files
- [ ] Fall back to full suite if mapping unavailable
- [ ] Log selection method in telemetry

### Phase 4: Adaptive Verification
- [ ] Configure test scope per risk tier in workflow.yaml
- [ ] Implement early-exit on critical failures (Grok suggestion)
- [ ] Add phase time caps (configurable)
- [ ] Feed telemetry into LEARN phase for threshold tuning

### Phase 5: Reporting & Dashboards
- [ ] `orchestrator telemetry summary` - Show aggregated metrics
- [ ] `orchestrator telemetry review` - Analyze patterns
- [ ] Flag workflows with high `verification_proportionality`
- [ ] Generate recommendations in LEARN phase

## CLI Commands

```bash
# View telemetry for current/past workflows
orchestrator telemetry show [workflow_id]

# Aggregated summary
orchestrator telemetry summary --days 30

# Analyze efficiency patterns
orchestrator telemetry review

# Set risk level explicitly
orchestrator start "task" --risk critical

# Override test scope
orchestrator advance --test-scope full    # Force full suite
orchestrator advance --test-scope impact  # Force impact analysis only
```

## Configuration

```yaml
# workflow.yaml
settings:
  telemetry:
    enabled: true
    file: .workflow_telemetry.jsonl

  verification:
    test_selection:
      default: impact_analysis  # or: full_suite, risk_based
      fallback: full_suite      # When impact analysis unavailable

    risk_tiers:
      low:
        test_scope: affected_only
        max_duration_ms: 60000   # 1 minute cap
      medium:
        test_scope: affected_plus_integration
        max_duration_ms: 300000  # 5 minute cap
      high:
        test_scope: full_suite
        max_duration_ms: 600000  # 10 minute cap
      critical:
        test_scope: full_suite_plus_smoke
        max_duration_ms: null    # No cap

    early_exit:
      enabled: true
      on_critical_failure: true  # Stop on first critical test failure
      max_failures: 10           # Stop after N failures
```

## Success Metrics

- **Efficiency:** Reduce average tests_run by 50%+ for low-risk changes
- **No quality loss:** Defect escape rate unchanged or improved
- **Visibility:** 100% of workflows have telemetry data
- **Actionable insights:** LEARN phase generates specific tuning recommendations

## Divergence Point: Thoroughness vs Efficiency

For zero-human-review platforms, models disagreed on balance:
- **Claude/DeepSeek:** High test counts *may be justified* for safety-critical modules
- **GPT:** Lean on deployment safety nets (canary, feature flags, auto-rollback)
- **Grok:** Aggressive early-exit (abort on first N failures, cap phase time)

**Recommendation for this project:** Start with **data collection only** (Phase 1). Make optimization decisions based on actual telemetry, not assumptions. Given the "gold plating is OK" stance, err on side of thoroughness but gain visibility into costs.

## YAGNI Check

- **Phase 1 (Instrumentation):** ✅ IMPLEMENT - Need data to make decisions
- **Phase 2 (Risk Scoring):** ✅ IMPLEMENT - Aligns with WF-024, low complexity
- **Phase 3 (Test Impact):** ⚠️ VALIDATE FIRST - Check if test suite is actually slow
- **Phase 4 (Adaptive):** ⚠️ DEFER - Wait for Phase 1-2 data
- **Phase 5 (Dashboards):** ⚠️ DEFER - Nice-to-have after core instrumentation

## References

- **WF-024:** Risk-Based Multi-AI Phase Reviews (ROADMAP.md:911-1149)
- **WF-035:** Zero-Human Mode Risk Analysis (docs/plans/wf-035-risk-analysis.md)
- **Phase 3b Feedback:** Existing telemetry infrastructure (.workflow_tool_feedback.jsonl)
- **Minds Synthesis:** Multi-model consensus on workflow efficiency (2026-01-17)
