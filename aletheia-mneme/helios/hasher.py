"""SHA-256 content hash for Helios Core (Python conformance)."""

import hashlib

from helios.canon import (
    canonicalize_object,
    normalize_string,
    normalize_timestamp,
    relationship_to_map,
    sort_relationships,
)
from helios.objects import MemoryObject, new_hash_input


def content_hash(obj: MemoryObject) -> str:
    inp = new_hash_input(obj)
    inp.created_at = normalize_timestamp(inp.created_at)
    sorted_rels = sort_relationships(inp.relationships)
    inp.category = normalize_string(inp.category)
    inp.key = normalize_string(inp.key)
    inp.source = normalize_string(inp.source)
    if isinstance(inp.value, str):
        inp.value = normalize_string(inp.value)

    rel_maps = []
    for r in sorted_rels:
        rel_maps.append({
            "key": normalize_string(r.key),
            "type": normalize_string(r.type),
        })

    fields = {
        "_helios_schema_version": "1",
        "category": inp.category,
        "created_at": inp.created_at,
        "key": inp.key,
        "relationships": rel_maps,
        "source": inp.source,
        "value": inp.value,
    }

    canonical = canonicalize_object(fields)
    return hashlib.sha256(canonical).hexdigest()
