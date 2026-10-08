"""Stage E: physics and forecasting.

Implements the operational inverse-velocity protocol of Carla, Intrieri et al., Landslides
14:517-534 (2017): velocity is smoothed with a short and a long moving average, onset of
acceleration (OOA) is declared when the short average stays above the long one, and from OOA
onward 1/v is regressed against time (Fukuzono 1985, alpha = 2). The time-axis intercept is the
forecast failure time. Three estimators form an ensemble (weighted linear, Theil-Sen, and a
Voight fit with alpha free in a grid); the reported window combines residual bootstrap of the
linear fit with ensemble disagreement. The result is never a bare timestamp.

Alarm ladder: QUIET -> MOVING -> ACCELERATING -> CRITICAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import ForecastConfig

STATE_QUIET = "QUIET"
STATE_MOVING = "MOVING"
STATE_ACCELERATING = "ACCELERATING"
STATE_CRITICAL = "CRITICAL"


def moving_average(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing (causal) moving average; partial windows at the start use what exists."""
    x = np.asarray(x, dtype=np.float64)
    if window <= 1 or len(x) == 0:
        return x.copy()
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.empty_like(x)
    for i in range(len(x)):
        lo = max(0, i + 1 - window)
        out[i] = (c[i + 1] - c[lo]) / (i + 1 - lo)
    return out


def velocity(times: np.ndarray, disp: np.ndarray) -> np.ndarray:
    times = np.asarray(times, dtype=np.float64)
    disp = np.asarray(disp, dtype=np.float64)
    if len(times) < 2:
        return np.zeros_like(disp)
    return np.gradient(disp, times)


def smoothed_velocities(times, disp, cfg: ForecastConfig) -> tuple[np.ndarray, np.ndarray]:
    v = velocity(times, disp)
    return moving_average(v, cfg.sma_window), moving_average(v, cfg.lma_window)


def detect_ooa(times, disp, cfg: ForecastConfig) -> int | None:
    """Index of the first epoch of a run of ``ooa_k`` epochs with SMA > LMA and acceleration > 0."""
    times = np.asarray(times, dtype=np.float64)
    disp = np.asarray(disp, dtype=np.float64)
    if len(times) < max(cfg.ooa_k, 2):
        return None
    sma, lma = smoothed_velocities(times, disp, cfg)
    acc = np.gradient(sma, times) if len(times) > 1 else np.zeros_like(sma)
    moving = (disp - disp[0]) > cfg.noise_floor
    cond = (sma > lma) & (acc > 0) & moving
    run = 0
    for i, ok in enumerate(cond):
        run = run + 1 if ok else 0
        if run >= cfg.ooa_k:
            return i - cfg.ooa_k + 1
    return None


def _wls(t: np.ndarray, y: np.ndarray, w: np.ndarray | None = None):
    """Weighted least squares line y = slope t + intercept; returns slope, intercept, r2."""
    if w is None:
        w = np.ones_like(t)
    w = w / w.sum()
    tm, ym = np.sum(w * t), np.sum(w * y)
    stt = np.sum(w * (t - tm) ** 2)
    if stt <= 0:
        return None
    slope = np.sum(w * (t - tm) * (y - ym)) / stt
    intercept = ym - slope * tm
    fit = slope * t + intercept
    ss_res = np.sum(w * (y - fit) ** 2)
    ss_tot = np.sum(w * (y - ym) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(intercept), float(r2)


def fit_linear_iv(t: np.ndarray, v: np.ndarray, sigma_v: np.ndarray | None = None):
    """Fukuzono alpha = 2: 1/v linear in t, failure at the t-axis intercept."""
    y = 1.0 / v
    w = None
    if sigma_v is not None:
        var_y = (sigma_v / v ** 2) ** 2
        w = 1.0 / np.maximum(var_y, 1e-12)
    res = _wls(t, y, w)
    if res is None:
        return None
    slope, intercept, r2 = res
    if slope >= 0:
        return None
    return {"tf": -intercept / slope, "slope": slope, "intercept": intercept, "r2": r2}


def fit_theil_sen_iv(t: np.ndarray, v: np.ndarray):
    y = 1.0 / v
    n = len(t)
    if n < 2:
        return None
    i, j = np.triu_indices(n, k=1)
    dt = t[j] - t[i]
    ok = dt > 0
    if not ok.any():
        return None
    slopes = (y[j] - y[i])[ok] / dt[ok]
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * t))
    if slope >= 0:
        return None
    fit = slope * t + intercept
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = float(1.0 - np.sum((y - fit) ** 2) / ss_tot) if ss_tot > 0 else 0.0
    return {"tf": -intercept / slope, "slope": slope, "intercept": intercept, "r2": r2}


def fit_voight_iv(t: np.ndarray, v: np.ndarray, alpha_grid=(1.5, 2.2, 0.05)):
    """Voight / Fukuzono general alpha: v^-(alpha-1) linear in t; best alpha by r2."""
    lo, hi, step = alpha_grid
    best = None
    for alpha in np.arange(lo, hi + 1e-9, step):
        y = v ** (-(alpha - 1.0))
        res = _wls(t, y, None)
        if res is None:
            continue
        slope, intercept, r2 = res
        if slope >= 0:
            continue
        cand = {"tf": -intercept / slope, "slope": slope, "intercept": intercept,
                "r2": r2, "alpha": float(alpha)}
        if best is None or r2 > best["r2"]:
            best = cand
    return best


def bootstrap_window(t: np.ndarray, v: np.ndarray, lin: dict, n_draws: int,
                     rng: np.random.Generator, q=(10, 90)) -> tuple[float, float]:
    """Residual bootstrap of the linear 1/v fit; returns the (q_lo, q_hi) failure-time window."""
    y = 1.0 / v
    fit = lin["slope"] * t + lin["intercept"]
    resid = y - fit
    n = len(t)
    if n < 3 or n_draws <= 0:
        return (lin["tf"], lin["tf"])
    draws = fit[None, :] + resid[rng.integers(0, n, size=(n_draws, n))]
    tm = t.mean()
    stt = np.sum((t - tm) ** 2)
    slopes = ((t - tm)[None, :] * (draws - draws.mean(axis=1, keepdims=True))).sum(axis=1) / stt
    intercepts = draws.mean(axis=1) - slopes * tm
    ok = slopes < 0
    if ok.sum() < 10:
        return (lin["tf"], lin["tf"])
    tfs = -intercepts[ok] / slopes[ok]
    lo, hi = np.percentile(tfs, q)
    return (float(lo), float(hi))


@dataclass
class ForecastResult:
    state: str
    t_now: float
    n_points: int
    ooa_index: int | None = None
    ooa_time: float | None = None
    tf: float | None = None
    t_lo: float | None = None
    t_hi: float | None = None
    r2: float | None = None
    n_fit: int = 0
    horizon: float | None = None
    methods: dict = field(default_factory=dict)
    v_sma: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_lma: np.ndarray = field(default_factory=lambda: np.zeros(0))
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "state": self.state, "t_now": self.t_now, "n_points": self.n_points,
            "ooa_index": self.ooa_index, "ooa_time": self.ooa_time, "tf": self.tf,
            "t_lo": self.t_lo, "t_hi": self.t_hi, "r2": self.r2, "n_fit": self.n_fit,
            "horizon": self.horizon, "methods": self.methods, "note": self.note,
        }


def forecast(times, disp, cfg: ForecastConfig | None = None, sigma=None,
             seed: int = 0) -> ForecastResult:
    """Full forecast from a displacement series (any consistent units of time and length)."""
    cfg = cfg or ForecastConfig()
    times = np.asarray(times, dtype=np.float64)
    disp = np.asarray(disp, dtype=np.float64)
    n = len(times)
    if n == 0:
        return ForecastResult(STATE_QUIET, float("nan"), 0, note="no data")
    t_now = float(times[-1])
    if n < 2:
        return ForecastResult(STATE_QUIET, t_now, n, note="need at least two epochs")

    sma, lma = smoothed_velocities(times, disp, cfg)
    moving = (disp[-1] - disp[0]) > cfg.noise_floor
    ooa = detect_ooa(times, disp, cfg)
    res = ForecastResult(STATE_QUIET if not moving else STATE_MOVING, t_now, n,
                         v_sma=sma, v_lma=lma)
    if ooa is None:
        return res

    res.state = STATE_ACCELERATING
    res.ooa_index = int(ooa)
    res.ooa_time = float(times[ooa])
    sel = np.arange(ooa, n)
    sel = sel[sma[sel] > 0]
    res.n_fit = int(len(sel))
    if res.n_fit < cfg.min_points_fit:
        res.note = "too few accelerating points for a fit"
        return res

    # A trailing average of velocity over W epochs is centred on the mean time of its window,
    # not on the last epoch; fitting it at the last epoch would bias the forecast late.
    t_sma = moving_average(times, cfg.sma_window)
    t, v = t_sma[sel], sma[sel]
    sv = None
    if sigma is not None:
        sig = np.asarray(sigma, dtype=np.float64)
        dt = np.gradient(times)
        sv = np.sqrt(2.0) * sig[sel] / np.maximum(dt[sel], 1e-9)
    lin = fit_linear_iv(t, v, sv)
    ts = fit_theil_sen_iv(t, v)
    vo = fit_voight_iv(t, v, cfg.alpha_grid)
    methods = {k: m for k, m in (("linear", lin), ("theil_sen", ts), ("voight", vo)) if m}
    res.methods = {k: {kk: vv for kk, vv in m.items()} for k, m in methods.items()}
    if lin is None:
        res.note = "1/v trend not decreasing; no forecast"
        return res

    rng = np.random.default_rng(seed)
    lo, hi = bootstrap_window(t, v, lin, cfg.bootstrap, rng)
    tfs = [m["tf"] for m in methods.values()]
    res.tf = float(np.median(tfs))
    res.t_lo = float(min(lo, min(tfs)))
    res.t_hi = float(max(hi, max(tfs)))
    res.r2 = float(lin["r2"])
    res.horizon = res.tf - t_now
    if res.r2 >= cfg.min_r2 and res.horizon <= cfg.critical_horizon:
        res.state = STATE_CRITICAL
    return res


def rolling_forecast(times, disp, cfg: ForecastConfig | None = None, sigma=None,
                     seed: int = 0) -> list[ForecastResult]:
    """Forecast as it would have been issued after each epoch (causal replay)."""
    out = []
    for k in range(1, len(times) + 1):
        s = None if sigma is None else np.asarray(sigma)[:k]
        out.append(forecast(np.asarray(times)[:k], np.asarray(disp)[:k], cfg, s, seed))
    return out
