import numpy as np

from telltale.config import ForecastConfig
from telltale.forecast import (STATE_ACCELERATING, STATE_CRITICAL, STATE_MOVING, STATE_QUIET,
                               detect_ooa, forecast, moving_average, rolling_forecast)
from telltale.synthetic import voight_displacement


def test_moving_average_is_causal():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert np.allclose(moving_average(x, 3), [1.0, 1.5, 2.0, 3.0, 4.0])


def test_quiet_and_steady_creep_states():
    t = np.linspace(0, 40, 41)
    cfg = ForecastConfig()
    rng = np.random.default_rng(0)
    quiet = rng.standard_normal(len(t)) * 0.01
    assert forecast(t, quiet, cfg).state == STATE_QUIET
    steady = 0.1 * t + rng.standard_normal(len(t)) * 0.01
    fc = forecast(t, steady, cfg)
    assert fc.state == STATE_MOVING
    assert fc.tf is None


def test_voight_creep_recovers_failure_time():
    tf = 50.0
    t = np.linspace(0, 47.0, 40)
    rng = np.random.default_rng(1)
    d = voight_displacement(t, tf, 2.0) + rng.standard_normal(len(t)) * 0.01
    cfg = ForecastConfig()
    ooa = detect_ooa(t, d, cfg)
    assert ooa is not None and t[ooa] < 40.0
    fc = forecast(t, d, cfg, sigma=np.full(len(t), 0.01))
    assert fc.state in (STATE_ACCELERATING, STATE_CRITICAL)
    assert fc.tf is not None
    assert abs(fc.tf - tf) < 1.0, fc.to_dict()
    assert fc.t_lo <= tf <= fc.t_hi
    assert fc.r2 > 0.9
    assert set(fc.methods) == {"linear", "theil_sen", "voight"}


def test_rolling_forecast_converges_toward_truth():
    tf = 50.0
    t = np.linspace(0, 47.0, 40)
    d = voight_displacement(t, tf, 2.0)
    results = rolling_forecast(t, d, ForecastConfig())
    tfs = [r.tf for r in results if r.tf is not None]
    assert len(tfs) >= 5
    assert abs(tfs[-1] - tf) < 0.5
    assert results[-1].state == STATE_CRITICAL
