-- Self-Healing Infrastructure Schema
-- Phase 2: Pattern Memory, Lookup & Security
--
-- Run this migration against your Supabase project:
-- https://igalnlhcblswjtwaruvy.supabase.co
--
-- Usage: Copy and paste into Supabase SQL Editor

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================
-- Configuration per project
-- ==========================================
CREATE TABLE IF NOT EXISTS healing_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT UNIQUE NOT NULL,

    -- Feature flags
    enabled BOOLEAN DEFAULT TRUE,
    auto_apply_safe BOOLEAN DEFAULT TRUE,
    auto_apply_moderate BOOLEAN DEFAULT FALSE,

    -- Cost controls
    max_daily_cost_usd FLOAT DEFAULT 10.0,
    max_validations_per_day INTEGER DEFAULT 100,
    max_cost_per_validation_usd FLOAT DEFAULT 0.50,

    -- Safety
    protected_paths TEXT[] DEFAULT ARRAY['src/auth/**', 'migrations/**', '*.env*'],

    -- Kill switch
    kill_switch_active BOOLEAN DEFAULT FALSE,

    -- Timeouts
    build_timeout_seconds INTEGER DEFAULT 300,
    test_timeout_seconds INTEGER DEFAULT 600,
    lint_timeout_seconds INTEGER DEFAULT 60,
    judge_timeout_seconds INTEGER DEFAULT 30,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- Error patterns (Tier 1 lookup)
-- ==========================================
CREATE TABLE IF NOT EXISTS error_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    fingerprint_coarse TEXT,

    -- Description (scrubbed)
    description TEXT,

    -- Precedent tracking (zero-human mode)
    is_preseeded BOOLEAN DEFAULT FALSE,
    verified_apply_count INTEGER DEFAULT 0,
    human_correction_count INTEGER DEFAULT 0,

    -- Stats
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    use_count INTEGER DEFAULT 0,

    -- Safety
    safety_category TEXT CHECK (safety_category IN ('safe', 'moderate', 'risky')),
    quarantined BOOLEAN DEFAULT FALSE,
    quarantine_reason TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint
    UNIQUE(project_id, fingerprint)
);

-- ==========================================
-- Learnings with RAG embeddings (Tier 2 lookup)
-- ==========================================
CREATE TABLE IF NOT EXISTS learnings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    pattern_id UUID REFERENCES error_patterns(id) ON DELETE CASCADE,
    pattern_fingerprint TEXT,

    -- Content
    title TEXT NOT NULL,
    description TEXT,
    action JSONB NOT NULL,  -- Fix template (FixAction schema)

    -- RAG
    embedding VECTOR(1536),
    embedding_model TEXT DEFAULT 'text-embedding-ada-002',

    -- Lifecycle (4-state)
    lifecycle TEXT DEFAULT 'draft' CHECK (lifecycle IN ('draft', 'active', 'automated', 'deprecated')),

    -- Tracking
    confidence FLOAT DEFAULT 0.5,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- Causality edges (Tier 3 lookup)
-- ==========================================
CREATE TABLE IF NOT EXISTS causality_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    error_fingerprint TEXT NOT NULL,
    error_timestamp TIMESTAMPTZ NOT NULL,

    -- Cause
    causing_commit TEXT NOT NULL,
    causing_file TEXT NOT NULL,
    causing_function TEXT,

    -- Evidence
    evidence_type TEXT CHECK (evidence_type IN ('temporal', 'git_blame', 'dependency', 'cascade', 'manual')),
    confidence FLOAT DEFAULT 0.5,
    occurrence_count INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint
    UNIQUE(error_fingerprint, causing_commit, causing_file)
);

-- ==========================================
-- Audit log (for cloud environments)
-- ==========================================
CREATE TABLE IF NOT EXISTS healing_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    action TEXT NOT NULL,  -- 'fix_attempted', 'fix_applied', 'fix_reverted', etc.
    fingerprint TEXT,
    fix_id UUID,
    details JSONB,
    success BOOLEAN,
    error_message TEXT
);

-- ==========================================
-- Indexes for performance
-- ==========================================

-- Error patterns indexes
CREATE INDEX IF NOT EXISTS idx_error_patterns_project_fingerprint
    ON error_patterns(project_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_error_patterns_fingerprint_coarse
    ON error_patterns(fingerprint_coarse);
CREATE INDEX IF NOT EXISTS idx_error_patterns_quarantined
    ON error_patterns(project_id, quarantined)
    WHERE quarantined = FALSE;

-- Learnings indexes
CREATE INDEX IF NOT EXISTS idx_learnings_project_lifecycle
    ON learnings(project_id, lifecycle);
CREATE INDEX IF NOT EXISTS idx_learnings_pattern_fingerprint
    ON learnings(pattern_fingerprint);

-- Vector similarity index (IVFFlat for approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS idx_learnings_embedding
    ON learnings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Causality indexes
CREATE INDEX IF NOT EXISTS idx_causality_fingerprint
    ON causality_edges(error_fingerprint);
CREATE INDEX IF NOT EXISTS idx_causality_causing_file
    ON causality_edges(causing_file);

-- Audit log indexes
CREATE INDEX IF NOT EXISTS idx_healing_audit_project_timestamp
    ON healing_audit(project_id, timestamp DESC);

-- ==========================================
-- RPC Functions
-- ==========================================

-- Function to match learnings by embedding similarity
CREATE OR REPLACE FUNCTION match_learnings(
    query_embedding VECTOR(1536),
    match_threshold FLOAT,
    match_count INTEGER,
    p_project_id TEXT
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    description TEXT,
    action JSONB,
    pattern_fingerprint TEXT,
    lifecycle TEXT,
    confidence FLOAT,
    similarity FLOAT
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
        1 - (l.embedding <=> query_embedding) AS similarity
    FROM learnings l
    WHERE l.project_id = p_project_id
      AND l.lifecycle IN ('active', 'automated')
      AND l.embedding IS NOT NULL
      AND 1 - (l.embedding <=> query_embedding) > match_threshold
    ORDER BY l.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to get error causes with depth
CREATE OR REPLACE FUNCTION get_error_causes(
    p_fingerprint TEXT,
    p_depth INTEGER DEFAULT 2
)
RETURNS TABLE (
    causing_commit TEXT,
    causing_file TEXT,
    causing_function TEXT,
    evidence_type TEXT,
    confidence FLOAT,
    occurrence_count INTEGER,
    depth INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- For now, return direct causes only
    -- Recursive causality traversal can be added later
    RETURN QUERY
    SELECT
        c.causing_commit,
        c.causing_file,
        c.causing_function,
        c.evidence_type,
        c.confidence,
        c.occurrence_count,
        1 AS depth
    FROM causality_edges c
    WHERE c.error_fingerprint = p_fingerprint
    ORDER BY c.confidence DESC, c.occurrence_count DESC
    LIMIT 10;
END;
$$;

-- Function to increment pattern statistics
CREATE OR REPLACE FUNCTION increment_pattern_stat(
    p_fingerprint TEXT,
    p_project_id TEXT,
    p_column TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_column = 'success_count' THEN
        UPDATE error_patterns
        SET success_count = success_count + 1,
            use_count = use_count + 1,
            updated_at = NOW()
        WHERE fingerprint = p_fingerprint
          AND project_id = p_project_id;
    ELSIF p_column = 'failure_count' THEN
        UPDATE error_patterns
        SET failure_count = failure_count + 1,
            use_count = use_count + 1,
            updated_at = NOW()
        WHERE fingerprint = p_fingerprint
          AND project_id = p_project_id;
    END IF;
END;
$$;

-- ==========================================
-- Row Level Security (RLS)
-- ==========================================

-- Enable RLS on all tables
ALTER TABLE healing_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE learnings ENABLE ROW LEVEL SECURITY;
ALTER TABLE causality_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE healing_audit ENABLE ROW LEVEL SECURITY;

-- Create policies (adjust based on your auth setup)
-- For now, allow all authenticated users to access their project's data
-- You should customize these based on your auth strategy

CREATE POLICY "Users can view their project config"
    ON healing_config FOR SELECT
    USING (TRUE);  -- Customize with auth.uid() or project membership

CREATE POLICY "Users can view their project patterns"
    ON error_patterns FOR SELECT
    USING (TRUE);

CREATE POLICY "Users can insert patterns"
    ON error_patterns FOR INSERT
    WITH CHECK (TRUE);

CREATE POLICY "Users can update patterns"
    ON error_patterns FOR UPDATE
    USING (TRUE);

CREATE POLICY "Users can view learnings"
    ON learnings FOR SELECT
    USING (TRUE);

CREATE POLICY "Users can insert learnings"
    ON learnings FOR INSERT
    WITH CHECK (TRUE);

CREATE POLICY "Users can view causality"
    ON causality_edges FOR SELECT
    USING (TRUE);

CREATE POLICY "Users can insert causality"
    ON causality_edges FOR INSERT
    WITH CHECK (TRUE);

CREATE POLICY "Users can view audit logs"
    ON healing_audit FOR SELECT
    USING (TRUE);

CREATE POLICY "Users can insert audit logs"
    ON healing_audit FOR INSERT
    WITH CHECK (TRUE);

-- ==========================================
-- Triggers for updated_at
-- ==========================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_healing_config_updated_at
    BEFORE UPDATE ON healing_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_error_patterns_updated_at
    BEFORE UPDATE ON error_patterns
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_learnings_updated_at
    BEFORE UPDATE ON learnings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
