"""E6: COOL versus stock OpenCV 5 on the same workload.

Run the identical epoch workload (burst stacking, stabilization, dense DIC) on:
  (a) the COOL AMI on a Graviton instance          --label cool
  (b) the stock pip OpenCV 5 wheel on the same instance type   --label stock-arm
  (c) the stock wheel on an x86 instance at matched vCPUs      --label stock-x86

    python evaluation/e6_cool_benchmark.py --label stock-arm --res 1080p --reps 20 \
        --price-per-hour 0.0798 --out evaluation/results

Writes <out>/e6_<label>_<res>.json with per-stage p50/p95 latency, epochs per hour, cost per
1,000 epochs, nights of monitoring per dollar at daily cadence, an op-level microbenchmark, and
the runtime proof (cv2 path, build hash, instance type, AMI id). Deterministic inputs (seeded
synthetic texture) so every cell measures the same pixels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import GridConfig, polygon_mask  # noqa: E402
from telltale.dic import compute_field  # noqa: E402
from telltale.stabilize import stabilize  # noqa: E402
from telltale.stack import stack_burst, translate  # noqa: E402
from telltale.synthetic import make_texture, perturb, shift_image  # noqa: E402

RES = {"720p": (720, 1280), "1080p": (1080, 1920), "4k": (2160, 3840)}


def imds(path: str):
    try:
        req = urllib.request.Request("http://169.254.169.254/latest/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        tok = urllib.request.urlopen(req, timeout=0.5).read().decode()
        req = urllib.request.Request(f"http://169.254.169.254/latest/meta-data/{path}",
                                     headers={"X-aws-ec2-metadata-token": tok})
        return urllib.request.urlopen(req, timeout=0.5).read().decode()
    except Exception:
        return None


def runtime() -> dict:
    return {"cv2_file": cv2.__file__, "opencv_version": cv2.__version__,
            "build_hash": hashlib.sha256(cv2.getBuildInformation().encode()).hexdigest()[:16],
            "cool": cv2.__file__.replace("\\", "/").startswith("/opt/cool"),
            "machine": platform.machine(), "python": platform.python_version(),
            "threads": cv2.getNumThreads(), "instance_type": imds("instance-type"),
            "ami_id": imds("ami-id"), "numpy": np.__version__}


def make_workload(res: str, seed: int = 0):
    h, w = RES[res]
    tex = make_texture(h, w, seed=seed)
    ref, cur, _ = shift_image(tex, 0.375, -0.25, noise=0.01, crop=0)
    rng = np.random.default_rng(seed)
    burst = [np.clip(perturb(translate(cur, rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)),
                             noise=0.01, rng=rng) * 255, 0, 255).astype(np.uint8) for _ in range(7)]
    stable = polygon_mask(ref.shape, [[(0, 0), (w // 3, 0), (w // 3, h - 1), (0, h - 1)]])
    return ref, burst, stable


def timed(fn, reps: int) -> dict:
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    ts = np.array(ts)
    return {"p50": float(np.percentile(ts, 50)), "p95": float(np.percentile(ts, 95)),
            "mean": float(ts.mean()), "min": float(ts.min()), "n": int(reps)}


def micro(ref: np.ndarray, reps: int) -> dict:
    """Op-level microbenchmark of the classical primitives the pipeline is built from."""
    u8 = (ref * 255).astype(np.uint8)
    tpl = ref[500:541, 500:541].copy()
    win = ref[480:561, 480:561].copy()
    H = np.array([[1.0, 0.001, 2.0], [-0.001, 1.0, -1.5], [0, 0, 1]])
    hann = cv2.createHanningWindow((ref.shape[1] // 2, ref.shape[0] // 2), cv2.CV_32F)
    half = cv2.resize(ref, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ops = {
        "matchTemplate_41in81_x1000": lambda: [cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED) for _ in range(1000)],
        "warpPerspective_lanczos": lambda: cv2.warpPerspective(ref, H, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_LANCZOS4),
        "warpAffine_lanczos": lambda: translate(ref, 0.3, -0.2),
        "resize_area_half": lambda: cv2.resize(ref, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
        "resize_lanczos_8x": lambda: cv2.resize(ref[:256, :256], None, fx=8, fy=8, interpolation=cv2.INTER_LANCZOS4),
        "GaussianBlur_s3": lambda: cv2.GaussianBlur(ref, (0, 0), 3.0),
        "cornerMinEigenVal": lambda: cv2.cornerMinEigenVal(ref, 3, 3),
        "boxFilter_41": lambda: cv2.boxFilter(ref, -1, (41, 41)),
        "phaseCorrelate_half": lambda: cv2.phaseCorrelate(half, half, hann),
        "ORB_4000": lambda: cv2.ORB_create(nfeatures=4000).detectAndCompute(u8, None),
        "median_stack_7": lambda: np.median(np.stack([ref] * 7), axis=0),
    }
    return {name: timed(fn, max(3, reps // 4)) for name, fn in ops.items()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True, help="cool | stock-arm | stock-x86 | laptop")
    p.add_argument("--res", default="1080p", choices=list(RES))
    p.add_argument("--reps", type=int, default=20)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--price-per-hour", type=float, default=None,
                   help="on-demand USD/hour of this instance (plus COOL software fee if any)")
    p.add_argument("--threads", type=int, default=None, help="cv2.setNumThreads override")
    p.add_argument("--search-dtype", default="float32", choices=["float32", "uint8"],
                   help="DIC integer-search data type (GridConfig.search_dtype)")
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    if a.threads is not None:
        cv2.setNumThreads(a.threads)

    rt = runtime()
    print(json.dumps(rt, indent=1))
    ref, burst, stable = make_workload(a.res)
    grid = GridConfig(search_dtype=a.search_dtype)
    print(f"workload {a.res}: {ref.shape[1]}x{ref.shape[0]}, burst of {len(burst)}, "
          f"{len(compute_field(ref, ref, GridConfig(search=2)).xs)} subsets")

    state = {}

    def do_stack():
        state["stack"] = stack_burst(burst)

    def do_stabilize():
        state["stab"] = stabilize(ref, state["stack"].image, stable)

    def do_dic():
        state["fld"] = compute_field(ref, state["stab"].image, grid)

    def do_epoch():
        do_stack(); do_stabilize(); do_dic()

    for _ in range(a.warmup):
        do_epoch()
    res = {"label": a.label, "res": a.res, "runtime": rt, "grid": vars(grid),
           "stages": {"stack": timed(do_stack, a.reps), "stabilize": timed(do_stabilize, a.reps),
                      "dic": timed(do_dic, a.reps)},
           "epoch": timed(do_epoch, a.reps)}
    res["field"] = {"n_subsets": int(len(state["fld"].xs)), "n_valid": state["fld"].n_valid,
                    "median_u": float(np.median(state["fld"].u[state["fld"].valid])),
                    "median_v": float(np.median(state["fld"].v[state["fld"].valid]))}
    ep = res["epoch"]["p50"]
    res["epochs_per_hour"] = 3600.0 / ep
    if a.price_per_hour:
        cost_per_epoch = a.price_per_hour * ep / 3600.0
        res["price_per_hour"] = a.price_per_hour
        res["cost_per_1000_epochs_usd"] = 1000 * cost_per_epoch
        res["nights_per_dollar_daily_cadence"] = 1.0 / cost_per_epoch
        res["site_month_usd_at_6_epochs_per_day"] = cost_per_epoch * 6 * 30
    res["micro"] = micro(ref, a.reps)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"e6_{a.label}_{a.res}.json"
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n{a.label} {a.res}: epoch p50 {ep:.3f}s p95 {res['epoch']['p95']:.3f}s "
          f"(stack {res['stages']['stack']['p50']:.3f}, stabilize {res['stages']['stabilize']['p50']:.3f}, "
          f"dic {res['stages']['dic']['p50']:.3f}); {res['epochs_per_hour']:.0f} epochs/hour")
    if a.price_per_hour:
        print(f"cost per 1,000 epochs {res['cost_per_1000_epochs_usd']:.3f} USD; "
              f"{res['nights_per_dollar_daily_cadence']:.0f} nights of monitoring per dollar")
    print("micro p50 (ms): " + ", ".join(f"{k} {v['p50']*1e3:.1f}" for k, v in res["micro"].items()))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
