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
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root, for `agent`

from telltale import (ForecastConfig, SiteConfig, compute_field, compute_field_pyramid, forecast, polygon_mask,
                      stabilize, stack_burst, zone_displacement)
from telltale.forecast import moving_average, smoothed_velocities
from telltale.masking import variance_mask
from telltale.overlay import render_overlay, render_status_map
from telltale.scale import PlaneScale
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
    if site_config is not None:
        # a manifest that carries a site config sets it: the first epoch of a site, or an
        # operator re-sending a corrected setup.html export
        store.put(f"{pub}/site.json", _json(site_config), "application/json")
        raw = _json(site_config)
    elif raw is None:
        raise RuntimeError(f"no site.json for {site_name} and manifest carried none")
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
    # Keep the stacked epoch so the supervising agent can re-run stabilization and DIC later.
    store.put(f"{priv}/stacked/{t:g}.npy", _npy(stack.image))


    chained = site.reference_mode == "chained"
    ref_key = f"{priv}/previous.npy" if chained else f"{priv}/reference.npy"
    ref_raw = store.get(ref_key)
    if ref_raw is None:
        store.put(f"{priv}/reference.npy", _npy(stack.image))
        if chained:
            store.put(f"{priv}/previous.npy", _npy(stack.image))
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

    if chained:
        # Chained mode advances the comparison image every non-blind epoch, usable or not, so
        # one bad day cannot strand the chain on a stale image. The motion during an unusable
        # epoch is not measured; the next usable increment is relative to that epoch's image
        # and the record carries chain_gap so the series is honest about it.
        prev_rec = None
        raw_series = store.get(f"{pub}/series.json")
        if raw_series:
            recs = json.loads(raw_series)["records"]
            prev_rec = recs[-1] if recs else None
        record["chain_gap"] = bool(prev_rec and not prev_rec.get("usable"))
        store.put(f"{priv}/previous.npy", _npy(stack.image))

    stable_mask = polygon_mask(ref.shape, site.stable_polys) if site.stable_polys else None
    st_t = time.perf_counter()
    st = stabilize(ref, stack.image, stable_mask)
    record["timing"]["stabilize_s"] = time.perf_counter() - st_t
    record["stabilize"] = st.to_dict()
    if st.verdict != VERDICT_OK:
        record["reason"] = st.verdict
        return _finish(store, site, site_name, record, None, t0)
    store.put(f"{priv}/stabilized/{t:g}.npy", _npy(st.image))

    grid_mask = None
    if site.mask_window > 0:
        recent = _recent_epochs(store, priv, site.mask_window)
        if len(recent) >= 2:
            grid_mask = variance_mask(recent + [st.image])
            record["mask"] = {"window": len(recent) + 1,
                              "excluded_frac": float(1.0 - (grid_mask > 0).mean())}
    st_t = time.perf_counter()
    fld = compute_field_pyramid(ref, st.image, site.grid, mask=grid_mask)
    record["timing"]["dic_s"] = time.perf_counter() - st_t
    if site.mask_window > 0:
        _push_recent(store, priv, t, st.image, site.mask_window)
    record["field"] = {"n_subsets": int(len(fld.xs)), "n_valid": fld.n_valid,
                       "coverage": fld.coverage, "status_counts": fld.status_counts(),
                       "crosscheck_px": fld.crosscheck_px, "review": fld.review}
    record["usable"] = not fld.review
    record["reason"] = "REVIEW" if fld.review else "OK"

    prev_zones = {}
    if chained:
        raw_series = store.get(f"{pub}/series.json")
        if raw_series:
            for r in reversed(json.loads(raw_series)["records"]):
                if r.get("usable") and r.get("zones"):
                    prev_zones = r["zones"]
                    break
    zones = {}
    plane = None
    try:
        plane = PlaneScale.from_dict(site.plane)
    except Exception as e:
        log.warning("plane scale invalid: %s", e)
    for name, poly in site.target_zones.items():
        zm = zone_displacement(fld, name, poly)
        zd = zm.to_dict()
        if plane is not None and zm.n_valid >= 3:
            m = polygon_mask(fld.shape, [poly])
            sel = (m[fld.ys, fld.xs] > 0) & fld.valid
            dmm = plane.displacement_mm(fld.xs[sel], fld.ys[sel], fld.u[sel], fld.v[sel])
            zd["mm_plane"] = float(np.median(np.hypot(dmm[:, 0], dmm[:, 1])))
            zd["mm_per_px_local"] = plane.mm_per_px_at(float(np.median(fld.xs[sel])), float(np.median(fld.ys[sel])))
        if chained:
            pz = prev_zones.get(name, {})
            zd["increment_u"], zd["increment_v"] = zd["u"], zd["v"]
            if zd["u"] is not None and np.isfinite(zd["u"]):
                zd["u"] = (pz.get("u") or 0.0) + zd["u"]
                zd["v"] = (pz.get("v") or 0.0) + zd["v"]
                zd["magnitude"] = float(np.hypot(zd["u"], zd["v"]))
                # chained uncertainty grows as a random walk of per-step sigmas
                zd["sigma"] = float(np.hypot(pz.get("sigma") or 0.0, zd["sigma"]))
        scale_here = zd.get("mm_per_px_local") or site.mm_per_px
        zd["mm"] = zd.get("mm_plane") if zd.get("mm_plane") is not None else (zd["magnitude"] or 0.0) * scale_here
        zd["sigma_mm"] = (zd["sigma"] or 0.0) * scale_here
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


def _recent_epochs(store, priv: str, window: int) -> list[np.ndarray]:
    keys = sorted(k for k in store.list(f"{priv}/recent/") if k.endswith(".npy"))[-window:]
    out = []
    for k in keys:
        raw = store.get(k)
        if raw is not None:
            out.append(np.load(io.BytesIO(raw)))
    return out


def _push_recent(store, priv: str, t: float, img: np.ndarray, window: int) -> None:
    store.put(f"{priv}/recent/{t:012.3f}.npy", _npy(img))
    keys = sorted(k for k in store.list(f"{priv}/recent/") if k.endswith(".npy"))
    for k in keys[:-window]:
        try:
            if hasattr(store, "s3"):
                store.s3.delete_object(Bucket=store.bucket, Key=k)
            else:
                (store.root / k).unlink(missing_ok=True)
        except Exception as e:
            log.warning("could not prune %s: %s", k, e)


# ------------------------------------------------------------------ human control
class Alerting:
    """Signed approve / dismiss links and SNS publication. Inert when not configured, so the
    local store path and the tests run without AWS."""

    def __init__(self):
        self.topic = os.environ.get("TELLTALE_ALERT_TOPIC") or None
        self.url = (os.environ.get("TELLTALE_APPROVAL_URL") or "").rstrip("/") or None
        self.dashboard = (os.environ.get("TELLTALE_DASHBOARD_URL") or "").rstrip("/") or None
        self.secret = os.environ.get("TELLTALE_APPROVAL_SECRET") or None
        arn = os.environ.get("TELLTALE_SECRET_ARN")
        param = os.environ.get("TELLTALE_SECRET_PARAM")      # older stacks kept it in SSM
        if self.secret is None and (arn or param):
            try:
                import boto3
                region = os.environ.get("TELLTALE_REGION")
                if arn:
                    sm = boto3.client("secretsmanager", region_name=region)
                    self.secret = sm.get_secret_value(SecretId=arn)["SecretString"]
                else:
                    ssm = boto3.client("ssm", region_name=region)
                    self.secret = ssm.get_parameter(Name=param)["Parameter"]["Value"]
            except Exception as e:
                log.warning("approval secret unavailable: %s", e)
        self._sns = None

    def sign(self, site: str, t: float, action: str) -> str:
        import hmac
        return hmac.new(self.secret.encode(), f"{site}|{t}|{action}".encode(),
                        hashlib.sha256).hexdigest()[:32]

    def links(self, site: str, t: float) -> dict:
        if not (self.url and self.secret):
            return {}
        ts = f"{t:g}"
        out = {a: f"{self.url}/?site={site}&t={ts}&action={a}&token={self.sign(site, ts, a)}"
               for a in ("approve", "dismiss")}
        if self.dashboard:
            # the investigation itself, with the fields the agent re-measured, one click away
            out["evidence"] = f"{self.dashboard}/?site={site}&event={ts}"
        return out

    def publish(self, subject: str, message: str) -> None:
        if not self.topic:
            return
        try:
            import boto3
            self._sns = self._sns or boto3.client("sns", region_name=os.environ.get("TELLTALE_REGION"))
            self._sns.publish(TopicArn=self.topic, Subject=subject[:99], Message=message)
        except Exception as e:
            log.warning("sns publish failed: %s", e)


_ALERTING: Alerting | None = None


def alerting() -> Alerting:
    global _ALERTING
    if _ALERTING is None:
        _ALERTING = Alerting()
    return _ALERTING


def approval_status(store, site_name: str, records: list[dict], overall: str) -> dict:
    """Human-control state for the current CRITICAL episode (contiguous trailing run)."""
    if overall != "CRITICAL":
        return {"required": False, "status": "none"}
    episode_start = records[-1]["t"]
    for r in reversed(records):
        if r.get("state") == "CRITICAL":
            episode_start = r["t"]
        else:
            break
    raw = store.get(f"public/sites/{site_name}/decisions.json")
    decisions = json.loads(raw)["decisions"] if raw else []
    applicable = [d for d in decisions if d["t"] >= episode_start]
    out = {"required": True, "episode_start": episode_start, "epoch_t": records[-1]["t"]}
    if applicable:
        last = max(applicable, key=lambda d: d["at"])
        out.update(status="approved" if last["action"] == "approve" else "dismissed",
                   decided_at=last["at"], decided_t=last["t"])
    else:
        out.update(status="pending", links=alerting().links(site_name, records[-1]["t"]))
    return out


def _jump_detected(records: list[dict], record: dict, site: SiteConfig, k: float = 4.0, window: int = 20) -> bool:
    """A single-epoch displacement step well outside the recent increments (a short event the
    acceleration ladder is not built for; on the Mukilteo record this is what catches the
    documented two-day movements). Causal and robust: median + k x MAD of the last ``window``
    increments, with a floor at the forecast noise floor."""
    if not record.get("usable") or not record.get("zones"):
        return False
    usable = [r for r in records if r.get("usable") and r.get("zones") and r["t"] < record["t"]]
    if len(usable) < 7:
        return False
    for name, z in record["zones"].items():
        mags = [r["zones"].get(name, {}).get("magnitude") for r in usable[-(window + 1):]]
        mags = [m for m in mags if m is not None]
        if len(mags) < 7 or z.get("magnitude") is None:
            continue
        incs = np.abs(np.diff(np.array(mags, dtype=float)))
        inc_now = abs(float(z["magnitude"]) - float(mags[-1]))
        med = float(np.median(incs))
        sig = 1.4826 * float(np.median(np.abs(incs - med)))
        if inc_now > med + k * max(sig, site.forecast.noise_floor / 4):
            return True
    return False


def _finish(store, site: SiteConfig, site_name: str, record: dict, fld, t0: float) -> dict:
    pub = f"public/sites/{site_name}"
    record["timing"]["total_s"] = time.perf_counter() - t0
    record = _clean(record)

    raw = store.get(f"{pub}/series.json")
    series = json.loads(raw) if raw else {"records": []}
    # A replay (SQS re-delivery of an epoch already recorded) or a late epoch (older than the
    # newest one) changes the record but must not re-announce a transition the site already
    # went through: the state "before" is the site's current state, and no event is raised.
    existing_t = [r["t"] for r in series["records"]]
    replay = record["t"] in existing_t or (bool(existing_t) and record["t"] < max(existing_t))
    if replay:
        newest = max(series["records"], key=lambda r: r["t"])
        prev_state = newest.get("state", "QUIET")
    else:
        prev_state = series["records"][-1].get("state", "QUIET") if series["records"] else "QUIET"

    fcs, overall = {}, "QUIET"
    rank = {"QUIET": 0, "MOVING": 1, "ACCELERATING": 2, "CRITICAL": 3}
    series["records"] = [r for r in series["records"] if r["t"] != record["t"]] + [record]
    series["records"].sort(key=lambda r: r["t"])
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
    if replay and record["t"] < max(existing_t):
        # a late epoch: its own state is the one that held when it was taken, not today's
        older = [r for r in series["records"] if r["t"] < record["t"]]
        record["state"] = older[-1].get("state", "QUIET") if older else "QUIET"
    else:
        record["state"] = overall
    store.put(f"{pub}/epochs/{record['t']:g}/record.json", _json(record), "application/json")
    store.put(f"{pub}/series.json", _json(series), "application/json")

    approval = approval_status(store, site_name, series["records"], overall)
    payload = {"site": site_name, "state": overall, "state_display": overall_display,
               "updated_t": series["records"][-1]["t"], "n_epochs": len(series["records"]),
               "n_unusable": n_unusable, "zones": fcs, "runtime": record["runtime"],
               "mm_per_px": site.mm_per_px, "approval": approval}
    store.put(f"{pub}/forecast.json", _json(payload), "application/json")
    # Snapshot of the forecast as it stood after this epoch, for the dashboard's replay scrubber.
    store.put(f"{pub}/epochs/{record['t']:g}/forecast.json", _json(payload), "application/json")

    # ---- supervising agent: investigates events; may page a human, never alerts the public
    agent_mode = os.environ.get("TELLTALE_AGENT", "llm" if hasattr(store, "s3") else "rules").lower()
    trace = None
    event = None
    if agent_mode != "off" and not replay:
        from agent.supervisor import _event_from, investigate
        prev_recs = [r for r in series["records"] if r["t"] < record["t"]]
        prev_reason = prev_recs[-1].get("reason") if prev_recs else None
        if prev_recs and (prev_recs[-1].get("field") or {}).get("coverage", 1.0) < 0.4:
            prev_reason = "LOW_COVERAGE"
        jump = _jump_detected(series["records"], record, site)
        record["jump"] = jump
        event = _event_from(record, prev_state, overall, prev_reason, jump=jump)
        if event:
            trace = investigate(store, site_name, record["t"], event, alerting(),
                                use_llm=(agent_mode == "llm"))
            payload["agent"] = {"t": record["t"], "event": event, "policy": trace["policy"],
                                "verdict": trace["verdict"], "paged_human": trace["paged_human"],
                                "n_tool_calls": trace["n_tool_calls"], "summary": trace["summary"]}
            store.put(f"{pub}/forecast.json", _json(payload), "application/json")

    entered_critical = overall == "CRITICAL" and prev_state != "CRITICAL" and not replay
    agent_handled = trace is not None and trace["verdict"] in ("CONFIRMED", "FALSE_ALARM")
    if entered_critical and not agent_handled:
        # Safety net: no agent, agent disabled, or agent inconclusive -> a person is paged.
        z = max(fcs.values(), key=lambda f: f.get("horizon") if f.get("horizon") is not None else 1e9, default={})
        links = approval.get("links", {})
        msg = (f"TellTale site {site_name} entered CRITICAL at epoch t={record['t']:g}.\n"
               f"Forecast failure window: t = {z.get('t_lo')} to {z.get('t_hi')} (median {z.get('tf')}), "
               f"R2 {z.get('r2')}.\n"
               + (f"Agent verdict: {trace['verdict']} ({trace['summary'][:300]})\n" if trace else "")
               + (f"Dashboard: {links['evidence'].split('&event=')[0]}\n" if links.get("evidence") else "")
               + f"\nNo public alert is sent automatically. Decide:\n"
               f"APPROVE: {links.get('approve', 'approval link not configured')}\n"
               f"DISMISS: {links.get('dismiss', 'approval link not configured')}\n")
        alerting().publish(f"TellTale CRITICAL: {site_name}", msg)
        log.info("CRITICAL transition for %s; alert published=%s", site_name, bool(alerting().topic))
    elif overall != "CRITICAL" and prev_state == "CRITICAL" and not replay:
        alerting().publish(f"TellTale {site_name}: left CRITICAL",
                           f"Site {site_name} is now {overall} at epoch t={record['t']:g}.")

    raw = store.get("public/sites/index.json")
    index = json.loads(raw) if raw else []
    index = [s for s in index if s["site"] != site_name]
    index.append({"site": site_name, "state": overall, "last_t": series["records"][-1]["t"],
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


class CloudWatchLogHandler(logging.Handler):
    """Ships worker log lines to CloudWatch Logs (/telltale/worker) so the operator never has
    to open a shell on the instance to see what the monitor is doing."""

    def __init__(self, group: str, stream: str, region: str | None):
        super().__init__()
        import boto3
        self.logs = boto3.client("logs", region_name=region)
        self.group, self.stream = group, stream
        try:
            self.logs.create_log_stream(logGroupName=group, logStreamName=stream)
        except Exception:
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.logs.put_log_events(logGroupName=self.group, logStreamName=self.stream,
                                     logEvents=[{"timestamp": int(record.created * 1000),
                                                 "message": self.format(record)}])
        except Exception:
            pass  # logging must never break processing


def queue_empty(sqs, queue: str) -> bool:
    a = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=[
        "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
    return int(a["ApproximateNumberOfMessages"]) == 0 and int(a["ApproximateNumberOfMessagesNotVisible"]) == 0


def _message_epoch(msg: dict) -> tuple:
    """(site, t) of an S3-notification message, for ordering; unknown shapes sort first."""
    try:
        key = urllib.parse.unquote_plus(json.loads(msg["Body"])["Records"][0]["s3"]["object"]["key"])
        _, site_name, t_str, _ = key.split("/")
        return (site_name, float(t_str))
    except Exception:
        return ("", float("-inf"))


def drain_in_order(sqs, queue: str, msgs: list, limit: int = 600) -> list:
    """Take every message already waiting (up to ``limit``, ten minutes of epochs at the
    measured rate) and return them in epoch order.

    The queue is SQS standard, which does not keep order, and S3 notifications cannot target a
    FIFO queue. A backlog (the worker was stopped, or the camera uploaded after an outage)
    would otherwise be processed shuffled: an early epoch could become the site reference, and
    each epoch's forecast, state change and agent event would be computed against an
    incomplete record. The visibility timeout is raised to cover the whole batch.
    """
    while len(msgs) < limit:
        more = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=10, WaitTimeSeconds=1,
                                   VisibilityTimeout=600)
        if not more.get("Messages"):
            break
        msgs.extend(more["Messages"])
    if len(msgs) > 1:
        hold = min(43200, 600 + 60 * len(msgs))
        for m in msgs:
            try:
                sqs.change_message_visibility(QueueUrl=queue, ReceiptHandle=m["ReceiptHandle"],
                                              VisibilityTimeout=hold)
            except Exception:
                pass
        log.info("drained %d waiting epochs; processing them in time order", len(msgs))
    return sorted(msgs, key=_message_epoch)


def main() -> int:
    import boto3
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)
    bucket = os.environ["TELLTALE_BUCKET"]
    queue = os.environ["TELLTALE_QUEUE_URL"]
    region = os.environ.get("TELLTALE_REGION")
    try:
        h = CloudWatchLogHandler("/telltale/worker", runtime_info().get("instance_id") or "local", region)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(h)
    except Exception as e:
        log.warning("CloudWatch Logs unavailable: %s", e)
    store = S3Store(bucket, region)
    sqs = boto3.client("sqs", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)
    log.info("worker up: bucket=%s runtime=%s", bucket, json.dumps(runtime_info()))
    idle_stop = float(os.environ.get("TELLTALE_IDLE_STOP_MIN") or 0) * 60
    last_work = time.monotonic()
    while True:
        resp = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=10, WaitTimeSeconds=20,
                                   VisibilityTimeout=600)
        if resp.get("Messages"):
            last_work = time.monotonic()
            resp["Messages"] = drain_in_order(sqs, queue, resp["Messages"])
        elif idle_stop and time.monotonic() - last_work > idle_stop and queue_empty(sqs, queue):
            # Scale to zero: the instance's shutdown behaviour is "stop", and the stack's wake
            # function starts it again when epochs are waiting.
            log.info("idle for %.0f min with an empty queue; stopping the instance", idle_stop / 60)
            subprocess.run(["shutdown", "-h", "now"], check=False)
            return 0
        for msg in resp.get("Messages", []):
            # One bad message must not stall the batch behind it: every step is guarded, and a
            # failed epoch is made visible again in a minute (three failures send it to the DLQ).
            ok = True
            try:
                body = json.loads(msg["Body"])
                for rec in body.get("Records", []):
                    key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
                    try:
                        handle_manifest(store, key, cw)
                    except Exception:
                        log.exception("epoch failed for %s", key)
                        ok = False
                if ok or body.get("Event") == "s3:TestEvent":
                    sqs.delete_message(QueueUrl=queue, ReceiptHandle=msg["ReceiptHandle"])
            except Exception:
                log.exception("message could not be handled")
                ok = False
            if not ok:
                try:
                    sqs.change_message_visibility(QueueUrl=queue, ReceiptHandle=msg["ReceiptHandle"],
                                                  VisibilityTimeout=60)
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(main())
