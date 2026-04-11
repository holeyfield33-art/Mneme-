"""Helios Core — cryptographic integrity test suite.

Tests:
  - All 5 positive vectors produce correct hashes
  - All 3 negative vectors are properly rejected
  - Canon serialization edge cases
  - Unicode NFC normalization
  - Timestamp validation
  - Float/null/schema rejection
  - Relationship sorting
"""
import pytest
import json
from helios.verifier import verify_vectors, input_to_memory_object
from helios.hasher import content_hash
from helios.objects import MemoryObject, Relationship
from helios.canon import (
    normalize_string,
    normalize_timestamp,
    canonicalize_object,
    validate_ingest_value,
    validate_schema_version,
    sort_relationships,
)


# ── Test Vector Verification ─────────────────────────────────

class TestVectorVerification:
    def test_all_vectors_pass(self):
        results, failures = verify_vectors("test_vectors/vectors.json")
        assert failures == 0, f"Helios vectors failed: {failures}"
        assert len(results) == 8

    def test_positive_vectors_count(self):
        results, _ = verify_vectors("test_vectors/vectors.json")
        passed = [r for r in results if r[3] is True and r[1] != "REJECT"]
        assert len(passed) == 5

    def test_negative_vectors_count(self):
        results, _ = verify_vectors("test_vectors/vectors.json")
        rejected = [r for r in results if r[1] == "REJECT" and r[3] is True]
        assert len(rejected) == 3

    def test_individual_positive_hashes(self):
        """Verify each positive vector produces the exact expected hash."""
        with open("test_vectors/vectors.json") as f:
            data = json.load(f)

        for vec in data["vectors"]:
            if vec["vector_type"] == "positive":
                obj = input_to_memory_object(vec["input"])
                computed = content_hash(obj)
                assert computed == vec["hash"], f"{vec['vector_id']} hash mismatch"


# ── Canonical Serialization ──────────────────────────────────

class TestCanon:
    def test_normalize_string_nfc(self):
        # café in NFD vs NFC
        nfd = "cafe\u0301"
        nfc = "café"
        assert normalize_string(nfd) == nfc

    def test_normalize_timestamp_valid(self):
        assert normalize_timestamp("2025-01-15T10:30:00.000Z") == "2025-01-15T10:30:00.000Z"

    def test_normalize_timestamp_rejects_non_utc(self):
        with pytest.raises(ValueError, match="CANON_ERR_TIMESTAMP_NON_UTC"):
            normalize_timestamp("2025-01-15T10:30:00.000+05:00")

    def test_normalize_timestamp_rejects_no_fraction(self):
        with pytest.raises(ValueError, match="CANON_ERR_TIMESTAMP_INVALID_PRECISION"):
            normalize_timestamp("2025-01-15T10:30:00Z")

    def test_normalize_timestamp_rejects_wrong_precision(self):
        with pytest.raises(ValueError, match="CANON_ERR_TIMESTAMP_INVALID_PRECISION"):
            normalize_timestamp("2025-01-15T10:30:00.1234Z")

    def test_canonicalize_sorted_keys(self):
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonicalize_object(obj)
        assert result == b'{"a":2,"m":3,"z":1}'

    def test_canonicalize_nested_sorted(self):
        obj = {"b": {"z": 1, "a": 2}, "a": 1}
        result = canonicalize_object(obj)
        assert result == b'{"a":1,"b":{"a":2,"z":1}}'

    def test_canonicalize_no_spaces(self):
        obj = {"key": "value", "num": 42}
        result = canonicalize_object(obj)
        assert b" " not in result

    def test_canonicalize_rejects_null(self):
        with pytest.raises(ValueError, match="CANON_ERR_NULL_PROHIBITED"):
            canonicalize_object({"key": None})

    def test_canonicalize_rejects_non_dict(self):
        with pytest.raises(TypeError):
            canonicalize_object("not a dict")


# ── Ingest Validation ────────────────────────────────────────

class TestIngestValidation:
    def test_rejects_float(self):
        with pytest.raises(ValueError, match="CANON_ERR_FLOAT_PROHIBITED"):
            validate_ingest_value(3.14, "test")

    def test_rejects_null(self):
        with pytest.raises(ValueError, match="CANON_ERR_NULL_PROHIBITED"):
            validate_ingest_value(None, "test")

    def test_accepts_string(self):
        validate_ingest_value("hello", "test")

    def test_accepts_int(self):
        validate_ingest_value(42, "test")

    def test_accepts_bool(self):
        validate_ingest_value(True, "test")

    def test_accepts_list(self):
        validate_ingest_value([1, 2, "three"], "test")

    def test_accepts_dict(self):
        validate_ingest_value({"key": "value"}, "test")

    def test_rejects_nested_float(self):
        with pytest.raises(ValueError, match="CANON_ERR_FLOAT_PROHIBITED"):
            validate_ingest_value({"nested": 3.14}, "test")

    def test_rejects_nested_null(self):
        with pytest.raises(ValueError, match="CANON_ERR_NULL_PROHIBITED"):
            validate_ingest_value({"nested": None}, "test")

    def test_rejects_int_out_of_range(self):
        with pytest.raises(ValueError, match="CANON_ERR_INTEGER_OUT_OF_RANGE"):
            validate_ingest_value(2**63, "test")


# ── Schema Version ───────────────────────────────────────────

class TestSchemaVersion:
    def test_rejects_missing(self):
        with pytest.raises(ValueError, match="CANON_ERR_SCHEMA_VERSION_MISSING"):
            validate_schema_version({})

    def test_rejects_wrong_value(self):
        with pytest.raises(ValueError, match="CANON_ERR_SCHEMA_VERSION_INVALID"):
            validate_schema_version({"_helios_schema_version": "2"})

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="CANON_ERR_SCHEMA_VERSION_INVALID"):
            validate_schema_version({"_helios_schema_version": 1})

    def test_accepts_valid(self):
        validate_schema_version({"_helios_schema_version": "1"})


# ── Relationship Sorting ────────────────────────────────────

class TestRelationshipSorting:
    def test_sort_by_key(self):
        rels = [
            Relationship(key="z", type="related_to"),
            Relationship(key="a", type="related_to"),
        ]
        sorted_rels = sort_relationships(rels)
        assert sorted_rels[0].key == "a"
        assert sorted_rels[1].key == "z"

    def test_sort_by_type_when_key_equal(self):
        rels = [
            Relationship(key="a", type="z_type"),
            Relationship(key="a", type="a_type"),
        ]
        sorted_rels = sort_relationships(rels)
        assert sorted_rels[0].type == "a_type"
        assert sorted_rels[1].type == "z_type"


# ── Content Hash Determinism ─────────────────────────────────

class TestHashDeterminism:
    def test_same_input_same_hash(self):
        obj = MemoryObject(
            category="test",
            created_at="2025-01-15T10:30:00.000Z",
            key="test/determinism",
            relationships=[],
            source="user",
            value="deterministic",
        )
        h1 = content_hash(obj)
        h2 = content_hash(obj)
        assert h1 == h2

    def test_different_value_different_hash(self):
        obj1 = MemoryObject(
            category="test",
            created_at="2025-01-15T10:30:00.000Z",
            key="test/diff",
            relationships=[],
            source="user",
            value="value_a",
        )
        obj2 = MemoryObject(
            category="test",
            created_at="2025-01-15T10:30:00.000Z",
            key="test/diff",
            relationships=[],
            source="user",
            value="value_b",
        )
        assert content_hash(obj1) != content_hash(obj2)

    def test_hash_is_64_hex_chars(self):
        obj = MemoryObject(
            category="test",
            created_at="2025-01-15T10:30:00.000Z",
            key="test/length",
            relationships=[],
            source="user",
            value="test",
        )
        h = content_hash(obj)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_boolean_value_hashes(self):
        obj = MemoryObject(
            category="flags",
            created_at="2025-12-25T23:59:59.999Z",
            key="test/boolean_value",
            relationships=[],
            source="system",
            value=True,
        )
        h = content_hash(obj)
        assert h == "84c6d544a9ee3b9c1bd48a17d8835f25a7df62cd520f78f12fa49810b9e35945"
