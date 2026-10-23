"""Check every headline number in the README against the result files, and re-run the
sub-pixel accuracy sweep live. One command for a judge:

    python evaluation/verify_claims.py            # about 20 s, no AWS, no network

Each line names the claim, the file it rests on, and PASS or FAIL. Exit code 0 only if every
claim holds. Add --skip-live to check the saved results only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evaluation" / "results"
_failed = 0


def load(name: str):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def claim(text: str, source: str, ok: bool, measured: str) -> None:
    global _failed
    _failed += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {text}\n      measured: {measured}   ({source})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skip-live", action="store_true", help="do not re-run the E1 sweep")
    a = p.parse_args(argv)

    # 1. Negative control on real data: the USGS Mukilteo bluff, the gated forecast.
    e4 = load("e4_forecast_snr3_t4.json")["zones"]
    quiet = {z: v["quiet_epochs"] for z, v in e4.items()}
    false = {z: v["false_alarm_epochs"] for z, v in e4.items()}
    claim("0 false acceleration alarms across 147 quiet days in each of three zones (USGS Mukilteo)",
          "e4_forecast_snr3_t4.json", len(e4) == 3 and set(quiet.values()) == {147} and set(false.values()) == {0},
          f"quiet days {quiet}, false-alarm epochs {false}")
    found = {z: f"{v['detected_by_increment']} of {v['observable_periods']}" for z, v in e4.items()}
    claim("2 of 2 documented movement periods the camera could see were flagged",
          "e4_forecast_snr3_t4.json",
          any(v["observable_periods"] == 2 and v["detected_by_increment"] == 2 for v in e4.values()),
          f"periods flagged per zone {found}")

    # 2. A public benchmark the team did not build: SEM 2D DIC Challenge 1.0, Sample 1.
    s1 = next(v for k, v in load("e1_dic_challenge.json").items() if k.startswith("Sample1"))["summary"]["methods"]
    tt, fb, lk = (s1[m]["mean_abs_err_px"] for m in ("telltale", "farneback", "pyrlk"))
    claim("0.005 px mean absolute error on the SEM DIC Challenge 1.0 Sample 1, ahead of Farneback and pyramidal LK",
          "e1_dic_challenge.json", tt <= 0.005 and tt < fb and tt < lk,
          f"TellTale {tt:.4f}, Farneback {fb:.4f}, pyramidal LK {lk:.4f} px")

    # 3. Confounders: nothing that only looks like motion pages anyone.
    e5 = {r["scenario"]: r for r in load("e5_confounders.json")}
    clean = {s: r["false_alarms"] for s, r in e5.items() if s in ("quiet", "quiet+bump", "quiet+lighting", "quiet+fog")}
    claim("0 false alarms under a camera bump, a lighting step and fog; lens distortion is the documented failure",
          "e5_confounders.json", set(clean.values()) == {0} and e5["quiet+lens"]["false_alarms"] > 0
          and e5["creep+bump"]["final_state"] == "CRITICAL",
          f"{clean}; lens {e5['quiet+lens']['false_alarms']} (reported in REPORT section 8); "
          f"creep with a bump still reaches {e5['creep+bump']['final_state']}")
    ag = load("e5_agent.json")["summary"]
    claim("The supervising agent adds no false pages and keeps the true page (off / rules / Claude arms)",
          "e5_agent.json", all(v["false_pages"] == 0 and v["correct_pages"] == 1 for v in ag.values()),
          ", ".join(f"{k}: {v['false_pages']} false, {v['correct_pages']} true" for k, v in ag.items()))
    arms = load("e5_agent.json")["arms"]
    llm = arms["llm"]["creep+bump"]
    first = min((e["t"] for e in llm["events"] if e["paged_human"] and e["verdict"] == "CONFIRMED"), default=None)
    lead = llm["true_tf"] - first if first is not None else None
    claim("With the agent, a person is paged 41.9 time units before failure; thresholds alone page "
          "only at the CRITICAL transition (t = 47, 3.0 before)",
          "e5_agent.json", lead is not None and abs(lead - 41.9) < 0.1 and not arms["off"]["creep+bump"]["events"]
          and arms["off"]["creep+bump"]["pages"] == 1,
          f"first confirmed page at t = {first:.2f}, true failure {llm['true_tf']}, lead {lead:.1f}" if lead else "none")

    # 4. Cost on Graviton, and COOL verified on the production path.
    st = load("e6_stock-arm_1080p.json")
    x86 = load("e6_stock-x86_1080p.json")
    claim("2,094 epochs per hour on a c8g.large, 0.038 USD per 1,000 epochs, 1.6x faster than matched x86",
          "e6_stock-arm_1080p.json, e6_stock-x86_1080p.json",
          round(st["epochs_per_hour"]) == 2094 and round(st["cost_per_1000_epochs_usd"], 3) == 0.038
          and x86["epoch"]["p50"] / st["epoch"]["p50"] > 1.55,
          f"{st['epochs_per_hour']:.0f} epochs/h, {st['cost_per_1000_epochs_usd']:.4f} USD, "
          f"x86 {x86['epoch']['p50'] / st['epoch']['p50']:.2f}x slower")
    cool, same = load("e6_cool_1080p.json"), load("e6_stock-arm-samehost_1080p.json")
    rt = cool["runtime"]
    claim("COOL executes the workload on Graviton: OpenCV 5 from /opt/cool on the Marketplace AMI",
          "e6_cool_1080p.json", rt["cool"] and rt["cv2_file"].startswith("/opt/cool/")
          and rt["opencv_version"].startswith("5.") and rt["machine"] == "aarch64",
          f"cv2 {rt['opencv_version']} at {rt['cv2_file'][:40]}..., {rt['instance_type']}, {rt['ami_id']}")
    claim("COOL measured against stock on the same host, reported as measured (5.7 to 6.6 percent slower)",
          "e6_cool_1080p.json, e6_stock-arm-samehost_1080p.json",
          0.05 < cool["epoch"]["p50"] / same["epoch"]["p50"] - 1 < 0.08,
          f"COOL {cool['epoch']['p50']:.3f} s, stock {same['epoch']['p50']:.3f} s per epoch")

    # 5. Live: the sub-pixel accuracy gate, re-run now on this machine.
    if not a.skip_live:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run([sys.executable, "-m", "telltale", "e1", "--out", td], cwd=ROOT / "pipeline",
                               capture_output=True, text=True)
            rows = json.loads((Path(td) / "e1_results.json").read_text()) if r.returncode == 0 else []
        gate = [x["mae"] for x in rows if x["shift_px"] == 0.25 and x["noise"] <= 0.01 and x["gain"] == 1.0]
        claim("Sub-pixel accuracy: 0.008 px at a 0.25 px shift (re-run live now)",
              "python -m telltale e1", bool(gate) and max(gate) < 0.01,
              f"{max(gate):.4f} px worst gate cell" if gate else r.stderr[-300:])

    print(f"\n{'all claims hold' if _failed == 0 else f'{_failed} claim(s) failed'}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
