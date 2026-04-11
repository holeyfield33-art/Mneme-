CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE namespaces (
  id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  email                       TEXT,
  tier                        TEXT NOT NULL DEFAULT 'free',
  stripe_customer_id          TEXT,
  stripe_subscription_id      TEXT,
  request_count_current_month INTEGER DEFAULT 0,
  created_at                  TIMESTAMP DEFAULT NOW(),
  is_active                   BOOLEAN DEFAULT TRUE
);

CREATE TABLE api_keys (
  id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id TEXT NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  key_hash     TEXT NOT NULL UNIQUE,
  key_prefix   TEXT NOT NULL,
  created_at   TIMESTAMP DEFAULT NOW(),
  revoked_at   TIMESTAMP,
  last_used    TIMESTAMP,
  expires_at   TIMESTAMP
);

CREATE TABLE memories (
  id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id    TEXT NOT NULL REFERENCES namespaces(id),
  key             TEXT NOT NULL,
  value           TEXT NOT NULL,
  category        TEXT NOT NULL DEFAULT 'general',
  source          TEXT DEFAULT 'user',
  confidence      FLOAT DEFAULT 1.0,
  content_hash    TEXT,
  embedding_model TEXT DEFAULT 'text-embedding-3-small',
  version         INTEGER DEFAULT 1,
  last_updated    TIMESTAMP DEFAULT NOW(),
  last_accessed   TIMESTAMP DEFAULT NOW(),
  access_count    INTEGER DEFAULT 0,
  expires_at      TIMESTAMP,
  is_deleted      BOOLEAN DEFAULT FALSE,
  UNIQUE(namespace_id, key)
);

CREATE TABLE memory_history (
  id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  memory_id   TEXT NOT NULL REFERENCES memories(id),
  old_value   TEXT NOT NULL,
  old_version INTEGER,
  changed_at  TIMESTAMP DEFAULT NOW(),
  changed_by  TEXT DEFAULT 'user'
);

CREATE TABLE memory_relationships (
  id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id TEXT NOT NULL,
  from_key     TEXT NOT NULL,
  to_key       TEXT NOT NULL,
  rel_type     TEXT NOT NULL,
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sync_log (
  id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id   TEXT NOT NULL,
  direction      TEXT NOT NULL,
  memory_count   INTEGER,
  target_url     TEXT,
  status         TEXT,
  helios_receipt TEXT,
  created_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE processed_events (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT NOW()
);
