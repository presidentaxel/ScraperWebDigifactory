-- DigiFactory Scraper - Supabase Schema (2 tables)
-- Run this in your Supabase SQL editor

-- Table 1: cto_runs (one record per nr scraped)
CREATE TABLE IF NOT EXISTS cto_runs (
    nr INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    gate_passed BOOLEAN NOT NULL DEFAULT false,
    gate_reason TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error JSONB,
    metrics JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: cto_pages (one record per page scraped)
CREATE TABLE IF NOT EXISTS cto_pages (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    nr INTEGER NOT NULL,
    page_type TEXT NOT NULL, -- view, payment, logistic, infos, orders
    url TEXT NOT NULL,
    status_code INTEGER,
    final_url TEXT,
    html_hash TEXT,
    content_length INTEGER, -- Size of HTML content in bytes
    extracted JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_html_gz_b64 TEXT, -- Optional: gzip+base64 encoded HTML (controlled size)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(run_id, page_type)
);

-- Indexes for cto_runs
CREATE INDEX IF NOT EXISTS idx_cto_runs_run_id ON cto_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_cto_runs_status ON cto_runs(status);
CREATE INDEX IF NOT EXISTS idx_cto_runs_gate_passed ON cto_runs(gate_passed);
CREATE INDEX IF NOT EXISTS idx_cto_runs_started_at ON cto_runs(started_at);

-- Indexes for cto_pages
CREATE INDEX IF NOT EXISTS idx_cto_pages_run_id ON cto_pages(run_id);
CREATE INDEX IF NOT EXISTS idx_cto_pages_nr ON cto_pages(nr);
CREATE INDEX IF NOT EXISTS idx_cto_pages_page_type ON cto_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_cto_pages_extracted_gin ON cto_pages USING GIN(extracted);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers to auto-update updated_at
CREATE TRIGGER update_cto_runs_updated_at
    BEFORE UPDATE ON cto_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cto_pages_updated_at
    BEFORE UPDATE ON cto_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security
ALTER TABLE cto_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cto_pages ENABLE ROW LEVEL SECURITY;

-- Policies to allow service role full access
CREATE POLICY "Service role can manage cto_runs"
    ON cto_runs
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage cto_pages"
    ON cto_pages
    FOR ALL
    USING (auth.role() = 'service_role');

-- Table 3: cto_errors (error logs for debugging)
CREATE TABLE IF NOT EXISTS cto_errors (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    nr INTEGER,
    error_type TEXT NOT NULL, -- fetch_error, parse_error, supabase_error, auth_error, etc.
    error_message TEXT NOT NULL,
    error_details JSONB, -- Stack trace, context, etc.
    page_type TEXT, -- If error is related to a specific page
    url TEXT, -- URL that caused the error
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for cto_errors
CREATE INDEX IF NOT EXISTS idx_cto_errors_run_id ON cto_errors(run_id);
CREATE INDEX IF NOT EXISTS idx_cto_errors_nr ON cto_errors(nr);
CREATE INDEX IF NOT EXISTS idx_cto_errors_error_type ON cto_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_cto_errors_occurred_at ON cto_errors(occurred_at);

-- Enable Row Level Security
ALTER TABLE cto_errors ENABLE ROW LEVEL SECURITY;

-- Policy to allow service role full access
CREATE POLICY "Service role can manage cto_errors"
    ON cto_errors
    FOR ALL
    USING (auth.role() = 'service_role');

-- Comments
COMMENT ON TABLE cto_runs IS 'Scraped DigiFactory sales runs (one per nr)';
COMMENT ON TABLE cto_pages IS 'Scraped DigiFactory pages (one per page type per nr)';
COMMENT ON TABLE cto_errors IS 'Error logs for debugging and monitoring';
COMMENT ON COLUMN cto_runs.nr IS 'Sale number (primary key)';
COMMENT ON COLUMN cto_runs.run_id IS 'Unique run identifier (UUID)';
COMMENT ON COLUMN cto_runs.gate_passed IS 'Whether Location de véhicule was found';
COMMENT ON COLUMN cto_pages.raw_html_gz_b64 IS 'Optional: gzip+base64 encoded HTML (max 1.5MB)';
COMMENT ON COLUMN cto_errors.error_type IS 'Type of error: fetch_error, parse_error, supabase_error, auth_error, etc.';
COMMENT ON COLUMN cto_errors.error_details IS 'JSONB with stack trace, context, and additional debugging info';
