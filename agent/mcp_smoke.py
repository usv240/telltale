"""Smoke test for the MCP server: start it over stdio, list its tools, and investigate one
epoch of the bundled demo site through MCP alone.

    python -m agent.mcp_smoke
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    env = dict(os.environ)
    env.setdefault("TELLTALE_STORE", str(ROOT / "web" / "dashboard" / "demo-data"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent.mcp_server"], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", ", ".join(t.name for t in tools.tools))

            def text(res):
                return "".join(c.text for c in res.content if getattr(c, "type", "") == "text")

            sites = json.loads(text(await session.call_tool("list_sites", {})))
            site = sites[0]["site"]
            status = json.loads(text(await session.call_tool("get_site_status", {"site": site})))
            t = status["recent_epochs"][-1]["t"]
            print(f"site {site}: state {status['state']}, last epoch t = {t}")
            a = json.loads(text(await session.call_tool("remeasure", {"site": site, "t": t, "reference": "previous"})))
            b = json.loads(text(await session.call_tool("remeasure", {"site": site, "t": t, "reference": "reference"})))
            c = json.loads(text(await session.call_tool("motion_coherence", {"site": site, "t": t})))
            s = json.loads(text(await session.call_tool("check_stabilization", {"site": site, "t": t})))
            z = next(iter(b["zones"]))
            print(f"remeasure vs previous: {a['zones'][z]['magnitude']:.3f} px; vs reference: {b['zones'][z]['magnitude']:.3f} px")
            print(f"coherence {c['zones'][z]['coherence']}, stabilization {s['verdict']} residual {s['residual_px']} scatter {s['scatter_px']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
