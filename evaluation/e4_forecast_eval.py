"""E4b: the forecaster on a real slope. Detection on documented movement periods and false
acceleration alarms on quiet days, from the Mukilteo chained series (output of e4_mukilteo.py).

    python evaluation/e4_forecast_eval.py [--snr 0] [--out evaluation/results]

For each zone, the cumulative chained displacement is replayed epoch by epoch through the same
forecaster the worker runs. An epoch counts as a false alarm if its state is ACCELERATING or
CRITICAL and it lies outside every documented movement window (plus a two-day tail). A period
counts as detected if any usable epoch inside the window (plus tail) reached ACCELERATING or
CRITICAL, or if a daily increment inside the window exceeded the 90th percentile of quiet days.
Periods with no usable epochs (wet lens) are reported as "not observable", separately.
``--snr 0`` reproduces the original onset rule so the before-and-after can be compared.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "evaluation"))

from e4_mukilteo import MOVEMENT_PERIODS  # noqa: E402
from telltale.config import ForecastConfig  # noqa: E402
from telltale.forecast import STATE_ACCELERATING, STATE_CRITICAL, rolling_forecast  # noqa: E402

TAIL_DAYS = 2


def in_window(d: dt.date) -> str | None:
    for name, a, b in MOVEMENT_PERIODS:
        if a <= d <= b + dt.timedelta(days=TAIL_DAYS):
            return name
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default=str(ROOT / "evaluation" / "results" / "e4_mukilteo.json"))
    p.add_argument("--snr", type=float, default=None, help="override ooa_min_snr (0 = off)")
    p.add_argument("--tstat", type=float, default=None, help="override ooa_min_tstat (0 = off)")
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    p.add_argument("--jump-k", dest="jump_k", type=float, default=4.0)
    p.add_argument("--jump-window", dest="jump_window", type=int, default=20)
    a = p.parse_args(argv)
    data = json.loads(Path(a.results).read_text(encoding="utf-8"))
    rows = [r for r in data["rows"] if r["usable"] and r.get("zones")]
    cfg = ForecastConfig()
    if a.snr is not None:
        cfg.ooa_min_snr = a.snr
    if a.tstat is not None:
        cfg.ooa_min_tstat = a.tstat
    start = dt.date.fromisoformat(data["rows"][0]["date"])
    summary = {"ooa_min_snr": cfg.ooa_min_snr, "ooa_min_tstat": cfg.ooa_min_tstat, "zones": {}}
    for z in rows[0]["zones"]:
        pts = [(r, r["zones"][z]) for r in rows if r["zones"].get(z) and r["zones"][z].get("cum_mag") is not None]
        dates = [dt.date.fromisoformat(r["date"]) for r, _ in pts]
        t = np.array([(d - start).days for d in dates], dtype=float)
        d_cum = np.array([zz["cum_mag"] for _, zz in pts])
        s = np.array([zz["sigma"] if zz.get("sigma") is not None else 0.1 for _, zz in pts])
        inc = np.array([float(np.hypot(zz["du"], zz["dv"])) for _, zz in pts])
        states = [fc.state for fc in rolling_forecast(t, d_cum, cfg, s)]
        quiet_inc = [m for m, d in zip(inc, dates) if in_window(d) is None]
        p90 = float(np.percentile(quiet_inc, 90))
        # Jump detector (what the worker raises as E_JUMP): today's increment against the robust
        # sigma of the trailing window of increments. Causal, no knowledge of the windows.
        jump = np.zeros(len(inc), bool)
        for i in range(len(inc)):
            lo = max(0, i - a.jump_window)
            past = inc[lo:i]
            if len(past) < 6:
                continue
            med = np.median(past); sig_i = 1.4826 * np.median(np.abs(past - med))
            jump[i] = inc[i] > med + a.jump_k * max(sig_i, 1e-3)
        quiet_jumps = sum(1 for i, d in enumerate(dates) if jump[i] and in_window(d) is None)
        false_epochs = [(dates[i].isoformat(), states[i]) for i in range(len(states))
                        if states[i] in (STATE_ACCELERATING, STATE_CRITICAL) and in_window(dates[i]) is None]
        # episodes = runs of consecutive false epochs
        episodes, prev = 0, None
        for i in range(len(states)):
            f = states[i] in (STATE_ACCELERATING, STATE_CRITICAL) and in_window(dates[i]) is None
            if f and not prev:
                episodes += 1
            prev = f
        periods = {}
        for name, a0, b0 in MOVEMENT_PERIODS:
            idx = [i for i, d in enumerate(dates) if a0 <= d <= b0 + dt.timedelta(days=TAIL_DAYS)]
            if not idx:
                periods[name] = {"observable": False}
                continue
            periods[name] = {"observable": True, "usable_epochs": len(idx),
                             "jump_detected": bool(any(jump[i] for i in idx)),
                             "state_detected": any(states[i] in (STATE_ACCELERATING, STATE_CRITICAL) for i in idx),
                             "increment_detected": any(inc[i] > p90 for i in idx),
                             "max_increment_px": float(max(inc[i] for i in idx)),
                             "max_state": max((states[i] for i in idx), key=lambda s: ["QUIET", "MOVING", "ACCELERATING", "CRITICAL"].index(s))}
        n_quiet = sum(1 for d in dates if in_window(d) is None)
        summary["zones"][z] = {
            "usable_epochs": len(states), "quiet_epochs": n_quiet, "quiet_p90_increment_px": p90,
            "false_alarm_epochs": len(false_epochs), "false_alarm_episodes": episodes,
            "false_critical_epochs": sum(1 for _, st in false_epochs if st == STATE_CRITICAL),
            "first_false_epochs": false_epochs[:6],
            "periods": periods,
            "observable_periods": sum(1 for v in periods.values() if v["observable"]),
            "detected_by_state": sum(1 for v in periods.values() if v.get("state_detected")),
            "detected_by_increment": sum(1 for v in periods.values() if v.get("increment_detected")),
            "jump_k": a.jump_k, "quiet_jump_days": quiet_jumps,
            "detected_by_jump": sum(1 for v in periods.values() if v.get("jump_detected")),
        }
    out = Path(a.out)
    tag = f"snr{cfg.ooa_min_snr:g}_t{cfg.ooa_min_tstat:g}"
    (out / f"e4_forecast_{tag}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"ooa_min_snr = {cfg.ooa_min_snr}, ooa_min_tstat = {cfg.ooa_min_tstat}")
    print(f"{'zone':12} {'quiet ep':>8} {'false ep':>8} {'episodes':>8} {'false CRIT':>10} {'periods obs':>11} {'det state':>9} {'det jump':>8} {'quiet jumps':>11}")
    for z, v in summary["zones"].items():
        print(f"{z:12} {v['quiet_epochs']:8d} {v['false_alarm_epochs']:8d} {v['false_alarm_episodes']:8d} {v['false_critical_epochs']:10d} "
              f"{v['observable_periods']:11d} {v['detected_by_state']:9d} {v['detected_by_jump']:8d} {v['quiet_jump_days']:11d}")
        for name, pr in v["periods"].items():
            print(f"    {name:22} " + ("not observable (wet lens)" if not pr["observable"] else
                  f"epochs {pr['usable_epochs']}, max state {pr['max_state']}, max increment {pr['max_increment_px']:.2f} px, jump {pr['jump_detected']}"))
    print(f"wrote {out / f'e4_forecast_{tag}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
