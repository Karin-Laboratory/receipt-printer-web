-- Apply using Wrangler D1 migrations in a separate authorized Cloudflare staging environment.
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY NOT NULL,
  owner TEXT NOT NULL,
  client_key TEXT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL,
  bytes INTEGER NOT NULL CHECK (bytes > 0 AND bytes <= 1048576),
  digest TEXT NOT NULL,
  object_key TEXT NOT NULL UNIQUE,
  approval_hash TEXT,
  state TEXT NOT NULL CHECK (state IN ('draft','queued','leased','captured','printed','uncertain','failed','cancelled')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  lease_id TEXT,
  lease_until INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  UNIQUE (owner, client_key)
);
CREATE INDEX IF NOT EXISTS idx_jobs_ready ON jobs(state, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_expiry ON jobs(expires_at);
