"""The skeptical supervisor: a bounded perception-decision-action loop over the pipeline.

Invoked by the worker on events, not on every epoch:

    E_ANOMALY   a zone's state rose to ACCELERATING or CRITICAL
    E_CAMERA    the stabilizer returned CAMERA_EVENT
    E_QUALITY   coverage fell sharply or the cross-check flagged REVIEW

The agent (Claude on Amazon Bedrock through the Anthropic SDK tool runner) gets the tools in
``tools.py``. Its job is to decide whether the anomaly is real ground motion, and the only way
it can find out is by calling OpenCV 5 again: re-measuring against alternate references,
re-estimating camera motion, checking image quality and direction coherence. What those tools
return determines what it calls next and how it closes the event. Autonomy is bounded: at most
``MAX_CALLS`` tool calls, no public alert ever (only a request for human approval), and every
call is logged to ``public/sites/<site>/agent/<t>.json`` for the dashboard.

A rule-based policy (``RulePolicy``) drives the same tools without a model. It is the control
arm of the E5 agent ablation and the fallback when Bedrock is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import time

from .tools import Toolbox

log = logging.getLogger("telltale.agent")

DEFAULT_MODEL = os.environ.get("TELLTALE_AGENT_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

SYSTEM = """You are the supervising investigator for TellTale, a camera-based slope-stability
instrument. An event has been raised. Your single job: decide whether the apparent motion is
real ground movement or an artefact, using the tools, and close the event with a verdict.

Be a skeptic. False alarms destroy trust in warning systems; missed real motion costs lives.
Rules:
- Real creep is consistent across references (remeasure against "previous" and "reference"
  give compatible increments), has coherent direction (coherence above about 0.7), and does
  not coincide with a camera event, a lighting step, blur, or a coverage collapse.
- Artefacts are tied to one reference, are incoherent, or coincide with stabilization
  residuals above 0.3 px, low sharpness, or a coverage drop.
- Call tools with purpose; each result should change what you do next. You have a budget of
  eight tool calls. Do not repeat a call with the same arguments.
- If the acceleration is real or cannot be ruled out, call request_human_approval with a
  short evidence summary (numbers, not adjectives), and raise the capture cadence.
- If it is an artefact, close it as FALSE_ALARM and say which measurement proves it.
- Always finish with close_event. Never claim a public alert was sent; you cannot send one.
Reply in plain language, under 120 words, after closing the event."""


def _event_from(record: dict, prev_state: str, overall: str, prev_reason: str | None = None) -> str | None:
    """Which event, if any, this epoch raises. Runs of identical camera or quality failures
    raise one event at their start, not one per epoch."""
    rank = {"QUIET": 0, "MOVING": 1, "ACCELERATING": 2, "CRITICAL": 3}
    if rank.get(overall, 0) >= 2 and rank.get(overall, 0) > rank.get(prev_state, 0):
        return "E_ANOMALY"
    if record.get("reason") == "CAMERA_EVENT":
        return None if prev_reason == "CAMERA_EVENT" else "E_CAMERA"
    if record.get("reason") == "REVIEW":
        return None if prev_reason == "REVIEW" else "E_QUALITY"
    f = record.get("field") or {}
    if f and f.get("coverage") is not None and f["coverage"] < 0.4:
        return None if prev_reason == "LOW_COVERAGE" else "E_QUALITY"
    return None


def make_tools(tb: Toolbox):
    """Wrap the toolbox as Anthropic SDK tools (schemas come from signatures and docstrings)."""
    from anthropic import beta_tool

    @beta_tool
    def get_site_status() -> str:
        """Current forecast state per zone and the last six epochs' quality metrics."""
        return json.dumps(tb.get_site_status())

    @beta_tool
    def remeasure(t: float, reference: str = "previous") -> str:
        """Re-run dense sub-pixel DIC for epoch t against an alternate reference.

        Args:
            t: Epoch time to re-measure.
            reference: "previous" (last usable epoch), "reference" (site reference), or "t=<value>".
        """
        return json.dumps(tb.remeasure(t, reference))

    @beta_tool
    def check_stabilization(t: float) -> str:
        """Re-estimate camera motion for epoch t and measure stable-ground residual and scatter.

        Args:
            t: Epoch time.
        """
        return json.dumps(tb.check_stabilization(t))

    @beta_tool
    def inspect_quality(t: float) -> str:
        """Sharpness, contrast, subset status counts, cross-check and burst stability for epoch t.

        Args:
            t: Epoch time.
        """
        return json.dumps(tb.inspect_quality(t))

    @beta_tool
    def motion_coherence(t: float) -> str:
        """Direction coherence of the stored displacement field for epoch t per zone.

        Args:
            t: Epoch time.
        """
        return json.dumps(tb.motion_coherence(t))

    @beta_tool
    def set_capture_cadence(epochs_per_day: int, reason: str) -> str:
        """Change the camera capture cadence (1 to 144 epochs per day).

        Args:
            epochs_per_day: New cadence.
            reason: One-line justification.
        """
        return json.dumps(tb.set_capture_cadence(epochs_per_day, reason))

    @beta_tool
    def request_human_approval(t: float, summary: str) -> str:
        """Page the duty contact with signed approve / dismiss links and an evidence summary.

        Args:
            t: Epoch time of the alert.
            summary: Evidence summary with numbers.
        """
        return json.dumps(tb.request_human_approval(t, summary))

    @beta_tool
    def close_event(t: float, verdict: str, reason: str) -> str:
        """Close the investigation with CONFIRMED, FALSE_ALARM or INCONCLUSIVE.

        Args:
            t: Epoch time.
            verdict: CONFIRMED, FALSE_ALARM or INCONCLUSIVE.
            reason: Which measurements decided it.
        """
        return json.dumps(tb.close_event(t, verdict, reason))

    return [get_site_status, remeasure, check_stabilization, inspect_quality, motion_coherence,
            set_capture_cadence, request_human_approval, close_event]


class RulePolicy:
    """Deterministic investigation using the same tools (control arm, offline fallback)."""

    def run(self, tb: Toolbox, event: str, t: float) -> str:
        status = tb.get_site_status()
        q = tb.inspect_quality(t)
        stab = tb.check_stabilization(t)
        if stab.get("verdict") != "OK" or (stab.get("scatter_px") or 0) > 0.3:
            tb.close_event(t, "FALSE_ALARM", f"stabilization verdict {stab.get('verdict')}, scatter {stab.get('scatter_px')}")
            return "Rule policy: camera motion not explained; false alarm."
        if (q.get("sharpness") or 1.0) < 0.004:
            tb.close_event(t, "FALSE_ALARM", f"sharpness {q.get('sharpness')} below floor")
            return "Rule policy: image too blurred; false alarm."
        if event == "E_ANOMALY":
            a = tb.remeasure(t, "previous")
            b = tb.remeasure(t, "reference")
            coh = tb.motion_coherence(t)
            zones = list(b.get("zones", {}))
            consistent = any((b["zones"][z].get("magnitude") or 0) > 3 * max(b["zones"][z].get("sigma") or 0.02, 0.02)
                             and (coh["zones"].get(z, {}).get("coherence") or 0) > 0.7 for z in zones)
            if consistent:
                tb.set_capture_cadence(24, "confirmed acceleration; tighten forecast")
                tb.request_human_approval(t, f"remeasure vs reference {json.dumps({z: round(b['zones'][z]['magnitude'] or 0, 3) for z in zones})}, coherence {json.dumps({z: coh['zones'][z].get('coherence') for z in zones})}")
                tb.close_event(t, "CONFIRMED", "consistent across references and coherent")
                return "Rule policy: acceleration confirmed; human paged."
            tb.close_event(t, "INCONCLUSIVE", "motion not consistent or not coherent")
            return "Rule policy: inconclusive."
        tb.close_event(t, "INCONCLUSIVE", f"event {event} with no anomaly to confirm")
        return "Rule policy: quality event noted."


def investigate(store, site_name: str, t: float, event: str, alerting=None,
                use_llm: bool | None = None, model: str = DEFAULT_MODEL) -> dict:
    """Run one investigation and write its trace. Returns the trace dict."""
    tb = Toolbox(store, site_name, alerting)
    t0 = time.perf_counter()
    if use_llm is None:
        use_llm = os.environ.get("TELLTALE_AGENT", "llm").lower() != "rules"
    trace = {"site": site_name, "t": t, "event": event, "policy": "llm" if use_llm else "rules",
             "model": model if use_llm else None, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    text = ""
    try:
        if use_llm:
            import anthropic
            client = anthropic.AnthropicBedrock(aws_region=os.environ.get("TELLTALE_REGION", "us-east-1"))
            prompt = (f"Event {event} at site {site_name}, epoch t={t:g}. Investigate and close it. "
                      f"Start with get_site_status.")
            runner = client.beta.messages.tool_runner(
                model=model, max_tokens=4096, system=SYSTEM, tools=make_tools(tb),
                messages=[{"role": "user", "content": prompt}])
            last = None
            usage = {"input": 0, "output": 0}
            for msg in runner:
                last = msg
                usage["input"] += msg.usage.input_tokens
                usage["output"] += msg.usage.output_tokens
                if len(tb.calls) >= Toolbox.MAX_CALLS + 2:
                    break
            text = " ".join(b.text for b in (last.content if last else []) if b.type == "text")
            trace["usage"] = usage
            trace["stop_reason"] = last.stop_reason if last else None
        else:
            text = RulePolicy().run(tb, event, t)
    except Exception as e:  # the agent must never take the worker down
        log.exception("agent failed")
        trace["error"] = f"{type(e).__name__}: {e}"
        if not tb.calls or tb.calls[-1]["tool"] != "close_event":
            tb.close_event(t, "INCONCLUSIVE", f"agent error: {type(e).__name__}")
            text = text or "Agent error; event closed as inconclusive."
    closes = [c for c in tb.calls if c["tool"] == "close_event"]
    trace["verdict"] = closes[-1]["result"]["verdict"] if closes else "INCONCLUSIVE"
    trace["paged_human"] = any(c["tool"] == "request_human_approval" for c in tb.calls)
    trace["cadence_changed"] = any(c["tool"] == "set_capture_cadence" for c in tb.calls)
    trace["n_tool_calls"] = len(tb.calls)
    trace["calls"] = tb.calls
    trace["summary"] = text.strip()
    trace["seconds"] = round(time.perf_counter() - t0, 2)
    pub = f"public/sites/{site_name}"
    store.put(f"{pub}/agent/{t:g}.json", json.dumps(trace, indent=1, default=str).encode(), "application/json")
    raw = store.get(f"{pub}/agentlog.json")
    logd = json.loads(raw) if raw else {"events": []}
    logd["events"] = [e for e in logd["events"] if e["t"] != t] + [
        {k: trace[k] for k in ("t", "event", "policy", "verdict", "paged_human", "cadence_changed",
                               "n_tool_calls", "seconds", "started", "summary")}]
    logd["events"].sort(key=lambda e: e["t"])
    store.put(f"{pub}/agentlog.json", json.dumps(logd, indent=1, default=str).encode(), "application/json")
    log.info("agent %s t=%s event=%s verdict=%s calls=%d paged=%s", site_name, t, event,
             trace["verdict"], len(tb.calls), trace["paged_human"])
    return trace


__all__ = ["investigate", "RulePolicy", "make_tools", "_event_from", "SYSTEM", "DEFAULT_MODEL"]
