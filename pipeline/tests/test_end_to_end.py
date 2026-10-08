"""Measurement plus physics recovering a known failure time from rendered frames."""

import numpy as np

from telltale.config import ForecastConfig, GridConfig, polygon_mask
from telltale.dic import compute_field, zone_displacement
from telltale.forecast import STATE_ACCELERATING, STATE_CRITICAL, forecast
from telltale.stabilize import VERDICT_OK, stabilize
from telltale.synthetic import simulate_collapse

GRID = GridConfig(template=41, stride=16, search=16)


def _run(scene, use_stabilize):
    ref = scene.frames[0]
    stable_mask = polygon_mask(ref.shape, [scene.stable_poly])
    times, meas, sig = [], [], []
    for k, (t, frame) in enumerate(zip(scene.times, scene.frames)):
        cur = frame
        if use_stabilize and k > 0:
            st = stabilize(ref, frame, stable_mask)
            assert st.verdict == VERDICT_OK, (k, st.to_dict())
            cur = st.image
        fld = compute_field(ref, cur, GRID, seed=k)
        zm = zone_displacement(fld, "slope", scene.zone_poly)
        assert zm.n_valid >= 6, (k, fld.status_counts())
        times.append(t)
        meas.append(zm.magnitude)
        sig.append(zm.sigma)
    return np.array(times), np.array(meas), np.array(sig)


def test_simulated_collapse_is_measured_and_forecast():
    scene = simulate_collapse(h=192, w=192, n_epochs=30, tf=50.0, t_end=47.0, amp=2.0,
                              noise=0.01, seed=3)
    t, d, s = _run(scene, use_stabilize=False)
    err = np.abs(d - scene.true_disp)
    assert err.max() < 0.15, err
    fc = forecast(t, d, ForecastConfig(), s)
    assert fc.state in (STATE_ACCELERATING, STATE_CRITICAL)
    assert fc.tf is not None
    assert abs(fc.tf - scene.tf) < 1.5, fc.to_dict()
    assert fc.t_lo <= scene.tf <= fc.t_hi


def test_simulated_collapse_with_camera_jitter():
    scene = simulate_collapse(h=192, w=192, n_epochs=30, tf=50.0, t_end=47.0, amp=2.0,
                              noise=0.01, jitter_px=1.5, seed=4)
    t, d, s = _run(scene, use_stabilize=True)
    err = np.abs(d - scene.true_disp)
    assert err.max() < 0.2, err
    fc = forecast(t, d, ForecastConfig(), s)
    assert fc.tf is not None
    assert abs(fc.tf - scene.tf) < 2.0, fc.to_dict()
