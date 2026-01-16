# Phase 2 Implementation Plan: Pattern Memory, Lookup & Security

## Overview
Implement Phase 2 of the Self-Healing Infrastructure as defined in `docs/self-healing-implementation-plan.md`.

**Goal:** Store patterns in Supabase, implement three-tier lookup, add security scrubbing.

## User Decisions
1. **Supabase schema:** Create file only, deploy manually later
2. **LLM model:** Claude Sonnet for pattern generation
3. **Missing API keys:** Fail gracefully, disable Tier 2 lookup

## Components to Implement

### 1. Security Scrubber (`src/healing/security.py`)
Remove secrets and PII before storing in Supabase:
- API keys, tokens, passwords
- AWS keys, private keys, connection strings
- Email addresses (PII)

### 2. Supabase Schema (`migrations/001_healing_schema.sql`)
Tables:
- `healing_config` - Per-project configuration
- `error_patterns` - Tier 1 lookup (fingerprint matching)
- `learnings` - Tier 2 lookup (RAG with pgvector)
- `causality_edges` - Tier 3 lookup (commit→error correlation)
- `healing_audit` - Audit log for cloud environments

### 3. Supabase Client (`src/healing/supabase_client.py`)
- `lookup_pattern(fingerprint)` - Tier 1 exact match
- `lookup_similar(embedding)` - Tier 2 RAG search
- `get_causes(fingerprint)` - Tier 3 causality
- `record_pattern()`, `record_fix_result()`, `audit_log()`

### 4. Embedding Service (`src/healing/embeddings.py`)
- Uses OpenAI text-embedding-ada-002
- Graceful failure when `OPENAI_API_KEY` not set
- `embed(text)`, `embed_error(error)` methods

### 5. Pre-seeded Patterns (`src/healing/preseeded_patterns.py`)
~30 patterns for common errors:
- Python: ModuleNotFoundError, SyntaxError, TypeError
- Node.js: Cannot find module
- Go: cannot find package
- Rust: error codes
- pytest: fixture not found

### 6. Pattern Generator (`src/healing/pattern_generator.py`)
Uses Claude Sonnet to:
- `generate_from_diff()` - Generalize specific fixes into reusable patterns
- `extract_from_transcript()` - Find error→fix sequences in conversations

### 7. Healing Client (`src/healing/client.py`)
Unified client with three-tier lookup:
1. **Tier 1:** Exact fingerprint match (cache → Supabase)
2. **Tier 2:** RAG semantic search (if embedding available)
3. **Tier 3:** Causality analysis (for investigation)

## FixAction Schema
**Already implemented in `src/healing/models.py`** - No changes needed.

## Execution Strategy

### Parallel Execution Assessment

**Components analyzed:**
- Security Scrubber - independent
- Supabase Schema - independent
- Embedding Service - independent
- Supabase Client - depends on Security Scrubber
- Pre-seeded Patterns - depends on Supabase Client
- Pattern Generator - depends on Embedding Service
- Healing Client - depends on all above

**Potential parallel groups:**
- Group 1: Security Scrubber + Supabase Schema + Embedding Service (all independent)
- Group 2: Supabase Client + Pattern Generator (after Group 1)
- Group 3: Pre-seeded Patterns (after Supabase Client)
- Group 4: Healing Client (after all above)

**Decision: SEQUENTIAL execution**

**Reasons:**
1. **Debugging complexity:** Parallel implementation makes it harder to isolate issues
2. **Incremental testing:** Each component can be tested immediately after implementation
3. **Dependencies chain:** Most components have dependencies, limiting parallelism benefit
4. **Code review:** Sequential commits are easier to review
5. **File size:** Each component is ~50-200 lines, fast to implement sequentially

**Verification approach:**
- Read and verify each file after implementation
- Run tests after each component
- Do NOT trust agent summaries - verify by reading files

### Implementation Order
1. Security Scrubber (independent)
2. Supabase Schema (independent)
3. Supabase Client (needs Security Scrubber)
4. Embedding Service (independent)
5. Pre-seeded Patterns (needs Supabase Client)
6. Pattern Generator (needs Embedding Service)
7. Healing Client (needs all above)

## Tests
- `tests/healing/test_security.py`
- `tests/healing/test_supabase_client.py`
- `tests/healing/test_preseeded.py`
- `tests/healing/test_pattern_generator.py`
- `tests/healing/test_embeddings.py`
- `tests/healing/test_healing_client.py`
- `tests/healing/test_lookup_tiers.py`

## Done Criteria (from implementation plan)
- [ ] Supabase schema deployed to `igalnlhcblswjtwaruvy.supabase.co`
- [ ] Pre-seeded patterns loaded (~30)
- [ ] Security scrubber removes secrets before storage
- [ ] Three-tier lookup returns results
- [ ] Embedding generation works
- [ ] Pattern generator creates patterns from diffs
- [ ] Cache works (local SQLite or in-memory for cloud)
- [ ] Works in both LOCAL and CLOUD environments
- [ ] Concurrent access tested (multiple workflows)
