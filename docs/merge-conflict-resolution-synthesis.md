# Merge Conflict Resolution: AI Feedback Synthesis

This document synthesizes feedback from ChatGPT, Gemini, Grok, and Codex on the proposed intelligent merge conflict resolution system for multi-agent AI coding.

## Universal Agreement (All 4 AIs)

| Theme | Consensus |
|-------|-----------|
| **Stage 0 is missing** | "Clean merge ≠ correct merge." Need semantic conflict detection *before* git flags anything |
| **Provenance/Attribution** | First-class artifact linking: agent → task → files → decisions → tests |
| **Structured records > traces** | Raw chain-of-thought is noisy. Use structured Decision Records (ADR-like) |
| **Intent needs evidence** | Extraction must be grounded in tests/task/files, with confidence scoring |
| **Candidate diversity must be enforced** | "Generate 3 candidates" yields superficial variations without distinct strategy templates |
| **Tiered validation** | Full test suites per conflict is too expensive. Fast filters first, escalate selectively |
| **Hybrid rebase/merge** | Classify conflict type → choose strategy dynamically |
| **Prevention > Resolution** | Shift left with coordination contracts, module ownership, design checkpoints |

## Novel Insights Worth Highlighting

### Gemini's "Agentic Rebase"

The most radical reframe:

```
Don't merge Agent B's code at all.
Extract intent + tests from Agent B.
Discard Agent B's code.
Re-implement Agent B's intent on Agent A's codebase.
```

This transforms a "diff patching" problem into a "code generation" problem, which LLMs are natively better at.

### Gemini's "Test Paradox"

Critical edge case:

> If Agent A changed a function signature that Agent B's tests rely on, the merged tests won't compile. You can't validate with tests that don't build.

Need a "Harness Repair" step before test synthesis.

### ChatGPT's Constraint Sets

Intent as structure, not prose:

```
Hard constraints: must not break API, must pass tests, must preserve backwards behavior X
Soft constraints: prefer existing patterns, minimize diff
Tradeoffs: security vs UX vs performance (explicit priority ordering)
```

### ChatGPT's Mutation Testing

Verify test quality:

> Mutate the resolved code deliberately. If tests still pass when code is broken, the tests are weak (hallucinated success).

### Grok's Prevention Feedback Loop

Missing from all architectures:

> No loop back to agents to learn "don't do that again" (e.g., via RLHF-like signals or prompt updates).

## Key Tensions/Disagreements

| Topic | Tension |
|-------|---------|
| **Stage count** | ChatGPT: 6 stages OK with refinement. Others: Collapse 4-5-6 into iterative loop |
| **Intent extraction reliability** | Ranges from "central to system" (ChatGPT) to "high risk of confident errors, needs fallback" (Codex) |
| **Debate approach** | ChatGPT: Useful for surfacing constraints, not final decision. Grok: Effective for rationale. Gemini: Didn't mention |
| **Structured merge first?** | Gemini: Yes, Tree-sitter/Mergiraf as Stage 0. ChatGPT: Yes, reduces spurious conflicts. Others: Less emphasis |

## Research Pointers (Consolidated)

### LLM-Based Resolution
- **DeepMerge** - edit-aware embeddings
- **MergeBERT** - transformer for merge patterns
- **Gmerge** - GPT-3 for textual/semantic conflicts
- **ConGra benchmark** - 44,948 conflicts, 34 projects
- **Harmony** - production system, ~90% auto-resolve rate

### Structured/Semantic Merge
- **Tree-sitter / Mergiraf** - syntax-aware
- **GumTree** - AST differencing
- **SPORK / Mastery** - structured merge for Java
- **Sesame** - semistructured with syntactic separators

### Tooling
- **WizardMerge** - dependency-aware suggestions
- **Plastic SCM / SemanticMerge** - industrial semantic merge

## Revised Architecture (Incorporating Feedback)

```
STAGE 0: SEMANTIC CONFLICT DETECTION (NEW - unanimous)
├── Compile/typecheck gate
├── API surface diff
├── Dependency diff
├── Import graph analysis
├── Symbol-level overlap detection
└── IF clean AND orthogonal → fast-path auto-merge

STAGE 1: CONTEXT ASSEMBLY (refined)
├── Structured Decision Records (not raw traces)
├── AST-sliced relevant code only (not "surrounding code")
├── Base commit analysis (the "before" state)
└── Provenance graph construction

STAGE 2: INTENT EXTRACTION (refined)
├── Evidence-backed extraction (task + tests + files + diff)
├── Output: constraint sets + priority ordering
├── Confidence scoring
├── Cross-check: task spec vs ADR vs actual diff
└── IF low confidence → escalate, don't guess

STAGE 2.5: INTERFACE HARMONIZATION (NEW - Gemini)
├── Align signatures/types before test synthesis
├── "Harness Repair" - make tests compilable
└── Build must pass before proceeding

STAGE 3: TEST SYNTHESIS (refined)
├── Union of tests + interface integration tests
├── Differential tests (C vs A for A-behavior, C vs B for B-behavior)
├── Mutation testing to verify test quality
└── IF tests weak → flag for human attention

STAGE 4: CANDIDATE GENERATION (refined)
├── Enforced strategy templates:
│   ├── Conservative (preserve both, adapter layers)
│   ├── Left-biased (A's architecture, B adapted)
│   ├── Right-biased (B's architecture, A adapted)
│   ├── Architectural reconciliation (new abstraction)
│   └── Safety-first (stricter validation)
└── Structural diversity constraints (not just temperature)

STAGE 5: TIERED VALIDATION (refined)
├── Tier 1: Compile/typecheck (seconds)
├── Tier 2: Lint + static analysis (seconds)
├── Tier 3: Targeted tests (impacted only)
├── Tier 4: Full suite (high-risk only)
├── Scoring: correctness, arch fit, diff size, security
└── Eliminate failing candidates early

STAGE 6: SELECTION + REFINEMENT (collapsed)
├── Multi-objective scoring
├── Critic review (if needed)
├── Mutation validation
└── Human escalation triggers:
    ├── Low intent confidence
    ├── Security-sensitive files
    ├── Tests removed/weakened
    ├── API changes across modules
    ├── Critic rejects 3+ times
    └── Complexity spike (2x+ original)

FEEDBACK LOOP (NEW - Grok)
└── Signal back to agents: patterns that cause conflicts
```

## Implementation Priority (Refined)

Based on consensus, the recommended order:

1. **Provenance capture + conflict classification** - Foundation everything else needs
2. **Stage 0: Semantic detection** - Catches "clean but wrong" merges (biggest silent failure mode)
3. **Structured Decision Records** - Replace flaky trace capture with reliable structured data
4. **Fast-path resolver** - Handle the easy 60-70% without expensive pipeline
5. **Test-first resolution** - For remaining conflicts, synthesize spec then generate
6. **Full candidate generation + validation** - Only for complex cases

## Key Architectural Shifts from Original Proposal

1. **Detection before resolution** (Stage 0)
2. **Evidence-grounded intent** (not hallucinated)
3. **Interface repair before test synthesis**
4. **Enforced candidate diversity**
5. **Tiered validation for cost control**
6. **Prevention feedback loop**

---

*Document generated from multi-AI review session, January 2026*
