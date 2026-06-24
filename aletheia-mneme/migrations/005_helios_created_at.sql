-- Migration 005: persist the exact canonical timestamp string used in the Helios hash.
--
-- The Helios spec treats created_at as an IMMUTABLE field included in content_hash.
-- Previously, _compute_helios_hash generated its own datetime.now() string and then
-- discarded it, so verify_memory could never recover the exact string that was hashed.
-- This column stores it verbatim so verify_memory can reconstruct the object correctly.
--
-- TEXT (not TIMESTAMP): must store the canonical "YYYY-MM-DDTHH:MM:SS.000Z" string
-- exactly as formatted by Python — no reformatting, no timezone coercion.
-- Rows stored before this migration have NULL and are marked "unverifiable".
--
-- Idempotent: safe to run multiple times.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS helios_created_at TEXT;
