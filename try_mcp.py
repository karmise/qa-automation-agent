import asyncio

from mcp import Client

from server import mcp


async def main() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("run_unit_tests", {})
        print(result)


if __name__ == "__main__":
    asyncio.run(main())