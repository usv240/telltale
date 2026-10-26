"""E7: TellTale's failure forecast, replayed on real slopes that failed.

    python evaluation/e7_real_failures.py --data <folder with the collection's CSVs> \
        [--veslemannen <ESM6 .txt>] --out evaluation/results

Data: Leinauer, Weber, Cicoira, Beutel and Krautblatter (2023), "Collection of slope deformation
data until failure with a timely resolution of daily or better", mediaTUM,
doi:10.14459/2023mp1688868, CC BY 4.0 (companion to Commun. Earth Environ. 4:253). Veslemannen
from Kristensen et al. (2021), Landslides, doi:10.1007/s10346-020-01609-x, ESM 6, CC BY 4.0.

The forecast is exactly the one the worker runs (`telltale.forecast.forecast`, default
ForecastConfig: onset gates on, CRITICAL when the forecast is within 5 days with R2 >= 0.5),
with time in days. Nothing is tuned per site. Each sensor's record starts 180 days before the
failure (60 days of history, then a 120-day replay window), as if the camera had been installed then. Each sensor is resampled to the camera's design
cadence (every 4 hours; daily records stay daily) and replayed causally: the state at each
epoch uses only the data up to it. A site is in the highest state of any of its sensors, as a
TellTale site is in the highest state of its zones. The true failure time is used only to score.

Scored per site: the first warning (ACCELERATING) and the first CRITICAL, how long before the
failure each came, whether the window issued at the first CRITICAL contained the failure, the
last forecast before the failure, and false CRITICAL episodes (a CRITICAL spell that ended more
than two days before the failure).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import ForecastConfig  # noqa: E402
from telltale.forecast import forecast  # noqa: E402

RANK = {"QUIET": 0, "MOVING": 1, "ACCELERATING": 2, "CRITICAL": 3}
HISTORY_D = 60.0   # days of record before the replay window starts

# Failure times. The collection's headers are used except where noted.
SITES = {
    "Preonzo_extensometers": {"site": "Preonzo 2012 (extensometers)", "failure": "2012-05-15 02:45"},
    "Preonzo_reflectors": {"site": "Preonzo 2012 (total station)", "failure": "2012-05-15 02:45"},
    "Arvigo": {"site": "Arvigo 2007", "failure": "2007-05-28 20:00"},
    # The collection's header says 1963-02-01; the Vajont slide failed on 9 October 1963 at
    # 22:39 local time (Nonveiller 1987; Müller 1964).
    "Vaiont": {"site": "Vajont 1963", "failure": "1963-10-09 22:39"},
    # Failure date only; noon is assumed, which matters little for a daily record.
    "Hogarth": {"site": "Hogarth pit 1975", "failure": "1975-06-23 12:00"},
}
VESLEMANNEN = {"site": "Veslemannen 2019 (ground radar)", "failure": "2019-09-05 20:58"}


def _dt(s: str) -> datetime | None:
    s = s.strip().strip('"')
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def _num(s: str) -> float | None:
    try:
        v = float(s)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def load_collection(path: Path) -> dict[str, list[tuple[datetime, float]]]:
    """Sensors of one collection CSV as {name: [(time, value)]}. Handles one shared time
    column (timestamp/date) and per-sensor time columns (<x>_time next to its value)."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = next(i for i, l in enumerate(lines) if l.split(",")[0].strip().lower() in ("timestamp", "date")
                or l.split(",")[0].strip().lower().endswith("_time"))
    rows = list(csv.reader(lines[head:]))
    cols = [c.strip() for c in rows[0]]
    out: dict[str, list] = {}
    if cols[0].lower().endswith("_time"):
        for j in range(0, len(cols) - 1, 2):
            if not cols[j]:
                continue
            name = cols[j + 1]
            for r in rows[1:]:
                if j + 1 < len(r):
                    t, v = _dt(r[j]) if r[j] else None, _num(r[j + 1])
                    if t and v is not None:
                        out.setdefault(name, []).append((t, v))
    else:
        for r in rows[1:]:
            t = _dt(r[0]) if r else None
            if not t:
                continue
            for j in range(1, min(len(cols), len(r))):
                v = _num(r[j])
                if cols[j] and v is not None:
                    out.setdefault(cols[j], []).append((t, v))
    return out


def load_veslemannen(path: Path) -> dict[str, list[tuple[datetime, float]]]:
    out: dict[str, list] = {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    cols = lines[0].split("\t")
    for l in lines[1:]:
        p = l.split("\t")
        t = _dt(p[0]) if p else None
        if not t:
            continue
        for j in range(1, min(len(cols), len(p))):
            v = _num(p[j])
            if v is not None:
                out.setdefault(cols[j].strip(), []).append((t, v))
    return out


def resample(series, t0: datetime, tf: datetime, step_d: float):
    """Days since t0 on a regular grid up to the failure, displacement signed to increase."""
    series = sorted(s for s in series if s[0] < tf)
    if len(series) < 10:
        return None
    t = np.array([(s[0] - t0).total_seconds() / 86400 for s in series])
    v = np.array([s[1] for s in series])
    t, idx = np.unique(t, return_index=True)
    v = v[idx]
    grid = np.arange(t[0], t[-1] + 1e-9, step_d)
    d = np.interp(grid, t, v) - v[0]
    sgn = 1.0 if d[-1] >= 0 else -1.0
    return grid, sgn * d


def replay(t: np.ndarray, d: np.ndarray, cfg: ForecastConfig, start: int):
    """Causal replay: the forecast as issued after each epoch from `start` on."""
    inc = np.diff(d[: max(start, 20)])
    mad = np.median(np.abs(inc - np.median(inc))) if len(inc) else 0.0
    sig = max(1.4826 * mad / np.sqrt(2.0), 1e-3)
    sigma = np.full(len(d), sig)
    out = []
    for k in range(start, len(t) + 1):
        r = forecast(t[:k], d[:k], cfg, sigma[:k])
        out.append({"t": float(t[k - 1]), "state": r.state, "tf": r.tf, "t_lo": r.t_lo, "t_hi": r.t_hi})
    return out, sig


def score_site(name: str, meta: dict, sensors: dict, window_d: float, cfg: ForecastConfig) -> dict:
    tf_dt = datetime.strptime(meta["failure"], "%Y-%m-%d %H:%M")
    starts = [min(s[0] for s in v) for v in sensors.values() if v]
    t0 = min(starts)
    native = []
    for v in sensors.values():
        ts = sorted(x[0] for x in v)
        if len(ts) > 2:
            native.append(np.median(np.diff([(a - ts[0]).total_seconds() / 86400 for a in ts])))
    step = 1.0 if np.median(native) >= 0.9 else 1.0 / 6.0
    tf = (tf_dt - t0).total_seconds() / 86400
    per_sensor = {}
    timeline: dict[float, int] = {}
    windows: dict[float, list] = {}
    jobs = []
    for sname, v in sensors.items():
        rs = resample(v, t0, tf_dt, step)
        if rs is None:
            continue
        t, d = rs
        # The record starts HISTORY_D days before the replay window, as if the camera had been
        # installed then: a deployed site has months of history, not the sensor's whole decade.
        rec = t >= tf - window_d - HISTORY_D
        if rec.sum() < 30:          # a sensor that stopped reporting before the window
            continue
        t, d = t[rec], d[rec] - d[rec][0]
        keep = t >= tf - window_d
        if keep.sum() < 30:
            continue
        first = int(np.argmax(keep))
        jobs.append((sname, t, d, max(first + 1, 15)))
    # Sensors are independent: replay them in parallel (each replay is causal on its own).
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), 20))) as ex:
        done = list(ex.map(replay, [j[1] for j in jobs], [j[2] for j in jobs], [cfg] * len(jobs),
                           [j[3] for j in jobs]))
    for (sname, t, d, start), (rep, sig) in zip(jobs, done):
        per_sensor[sname] = {"epochs": len(rep), "noise_sigma": sig,
                             "final_state": rep[-1]["state"] if rep else None,
                             "first_acc_lead_d": next((tf - r["t"] for r in rep if RANK[r["state"]] >= 2), None),
                             "first_crit_lead_d": next((tf - r["t"] for r in rep if r["state"] == "CRITICAL"), None)}
        for r in rep:
            key = round(r["t"], 4)
            timeline[key] = max(timeline.get(key, 0), RANK[r["state"]])
            if r["state"] == "CRITICAL":
                windows.setdefault(key, []).append((sname, r))
    if not timeline:
        return {"site": meta["site"], "error": "no usable sensor in the window"}
    ts = sorted(timeline)
    first_acc = next((t for t in ts if timeline[t] >= 2), None)
    first_crit = next((t for t in ts if timeline[t] == 3), None)
    at_first = None
    if first_crit is not None:
        sname, r = min(windows[first_crit], key=lambda x: abs((x[1]["tf"] or 1e9) - first_crit))
        at_first = {"sensor": sname, "tf": r["tf"], "t_lo": r["t_lo"], "t_hi": r["t_hi"],
                    "contains_failure": bool(r["t_lo"] is not None and r["t_lo"] <= tf <= r["t_hi"]),
                    "median_error_d": None if r["tf"] is None else r["tf"] - tf}
    last_t = ts[-1]
    last = [(s, r) for s, r in windows.get(last_t, [])]
    last_fc = None
    if last:
        sname, r = min(last, key=lambda x: abs((x[1]["t_hi"] or 1e9) - (x[1]["t_lo"] or -1e9)))
        last_fc = {"sensor": sname, "t": last_t, "tf": r["tf"], "t_lo": r["t_lo"], "t_hi": r["t_hi"],
                   "contains_failure": bool(r["t_lo"] <= tf <= r["t_hi"]), "median_error_d": r["tf"] - tf}
    # false CRITICAL episodes: a CRITICAL spell that ended (six or more epochs below CRITICAL)
    # more than two days before the failure
    false_eps, in_crit, below = 0, False, 0
    for t in ts:
        if timeline[t] == 3:
            in_crit, below = True, 0
        elif in_crit:
            below += 1
            if below >= 6 and tf - t > 2.0:
                false_eps += 1
                in_crit = False
    return {"site": meta["site"], "file": name, "failure": meta["failure"], "step_d": step,
            "window_d": window_d, "sensors": len(per_sensor), "epochs": len(ts),
            "first_warning_lead_d": None if first_acc is None else tf - first_acc,
            "first_critical_lead_d": None if first_crit is None else tf - first_crit,
            "window_at_first_critical": at_first, "last_forecast_before_failure": last_fc,
            "false_critical_episodes": false_eps, "per_sensor": per_sensor}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, help="folder with the collection's CSV files")
    p.add_argument("--veslemannen", default=None, help="Kristensen et al. 2021 ESM 6 text file")
    p.add_argument("--window", type=float, default=120.0, help="days before failure that are replayed")
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    cfg = ForecastConfig()
    results = []
    for name, meta in SITES.items():
        f = Path(a.data) / f"{name}.csv"
        if not f.exists():
            print(f"skip {name}: not found")
            continue
        r = score_site(name, meta, load_collection(f), a.window, cfg)
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "per_sensor"}, default=str))
    if a.veslemannen and Path(a.veslemannen).exists():
        ves = load_veslemannen(Path(a.veslemannen))
        # The whole five-year record, daily: Veslemannen accelerated many times before it failed,
        # which tests false CRITICAL episodes as much as the final warning.
        daily = {}
        for k, v in ves.items():
            byday = {}
            for t, x in v:
                byday[t.date()] = (t, x)
            daily[k] = sorted(byday.values())
        r = score_site("Veslemannen", VESLEMANNEN, daily, 2000.0, cfg)
        r["note"] = "whole record, daily; radar phase wrapping underestimates the final day (Kristensen et al. 2021)"
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "per_sensor"}, default=str))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "e7_real_failures.json").write_text(json.dumps({
        "data": "Leinauer et al. 2023, mediaTUM doi:10.14459/2023mp1688868 (CC BY 4.0); "
                "Kristensen et al. 2021 ESM 6 (CC BY 4.0)",
        "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(cfg).items()},
        "sites": results}, indent=1, default=str))
    print(f"wrote {out / 'e7_real_failures.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
