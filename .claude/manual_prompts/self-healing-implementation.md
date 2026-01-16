# Self-Healing Infrastructure Implementation Plan

## Prompt for Orchestrator

```
Create a phased implementation plan for the Self-Healing Infrastructure described in docs/design/self-healing-infrastructure.md (v3.2).

## Context

This is a zero-human automation system that enables the workflow orchestrator to automatically detect, learn from, and resolve errors. Key design principles:

- **Zero-human automation**: Pre-seeded patterns + verified AI precedent (no human bottleneck)
- **Three-tier lookup**: Pattern Memory (exact) → RAG (semantic) → Graph (causality)
- **Supabase backend**: pgvector for RAG, PostgreSQL for relational, recursive CTEs for graph
- **Local fallback**: SQLite cache for offline operation
- **Tiered validation**: 3-phase parallel validation, judge count by safety category

## What Needs Building

### Core Components (from design doc)

1. **Error Detection & Capture** (Section 2)
   - Workflow log parser
   - Session transcript analyzer
   - Subprocess output interceptor
   - Real-time workflow hooks

2. **Fingerprinting System** (Section 4.7)
   - Normalization rules
   - Hierarchical fingerprints (coarse + fine)
   - Fingerprint clustering
   - Stability tests

3. **Pattern Memory** (Sections 4.5, 17)
   - Pre-seeded universal patterns (~30)
   - Supabase schema (learnings, error_patterns, causality_edges)
   - Local SQLite cache
   - Sync mechanism

4. **Three-Tier Lookup** (Section 17.3-17.4)
   - Tier 1: Exact fingerprint match
   - Tier 2: RAG semantic search (pgvector)
   - Tier 3: Graph causality (explicit edges)

5. **Validation Pipeline** (Section 7)
   - Phase 1: Pre-flight (parallel fast checks)
   - Phase 2: Verification (parallel build/test/lint)
   - Phase 3: Approval (tiered multi-model)

6. **Fix Application** (Section 10)
   - Git branch creation
   - Diff application
   - Verification execution
   - Rollback mechanism

7. **Lifecycle Management** (Section 11.5)
   - 4-state lifecycle (DRAFT → ACTIVE → AUTOMATED → DEPRECATED)
   - Automatic graduation
   - Quarantine handling

8. **Cost Controls** (Section 4.8)
   - Daily limits
   - Rate limiting
   - Tiered validation costs

9. **CLI Commands** (Section 4.10)
   - `orchestrator heal status`
   - `orchestrator heal apply [--force] [--dry-run]`
   - `orchestrator heal ignore <fingerprint>`
   - `orchestrator heal unquarantine <fingerprint>`
   - `orchestrator heal explain <fingerprint>`
   - `orchestrator heal export`

10. **Issue Queue & Batching** (Section 9)
    - Silent accumulation during workflow
    - End-of-session review
    - Batch operations

## Constraints

- Must integrate with existing orchestrator codebase
- Supabase is already in use (credentials in secrets.enc.yaml)
- Python 3.11+ with async support
- Tests required for each component
- No breaking changes to existing CLI commands

## Phasing Guidance

The design doc recommends this rollout (from multi-model review):

```
Week 1-2: Detection + fingerprint validation only (no fixing)
Week 3-4: Suggestions shown, AI builds precedent via verification
Week 5-6: Auto-apply SAFE only (imports, formatting)
Week 7+:  Expand based on measured success rate (>90% target)
```

Please create an implementation plan that:
1. Breaks this into concrete development phases
2. Identifies dependencies between components
3. Specifies what's needed for each phase to be "done"
4. Considers testing strategy for the healing system itself
5. Includes integration points with existing orchestrator

Focus on what to build, not timelines. I'll use the orchestrator workflow to execute each phase.
```

## Usage

```bash
# Start the implementation workflow
orchestrator start "$(cat .claude/manual_prompts/self-healing-implementation.md)"

# Or copy the prompt section above and run:
orchestrator start "Create a phased implementation plan for..."
```

## Notes

- The design doc is comprehensive (~3,600 lines) - the plan should reference specific sections
- Consider starting with detection-only (Phase 1) to validate fingerprinting before building fix application
- The local SQLite cache should be early (enables offline development/testing)
- Supabase schema can be created incrementally as needed
