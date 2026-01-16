-- Migration 002: Intelligent Pattern Filtering
-- Self-Healing Infrastructure Enhancement
--
-- This migration adds:
-- 1. Context tracking (JSONB) for intelligent filtering
-- 2. Tags for fast GIN-indexed lookups
-- 3. Junction table for per-project pattern tracking
-- 4. Failure tracking with recency
-- 5. Provenance/trust fields
-- 6. Scored lookup function with Wilson score
--
-- Run this against your Supabase project after 001_healing_schema.sql

-- ==========================================
-- 1. Add new columns to error_patterns
-- ==========================================
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

-- Add occurrence_count if missing (needed for some queries)
ALTER TABLE error_patterns
  ADD COLUMN IF NOT EXISTS occurrence_count INTEGER DEFAULT 0;

-- ==========================================
-- 2. Add new columns to learnings
-- ==========================================
ALTER TABLE learnings
  ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

-- ==========================================
-- 3. Create junction table for per-project tracking
-- ==========================================
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

-- ==========================================
-- 4. Indexes for efficient querying
-- ==========================================

-- Context and tags indexes (GIN for JSONB and arrays)
CREATE INDEX IF NOT EXISTS idx_error_patterns_tags
  ON error_patterns USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_error_patterns_context
  ON error_patterns USING gin(context);
CREATE INDEX IF NOT EXISTS idx_error_patterns_context_language
  ON error_patterns ((context->>'language'));

-- Recency and universality indexes
CREATE INDEX IF NOT EXISTS idx_error_patterns_last_success
  ON error_patterns(last_success_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_error_patterns_last_failure
  ON error_patterns(last_failure_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_error_patterns_universality
  ON error_patterns(universality_score DESC);
CREATE INDEX IF NOT EXISTS idx_error_patterns_project_count
  ON error_patterns(project_count DESC);

-- Learnings indexes
CREATE INDEX IF NOT EXISTS idx_learnings_tags
  ON learnings USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_learnings_context
  ON learnings USING gin(context);

-- Junction table indexes
CREATE INDEX IF NOT EXISTS idx_ppa_pattern_id
  ON pattern_project_applications(pattern_id);
CREATE INDEX IF NOT EXISTS idx_ppa_project_id
  ON pattern_project_applications(project_id);
CREATE INDEX IF NOT EXISTS idx_ppa_last_applied
  ON pattern_project_applications(last_applied_at DESC);

-- ==========================================
-- 5. Function to record pattern application
-- ==========================================
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
    context_snapshot = CASE WHEN p_context != '{}' THEN p_context ELSE pattern_project_applications.context_snapshot END;

  -- Update denormalized counts on error_patterns
  UPDATE error_patterns SET
    project_count = (
      SELECT COUNT(DISTINCT ppa.project_id)
      FROM pattern_project_applications ppa
      WHERE ppa.pattern_id = v_pattern_id
    ),
    universality_score = LEAST(
      (SELECT COUNT(DISTINCT ppa.project_id)::float FROM pattern_project_applications ppa WHERE ppa.pattern_id = v_pattern_id) / 3.0,
      1.0
    ),
    last_success_at = CASE WHEN p_success THEN NOW() ELSE error_patterns.last_success_at END,
    last_failure_at = CASE WHEN p_success THEN error_patterns.last_failure_at ELSE NOW() END,
    success_count = CASE WHEN p_success THEN error_patterns.success_count + 1 ELSE error_patterns.success_count END,
    failure_count = CASE WHEN p_success THEN error_patterns.failure_count ELSE error_patterns.failure_count + 1 END,
    updated_at = NOW()
  WHERE id = v_pattern_id;
END;
$$;

-- ==========================================
-- 6. Function for scored pattern lookup
-- ==========================================
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
DECLARE
  v_total INTEGER;
  v_success_rate FLOAT;
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
    -- Calculate relevance score
    (
      -- Wilson score component (0.30 weight)
      -- Simplified Wilson score lower bound
      0.30 * CASE
        WHEN (ep.success_count + ep.failure_count) = 0 THEN 0.5
        WHEN (ep.success_count + ep.failure_count) < 5 THEN
          -- Low sample size: be conservative
          ep.success_count::float / GREATEST(ep.success_count + ep.failure_count, 1) * 0.7
        ELSE
          -- Wilson score approximation
          (ep.success_count::float + 1.92) / (ep.success_count + ep.failure_count + 3.84) -
          1.96 * SQRT(
            (ep.success_count::float * ep.failure_count / (ep.success_count + ep.failure_count)::float + 0.96) /
            (ep.success_count + ep.failure_count + 3.84)
          ) / (ep.success_count + ep.failure_count + 3.84)
      END +
      -- Context overlap (0.25 weight) - language match
      0.25 * CASE
        WHEN p_language IS NULL THEN 0.5
        WHEN ep.context->>'language' = p_language THEN 1.0
        WHEN ep.context->>'language' IS NULL THEN 0.5
        ELSE 0.1  -- Language mismatch penalty
      END +
      -- Error category match (bonus within context)
      0.05 * CASE
        WHEN p_error_category IS NULL THEN 0.5
        WHEN ep.context->>'error_category' = p_error_category THEN 1.0
        ELSE 0.3
      END +
      -- Universality (0.15 weight)
      0.15 * LEAST(COALESCE(ep.universality_score, 0), 1.0) +
      -- Recency (0.15 weight) - 30 day half-life
      0.15 * CASE
        WHEN ep.last_success_at IS NULL THEN 0.5
        WHEN ep.last_success_at > NOW() - INTERVAL '7 days' THEN 1.0
        WHEN ep.last_success_at > NOW() - INTERVAL '30 days' THEN 0.8
        WHEN ep.last_success_at > NOW() - INTERVAL '90 days' THEN 0.5
        ELSE 0.2
      END +
      -- Failure penalty inverse (0.10 weight)
      0.10 * (1.0 - CASE
        WHEN ep.failure_count = 0 THEN 0.0
        WHEN ep.last_failure_at IS NULL THEN
          LEAST(ep.failure_count::float / GREATEST(ep.success_count + ep.failure_count, 1), 0.5)
        WHEN ep.last_failure_at > NOW() - INTERVAL '7 days' THEN
          -- Recent failure: heavy penalty
          LEAST(ep.failure_count::float / GREATEST(ep.success_count + ep.failure_count, 1) * 1.5, 1.0)
        ELSE
          LEAST(ep.failure_count::float / GREATEST(ep.success_count + ep.failure_count, 1) * 0.75, 0.5)
      END)
    ) *
    -- Same project multiplier (1.2x boost)
    CASE
      WHEN EXISTS (
        SELECT 1 FROM pattern_project_applications ppa
        WHERE ppa.pattern_id = ep.id AND ppa.project_id = p_project_id
      ) THEN 1.2
      ELSE 1.0
    END *
    -- Risk multiplier
    CASE ep.risk_level
      WHEN 'low' THEN 1.0
      WHEN 'medium' THEN 0.95
      WHEN 'high' THEN 0.85
      WHEN 'critical' THEN 0.70
      ELSE 1.0
    END *
    -- Evergreen bonus
    CASE WHEN ep.is_evergreen THEN 1.1 ELSE 1.0 END
    AS relevance_score,
    -- Is same project flag
    EXISTS (
      SELECT 1 FROM pattern_project_applications ppa
      WHERE ppa.pattern_id = ep.id AND ppa.project_id = p_project_id
    ) AS is_same_project
  FROM error_patterns ep
  WHERE ep.fingerprint = p_fingerprint
    AND ep.quarantined = FALSE
    AND ep.deprecated_at IS NULL
  ORDER BY relevance_score DESC;
END;
$$;

-- ==========================================
-- 7. Function to check cross-project eligibility
-- ==========================================
CREATE OR REPLACE FUNCTION is_eligible_for_cross_project(
  p_fingerprint TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
  v_pattern RECORD;
  v_wilson_score FLOAT;
BEGIN
  SELECT * INTO v_pattern
  FROM error_patterns
  WHERE fingerprint = p_fingerprint
  LIMIT 1;

  IF v_pattern IS NULL THEN
    RETURN FALSE;
  END IF;

  -- Must have >= 3 projects
  IF v_pattern.project_count < 3 THEN
    RETURN FALSE;
  END IF;

  -- Must have >= 5 total successes
  IF v_pattern.success_count < 5 THEN
    RETURN FALSE;
  END IF;

  -- Calculate Wilson score (simplified)
  v_wilson_score := CASE
    WHEN (v_pattern.success_count + v_pattern.failure_count) = 0 THEN 0
    ELSE (v_pattern.success_count::float + 1.92) /
         (v_pattern.success_count + v_pattern.failure_count + 3.84)
  END;

  -- Must have Wilson score >= 0.7
  IF v_wilson_score < 0.7 THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$;

-- ==========================================
-- 8. Migrate existing data
-- ==========================================
DO $$
BEGIN
  -- For each existing pattern, create a project application entry
  INSERT INTO pattern_project_applications (
    pattern_id, project_id, success_count, failure_count,
    first_applied_at, last_applied_at
  )
  SELECT
    id, project_id, success_count, failure_count,
    created_at, updated_at
  FROM error_patterns
  WHERE project_id IS NOT NULL
  ON CONFLICT (pattern_id, project_id) DO NOTHING;

  -- Update denormalized counts
  UPDATE error_patterns ep SET
    project_count = (
      SELECT COUNT(DISTINCT ppa.project_id)
      FROM pattern_project_applications ppa
      WHERE ppa.pattern_id = ep.id
    ),
    universality_score = LEAST(
      (SELECT COUNT(DISTINCT ppa.project_id)::float
       FROM pattern_project_applications ppa
       WHERE ppa.pattern_id = ep.id) / 3.0,
      1.0
    )
  WHERE EXISTS (
    SELECT 1 FROM pattern_project_applications ppa WHERE ppa.pattern_id = ep.id
  );
END $$;

-- ==========================================
-- 9. RLS policies for new table
-- ==========================================
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

-- ==========================================
-- 10. Add circuit breaker columns to healing_config if missing
-- ==========================================
ALTER TABLE healing_config
  ADD COLUMN IF NOT EXISTS circuit_state TEXT DEFAULT 'closed',
  ADD COLUMN IF NOT EXISTS circuit_opened_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS circuit_reverts JSONB DEFAULT '[]';
