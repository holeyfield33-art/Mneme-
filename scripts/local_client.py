"""Authenticated MCP client; accepts JSON from a file without exposing API keys."""
import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from local_config import load_config


async def call_tool(tool, arguments):
    config = load_config()
    async with streamablehttp_client(
        config["endpoint"], headers={"Authorization": f"Bearer {config['personal_api_key']}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            if result.isError:
                raise RuntimeError("; ".join(item.text for item in result.content if item.type == "text"))
            if result.structuredContent is not None:
                return result.structuredContent
            if len(result.content) == 1 and result.content[0].type == "text":
                return json.loads(result.content[0].text)
            return [
                json.loads(item.text) if item.type == "text" else item.model_dump()
                for item in result.content
            ]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-file", type=Path, required=True,
                        help='UTF-8 JSON {"tool":"store_memory","arguments":{"key":"...","value":"...","category":"prompt","attribution":"user"}}')
    parser.add_argument("--output-file", type=Path, help="Write retrieved memory privately to a local file")
    args = parser.parse_args()
    request = json.loads(args.request_file.read_text(encoding="utf-8-sig"))
    result = await call_tool(request["tool"], request.get("arguments", {}))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_file:
        args.output_file.write_text(output, encoding="utf-8")
        print(f"Result written to {args.output_file}")
    else:
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
