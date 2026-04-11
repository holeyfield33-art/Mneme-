"""Canonical serialization primitives for Helios Core (Python conformance)."""

import json
import unicodedata


def normalize_string(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def normalize_timestamp(s: str) -> str:
    if not s.endswith("Z"):
        raise ValueError(f"CANON_ERR_TIMESTAMP_NON_UTC: Timestamp must end in Z, got: {s}")

    dot_idx = s.rfind(".")
    if dot_idx == -1:
        raise ValueError(f"CANON_ERR_TIMESTAMP_INVALID_PRECISION: Timestamp must have exactly 3 fractional digits, got none: {s}")

    frac = s[dot_idx + 1 : -1]
    if len(frac) != 3:
        raise ValueError(
            f"CANON_ERR_TIMESTAMP_INVALID_PRECISION: Timestamp must have exactly 3 fractional digits, got {len(frac)}: {s}"
        )

    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {s}")

    ms = dt.microsecond // 1000
    return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{ms:03d}Z")


def canonicalize_object(obj: dict) -> bytes:
    if not isinstance(obj, dict):
        raise TypeError(f"canonicalize_object expects dict, got {type(obj)}")
    normalized = _normalize_dict(obj)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize_dict(d: dict) -> dict:
    return {k: _normalize_value(v) for k, v in sorted(d.items())}


def _normalize_value(v):
    if v is None:
        raise ValueError("CANON_ERR_NULL_PROHIBITED: null values are not permitted")
    if isinstance(v, dict):
        return _normalize_dict(v)
    elif isinstance(v, list):
        return [_normalize_value(item) for item in v]
    else:
        return v


def sort_relationships(rels: list) -> list:
    return sorted(rels, key=lambda r: (r.key, r.type))


def relationship_to_map(r) -> dict:
    return {"key": r.key, "type": r.type}


def validate_schema_version(input: dict) -> None:
    if "_helios_schema_version" not in input:
        raise ValueError("CANON_ERR_SCHEMA_VERSION_MISSING: _helios_schema_version field is required")
    v = input["_helios_schema_version"]
    if not isinstance(v, str) or v != "1":
        raise ValueError(f"CANON_ERR_SCHEMA_VERSION_INVALID: _helios_schema_version must be string \"1\", got {v!r}")


def validate_ingest_value(v, path: str = "") -> None:
    if v is None:
        raise ValueError(f"CANON_ERR_NULL_PROHIBITED: null value at {path}")
    elif isinstance(v, float):
        raise ValueError(f"CANON_ERR_FLOAT_PROHIBITED: float value at {path}")
    elif isinstance(v, bool):
        pass
    elif isinstance(v, int):
        if v > 9223372036854775807 or v < -9223372036854775808:
            raise ValueError(f"CANON_ERR_INTEGER_OUT_OF_RANGE: value {v} at {path} exceeds int64 bounds")
    elif isinstance(v, dict):
        for k, child in v.items():
            validate_ingest_value(child, f"{path}.{k}")
    elif isinstance(v, list):
        for i, child in enumerate(v):
            validate_ingest_value(child, f"{path}[{i}]")
    elif isinstance(v, str):
        pass
    else:
        raise ValueError(f"Unsupported type {type(v)} at {path}")
