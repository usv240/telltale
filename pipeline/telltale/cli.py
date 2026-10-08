"""Command line: ``python -m telltale <command>``.

Commands:
    e1        synthetic sub-pixel accuracy sweep (bias and sigma per condition)
    simulate  render a synthetic collapse and run the full pipeline and forecast on it
    epoch     process one burst directory against a reference burst and a site config
    forecast  recompute the forecast from a stored zone series
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from .config import ForecastConfig, GridConfig, SiteConfig, polygon_mask
from .dic import compute_field, zone_displacement
from .forecast import forecast, rolling_forecast
from .overlay import render_overlay, render_status_map
from .series import SeriesStore
from .stabilize import VERDICT_OK, stabilize
from .stack import STATUS_BLIND, stack_burst, to_gray32
from .synthetic import make_texture, shift_image, simulate_collapse

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")


def _load_burst(folder: Path) -> list[np.ndarray]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
    if not files:
        raise SystemExit(f"no images in {folder}")
    frames = []
    for p in files:
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise SystemExit(f"cannot read {p}")
        frames.append(img)
    return frames


def cmd_e1(args) -> int:
    rng = np.random.default_rng(args.seed)
    tex = make_texture(args.size, args.size, seed=args.seed)
    grid = GridConfig(template=args.template, stride=args.stride, search=args.search)
    shifts = [0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0]
    noises = [0.0, 0.01, 0.02]
    gains = [1.0, 0.85]
    rows = []
    t0 = time.perf_counter()
    for noise in noises:
        for gain in gains:
            for sh in shifts:
                errs_u, errs_v = [], []
                for trial in range(args.trials):
                    angle = rng.uniform(0, 2 * np.pi)
                    dx, dy = sh * np.cos(angle), sh * np.sin(angle)
                    ref, cur, (ax, ay) = shift_image(tex, dx, dy, noise=noise, gain=gain,
                                                      bias=0.0, seed=int(rng.integers(1 << 30)))
                    fld = compute_field(ref, cur, grid, seed=trial)
                    if fld.n_valid == 0:
                        continue
                    errs_u.append(fld.u[fld.valid] - ax)
                    errs_v.append(fld.v[fld.valid] - ay)
                eu = np.concatenate(errs_u) if errs_u else np.array([np.nan])
                ev = np.concatenate(errs_v) if errs_v else np.array([np.nan])
                e = np.concatenate([eu, ev])
                rows.append({
                    "shift_px": sh, "noise": noise, "gain": gain, "n": int(len(e)),
                    "bias": float(np.nanmean(e)), "sigma": float(np.nanstd(e)),
                    "mae": float(np.nanmean(np.abs(e))),
                    "p95_abs": float(np.nanpercentile(np.abs(e), 95)),
                })
    dt = time.perf_counter() - t0
    print(f"{'shift':>6} {'noise':>6} {'gain':>5} {'n':>6} {'bias':>8} {'sigma':>8} {'mae':>8} {'p95':>8}")
    for r in rows:
        print(f"{r['shift_px']:6.3f} {r['noise']:6.3f} {r['gain']:5.2f} {r['n']:6d} "
              f"{r['bias']:8.4f} {r['sigma']:8.4f} {r['mae']:8.4f} {r['p95_abs']:8.4f}")
    gate = [r for r in rows if r["shift_px"] == 0.25 and r["noise"] <= 0.01 and r["gain"] == 1.0]
    worst = max(r["mae"] for r in gate) if gate else float("nan")
    print(f"\nG1 gate (MAE at 0.25 px, noise <= 0.01): {worst:.4f} px "
          f"({'PASS' if worst < 0.05 else 'FAIL'}); {len(rows)} cells in {dt:.1f}s")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "e1_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"wrote {out / 'e1_results.json'}")
    return 0


def cmd_simulate(args) -> int:
    scene = simulate_collapse(h=args.size, w=args.size, n_epochs=args.epochs, tf=args.tf,
                              t_end=args.t_end, amp=args.amp, noise=args.noise,
                              jitter_px=args.jitter, seed=args.seed)
    grid = GridConfig(template=args.template, stride=args.stride, search=args.search)
    fcfg = ForecastConfig()
    stable_mask = polygon_mask(scene.frames[0].shape, [scene.stable_poly])
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    store = SeriesStore(out / "series.jsonl") if out else None
    ref = scene.frames[0]
    times, meas, sig = [], [], []
    print(f"{'k':>3} {'t':>7} {'true':>7} {'meas':>7} {'sigma':>6} {'cov':>5} {'stab':>12} {'state':>12} {'tf':>8} {'window':>17}")
    t0 = time.perf_counter()
    for k, (t, frame) in enumerate(zip(scene.times, scene.frames)):
        stab_verdict = "-"
        cur = frame
        if args.jitter > 0 and k > 0:
            st = stabilize(ref, frame, stable_mask)
            stab_verdict = st.verdict
            if st.verdict != VERDICT_OK:
                print(f"{k:3d} {t:7.2f} {scene.true_disp[k]:7.3f} {'skip':>7} {'':>6} {'':>5} {stab_verdict:>12}")
                continue
            cur = st.image
        fld = compute_field(ref, cur, grid, seed=k)
        zm = zone_displacement(fld, "slope", scene.zone_poly)
        times.append(t)
        meas.append(zm.magnitude)
        sig.append(zm.sigma)
        if store:
            store.append({"t": float(t), "zone": "slope", **zm.to_dict(), "usable": True,
                          "stabilize": stab_verdict, "review": fld.review})
        fc = forecast(np.array(times), np.array(meas), fcfg, np.array(sig))
        tf_s = f"{fc.tf:8.2f}" if fc.tf is not None else f"{'-':>8}"
        win = f"[{fc.t_lo:7.2f},{fc.t_hi:7.2f}]" if fc.tf is not None else f"{'':>17}"
        print(f"{k:3d} {t:7.2f} {scene.true_disp[k]:7.3f} {zm.magnitude:7.3f} {zm.sigma:6.3f} "
              f"{zm.coverage:5.2f} {stab_verdict:>12} {fc.state:>12} {tf_s} {win}")
        if out and (k % max(1, args.epochs // 6) == 0 or k == args.epochs - 1):
            label = f"t={t:.1f} {fc.state} |d|={zm.magnitude:.2f}px"
            cv2.imwrite(str(out / f"overlay_{k:03d}.png"), render_overlay(cur, fld, label=label))
            if k == 0:
                cv2.imwrite(str(out / "status_map.png"), render_status_map(cur, fld))
    dt = time.perf_counter() - t0
    fc = forecast(np.array(times), np.array(meas), fcfg, np.array(sig))
    err = np.abs(np.array(meas) - scene.true_disp[:len(meas)]) if len(meas) == len(scene.true_disp) else None
    print(f"\ntrue tf = {scene.tf:.2f}; last epoch t = {times[-1]:.2f}")
    if fc.tf is not None:
        print(f"forecast tf = {fc.tf:.2f} window [{fc.t_lo:.2f}, {fc.t_hi:.2f}] r2 = {fc.r2:.3f} "
              f"state = {fc.state}; error = {fc.tf - scene.tf:+.2f} "
              f"({'inside' if fc.t_lo <= scene.tf <= fc.t_hi else 'OUTSIDE'} window)")
        for name, m in fc.methods.items():
            print(f"  {name:10s} tf = {m['tf']:.2f} r2 = {m['r2']:.3f}"
                  + (f" alpha = {m['alpha']:.2f}" if 'alpha' in m else ""))
    else:
        print(f"no forecast: state = {fc.state} ({fc.note})")
    if err is not None:
        print(f"measurement MAE vs truth = {err.mean():.4f} px, max = {err.max():.4f} px")
    print(f"{len(times)} epochs in {dt:.1f}s")
    if out:
        (out / "forecast.json").write_text(json.dumps(fc.to_dict(), indent=2), encoding="utf-8")
        print(f"wrote {out}")
    return 0


def cmd_epoch(args) -> int:
    site = SiteConfig.from_json(args.site)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ref_stack = stack_burst(_load_burst(Path(args.ref)))
    cur_stack = stack_burst(_load_burst(Path(args.cur)))
    record = {"t": args.t, "site": site.name, "ref_status": ref_stack.status,
              "cur_status": cur_stack.status, "cur_max_shift": cur_stack.max_shift}
    if ref_stack.status == STATUS_BLIND or cur_stack.status == STATUS_BLIND:
        print(json.dumps({**record, "usable": False, "reason": "BLIND"}, indent=2))
        return 2
    ref, cur = ref_stack.image, cur_stack.image
    stable_mask = polygon_mask(ref.shape, site.stable_polys) if site.stable_polys else None
    st = stabilize(ref, cur, stable_mask)
    record["stabilize"] = st.to_dict()
    if st.verdict != VERDICT_OK:
        print(json.dumps({**record, "usable": False, "reason": st.verdict}, indent=2))
        return 3
    fld = compute_field(ref, st.image, site.grid)
    fld.save(out / f"field_{args.t}.npz")
    cv2.imwrite(str(out / f"overlay_{args.t}.png"), render_overlay(st.image, fld))
    record["coverage"] = fld.coverage
    record["review"] = fld.review
    record["crosscheck_px"] = fld.crosscheck_px
    record["status_counts"] = fld.status_counts()
    store = SeriesStore(out / "series.jsonl")
    zones = {}
    for name, poly in site.target_zones.items():
        zm = zone_displacement(fld, name, poly)
        zones[name] = zm.to_dict()
        store.append({"t": args.t, "zone": name, **zm.to_dict(),
                      "mm": zm.magnitude * site.mm_per_px, "usable": not fld.review,
                      "stabilize": st.verdict, "review": fld.review})
    record["zones"] = zones
    print(json.dumps(record, indent=2))
    return 0


def cmd_forecast(args) -> int:
    cfg = SiteConfig.from_json(args.site).forecast if args.site else ForecastConfig()
    store = SeriesStore(args.series)
    t, d, s = store.arrays(args.zone)
    if len(t) == 0:
        raise SystemExit(f"no records for zone {args.zone!r} in {args.series}")
    if args.rolling:
        for fc in rolling_forecast(t, d, cfg, s if np.isfinite(s).all() else None):
            tf = f"{fc.tf:.2f}" if fc.tf is not None else "-"
            print(f"t={fc.t_now:8.2f} {fc.state:12s} tf={tf}")
    fc = forecast(t, d, cfg, s if np.isfinite(s).all() else None)
    print(json.dumps(fc.to_dict(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="telltale", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e1 = sub.add_parser("e1", help="synthetic sub-pixel accuracy sweep")
    e1.add_argument("--size", type=int, default=256)
    e1.add_argument("--trials", type=int, default=5)
    e1.add_argument("--template", type=int, default=41)
    e1.add_argument("--stride", type=int, default=24)
    e1.add_argument("--search", type=int, default=8)
    e1.add_argument("--seed", type=int, default=0)
    e1.add_argument("--out", default=None)
    e1.set_defaults(fn=cmd_e1)

    sim = sub.add_parser("simulate", help="synthetic collapse through the full pipeline")
    sim.add_argument("--size", type=int, default=256)
    sim.add_argument("--epochs", type=int, default=40)
    sim.add_argument("--tf", type=float, default=50.0)
    sim.add_argument("--t-end", dest="t_end", type=float, default=47.0)
    sim.add_argument("--amp", type=float, default=2.0)
    sim.add_argument("--noise", type=float, default=0.01)
    sim.add_argument("--jitter", type=float, default=0.0, help="camera jitter px per epoch")
    sim.add_argument("--template", type=int, default=41)
    sim.add_argument("--stride", type=int, default=16)
    sim.add_argument("--search", type=int, default=16)
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--out", default=None)
    sim.set_defaults(fn=cmd_simulate)

    ep = sub.add_parser("epoch", help="process one burst against a reference burst")
    ep.add_argument("--site", required=True)
    ep.add_argument("--ref", required=True, help="reference burst directory")
    ep.add_argument("--cur", required=True, help="current burst directory")
    ep.add_argument("--t", type=float, required=True, help="epoch time (hours or any unit)")
    ep.add_argument("--out", required=True)
    ep.set_defaults(fn=cmd_epoch)

    fc = sub.add_parser("forecast", help="forecast from a stored series")
    fc.add_argument("--series", required=True)
    fc.add_argument("--zone", required=True)
    fc.add_argument("--site", default=None)
    fc.add_argument("--rolling", action="store_true")
    fc.set_defaults(fn=cmd_forecast)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
