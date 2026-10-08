import numpy as np
import pytest

from telltale.config import GridConfig
from telltale.dic import STATUS_LOW_TEXTURE, compute_field, zone_displacement
from telltale.synthetic import make_texture, shift_image

GRID = GridConfig(template=41, stride=24, search=8)


@pytest.mark.parametrize("dx,dy", [(0.25, 0.0), (0.0, 0.5), (1.375, -0.75), (-0.125, 0.125), (2.0, 1.0)])
def test_known_subpixel_shift_recovered(dx, dy):
    tex = make_texture(256, 256, seed=0)
    ref, cur, (ax, ay) = shift_image(tex, dx, dy, noise=0.005)
    fld = compute_field(ref, cur, GRID)
    assert fld.n_valid >= 20
    eu = np.abs(fld.u[fld.valid] - ax)
    ev = np.abs(fld.v[fld.valid] - ay)
    assert np.median(eu) < 0.05 and np.median(ev) < 0.05
    assert not fld.review


def test_illumination_change_does_not_read_as_motion():
    tex = make_texture(256, 256, seed=4)
    ref, cur, _ = shift_image(tex, 0.0, 0.0, gain=0.8, bias=0.05, noise=0.005)
    fld = compute_field(ref, cur, GRID)
    assert fld.n_valid >= 20
    assert np.abs(fld.u[fld.valid]).max() < 0.1 and np.abs(fld.v[fld.valid]).max() < 0.1


def test_low_texture_is_excluded_not_measured():
    flat = np.full((200, 200), 0.5, np.float32)
    rng = np.random.default_rng(0)
    a = np.clip(flat + rng.standard_normal(flat.shape).astype(np.float32) * 0.002, 0, 1)
    b = np.clip(flat + rng.standard_normal(flat.shape).astype(np.float32) * 0.002, 0, 1)
    fld = compute_field(a, b, GRID)
    assert fld.n_valid == 0
    assert (fld.status == STATUS_LOW_TEXTURE).all()


def test_zone_displacement_median_and_sigma():
    tex = make_texture(256, 256, seed=5)
    ref, cur, (ax, ay) = shift_image(tex, 0.5, 0.25, noise=0.005)
    fld = compute_field(ref, cur, GRID)
    h, w = ref.shape
    zm = zone_displacement(fld, "all", [(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)])
    assert zm.n_valid == fld.n_valid
    assert abs(zm.u - ax) < 0.03 and abs(zm.v - ay) < 0.03
    assert zm.sigma < 0.1


def test_field_roundtrip(tmp_path):
    tex = make_texture(200, 200, seed=6)
    ref, cur, _ = shift_image(tex, 0.375, 0.0)
    fld = compute_field(ref, cur, GRID)
    fld.save(tmp_path / "f.npz")
    back = type(fld).load(tmp_path / "f.npz")
    assert np.allclose(back.u, fld.u) and back.shape == fld.shape and back.n_valid == fld.n_valid
