# Intelligent Pattern Filtering Design v2

**Status**: Ready for Implementation
**Version**: 2.0 (Revised based on multi-model review)

## Summary of Changes from v1

Based on multi-model review (Claude, GPT, Gemini, Grok, DeepSeek), key improvements:

1. **Wilson score** for success rate (handles sample size)
2. **Junction table** for per-project tracking (scales better than arrays)
3. **Failure tracking** with recency penalty
4. **Provenance fields** for trust scoring
5. **Hierarchical context matching** with weighted dimensions
6. **Exponential decay** for recency (30-day half-life)
7. **Same-project as multiplier** not additive

---

## Schema Changes

### error_patterns Table Updates

```sql
ALTER TABLE error_patterns ADD COLUMN IF NOT EXISTS
  -- Context (JSONB for flexibility)
  context JSONB DEFAULT '{}',
  tags TEXT[] DEFAULT '{}',

  -- Failure tracking (critical gap identified)
  last_failure_at TIMESTAMPTZ,

  -- Recency
  last_success_at TIMESTAMPTZ,

  -- Universality (computed from project applications)
  universality_score FLOAT DEFAULT 0.0,
  project_count INTEGER DEFAULT 0,

  -- Provenance/Trust
  resolution_source TEXT DEFAULT 'auto',  -- 'auto' | 'human' | 'community'
  verified_by TEXT,
  verified_at TIMESTAMPTZ,

  -- Lifecycle
  deprecated_at TIMESTAMPTZ,
  superseded_by UUID,

  -- Safety (already have safety_category, add risk_level)
  risk_level TEXT DEFAULT 'low',  -- 'low' | 'medium' | 'high' | 'critical'

  -- Evergreen flag (manual curation override)
  is_evergreen BOOLEAN DEFAULT FALSE;
```

### New Junction Table: pattern_project_applications

Tracks per-project outcomes (scales better than project_ids[]):

```sql
CREATE TABLE IF NOT EXISTS pattern_project_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_id UUID NOT NULL REFERENCES error_patterns(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,

  -- Timestamps
  first_applied_at TIMESTAMPTZ DEFAULT NOW(),
  last_applied_at TIMESTAMPTZ DEFAULT NOW(),
  last_success_at TIMESTAMPTZ,
  last_failure_at TIMESTAMPTZ,

  -- Per-project stats
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,

  -- Context snapshot when applied
  context_snapshot JSONB DEFAULT '{}',

  UNIQUE(pattern_id, project_id)
);
```

### learnings Table Updates

```sql
ALTER TABLE learnings ADD COLUMN IF NOT EXISTS
  context JSONB DEFAULT '{}',
  tags TEXT[] DEFAULT '{}';
```

---

## Context Schema

```python
@dataclass
class PatternContext:
    """Context captured with each pattern.

    Dimensions ordered by matching weight (highest first).
    """

    # Tier 1: Must match (weight 1.0)
    language: str | None = None  # python, javascript, go, rust, java, unknown

    # Tier 2: Should match (weight 0.8)
    error_category: str | None = None  # dependency, syntax, runtime, network, permission, config, test

    # Tier 3: Nice to match (weight 0.5)
    workflow_phase: str | None = None  # plan, execute, review, verify, learn
    framework: str | None = None  # react, django, express, etc.

    # Tier 4: Optional refinement (weight 0.3)
    os: str | None = None  # linux, darwin, windows
    runtime_version: str | None = None  # Semver string
    package_manager: str | None = None  # pip, npm, cargo, go

    # Metadata
    extraction_confidence: float = 0.5  # How confident we are in this context
```

---

## Scoring Formula (Revised)

### Wilson Score for Confidence-Adjusted Success Rate

Handles the sample size problem (1/1 shouldn't beat 95/100):

```python
def wilson_score(successes: int, total: int, confidence: float = 0.95) -> float:
    """Calculate Wilson score lower bound for success rate.

    Returns conservative estimate of success rate accounting for sample size.
    """
    if total == 0:
        return 0.5  # Neutral if no data

    import math
    z = 1.96  # 95% confidence interval
    p = successes / total
    n = total

    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adjustment = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)

    return (centre - adjustment) / denominator
```

### Relevance Score Calculation

```python
def calculate_relevance_score(
    pattern: dict,
    query_context: PatternContext,
    query_project_id: str,
) -> float:
    """Calculate relevance score with Wilson scoring and multiplicative same-project boost."""

    success_count = pattern.get("success_count", 0)
    failure_count = pattern.get("failure_count", 0)
    total = success_count + failure_count

    # 1. Confidence-adjusted success rate (Wilson score)
    confidence_rate = wilson_score(success_count, total)

    # 2. Failure penalty (recent failures hurt more)
    failure_penalty = calculate_failure_penalty(
        pattern.get("last_failure_at"),
        failure_count,
        total
    )

    # 3. Context overlap (hierarchical weighted matching)
    context_overlap = calculate_context_overlap(
        pattern.get("context", {}),
        query_context
    )

    # 4. Universality (log scale with diminishing returns)
    project_count = pattern.get("project_count", 1)
    universality = min(math.log10(project_count + 1) / math.log10(10), 1.0)  # Cap at 10 projects

    # 5. Recency (exponential decay, 30-day half-life)
    recency = calculate_recency_score(pattern.get("last_success_at"), half_life_days=30)

    # 6. Trust bonus (human verified or evergreen)
    trust_bonus = 0.0
    if pattern.get("verified_by"):
        trust_bonus = 0.15
    elif pattern.get("is_evergreen"):
        trust_bonus = 0.10

    # Base score (weighted sum)
    base_score = (
        0.30 * confidence_rate +
        0.25 * context_overlap +
        0.15 * universality +
        0.15 * recency +
        0.15 * (1.0 - failure_penalty)  # Inverse of penalty
    )

    # Add trust bonus
    base_score = min(base_score + trust_bonus, 1.0)

    # 7. Same-project as MULTIPLIER (not additive)
    project_ids = get_pattern_project_ids(pattern)
    if query_project_id in project_ids:
        base_score *= 1.2  # 20% boost

    # 8. Risk penalty for high-stakes fixes
    risk_multipliers = {
        "low": 1.0,
        "medium": 0.95,
        "high": 0.85,
        "critical": 0.70,
    }
    risk_level = pattern.get("risk_level", "low")
    base_score *= risk_multipliers.get(risk_level, 1.0)

    return min(base_score, 1.0)


def calculate_failure_penalty(
    last_failure_at: str | None,
    failure_count: int,
    total: int,
) -> float:
    """Calculate penalty for recent failures.

    Recent failures hurt more than old failures.
    """
    if failure_count == 0 or total == 0:
        return 0.0

    base_failure_rate = failure_count / total

    if last_failure_at:
        days_since_failure = (datetime.utcnow() - parse_timestamp(last_failure_at)).days
        # Exponential decay of penalty (7-day half-life)
        recency_factor = math.exp(-days_since_failure / 7)
        return base_failure_rate * (0.5 + 0.5 * recency_factor)

    return base_failure_rate * 0.5


def calculate_context_overlap(
    pattern_context: dict,
    query_context: PatternContext,
) -> float:
    """Calculate weighted overlap between contexts.

    Language match is most important, then error_category, etc.
    """
    if not pattern_context:
        return 0.5  # Neutral if no context

    query_dict = query_context.to_dict() if hasattr(query_context, 'to_dict') else {}
    if not query_dict:
        return 0.5

    # Hierarchical weights
    weights = {
        "language": 1.0,
        "error_category": 0.8,
        "workflow_phase": 0.5,
        "framework": 0.5,
        "os": 0.3,
        "runtime_version": 0.3,
        "package_manager": 0.3,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for key, weight in weights.items():
        if key in pattern_context and key in query_dict:
            total_weight += weight
            if pattern_context[key] == query_dict[key]:
                weighted_sum += weight
            elif key == "runtime_version":
                # Version proximity scoring
                weighted_sum += weight * version_similarity(
                    pattern_context[key],
                    query_dict[key]
                )

    return weighted_sum / total_weight if total_weight > 0 else 0.5


def calculate_recency_score(
    last_success_at: str | None,
    half_life_days: int = 30,
) -> float:
    """Calculate recency score with exponential decay."""
    if not last_success_at:
        return 0.5  # Neutral if unknown

    days_since = (datetime.utcnow() - parse_timestamp(last_success_at)).days
    return math.exp(-days_since * math.log(2) / half_life_days)
```

---

## Lookup Strategy (Revised)

```
Tier 0: In-memory/Redis cache (hot fingerprints) - Optional future optimization
Tier 1a: Exact fingerprint, same project (threshold 0.6)
Tier 1b: Exact fingerprint, cross-project (threshold 0.75, requires >3 project successes)
Tier 2: RAG semantic search (filtered by language first, then re-ranked)
Tier 3: Causality analysis (recent changes correlation)
```

### Cross-Project Guardrails

For a pattern to be used cross-project:
- Must have ≥3 project successes (universality threshold)
- Must have success_count ≥ 5 total
- Must have Wilson score ≥ 0.7
- Language must match (or pattern has no language restriction)

```python
def is_eligible_for_cross_project(pattern: dict) -> bool:
    """Check if pattern meets cross-project guardrails."""
    project_count = pattern.get("project_count", 0)
    success_count = pattern.get("success_count", 0)
    failure_count = pattern.get("failure_count", 0)

    if project_count < 3:
        return False
    if success_count < 5:
        return False

    wilson = wilson_score(success_count, success_count + failure_count)
    if wilson < 0.7:
        return False

    return True
```

---

## SQL Migration

```sql
-- Migration 002: Intelligent Pattern Filtering
-- Run against Supabase

-- 1. Add new columns to error_patterns
ALTER TABLE error_patterns
  ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS last_failure_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS universality_score FLOAT DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS project_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS resolution_source TEXT DEFAULT 'auto',
  ADD COLUMN IF NOT EXISTS verified_by TEXT,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS superseded_by UUID,
  ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'low',
  ADD COLUMN IF NOT EXISTS is_evergreen BOOLEAN DEFAULT FALSE;

-- 2. Add new columns to learnings
ALTER TABLE learnings
  ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

-- 3. Create junction table for per-project tracking
CREATE TABLE IF NOT EXISTS pattern_project_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_id UUID NOT NULL REFERENCES error_patterns(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  first_applied_at TIMESTAMPTZ DEFAULT NOW(),
  last_applied_at TIMESTAMPTZ DEFAULT NOW(),
  last_success_at TIMESTAMPTZ,
  last_failure_at TIMESTAMPTZ,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  context_snapshot JSONB DEFAULT '{}',
  UNIQUE(pattern_id, project_id)
);

-- 4. Indexes
CREATE INDEX IF NOT EXISTS idx_error_patterns_tags ON error_patterns USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_error_patterns_context ON error_patterns USING gin(context);
CREATE INDEX IF NOT EXISTS idx_error_patterns_last_success ON error_patterns(last_success_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_error_patterns_universality ON error_patterns(universality_score DESC);
CREATE INDEX IF NOT EXISTS idx_error_patterns_project_count ON error_patterns(project_count DESC);

CREATE INDEX IF NOT EXISTS idx_learnings_tags ON learnings USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_learnings_context ON learnings USING gin(context);

CREATE INDEX IF NOT EXISTS idx_ppa_pattern_id ON pattern_project_applications(pattern_id);
CREATE INDEX IF NOT EXISTS idx_ppa_project_id ON pattern_project_applications(project_id);

-- 5. Function to record pattern application
CREATE OR REPLACE FUNCTION record_pattern_application(
  p_fingerprint TEXT,
  p_project_id TEXT,
  p_success BOOLEAN,
  p_context JSONB DEFAULT '{}'
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
  v_pattern_id UUID;
BEGIN
  -- Get pattern ID
  SELECT id INTO v_pattern_id
  FROM error_patterns
  WHERE fingerprint = p_fingerprint
  LIMIT 1;

  IF v_pattern_id IS NULL THEN
    RETURN;
  END IF;

  -- Upsert into junction table
  INSERT INTO pattern_project_applications (
    pattern_id, project_id, context_snapshot,
    success_count, failure_count,
    last_success_at, last_failure_at
  )
  VALUES (
    v_pattern_id, p_project_id, p_context,
    CASE WHEN p_success THEN 1 ELSE 0 END,
    CASE WHEN p_success THEN 0 ELSE 1 END,
    CASE WHEN p_success THEN NOW() ELSE NULL END,
    CASE WHEN p_success THEN NULL ELSE NOW() END
  )
  ON CONFLICT (pattern_id, project_id) DO UPDATE SET
    last_applied_at = NOW(),
    success_count = pattern_project_applications.success_count + CASE WHEN p_success THEN 1 ELSE 0 END,
    failure_count = pattern_project_applications.failure_count + CASE WHEN p_success THEN 0 ELSE 1 END,
    last_success_at = CASE WHEN p_success THEN NOW() ELSE pattern_project_applications.last_success_at END,
    last_failure_at = CASE WHEN p_success THEN pattern_project_applications.last_failure_at ELSE NOW() END,
    context_snapshot = p_context;

  -- Update denormalized counts on error_patterns
  UPDATE error_patterns SET
    project_count = (
      SELECT COUNT(DISTINCT project_id)
      FROM pattern_project_applications
      WHERE pattern_id = v_pattern_id
    ),
    universality_score = LEAST(
      (SELECT COUNT(DISTINCT project_id)::float FROM pattern_project_applications WHERE pattern_id = v_pattern_id) / 3.0,
      1.0
    ),
    last_success_at = CASE WHEN p_success THEN NOW() ELSE last_success_at END,
    last_failure_at = CASE WHEN p_success THEN last_failure_at ELSE NOW() END,
    updated_at = NOW()
  WHERE id = v_pattern_id;
END;
$$;

-- 6. Function for scored pattern lookup
CREATE OR REPLACE FUNCTION lookup_patterns_scored(
  p_fingerprint TEXT,
  p_project_id TEXT,
  p_language TEXT DEFAULT NULL,
  p_error_category TEXT DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  fingerprint TEXT,
  description TEXT,
  context JSONB,
  tags TEXT[],
  success_count INTEGER,
  failure_count INTEGER,
  project_count INTEGER,
  last_success_at TIMESTAMPTZ,
  last_failure_at TIMESTAMPTZ,
  universality_score FLOAT,
  is_evergreen BOOLEAN,
  risk_level TEXT,
  relevance_score FLOAT,
  is_same_project BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ep.id,
    ep.fingerprint,
    ep.description,
    ep.context,
    ep.tags,
    ep.success_count,
    ep.failure_count,
    ep.project_count,
    ep.last_success_at,
    ep.last_failure_at,
    ep.universality_score,
    ep.is_evergreen,
    ep.risk_level,
    -- Calculate relevance score in SQL
    (
      -- Wilson score component (0.30 weight)
      0.30 * CASE
        WHEN (ep.success_count + ep.failure_count) = 0 THEN 0.5
        ELSE (
          (ep.success_count::float / (ep.success_count + ep.failure_count)) +
          1.96 * 1.96 / (2 * (ep.success_count + ep.failure_count)) -
          1.96 * SQRT(
            (ep.success_count::float / (ep.success_count + ep.failure_count)) *
            (1 - ep.success_count::float / (ep.success_count + ep.failure_count)) / (ep.success_count + ep.failure_count) +
            1.96 * 1.96 / (4 * (ep.success_count + ep.failure_count) * (ep.success_count + ep.failure_count))
          )
        ) / (1 + 1.96 * 1.96 / (ep.success_count + ep.failure_count))
      END +
      -- Context overlap (0.25 weight) - language match
      0.25 * CASE
        WHEN p_language IS NULL THEN 0.5
        WHEN ep.context->>'language' = p_language THEN 1.0
        WHEN ep.context->>'language' IS NULL THEN 0.5
        ELSE 0.0
      END +
      -- Universality (0.15 weight)
      0.15 * LEAST(ep.universality_score, 1.0) +
      -- Recency (0.15 weight) - 30 day half-life
      0.15 * CASE
        WHEN ep.last_success_at IS NULL THEN 0.5
        ELSE EXP(-EXTRACT(EPOCH FROM (NOW() - ep.last_success_at)) / (30 * 86400) * LN(2))
      END +
      -- Failure penalty inverse (0.15 weight)
      0.15 * (1.0 - CASE
        WHEN ep.failure_count = 0 THEN 0.0
        WHEN ep.last_failure_at IS NULL THEN ep.failure_count::float / NULLIF(ep.success_count + ep.failure_count, 0) * 0.5
        ELSE (ep.failure_count::float / NULLIF(ep.success_count + ep.failure_count, 0)) *
             (0.5 + 0.5 * EXP(-EXTRACT(EPOCH FROM (NOW() - ep.last_failure_at)) / (7 * 86400)))
      END)
    ) *
    -- Same project multiplier (1.2x boost)
    CASE
      WHEN EXISTS (SELECT 1 FROM pattern_project_applications ppa WHERE ppa.pattern_id = ep.id AND ppa.project_id = p_project_id)
      THEN 1.2
      ELSE 1.0
    END *
    -- Risk multiplier
    CASE ep.risk_level
      WHEN 'low' THEN 1.0
      WHEN 'medium' THEN 0.95
      WHEN 'high' THEN 0.85
      WHEN 'critical' THEN 0.70
      ELSE 1.0
    END AS relevance_score,
    -- Is same project flag
    EXISTS (SELECT 1 FROM pattern_project_applications ppa WHERE ppa.pattern_id = ep.id AND ppa.project_id = p_project_id) AS is_same_project
  FROM error_patterns ep
  WHERE ep.fingerprint = p_fingerprint
    AND ep.quarantined = FALSE
    AND ep.deprecated_at IS NULL
  ORDER BY relevance_score DESC;
END;
$$;

-- 7. Migrate existing patterns (populate project_count from project_id)
DO $$
BEGIN
  -- For each existing pattern, create a project application entry
  INSERT INTO pattern_project_applications (pattern_id, project_id, success_count, failure_count)
  SELECT id, project_id, success_count, failure_count
  FROM error_patterns
  WHERE project_id IS NOT NULL
  ON CONFLICT (pattern_id, project_id) DO NOTHING;

  -- Update denormalized counts
  UPDATE error_patterns ep SET
    project_count = (
      SELECT COUNT(DISTINCT project_id)
      FROM pattern_project_applications ppa
      WHERE ppa.pattern_id = ep.id
    ),
    universality_score = LEAST(
      (SELECT COUNT(DISTINCT project_id)::float FROM pattern_project_applications ppa WHERE ppa.pattern_id = ep.id) / 3.0,
      1.0
    );
END $$;

-- 8. RLS policies for new table
ALTER TABLE pattern_project_applications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view pattern applications"
  ON pattern_project_applications FOR SELECT
  USING (TRUE);

CREATE POLICY "Users can insert pattern applications"
  ON pattern_project_applications FOR INSERT
  WITH CHECK (TRUE);

CREATE POLICY "Users can update pattern applications"
  ON pattern_project_applications FOR UPDATE
  USING (TRUE);
```

---

## Implementation Phases

### Phase 1: Schema Migration (This PR)
- Run SQL migration
- Add new columns (non-breaking, all have defaults)
- Create junction table
- Migrate existing data

### Phase 2: Context Capture
- Update `PatternContext` dataclass in models.py
- Update detectors to populate context
- Update backfill to extract context
- Add language detection helpers

### Phase 3: Scored Lookup
- Update `HealingSupabaseClient` with `lookup_patterns_scored`
- Update `HealingClient` to use scored results
- Add cross-project guardrails
- Add thresholds configuration

### Phase 4: Recording Updates
- Update `record_fix_result` to use `record_pattern_application`
- Track per-project outcomes
- Update failure tracking

---

## Open Questions Resolved

| Question | Decision |
|----------|----------|
| Global patterns? | Yes, with guardrails (≥5 successes, ≥3 projects) |
| Same fingerprint, different contexts? | Single pattern + junction table for per-project stats |
| Tier 2 RAG boundaries? | Filter by language first, respect project boundaries by default |
| Evergreen tagging? | Both: auto-computed `universality_score` + manual `is_evergreen` flag |
