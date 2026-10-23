"""Perception and action tools the supervising agent can call.

Every perception tool re-runs OpenCV 5 code on stored epoch images and returns numbers; every
action tool changes what the system does next (capture cadence, whether a human is paged, how
the event is closed). The agent's decisions are therefore driven by fresh vision output, not by
re-reading the forecast.

Tools are plain functions bound to a store (local folder or S3) through ``Toolbox``. The same
functions are exposed to Claude through the Anthropic SDK tool runner (``supervisor.py``) and
run unchanged under the rule-based policy, so the two arms of E5 call identical code.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import cv2
import numpy as np

from telltale.config import GridConfig, SiteConfig, polygon_mask
from telltale.dic import DisplacementField, compute_field, robust_sigma, zone_displacement
from telltale.stabilize import stabilize
from telltale.stack import sharpness


def _npy(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, a)
    return buf.getvalue()


def _load_npy(raw: bytes | None):
    return None if raw is None else np.load(io.BytesIO(raw))


class Toolbox:
    """Bound tools for one site. ``calls`` records every invocation for the trace."""

    MAX_CALLS = 10

    def __init__(self, store, site_name: str, alerting=None, event_t: float | None = None):
        self.store = store
        self.site = site_name
        self.event_t = event_t  # the investigation's epoch; evidence images are filed under it
        self.pub = f"public/sites/{site_name}"
        self.priv = f"private/sites/{site_name}"
        self.alerting = alerting
        self.calls: list[dict] = []
        cfg = json.loads(store.get(f"{self.pub}/site.json"))
        self.cfg = SiteConfig.from_json_dict(cfg)

    # ------------------------------------------------------------ bookkeeping
    def _record(self, name: str, args: dict, result: dict) -> dict:
        self.calls.append({"n": len(self.calls) + 1, "tool": name, "args": args,
                           "result": result, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        if len(self.calls) > self.MAX_CALLS:
            result = dict(result, budget_exhausted=True,
                          note="tool budget exhausted; close the event now")
        return result

    def _save_evidence(self, img, fld, n: int) -> str | None:
        """Render a measured field over its image, store it beside the trace, return its key
        relative to the site folder (None if rendering or storage fails; evidence is optional)."""
        if self.event_t is None:
            return None
        try:
            from telltale.overlay import render_overlay
            ok, buf = cv2.imencode(".png", render_overlay(img, fld))
            rel = f"agent/{self.event_t:g}/call-{n}.png"
            if ok:
                self.store.put(f"{self.pub}/{rel}", buf.tobytes(), "image/png")
                return rel
        except Exception:
            pass
        return None

    def _series(self) -> list[dict]:
        raw = self.store.get(f"{self.pub}/series.json")
        return json.loads(raw)["records"] if raw else []

    def _snap(self, t: float) -> float:
        """The stored epoch a caller means by ``t``. Models pass rounded times (38.9429 for
        38.942857...), and an unsnapped time would make "previous" resolve to the epoch itself,
        so any value within half the closest epoch spacing maps to that epoch."""
        ts = sorted(r["t"] for r in self._series())
        if not ts:
            return float(t)
        near = min(ts, key=lambda x: abs(x - t))
        gaps = [b - a for a, b in zip(ts, ts[1:]) if b > a]
        tol = 0.5 * min(gaps) if gaps else 1e-3
        return float(near) if abs(near - t) <= tol else float(t)

    def _epoch_image(self, t: float, kind: str = "stabilized"):
        return _load_npy(self.store.get(f"{self.priv}/{kind}/{t:g}.npy"))

    def _reference(self, t: float | None = None):
        """The image the worker compared epoch t against: the site reference in fixed mode, the
        previous epoch's stacked image in chained mode (a months-old reference would be
        decorrelated on a chained site and every re-check would fail for the wrong reason)."""
        if self.cfg.reference_mode == "chained" and t is not None:
            prev = [r["t"] for r in self._series() if r["t"] < t and r.get("reason") not in ("BLIND", "BLURRED")]
            if prev:
                img = self._epoch_image(prev[-1], "stacked")
                if img is not None:
                    return img
        return _load_npy(self.store.get(f"{self.priv}/reference.npy"))

    def _usable_before(self, t: float, n: int = 1) -> list[float]:
        ts = [r["t"] for r in self._series() if r.get("usable") and r["t"] < t and r.get("field")]
        return ts[-n:]

    # ------------------------------------------------------------ perception tools
    def get_site_status(self) -> dict:
        """Current forecast state and the last epochs' quality, as the worker reported them."""
        fc = json.loads(self.store.get(f"{self.pub}/forecast.json") or "{}")
        recs = self._series()[-6:]
        last = []
        for r in recs:
            last.append({"t": r["t"], "usable": r.get("usable"), "reason": r.get("reason"),
                         "state": r.get("state"),
                         "coverage": (r.get("field") or {}).get("coverage"),
                         "stabilize": {k: (r.get("stabilize") or {}).get(k)
                                       for k in ("verdict", "refine_model", "residual", "scatter", "n_inliers")},
                         "zones": {z: ({"increment_px": (None if v.get("increment_u") is None else
                                                          float(np.hypot(v["increment_u"], v["increment_v"]))),
                                        "cumulative_px": v.get("magnitude")}
                                       if self.cfg.reference_mode == "chained" else
                                       {k: v.get(k) for k in ("magnitude", "sigma", "n_valid", "n_total")})
                                   for z, v in (r.get("zones") or {}).items()}})
        zones = {z: {k: v.get(k) for k in ("state", "tf", "t_lo", "t_hi", "r2", "ooa_time", "horizon")}
                 for z, v in fc.get("zones", {}).items()}
        # Baseline of recent daily motion per zone, so the agent can judge materiality: a
        # confirmed step that is not well above this is logged, not paged.
        usable = [r for r in self._series() if r.get("usable") and r.get("zones")][-21:]
        baseline = {}
        for z in self.cfg.target_zones:
            mags = [r["zones"].get(z, {}).get("magnitude") for r in usable]
            mags = [m for m in mags if m is not None]
            if len(mags) >= 5:
                inc = np.abs(np.diff(np.array(mags, dtype=float)))
                baseline[z] = {"median_increment_px": float(np.median(inc)),
                               "p90_increment_px": float(np.percentile(inc, 90)), "n": int(len(inc))}
        out = {"site": self.site, "state": fc.get("state"), "zones": zones, "recent_epochs": last,
               "recent_increment_baseline": baseline,
               "mm_per_px": self.cfg.mm_per_px, "reference_mode": self.cfg.reference_mode,
               "note": ("chained site: each epoch is measured against the previous epoch; increment_px is "
                        "that day's motion and is what remeasure returns; cumulative_px is the running sum "
                        "and is not comparable to a single re-measurement"
                        if self.cfg.reference_mode == "chained" else
                        "fixed site: magnitudes are displacement since the site reference")}
        return self._record("get_site_status", {}, out)

    def remeasure(self, t: float, reference: str = "previous") -> dict:
        """Re-run dense sub-pixel DIC for epoch t against an alternate reference and return
        each zone's displacement. reference: "previous" (the last usable epoch, gives the
        increment since then), "reference" (the site reference), or "t=<value>" (a specific
        earlier usable epoch). Real ground motion is consistent across references; an artefact
        tied to one reference is not."""
        t = self._snap(t)
        cur = self._epoch_image(t)
        if cur is None:
            return self._record("remeasure", {"t": t, "reference": reference},
                                {"error": f"no stored image for epoch {t:g}"})
        if reference == "reference":
            ref, ref_t = self._reference(t), None
        elif reference.startswith("t="):
            ref_t = self._snap(float(reference[2:]))
            ref = self._epoch_image(ref_t)
        else:
            prev = self._usable_before(t, 1)
            ref_t = prev[0] if prev else None
            kind = "stacked" if self.cfg.reference_mode == "chained" else "stabilized"
            ref = self._epoch_image(ref_t, kind) if ref_t is not None else None
        stab_note = None
        if self.cfg.reference_mode == "chained":
            # Chained increments are measured exactly as the worker measures them: the raw
            # stacked image of epoch t is stabilised against the chosen reference image first,
            # so camera motion on either day is removed before the dense correlation.
            cur = self._epoch_image(t, "stacked")
            if ref is not None and cur is not None:
                mask = polygon_mask(ref.shape, self.cfg.stable_polys) if self.cfg.stable_polys else None
                st = stabilize(ref, cur, mask)
                if st.verdict != "OK":
                    return self._record("remeasure", {"t": t, "reference": reference},
                                        {"error": f"stabilization against this reference failed: {st.verdict}",
                                         "reference_t": ref_t, "residual_px": list(st.residual), "scatter_px": st.scatter})
                cur = st.image
                stab_note = {"camera_model": st.diag.get("refine_model"), "residual_px": list(st.residual),
                             "scatter_px": st.scatter}
        if ref is None or cur is None:
            return self._record("remeasure", {"t": t, "reference": reference},
                                {"error": "reference image unavailable"})
        grid = self.cfg.grid
        fld = compute_field(ref, cur, grid)
        zones = {}
        for name, poly in self.cfg.target_zones.items():
            zm = zone_displacement(fld, name, poly)
            zones[name] = {"u": zm.u, "v": zm.v, "magnitude": zm.magnitude, "sigma": zm.sigma,
                           "n_valid": zm.n_valid, "n_total": zm.n_total,
                           "coherence": _coherence(fld, poly)}
        out = {"t": t, "reference": reference, "reference_t": ref_t, "coverage": fld.coverage,
               "review": fld.review, "zones": _clean(zones)}
        if stab_note:
            out["stabilization"] = _clean(stab_note)
        # The field this call measured, as the picture a reviewer reads: the dashboard shows it
        # in the investigation, so the visual evidence behind each verdict is on screen.
        out["evidence_png"] = self._save_evidence(cur, fld, len(self.calls) + 1)
        # Compare with what the worker recorded for the same epoch
        rec = next((r for r in self._series() if r["t"] == t), None)
        if rec and rec.get("zones") and reference in ("reference", "previous"):
            if self.cfg.reference_mode == "chained":
                out["worker_recorded_increment"] = {z: (None if rec["zones"][z].get("increment_u") is None else
                                                        float(np.hypot(rec["zones"][z]["increment_u"], rec["zones"][z]["increment_v"])))
                                                    for z in rec["zones"]}
            else:
                out["worker_recorded"] = {z: rec["zones"][z].get("magnitude") for z in rec["zones"]}
        return self._record("remeasure", {"t": t, "reference": reference}, out)

    def check_stabilization(self, t: float) -> dict:
        """Re-run camera-motion estimation for epoch t from the stacked (unwarped) image and
        measure what the stable ground did after the warp. Residual or scatter above 0.3 px
        means the camera model does not explain the stable regions: suspect the camera, not
        the slope. mount_moved only says the camera pose differed from the reference and was
        corrected; a corrected pose with a small residual and scatter is a clean measurement,
        not evidence against ground motion."""
        t = self._snap(t)
        stacked = self._epoch_image(t, "stacked")
        ref = self._reference(t)
        if stacked is None or ref is None:
            return self._record("check_stabilization", {"t": t}, {"error": "images unavailable"})
        mask = polygon_mask(ref.shape, self.cfg.stable_polys) if self.cfg.stable_polys else None
        st = stabilize(ref, stacked, mask, verify_grid=GridConfig(template=41, stride=16, search=3))
        d = st.to_dict()
        out = {"t": t, "verdict": st.verdict, "camera_model": d.get("refine_model"),
               "coarse_method": d.get("coarse"), "n_inliers": st.n_inliers,
               "residual_px": list(st.residual), "scatter_px": st.scatter,
               "translation_px": list(st.translation), "rotation_deg": st.rotation_deg,
               "scale": st.scale, "mount_moved": st.mount_moved}
        return self._record("check_stabilization", {"t": t}, _clean(out))

    def inspect_quality(self, t: float) -> dict:
        """Image and matching quality for epoch t: sharpness, contrast, subset status counts,
        the phase-correlation cross-check, and burst stability."""
        t = self._snap(t)
        rec = next((r for r in self._series() if r["t"] == t), None)
        img = self._epoch_image(t)
        out = {"t": t}
        if img is not None:
            out["sharpness"] = sharpness(img)
            out["contrast"] = float(img.std())
        if rec:
            out["stack"] = rec.get("stack")
            out["field"] = rec.get("field")
            out["reason"] = rec.get("reason")
        return self._record("inspect_quality", {"t": t}, _clean(out))

    def motion_coherence(self, t: float) -> dict:
        """Direction coherence of the stored displacement field for epoch t per zone: the share
        of valid subsets moving within 45 degrees of the zone's median direction. Creep is
        coherent (above about 0.7); vegetation flutter, shadows and noise are not."""
        t = self._snap(t)
        raw = self.store.get(f"{self.pub}/epochs/{t:g}/field.npz")
        if raw is None:
            return self._record("motion_coherence", {"t": t}, {"error": "no field stored"})
        fld = DisplacementField.load(io.BytesIO(raw))
        zones = {name: _coherence(fld, poly, full=True) for name, poly in self.cfg.target_zones.items()}
        return self._record("motion_coherence", {"t": t}, _clean({"t": t, "zones": zones}))

    # ------------------------------------------------------------ action tools
    def set_capture_cadence(self, epochs_per_day: int, reason: str) -> dict:
        """Change how often the camera captures. Raising cadence after a confirmed acceleration
        tightens the forecast; lowering it saves power on a quiet site. Written to the site's
        control file, which the capture client polls."""
        epochs_per_day = int(max(1, min(144, epochs_per_day)))
        ctrl = {"epochs_per_day": epochs_per_day, "reason": reason,
                "set_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "by": "agent"}
        self.store.put(f"{self.pub}/control.json", json.dumps(ctrl, indent=1).encode(), "application/json")
        return self._record("set_capture_cadence", {"epochs_per_day": epochs_per_day, "reason": reason}, ctrl)

    def request_human_approval(self, t: float, summary: str) -> dict:
        """Page the duty contact with the evidence summary and signed approve / dismiss links.
        Use only when the acceleration is real or cannot be ruled out. The agent can never send
        a public alert itself."""
        t = self._snap(t)
        links = self.alerting.links(self.site, t) if self.alerting else {}
        msg = (f"TellTale site {self.site}, epoch t={t:g}.\nAgent investigation summary:\n{summary}\n\n"
               f"APPROVE: {links.get('approve', 'n/a')}\nDISMISS: {links.get('dismiss', 'n/a')}\n")
        if self.alerting:
            self.alerting.publish(f"TellTale CRITICAL (agent-verified): {self.site}", msg)
        out = {"t": t, "paged": bool(self.alerting and self.alerting.topic), "links_issued": bool(links)}
        return self._record("request_human_approval", {"t": t, "summary": summary}, out)

    def close_event(self, t: float, verdict: str, reason: str) -> dict:
        """Close the investigation. verdict: CONFIRMED (real ground motion), FALSE_ALARM
        (artefact: camera, lighting, vegetation, blur), or INCONCLUSIVE (could not rule out)."""
        t = self._snap(t)
        verdict = verdict.upper()
        if verdict not in ("CONFIRMED", "FALSE_ALARM", "INCONCLUSIVE"):
            verdict = "INCONCLUSIVE"
        out = {"t": t, "verdict": verdict, "reason": reason}
        return self._record("close_event", {"t": t, "verdict": verdict, "reason": reason}, out)


def _coherence(fld: DisplacementField, poly: list, full: bool = False):
    m = polygon_mask(fld.shape, [poly])
    sel = (m[fld.ys, fld.xs] > 0) & fld.valid
    if sel.sum() < 5:
        return None if not full else {"coherence": None, "n": int(sel.sum())}
    u, v = fld.u[sel], fld.v[sel]
    mag = np.hypot(u, v)
    moving = mag > max(0.05, 2 * robust_sigma(mag))
    if moving.sum() < 5:
        res = {"coherence": None, "n": int(sel.sum()), "n_moving": int(moving.sum()),
               "note": "too few subsets above the noise floor to judge direction"}
        return res if full else None
    ang = np.arctan2(v[moving], u[moving])
    med = np.arctan2(np.median(np.sin(ang)), np.median(np.cos(ang)))
    d = np.abs((ang - med + np.pi) % (2 * np.pi) - np.pi)
    coh = float((d < np.pi / 4).mean())
    if not full:
        return coh
    return {"coherence": coh, "n": int(sel.sum()), "n_moving": int(moving.sum()),
            "median_direction_deg": float(np.degrees(med)), "median_magnitude_px": float(np.median(mag[moving]))}


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x
