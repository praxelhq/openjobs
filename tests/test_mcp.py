import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from openjobs.store import connect, sync_jobs


def test_mcp_stdio_round_trip(tmp_path):
    database = tmp_path / "jobs.sqlite"
    sample = json.loads(
        (Path(__file__).parent.parent / "examples/demo.json").read_text()
    )
    with connect(database) as connection:
        sync_jobs(connection, "demo", sample)

    async def exercise():
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "openjobs.mcp_server"],
            env={"OPENJOBS_DB": str(database), "PRAXY_JOBS_KEY": ""},
        )
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert names == {
                "search_jobs",
                "get_job_details",
                "get_company_jobs",
                "list_sources",
                "get_source_syncs",
                "search_praxy_jobs",
            }
            response = await client.call_tool("search_jobs", {"query": "Python"})
            assert response.structured_content["jobs"][0]["title"] == "Backend Engineer"
            page = await client.call_tool("search_jobs", {"limit": 1, "offset": 1})
            assert page.structured_content["total"] == len(sample)
            assert len(page.structured_content["jobs"]) == 1
            empty_company = await client.call_tool("get_company_jobs", {"company": ""})
            assert empty_company.is_error
            missing = await client.call_tool("get_job_details", {"job_id": "missing"})
            assert missing.is_error
            sources = await client.call_tool("list_sources", {})
            assert sources.structured_content["total"] == 1
            assert sources.structured_content["sources"][0]["new_count"] == len(sample)
            syncs = await client.call_tool("get_source_syncs", {"source": "demo"})
            assert syncs.structured_content["syncs"][0]["source"] == "demo"
            missing_source = await client.call_tool(
                "get_source_syncs", {"source": "missing"}
            )
            assert missing_source.is_error
            no_hosted_key = await client.call_tool(
                "search_praxy_jobs", {"query": "engineer"}
            )
            assert no_hosted_key.is_error

    asyncio.run(exercise())
