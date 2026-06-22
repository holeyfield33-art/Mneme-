-- Migration 004: personal namespace seed + performance indexes
-- Idempotent: safe to run multiple times.

-- Speed up key-prefix lookups used by auth.get_namespace_from_key
CREATE INDEX IF NOT EXISTS api_keys_key_prefix_idx
    ON api_keys (key_prefix);

-- Ensure the personal namespace row exists so that PERSONAL_MODE
-- store_memory calls satisfy the memories.namespace_id FK constraint.
INSERT INTO namespaces (id, tier, is_active)
VALUES ('personal', 'premium', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Speed up the hot query path: list/search memories filtered by namespace
CREATE INDEX IF NOT EXISTS memories_namespace_active_idx
    ON memories (namespace_id, is_deleted);
