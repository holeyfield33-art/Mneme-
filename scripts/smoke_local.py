"""Real loopback MCP/database verification. Stores only an explicit audit fixture."""
import argparse
import asyncio
import json

import httpx
from local_client import call_tool
from local_config import LOCAL, load_config

KEY = "audit/local-persistence-smoke"
VALUE = "Mneme local durability smoke check: prompts and agent handoffs persist in PostgreSQL."


def _items(result):
    """Normalize SDK list results across MCP structured-content versions."""
    if isinstance(result, dict) and "result" in result:
        result = result["result"]
    if isinstance(result, dict):
        return [result]
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["write", "verify"])
    args = parser.parse_args()
    config = load_config()
    async with httpx.AsyncClient() as client:
        health = (await client.get(config["health_endpoint"])).json()
        assert health["offline"] and health["database"] == "connected", health
        response = await client.post(config["endpoint"], json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        assert response.status_code == 401, response.status_code
        response = await client.post(config["health_endpoint"].replace("/health", "/sync/push"), json={})
        assert response.status_code == 404, response.status_code
    if args.phase == "write":
        stored = await call_tool("store_memory", {"key": KEY, "value": VALUE, "category": "audit"})
        (LOCAL / "smoke-receipt.json").write_text(json.dumps({"id": stored["id"], "content_hash": stored["content_hash"]}), encoding="utf-8")
    memory = await call_tool("get_memory", {"key": KEY})
    assert memory["value"] == VALUE, memory
    receipt = json.loads((LOCAL / "smoke-receipt.json").read_text(encoding="utf-8"))
    assert memory["id"] == receipt["id"] and memory["content_hash"] == receipt["content_hash"]
    integrity = await call_tool("verify_memory", {"key": KEY})
    assert integrity["valid"], integrity
    search = await call_tool("search_memory", {"query": "durability", "limit": 5})
    search = _items(search)
    assert any(item["key"] == KEY for item in search), search
    fallback = await call_tool("semantic_search", {"query": "durability", "limit": 5})
    fallback = _items(fallback)
    assert any(item["key"] == KEY for item in fallback), fallback
    print(json.dumps({"phase": args.phase, "passed": True, "checks": ["offline", "database", "auth", "sync_disabled", "store/get", "keyword_search", "semantic_keyword_fallback", "integrity", "durable_id_and_hash"]}))


if __name__ == "__main__":
    asyncio.run(main())
