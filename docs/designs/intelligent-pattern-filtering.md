# Intelligent Pattern Filtering Design

## Problem Statement

Error patterns learned in one context (repo, workflow YAML, phase) should be intelligently applicable across contexts while respecting relevance. The system needs to:

1. **Share universally applicable patterns** (e.g., `ModuleNotFoundError: pip install X`)
2. **Respect context-specific patterns** (e.g., workflow phase-specific fixes)
3. **Handle YAML workflow evolution** without invalidating old learnings
4. **Enable intelligent filtering** without over-engineering

## Guiding Principles

From multi-model consensus:
- **Capture context now, filter intelligently later**
- **Search globally, rank by context similarity** (don't filter - score)
- **Decay without deletion** - demote old patterns, let evergreen patterns self-identify
- **Let data reveal universality** rather than predicting upfront

---

## Current System Analysis

### Touchpoints That Need Changes

| Component | File | Current State | Change Needed |
|-----------|------|---------------|---------------|
| **ErrorEvent model** | `models.py:12` | Has `workflow_id`, `phase_id`, `project_id` | Add `context: dict` field |
| **Fingerprinter** | `fingerprint.py` | Extracts `error_type` | Add `extract_language()` helper |
| **Detectors** | `detectors/*.py` | Capture workflow/phase | Populate `context` field |
| **Supabase Schema** | `migrations/001_healing_schema.sql` | `project_id` only | Add `context`, `tags`, `project_ids[]`, `last_success_at` |
| **Supabase Client** | `supabase_client.py` | Filter by `project_id` | Add scored lookup, context updates |
| **HealingClient** | `client.py:74` | Returns first match | Return scored results, filter by threshold |
| **Backfill** | `backfill.py` | Basic error extraction | Extract context from log events |

### Current Data Flow

```
Error occurs
    ↓
Detector captures error → ErrorEvent (has fingerprint, workflow_id, phase_id)
    ↓
Fingerprinter adds fingerprint/fingerprint_coarse
    ↓
HealingClient.lookup() → Tier 1 (exact match) → Tier 2 (RAG) → Tier 3 (causality)
    ↓
Supabase query filters by project_id + fingerprint
    ↓
Pattern returned (or not)
```

**Problem**: Lookup is project_id-scoped. A fix learned in `project-A` won't help `project-B`.

---

## Proposed Design

### 1. Schema Changes

```sql
-- Add to error_patterns table
ALTER TABLE error_patterns ADD COLUMN IF NOT EXISTS
  context JSONB DEFAULT '{}',              -- Flexible context bag
  tags TEXT[] DEFAULT '{}',                -- Fast filtering tags
  project_ids TEXT[] DEFAULT '{}',         -- Projects where this worked
  last_success_at TIMESTAMPTZ,             -- For recency scoring
  universality_score FLOAT DEFAULT 0.0;    -- Computed: len(project_ids) / threshold

-- Add to learnings table
ALTER TABLE learnings ADD COLUMN IF NOT EXISTS
  context JSONB DEFAULT '{}',              -- Context when learning was created
  tags TEXT[] DEFAULT '{}';                -- Fast filtering tags

-- Indexes for tag filtering
CREATE INDEX IF NOT EXISTS idx_error_patterns_tags
  ON error_patterns USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_error_patterns_project_ids
  ON error_patterns USING gin(project_ids);
```

### 2. Context Schema

```python
@dataclass
class PatternContext:
    """Context captured with each pattern."""

    # Most valuable for filtering (all models agree)
    language: str | None = None           # python, javascript, go, rust
    error_category: str | None = None     # import, syntax, type, runtime, test

    # Workflow-specific (optional)
    workflow_phase: str | None = None     # plan, execute, review, verify, learn
    workflow_version: str | None = None   # Workflow YAML version if available

    # Environment
    os: str | None = None                 # linux, darwin, windows
    runtime_version: str | None = None    # python 3.11, node 18, etc.

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}
```

### 3. Tag Derivation

Tags are derived from context for fast filtering:

```python
def derive_tags(context: PatternContext, error: ErrorEvent) -> list[str]:
    """Derive searchable tags from context."""
    tags = []

    # Language tag (highest value)
    if context.language:
        tags.append(context.language)

    # Error category
    if context.error_category:
        tags.append(f"cat:{context.error_category}")

    # Error type (from fingerprinting)
    error_type = extract_error_type(error.description)
    if error_type and error_type != "UnknownError":
        tags.append(f"type:{error_type}")

    # Phase (if workflow-aware)
    if context.workflow_phase:
        tags.append(f"phase:{context.workflow_phase}")

    return tags
```

### 4. Lookup with Relevance Scoring

Replace binary "found/not found" with scored results:

```python
@dataclass
class ScoredPattern:
    """Pattern with relevance score."""
    pattern: dict
    score: float              # 0.0 - 1.0
    match_type: str           # 'exact', 'cross_project', 'rag'
    context_overlap: float    # How much context matched

class HealingClient:
    # Thresholds
    EXACT_MATCH_THRESHOLD = 0.7      # Use exact match if score > this
    CROSS_PROJECT_THRESHOLD = 0.85   # Higher bar for cross-project
    RAG_THRESHOLD = 0.85             # Existing RAG threshold

    async def lookup(self, error: ErrorEvent, context: PatternContext) -> LookupResult:
        """Three-tier lookup with relevance scoring."""

        # Tier 1a: Exact match in same project
        result = await self._lookup_exact_same_project(error)
        if result and result.score >= self.EXACT_MATCH_THRESHOLD:
            return result

        # Tier 1b: Exact match in OTHER projects (cross-project learning)
        result = await self._lookup_exact_cross_project(error, context)
        if result and result.score >= self.CROSS_PROJECT_THRESHOLD:
            return result

        # Tier 2: RAG semantic search (already cross-project)
        result = await self._lookup_tier2(error)
        if result and result.pattern:
            return result

        # Tier 3: Causality
        return await self._lookup_tier3(error)
```

### 5. Relevance Scoring Function

```python
def calculate_relevance_score(
    pattern: dict,
    query_context: PatternContext,
    query_project_id: str,
) -> float:
    """Calculate relevance score for a pattern.

    Components:
    - success_rate: Historical success rate (0-1)
    - context_overlap: How much context matches (0-1)
    - universality: Pattern worked in multiple projects (0-1)
    - recency: Recent success boosts score (0-1)
    """

    # Base: Success rate
    success_count = pattern.get("success_count", 0)
    failure_count = pattern.get("failure_count", 0)
    total = success_count + failure_count
    success_rate = success_count / total if total > 0 else 0.5

    # Context overlap (0-1)
    pattern_context = pattern.get("context", {})
    overlap = calculate_context_overlap(pattern_context, query_context.to_dict())

    # Universality bonus (worked in multiple projects)
    project_ids = pattern.get("project_ids", [])
    universality = min(len(project_ids) / 3, 1.0)  # Cap at 3 projects

    # Recency factor (gentle decay over 90 days)
    last_success = pattern.get("last_success_at")
    recency = calculate_recency_factor(last_success, decay_days=90)

    # Same-project bonus
    same_project = 1.0 if query_project_id in project_ids else 0.0

    # Weighted combination
    score = (
        0.35 * success_rate +
        0.25 * overlap +
        0.15 * universality +
        0.10 * recency +
        0.15 * same_project
    )

    return min(score, 1.0)


def calculate_context_overlap(pattern_ctx: dict, query_ctx: dict) -> float:
    """Calculate overlap between two context dicts.

    Language match is weighted highest.
    """
    if not pattern_ctx or not query_ctx:
        return 0.5  # Neutral if no context

    score = 0.0
    weights = {
        "language": 0.4,           # Most important
        "error_category": 0.25,
        "workflow_phase": 0.15,
        "os": 0.1,
        "runtime_version": 0.1,
    }

    for key, weight in weights.items():
        if key in pattern_ctx and key in query_ctx:
            if pattern_ctx[key] == query_ctx[key]:
                score += weight

    return score
```

### 6. Recording Patterns with Context

When recording a fix result, update `project_ids[]` and context:

```python
async def record_fix_result(
    self,
    fingerprint: str,
    success: bool,
    project_id: str,
    context: PatternContext,
) -> None:
    """Record fix result with context updates."""

    if success:
        # Add this project to the list of projects where it worked
        await self.client.rpc(
            "add_project_to_pattern",
            {
                "p_fingerprint": fingerprint,
                "p_project_id": project_id,
            },
        ).execute()

        # Update last_success_at
        await (
            self.client.table("error_patterns")
            .update({"last_success_at": datetime.utcnow().isoformat()})
            .eq("fingerprint", fingerprint)
            .execute()
        )

    # Update context (merge, don't overwrite)
    await self._merge_pattern_context(fingerprint, context)
```

### 7. Backfill Enhancement

Update backfill to extract context from historical logs:

```python
def _extract_context(self, event: dict) -> PatternContext:
    """Extract context from a workflow log event."""

    # Language detection from error message
    description = event.get("description", "")
    language = self._detect_language(description, event)

    # Error category
    error_category = self._categorize_error(description)

    return PatternContext(
        language=language,
        error_category=error_category,
        workflow_phase=event.get("phase_id") or event.get("phase"),
        os=event.get("os"),
    )

def _detect_language(self, description: str, event: dict) -> str | None:
    """Detect programming language from error."""

    # Python indicators
    if any(x in description for x in ["ModuleNotFoundError", "ImportError", "TypeError:", "ValueError:", ".py"]):
        return "python"

    # JavaScript indicators
    if any(x in description for x in ["ReferenceError", "TypeError:", "SyntaxError:", ".js", ".ts", "npm", "node"]):
        return "javascript"

    # Go indicators
    if any(x in description for x in ["panic:", "go:", ".go", "cannot find package"]):
        return "go"

    # Rust indicators
    if any(x in description for x in ["error[E", "cargo", ".rs", "rustc"]):
        return "rust"

    # Check file extensions in event
    file_path = event.get("file_path", "")
    if file_path:
        if file_path.endswith(".py"):
            return "python"
        elif file_path.endswith((".js", ".ts", ".tsx")):
            return "javascript"
        elif file_path.endswith(".go"):
            return "go"
        elif file_path.endswith(".rs"):
            return "rust"

    return None
```

---

## SQL Migration

```sql
-- Migration 002: Intelligent Pattern Filtering
-- Phase: Context-Aware Pattern Matching

-- 1. Add new columns to error_patterns
ALTER TABLE error_patterns
  ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS project_ids TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS universality_score FLOAT DEFAULT 0.0;

-- 2. Add new columns to learnings
ALTER TABLE learnings
  ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

-- 3. Indexes for efficient filtering
CREATE INDEX IF NOT EXISTS idx_error_patterns_tags
  ON error_patterns USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_error_patterns_project_ids
  ON error_patterns USING gin(project_ids);
CREATE INDEX IF NOT EXISTS idx_error_patterns_context
  ON error_patterns USING gin(context);
CREATE INDEX IF NOT EXISTS idx_error_patterns_last_success
  ON error_patterns(last_success_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_learnings_tags
  ON learnings USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_learnings_context
  ON learnings USING gin(context);

-- 4. Function to add a project to pattern's project_ids
CREATE OR REPLACE FUNCTION add_project_to_pattern(
  p_fingerprint TEXT,
  p_project_id TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE error_patterns
  SET
    project_ids = array_append(
      COALESCE(project_ids, '{}'),
      p_project_id
    ),
    -- Deduplicate
    project_ids = (
      SELECT array_agg(DISTINCT x)
      FROM unnest(array_append(COALESCE(project_ids, '{}'), p_project_id)) x
    ),
    -- Update universality score
    universality_score = (
      SELECT COUNT(DISTINCT x)::float / 3.0
      FROM unnest(array_append(COALESCE(project_ids, '{}'), p_project_id)) x
    ),
    updated_at = NOW()
  WHERE fingerprint = p_fingerprint;
END;
$$;

-- 5. Function for cross-project pattern lookup with scoring
CREATE OR REPLACE FUNCTION lookup_patterns_scored(
  p_fingerprint TEXT,
  p_project_id TEXT,
  p_language TEXT DEFAULT NULL,
  p_tags TEXT[] DEFAULT '{}'
)
RETURNS TABLE (
  id UUID,
  fingerprint TEXT,
  description TEXT,
  context JSONB,
  tags TEXT[],
  project_ids TEXT[],
  success_count INTEGER,
  failure_count INTEGER,
  last_success_at TIMESTAMPTZ,
  universality_score FLOAT,
  relevance_score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_success_weight FLOAT := 0.35;
  v_universality_weight FLOAT := 0.20;
  v_recency_weight FLOAT := 0.15;
  v_same_project_weight FLOAT := 0.20;
  v_tag_match_weight FLOAT := 0.10;
BEGIN
  RETURN QUERY
  SELECT
    ep.id,
    ep.fingerprint,
    ep.description,
    ep.context,
    ep.tags,
    ep.project_ids,
    ep.success_count,
    ep.failure_count,
    ep.last_success_at,
    ep.universality_score,
    -- Calculate relevance score
    (
      -- Success rate component
      v_success_weight * COALESCE(
        ep.success_count::float / NULLIF(ep.success_count + ep.failure_count, 0),
        0.5
      ) +
      -- Universality component
      v_universality_weight * LEAST(COALESCE(ep.universality_score, 0), 1.0) +
      -- Recency component (decay over 90 days)
      v_recency_weight * CASE
        WHEN ep.last_success_at IS NULL THEN 0.5
        WHEN ep.last_success_at > NOW() - INTERVAL '7 days' THEN 1.0
        WHEN ep.last_success_at > NOW() - INTERVAL '30 days' THEN 0.8
        WHEN ep.last_success_at > NOW() - INTERVAL '90 days' THEN 0.5
        ELSE 0.2
      END +
      -- Same project bonus
      v_same_project_weight * CASE
        WHEN p_project_id = ANY(COALESCE(ep.project_ids, '{}')) THEN 1.0
        ELSE 0.0
      END +
      -- Tag match component
      v_tag_match_weight * CASE
        WHEN p_language IS NOT NULL AND p_language = ANY(ep.tags) THEN 1.0
        WHEN array_length(p_tags, 1) > 0 AND ep.tags && p_tags THEN 0.5
        ELSE 0.0
      END
    )::FLOAT AS relevance_score
  FROM error_patterns ep
  WHERE ep.fingerprint = p_fingerprint
    AND ep.quarantined = FALSE
  ORDER BY relevance_score DESC;
END;
$$;

-- 6. Update match_learnings to include context scoring
CREATE OR REPLACE FUNCTION match_learnings_with_context(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INTEGER,
  p_project_id TEXT,
  p_language TEXT DEFAULT NULL,
  p_tags TEXT[] DEFAULT '{}'
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  description TEXT,
  action JSONB,
  pattern_fingerprint TEXT,
  lifecycle TEXT,
  confidence FLOAT,
  similarity FLOAT,
  context_score FLOAT,
  final_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    l.id,
    l.title,
    l.description,
    l.action,
    l.pattern_fingerprint,
    l.lifecycle,
    l.confidence,
    (1 - (l.embedding <=> query_embedding))::FLOAT AS similarity,
    -- Context score
    CASE
      WHEN p_language IS NOT NULL AND p_language = ANY(l.tags) THEN 0.3
      WHEN l.tags && p_tags THEN 0.15
      ELSE 0.0
    END::FLOAT AS context_score,
    -- Final weighted score
    (
      0.7 * (1 - (l.embedding <=> query_embedding)) +
      0.2 * l.confidence +
      0.1 * CASE
        WHEN p_language IS NOT NULL AND p_language = ANY(l.tags) THEN 1.0
        WHEN l.tags && p_tags THEN 0.5
        ELSE 0.0
      END
    )::FLOAT AS final_score
  FROM learnings l
  WHERE l.project_id = p_project_id OR l.project_id IS NULL  -- Include global learnings
    AND l.lifecycle IN ('active', 'automated')
    AND l.embedding IS NOT NULL
    AND 1 - (l.embedding <=> query_embedding) > match_threshold
  ORDER BY final_score DESC, similarity DESC
  LIMIT match_count;
END;
$$;

-- 7. Migrate existing patterns to populate project_ids from project_id
UPDATE error_patterns
SET project_ids = ARRAY[project_id]
WHERE project_ids IS NULL OR project_ids = '{}';
```

---

## Implementation Plan

### Phase 1: Schema & Models (Non-Breaking)
1. Run SQL migration
2. Add `PatternContext` dataclass to `models.py`
3. Add `context` field to `ErrorEvent`
4. No behavior changes yet

### Phase 2: Context Capture
1. Update all detectors to populate `context`
2. Update `fingerprint.py` with `extract_language()` helper
3. Update backfill to extract context from historical logs
4. Test that context is being captured

### Phase 3: Scoring Lookup
1. Add `lookup_patterns_scored` RPC call to Supabase client
2. Update `HealingClient.lookup()` to use scored results
3. Add thresholds for same-project vs cross-project
4. Test cross-project pattern matching

### Phase 4: Recording Updates
1. Update `record_fix_result` to populate `project_ids[]`
2. Update `last_success_at` on success
3. Merge context on fix application
4. Test universality accumulation

---

## Testing Strategy

1. **Unit Tests**
   - `test_context_extraction`: Verify language/category detection
   - `test_relevance_scoring`: Verify score calculation
   - `test_tag_derivation`: Verify tags derived correctly

2. **Integration Tests**
   - `test_cross_project_lookup`: Pattern from project A found in project B
   - `test_same_project_priority`: Same-project patterns ranked higher
   - `test_universality_accumulation`: project_ids grows with usage

3. **Backfill Tests**
   - `test_backfill_extracts_context`: Historical logs get context
   - `test_backfill_updates_project_ids`: Existing patterns updated

---

## Open Questions for Review

1. **Should we support "global" patterns?** Patterns not tied to any project_id that apply everywhere?

2. **Context merging strategy**: When the same fingerprint is seen in different contexts, should we union the contexts or keep separate records?

3. **Decay vs evergreen**: Should there be explicit "evergreen" tagging, or let universality score handle it?

4. **RAG scope**: Should Tier 2 (RAG) search across all projects or respect project boundaries?

5. **Backfill strategy**: Should backfill re-fingerprint with context, or just add context to existing patterns?
