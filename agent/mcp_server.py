"""TellTale's OpenCV perception tools as a Model Context Protocol server.

The same functions the in-worker agent calls through the Anthropic SDK tool runner
(``agent/tools.py``), exposed over MCP so any MCP client (Claude Code, Kiro, Claude Desktop,
an AgentCore runtime) can investigate a site by running OpenCV 5 again on its stored images.
Two transports of one toolbox: the worker's loop is the production path, this server is the
open one, and each is the other's backup.

Run it against a local store (the worker's LocalStore layout, e.g. the bundled demo data):

    TELLTALE_STORE=web/dashboard/demo-data python -m agent.mcp_server

or against the deployed bucket:

    TELLTALE_BUCKET=telltale-123456789012 python -m agent.mcp_server

Claude Code: ``claude mcp add telltale -- python -m agent.mcp_server`` from the repository root
(with one of the variables above set). Action tools never send a public alert; paging a person
is the most they can do, and only when an alert topic is configured.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "infra" / "worker"))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from agent.tools import Toolbox  # noqa: E402

server = MCPServer(
    name="telltale",
    title="TellTale slope instrument",
    instructions=(
        "Tools re-run OpenCV 5 on a TellTale site's stored camera epochs. Start with list_sites, "
        "then get_site_status. Real ground motion is consistent across references (remeasure with "
        "'previous' and 'reference'), coherent in direction (motion_coherence above about 0.7), and "
        "not coincident with a camera event, blur or a coverage drop. close_event records a verdict; "
        "no tool can send a public alert."),
)

_store = None
_alerting = None


def store():
    global _store, _alerting
    if _store is None:
        import worker as W
        if os.environ.get("TELLTALE_BUCKET"):
            _store = W.S3Store(os.environ["TELLTALE_BUCKET"], os.environ.get("TELLTALE_REGION"))
            _alerting = W.alerting()
        else:
            _store = W.LocalStore(os.environ.get("TELLTALE_STORE", str(ROOT / "web" / "dashboard" / "demo-data")))
    return _store


def box(site: str) -> Toolbox:
    return Toolbox(store(), site, _alerting)


@server.tool(description="List the monitored sites with their current state, last epoch and epoch count.")
def list_sites() -> str:
    raw = store().get("public/sites/index.json")
    return raw.decode("utf-8") if raw else "[]"


@server.tool(description="Forecast state per zone and the last six epochs' quality metrics for a site.")
def get_site_status(site: str) -> str:
    return json.dumps(box(site).get_site_status())


@server.tool(description="Re-run dense sub-pixel DIC (OpenCV matchTemplate ZNCC) for epoch t against "
             "'previous', 'reference' or 't=<value>'. Real motion is reference-independent.")
def remeasure(site: str, t: float, reference: str = "previous") -> str:
    return json.dumps(box(site).remeasure(t, reference))


@server.tool(description="Re-estimate camera motion for epoch t (ORB + USAC_MAGSAC, DIC-refined) and "
             "report stable-ground residual and scatter after the warp.")
def check_stabilization(site: str, t: float) -> str:
    return json.dumps(box(site).check_stabilization(t))


@server.tool(description="Sharpness (Laplacian variance), contrast, subset status counts and the "
             "phase-correlation cross-check for epoch t.")
def inspect_quality(site: str, t: float) -> str:
    return json.dumps(box(site).inspect_quality(t))


@server.tool(description="Share of valid subsets moving within 45 degrees of the zone's median "
             "direction for epoch t. Creep is coherent; vegetation and noise are not.")
def motion_coherence(site: str, t: float) -> str:
    return json.dumps(box(site).motion_coherence(t))


@server.tool(description="Set the camera's capture cadence (1 to 144 epochs per day) with a reason; "
             "the capture client polls it.")
def set_capture_cadence(site: str, epochs_per_day: int, reason: str) -> str:
    return json.dumps(box(site).set_capture_cadence(epochs_per_day, reason))


@server.tool(description="Page the duty contact with an evidence summary and signed approve / dismiss "
             "links. Never sends a public alert.")
def request_human_approval(site: str, t: float, summary: str) -> str:
    return json.dumps(box(site).request_human_approval(t, summary))


@server.tool(description="Close an investigation with CONFIRMED, FALSE_ALARM or INCONCLUSIVE and the "
             "measurement that decided it.")
def close_event(site: str, t: float, verdict: str, reason: str) -> str:
    return json.dumps(box(site).close_event(t, verdict, reason))


if __name__ == "__main__":
    server.run("stdio")
