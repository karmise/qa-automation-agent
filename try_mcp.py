import asyncio
import json

from mcp import Client

from server import mcp


async def main() -> None:
    async with Client(mcp) as client:
        run_response = await client.call_tool("run_unit_tests", {})
        run_data = json.loads(run_response.content[0].text)

        print("Run result:")
        print(json.dumps(run_data, indent=2))

        if run_data.get("status") not in {"passed", "unsuccessful"}:
            print("Execution did not complete. Skipping Allure lookup.")
            return

        run_id = run_data["run_id"]

        allure_response = await client.call_tool(
            "read_allure_failures",
            {"run_id": run_id},
        )
        allure_data = json.loads(allure_response.content[0].text)

        print("Allure result:")
        print(json.dumps(allure_data, indent=2))

        assert allure_data["run_id"] == run_id, "Run IDs do not match"


if __name__ == "__main__":
    asyncio.run(main())