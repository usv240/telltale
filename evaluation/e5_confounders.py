"""E5 (thresholds-only arm): injected confounders through the full pipeline.

Each scenario renders an epoch sequence with a known truth and a deliberate nuisance, runs the
same stack -> stabilize -> DIC -> forecast path as the cloud worker, and reports what the system
said. False alarm = any epoch in a QUIET scenario whose state left QUIET. Missed event = a true
acceleration whose forecast window did not contain the true failure time at the final epoch.

    python evaluation/e5_confounders.py [--out evaluation/results] [--size 256]

Scenarios
  quiet                  nothing moves; noise and small illumination drift only
  quiet+bump             camera bumped at epoch 10 (3 px shift, 0.4 degree roll, 0.2 % zoom)
  quiet+lighting         illumination gain steps from 1.0 to 0.7 at epoch 10 and stays there
  quiet+fog              contrast collapses to 5 % for epochs 10..14, then recovers
  quiet+lens             non-rigid distortion (thermal / lens shift) from epoch 10 on
  creep+bump             Voight creep to failure, plus the same camera bump at epoch 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import ForecastConfig, GridConfig, polygon_mask  # noqa: E402
from telltale.dic import compute_field, zone_displacement  # noqa: E402
from telltale.forecast import STATE_QUIET, forecast  # noqa: E402
from telltale.stabilize import VERDICT_OK, stabilize  # noqa: E402
from telltale.stack import STATUS_BLIND, stack_burst, translate  # noqa: E402
from telltale.synthetic import make_texture, perturb, simulate_collapse  # noqa: E402


def quiet_scene(h, w, n, seed):
    tex = make_texture(h, w, seed)
    sc = simulate_collapse(h=h, w=w, n_epochs=n, tf=1e9, t_end=47.0, amp=0.0, noise=0.0, seed=seed)
    return [tex.copy() for _ in range(n)], sc.times, sc.zone_poly, sc.stable_poly


def bump(frame):
    h, w = frame.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0.4, 1.002)
    m[:, 2] += (3.0, -2.0)
    return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)


def lens(frame, k):
    h, w = frame.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return cv2.remap(frame, xx + 1.5 * np.sin(yy / 12.0 + k), yy + 1.5 * np.cos(xx / 12.0),
                     cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)


def fog(frame):
    return (0.5 + (frame - 0.5) * 0.05).astype(np.float32)


def build(name, size, seed):
    n = 30
    if name.startswith("quiet"):
        frames, times, zone, stable = quiet_scene(size, size, n, seed)
        true_tf = None
    else:
        sc = simulate_collapse(h=size, w=size, n_epochs=n, tf=50.0, t_end=47.0, amp=2.0,
                               noise=0.0, seed=seed)
        frames, times, zone, stable, true_tf = sc.frames, sc.times, sc.zone_poly, sc.stable_poly, sc.tf
    out = []
    gain = 1.0
    for k, f in enumerate(frames):
        g = f
        if name == "quiet+bump" and k >= 10:
            g = bump(g)
        if name == "creep+bump" and k >= 20:
            g = bump(g)
        if name == "quiet+lighting" and k >= 10:
            gain = 0.7
        if name == "quiet+lens" and k >= 10:
            g = lens(g, k * 0.3)
        if name == "quiet+fog" and 10 <= k <= 14:
            g = fog(g)
        out.append((g, gain))
    return out, times, zone, stable, true_tf


def run(name, size, seed, burst=5):
    epochs, times, zone, stable, true_tf = build(name, size, seed)
    rng = np.random.default_rng(seed + 7)
    grid = GridConfig(template=41, stride=16, search=16)
    cfg = ForecastConfig()
    stable_mask = polygon_mask((size, size), [stable])
    ref = None
    t_used, d_used, s_used = [], [], []
    rows = []
    for k, ((frame, gain), t) in enumerate(zip(epochs, times)):
        fr = [np.clip(perturb(translate(frame, rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)),
                              noise=0.015, gain=gain, rng=rng) * 255, 0, 255).astype(np.uint8)
              for _ in range(burst)]
        st = stack_burst(fr)
        row = {"k": k, "t": float(t), "stack": st.status, "stabilize": None, "usable": False,
               "reason": None, "disp": None, "state": None}
        if st.status == STATUS_BLIND:
            row["reason"] = "BLIND"
        elif ref is None:
            ref = st.image
            row.update(usable=True, reason="REFERENCE", disp=0.0)
        else:
            sb = stabilize(ref, st.image, stable_mask)
            row["stabilize"] = sb.verdict
            row["model"] = sb.diag.get("refine_model")
            if sb.verdict != VERDICT_OK:
                row["reason"] = sb.verdict
            else:
                fld = compute_field(ref, sb.image, grid, seed=k)
                zm = zone_displacement(fld, "z", zone)
                row.update(usable=not fld.review, reason="REVIEW" if fld.review else "OK",
                           disp=zm.magnitude, sigma=zm.sigma, coverage=fld.coverage)
        if row["usable"] and row["disp"] is not None:
            t_used.append(t); d_used.append(row["disp"]); s_used.append(row.get("sigma", 0.02) or 0.02)
            fc = forecast(np.array(t_used), np.array(d_used), cfg, np.array(s_used))
            row["state"] = fc.state
            row["tf"] = fc.tf; row["t_lo"] = fc.t_lo; row["t_hi"] = fc.t_hi
        rows.append(row)
    states = [r["state"] for r in rows if r["state"]]
    false_alarms = sum(1 for s in states if s != STATE_QUIET) if true_tf is None else 0
    final = [r for r in rows if r["state"]][-1] if states else None
    missed = None
    if true_tf is not None:
        missed = not (final and final.get("tf") is not None and final["t_lo"] <= true_tf <= final["t_hi"])
    max_false_disp = max((r["disp"] for r in rows if r["disp"] is not None), default=0.0) if true_tf is None else None
    return {"scenario": name, "n_epochs": len(rows), "usable": sum(r["usable"] for r in rows),
            "unusable_reasons": {r["reason"]: sum(1 for q in rows if q["reason"] == r["reason"])
                                 for r in rows if not r["usable"]},
            "false_alarms": false_alarms, "max_false_disp_px": max_false_disp,
            "true_tf": true_tf, "final_state": final["state"] if final else None,
            "final_tf": final.get("tf") if final else None,
            "final_window": [final.get("t_lo"), final.get("t_hi")] if final else None,
            "missed": missed, "rows": rows}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    names = ["quiet", "quiet+bump", "quiet+lighting", "quiet+fog", "quiet+lens", "creep+bump"]
    results = []
    print(f"{'scenario':16} {'usable':>7} {'unusable (reason)':>24} {'false alarms':>12} {'max false |d| px':>17} {'final':>13} {'tf':>7} {'window':>16} {'missed':>6}")
    for name in names:
        r = run(name, a.size, a.seed)
        results.append(r)
        un = ", ".join(f"{k}:{v}" for k, v in r["unusable_reasons"].items()) or "-"
        tf = f"{r['final_tf']:.2f}" if r["final_tf"] else "-"
        win = f"[{r['final_window'][0]:.1f},{r['final_window'][1]:.1f}]" if r["final_window"] and r["final_window"][0] else "-"
        mfd = f"{r['max_false_disp_px']:.3f}" if r["max_false_disp_px"] is not None else "-"
        print(f"{name:16} {r['usable']:>3}/{r['n_epochs']:<3} {un:>24} {r['false_alarms']:>12} {mfd:>17} "
              f"{str(r['final_state']):>13} {tf:>7} {win:>16} {str(r['missed']):>6}")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "e5_confounders.json").write_text(json.dumps(results, indent=1, default=float), encoding="utf-8")
    print(f"wrote {out / 'e5_confounders.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
