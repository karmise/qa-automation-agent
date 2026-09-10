import asyncio

from mcp import Client

from server import mcp


async def main() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "project_info",
            {"project_path": "/Users/karmise/Documents/Codex/2026-07-29/restful-booker-eee"},
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())