"""TellTale epoch worker.

Consumes S3 "manifest.json created" events from SQS, runs the OpenCV 5 pipeline on the burst,
and publishes dashboard artifacts. The same ``process_epoch`` function runs against a local
folder (``LocalStore``) for offline demos and tests, so the cloud path and the laptop path are
one code path with two storage backends.

Bucket layout (``S3Store``) or folder layout (``LocalStore``):

    ingest/<site>/<t>/frame_*.png|jpg   raw burst (private, expires)
    ingest/<site>/<t>/manifest.json     {"site", "t", "frames": [...], "site_config"?: {...}}
    private/sites/<site>/reference.npy  stacked reference epoch (float32)
    public/sites/index.json             [{"site", "state", "last_t", ...}]
    public/sites/<site>/site.json       SiteConfig
    public/sites/<site>/series.json     {"records": [...]}      one record per zone per epoch
    public/sites/<site>/forecast.json   {"zones": {name: {...}}, "state", "updated"}
    public/sites/<site>/epochs/<t>/overlay.png | status.png | field.npz | record.json

Every record carries ``runtime``: cv2 module path, OpenCV version, a hash of the build info,
instance type and AMI id. ``runtime.cool`` is true only when cv2 was imported from /opt/cool,
which is the Best Use of COOL award's proof-of-execution requirement.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import platform
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from telltale import (ForecastConfig, SiteConfig, compute_field, forecast, polygon_mask,
                      stabilize, stack_burst, zone_displacement)
from telltale.forecast import moving_average, smoothed_velocities
from telltale.overlay import render_overlay, render_status_map
from telltale.stabilize import VERDICT_OK
from telltale.stack import STATUS_BLIND, STATUS_BLURRED

log = logging.getLogger("telltale.worker")


# ------------------------------------------------------------------ storage backends
class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def get(self, key: str) -> bytes | None:
        p = self.root / key
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)).replace("\\", "/")
                      for p in base.rglob("*") if p.is_file())


class S3Store:
    def __init__(self, bucket: str, region: str | None = None):
        import boto3
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def get(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None
        except Exception as e:  # botocore ClientError 404
            if "NoSuchKey" in str(e) or "Not Found" in str(e) or "404" in str(e):
                return None
            raise

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def list(self, prefix: str) -> list[str]:
        keys, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            resp = self.s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            token = resp.get("NextContinuationToken")
            if not token:
                return sorted(keys)


# ------------------------------------------------------------------ helpers
def _json(obj) -> bytes:
    return json.dumps(obj, indent=1, default=_default).encode("utf-8")


def _default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    raise TypeError(str(type(o)))


def _clean(x):
    """Replace NaN/inf with None recursively so the JSON is valid for browsers."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (float, np.floating)) and not np.isfinite(x):
        return None
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def _imds(path: str) -> str | None:
    try:
        req = urllib.request.Request("http://169.254.169.254/latest/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        token = urllib.request.urlopen(req, timeout=0.5).read().decode()
        req = urllib.request.Request(f"http://169.254.169.254/latest/meta-data/{path}",
                                     headers={"X-aws-ec2-metadata-token": token})
        return urllib.request.urlopen(req, timeout=0.5).read().decode()
    except Exception:
        return None


_RUNTIME: dict | None = None


def runtime_info() -> dict:
    global _RUNTIME
    if _RUNTIME is None:
        build = cv2.getBuildInformation()
        _RUNTIME = {
            "cv2_file": cv2.__file__,
            "opencv_version": cv2.__version__,
            "build_hash": hashlib.sha256(build.encode()).hexdigest()[:16],
            "cool": cv2.__file__.replace("\\", "/").startswith("/opt/cool"),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "threads": cv2.getNumThreads(),
            "instance_type": _imds("instance-type"),
            "ami_id": _imds("ami-id"),
            "instance_id": _imds("instance-id"),
        }
    return _RUNTIME


def _decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("undecodable frame")
    return img


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


# ------------------------------------------------------------------ core
def forecast_payload(times, disp, sigma, cfg: ForecastConfig, mm_per_px: float) -> dict:
    fc = forecast(times, disp, cfg, sigma)
    d = fc.to_dict()
    sma, lma = smoothed_velocities(times, disp, cfg) if len(times) >= 2 else (np.zeros(0), np.zeros(0))
    t_sma = moving_average(times, cfg.sma_window) if len(times) >= 2 else np.zeros(0)
    d["series"] = {
        "t": list(map(float, times)), "disp_px": list(map(float, disp)),
        "disp_mm": [float(x * mm_per_px) for x in disp],
        "sigma_px": [None if not np.isfinite(s) else float(s) for s in sigma],
        "v_sma": list(map(float, sma)), "v_lma": list(map(float, lma)),
        "t_sma": list(map(float, t_sma)),
    }
    if fc.ooa_index is not None:
        sel = np.arange(fc.ooa_index, len(times))
        sel = sel[sma[sel] > 0]
        d["inverse_velocity"] = {"t": [float(t_sma[i]) for i in sel],
                                 "inv_v": [float(1.0 / sma[i]) for i in sel]}
        lin = fc.methods.get("linear")
        if lin:
            d["fit_line"] = {"slope": lin["slope"], "intercept": lin["intercept"]}
    return _clean(d)


def process_epoch(store, site_name: str, t: float, frames: list[np.ndarray],
                  site_config: dict | None = None) -> dict:
    """Run one burst through the pipeline and publish artifacts. Returns the epoch record."""
    t0 = time.perf_counter()
    pub = f"public/sites/{site_name}"
    priv = f"private/sites/{site_name}"
    epoch_dir = f"{pub}/epochs/{t:g}"
    rt = runtime_info()

    raw = store.get(f"{pub}/site.json")
    if raw is None:
        if site_config is None:
            raise RuntimeError(f"no site.json for {site_name} and manifest carried none")
        store.put(f"{pub}/site.json", _json(site_config), "application/json")
        raw = _json(site_config)
    cfg_dict = json.loads(raw)
    site = SiteConfig.from_json_dict(cfg_dict)

    record = {"t": float(t), "site": site_name, "usable": False, "reason": None,
              "runtime": rt, "timing": {}, "overlay": None}

    st_t = time.perf_counter()
    stack = stack_burst(frames)
    record["timing"]["stack_s"] = time.perf_counter() - st_t
    record["stack"] = {"status": stack.status, "n_frames": stack.n_frames,
                       "max_shift": stack.max_shift, "contrast": stack.contrast}
    if stack.status in (STATUS_BLIND, STATUS_BLURRED):
        record["reason"] = stack.status
        return _finish(store, site, site_name, record, None, t0)

    ref_raw = store.get(f"{priv}/reference.npy")
    if ref_raw is None:
        store.put(f"{priv}/reference.npy", _npy(stack.image))
        store.put(f"{pub}/reference.png", _png(np.clip(stack.image * 255, 0, 255).astype(np.uint8)),
                  "image/png")
        record["usable"] = True
        record["reason"] = "REFERENCE"
        record["zones"] = {name: {"zone": name, "u": 0.0, "v": 0.0, "sigma_u": 0.0,
                                  "sigma_v": 0.0, "n_valid": 0, "n_total": 0,
                                  "magnitude": 0.0, "sigma": 0.0}
                           for name in site.target_zones}
        store.put(f"{epoch_dir}/overlay.png",
                  _png(cv2.cvtColor(np.clip(stack.image * 255, 0, 255).astype(np.uint8),
                                    cv2.COLOR_GRAY2BGR)), "image/png")
        record["overlay"] = f"epochs/{t:g}/overlay.png"
        return _finish(store, site, site_name, record, None, t0)
    ref = np.load(io.BytesIO(ref_raw))

    stable_mask = polygon_mask(ref.shape, site.stable_polys) if site.stable_polys else None
    st_t = time.perf_counter()
    st = stabilize(ref, stack.image, stable_mask)
    record["timing"]["stabilize_s"] = time.perf_counter() - st_t
    record["stabilize"] = st.to_dict()
    if st.verdict != VERDICT_OK:
        record["reason"] = st.verdict
        return _finish(store, site, site_name, record, None, t0)

    st_t = time.perf_counter()
    fld = compute_field(ref, st.image, site.grid)
    record["timing"]["dic_s"] = time.perf_counter() - st_t
    record["field"] = {"n_subsets": int(len(fld.xs)), "n_valid": fld.n_valid,
                       "coverage": fld.coverage, "status_counts": fld.status_counts(),
                       "crosscheck_px": fld.crosscheck_px, "review": fld.review}
    record["usable"] = not fld.review
    record["reason"] = "REVIEW" if fld.review else "OK"

    zones = {}
    for name, poly in site.target_zones.items():
        zm = zone_displacement(fld, name, poly)
        zd = zm.to_dict()
        zd["mm"] = zm.magnitude * site.mm_per_px
        zd["sigma_mm"] = zm.sigma * site.mm_per_px
        zones[name] = zd
    record["zones"] = zones

    label = f"t={t:g}  " + "  ".join(f"{n}: {z['magnitude']:.2f}px" for n, z in zones.items())
    store.put(f"{epoch_dir}/overlay.png", _png(render_overlay(st.image, fld, label=label)), "image/png")
    store.put(f"{epoch_dir}/status.png", _png(render_status_map(st.image, fld)), "image/png")
    buf = io.BytesIO()
    fld.save(buf)
    store.put(f"{epoch_dir}/field.npz", buf.getvalue())
    record["overlay"] = f"epochs/{t:g}/overlay.png"
    return _finish(store, site, site_name, record, fld, t0)


def _npy(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, a)
    return buf.getvalue()


def _finish(store, site: SiteConfig, site_name: str, record: dict, fld, t0: float) -> dict:
    pub = f"public/sites/{site_name}"
    record["timing"]["total_s"] = time.perf_counter() - t0
    record = _clean(record)
    store.put(f"{pub}/epochs/{record['t']:g}/record.json", _json(record), "application/json")

    raw = store.get(f"{pub}/series.json")
    series = json.loads(raw) if raw else {"records": []}
    series["records"] = [r for r in series["records"] if r["t"] != record["t"]] + [record]
    series["records"].sort(key=lambda r: r["t"])
    store.put(f"{pub}/series.json", _json(series), "application/json")

    fcs, overall = {}, "QUIET"
    rank = {"QUIET": 0, "MOVING": 1, "ACCELERATING": 2, "CRITICAL": 3}
    for name in site.target_zones:
        pts = [(r["t"], r["zones"][name]["magnitude"], r["zones"][name]["sigma"])
               for r in series["records"] if r.get("usable") and r.get("zones", {}).get(name)
               and r["zones"][name]["magnitude"] is not None]
        if not pts:
            continue
        t_arr = np.array([p[0] for p in pts]); d_arr = np.array([p[1] for p in pts])
        s_arr = np.array([p[2] if p[2] is not None else np.nan for p in pts])
        if not np.isfinite(s_arr).all():
            s_arr = np.where(np.isfinite(s_arr), s_arr, np.nanmedian(s_arr) if np.isfinite(s_arr).any() else 0.05)
        fcs[name] = forecast_payload(t_arr, d_arr, s_arr, site.forecast, site.mm_per_px)
        if rank.get(fcs[name]["state"], 0) > rank[overall]:
            overall = fcs[name]["state"]
    n_unusable = sum(1 for r in series["records"] if not r.get("usable"))
    if not record["usable"]:
        overall_display = f"{overall} (last epoch {record['reason']})"
    else:
        overall_display = overall
    payload = {"site": site_name, "state": overall, "state_display": overall_display,
               "updated_t": record["t"], "n_epochs": len(series["records"]),
               "n_unusable": n_unusable, "zones": fcs, "runtime": record["runtime"],
               "mm_per_px": site.mm_per_px}
    store.put(f"{pub}/forecast.json", _json(payload), "application/json")

    raw = store.get("public/sites/index.json")
    index = json.loads(raw) if raw else []
    index = [s for s in index if s["site"] != site_name]
    index.append({"site": site_name, "state": overall, "last_t": record["t"],
                  "n_epochs": len(series["records"]), "cool": record["runtime"].get("cool")})
    index.sort(key=lambda s: s["site"])
    store.put("public/sites/index.json", _json(index), "application/json")
    log.info("epoch %s t=%s usable=%s reason=%s state=%s total=%.2fs", site_name, record["t"],
             record["usable"], record["reason"], overall, record["timing"]["total_s"])
    return record


# ------------------------------------------------------------------ cloud loop
def _put_metrics(cw, site: str, record: dict, state: str) -> None:
    dims = [{"Name": "Site", "Value": site}]
    data = [
        {"MetricName": "EpochProcessed", "Dimensions": dims, "Value": 1, "Unit": "Count"},
        {"MetricName": "EpochUsable", "Dimensions": dims, "Value": 1 if record["usable"] else 0, "Unit": "Count"},
        {"MetricName": "EpochSeconds", "Dimensions": dims, "Value": record["timing"]["total_s"], "Unit": "Seconds"},
        {"MetricName": "AlarmLevel", "Dimensions": dims,
         "Value": {"QUIET": 0, "MOVING": 1, "ACCELERATING": 2, "CRITICAL": 3}.get(state, 0), "Unit": "None"},
    ]
    if record.get("field"):
        data.append({"MetricName": "Coverage", "Dimensions": dims,
                     "Value": record["field"]["coverage"], "Unit": "None"})
    if record.get("stabilize"):
        data.append({"MetricName": "StabilizeInliers", "Dimensions": dims,
                     "Value": record["stabilize"]["n_inliers"], "Unit": "Count"})
    try:
        cw.put_metric_data(Namespace="TellTale", MetricData=data)
    except Exception as e:  # metrics must never break processing
        log.warning("metrics failed: %s", e)


def handle_manifest(store: S3Store, key: str, cw=None) -> dict | None:
    """key: ingest/<site>/<t>/manifest.json"""
    parts = key.split("/")
    if len(parts) != 4 or parts[0] != "ingest" or parts[3] != "manifest.json":
        log.warning("ignoring key %s", key)
        return None
    site_name, t_str = parts[1], parts[2]
    manifest = json.loads(store.get(key))
    t = float(manifest.get("t", t_str))
    prefix = f"ingest/{site_name}/{t_str}/"
    frames = []
    for name in manifest["frames"]:
        data = store.get(prefix + name)
        if data is None:
            raise RuntimeError(f"missing frame {prefix + name}")
        frames.append(_decode(data))
    record = process_epoch(store, site_name, t, frames, manifest.get("site_config"))
    if cw is not None:
        fc = json.loads(store.get(f"public/sites/{site_name}/forecast.json"))
        _put_metrics(cw, site_name, record, fc["state"])
    return record


def main() -> int:
    import boto3
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)
    bucket = os.environ["TELLTALE_BUCKET"]
    queue = os.environ["TELLTALE_QUEUE_URL"]
    region = os.environ.get("TELLTALE_REGION")
    store = S3Store(bucket, region)
    sqs = boto3.client("sqs", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)
    log.info("worker up: bucket=%s runtime=%s", bucket, json.dumps(runtime_info()))
    while True:
        resp = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=1, WaitTimeSeconds=20,
                                   VisibilityTimeout=600)
        for msg in resp.get("Messages", []):
            body = json.loads(msg["Body"])
            ok = True
            for rec in body.get("Records", []):
                key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
                try:
                    handle_manifest(store, key, cw)
                except Exception:
                    log.exception("epoch failed for %s", key)
                    ok = False
            if ok or body.get("Event") == "s3:TestEvent":
                sqs.delete_message(QueueUrl=queue, ReceiptHandle=msg["ReceiptHandle"])


if __name__ == "__main__":
    sys.exit(main())
