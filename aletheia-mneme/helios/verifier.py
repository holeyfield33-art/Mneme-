"""Test vector verification for Helios Core (Python conformance)."""

import json
import sys
from helios.hasher import content_hash
from helios.objects import MemoryObject, Relationship
from helios.canon import validate_ingest_value, validate_schema_version


def load_vectors(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    return data["vectors"]


def input_to_memory_object(inp: dict) -> MemoryObject:
    validate_schema_version(inp)
    validate_ingest_value(inp.get("value"), "value")
    relationships = []
    for r in inp.get("relationships", []):
        relationships.append(Relationship(key=r["key"], type=r["type"]))
    return MemoryObject(
        category=inp.get("category", ""),
        created_at=inp.get("created_at", ""),
        key=inp.get("key", ""),
        relationships=relationships,
        source=inp.get("source", ""),
        value=inp.get("value"),
    )


def verify_vectors(path: str) -> tuple:
    vectors = load_vectors(path)
    results = []
    failures = 0
    for vec in vectors:
        vector_id = vec["vector_id"]
        vector_type = vec.get("vector_type", "positive")
        if vector_type == "negative":
            rejection_code = vec.get("rejection_code", "")
            try:
                obj = input_to_memory_object(vec["input"])
                got = content_hash(obj)
                results.append((vector_id, "REJECT", f"ACCEPT: {got}", False))
                failures += 1
            except (ValueError, Exception) as e:
                error_msg = str(e)
                passed = rejection_code and rejection_code in error_msg
                results.append((vector_id, "REJECT", error_msg, passed))
                if not passed:
                    failures += 1
        else:
            expected_hash = vec["hash"]
            obj = input_to_memory_object(vec["input"])
            got = content_hash(obj)
            passed = got == expected_hash
            results.append((vector_id, expected_hash, got, passed))
            if not passed:
                failures += 1
    return results, failures
