import numpy as np

from telltale.config import GridConfig
from telltale.dic import compute_field
from telltale.magnify import dense_flow, magnify
from telltale.synthetic import make_texture, shift_image


def test_magnified_motion_scales_with_gain():
    tex = make_texture(256, 256, seed=21)
    ref, cur, (ax, ay) = shift_image(tex, 0.25, 0.0, noise=0.003)
    fld = compute_field(ref, cur, GridConfig(template=41, stride=16, search=8))
    flow = dense_flow(fld, ref.shape)
    assert abs(float(np.median(flow[40:-40, 40:-40, 0])) - ax) < 0.05
    mag = magnify(ref, fld, gain=20.0, smooth_sigma=0.0)
    # the magnified image should be the reference shifted by about 20 x 0.25 = 5 px
    inner = (slice(40, -40), slice(40, -40))
    best, best_s = None, -1.0
    for s in range(0, 9):
        c = np.corrcoef(mag[inner][:, s:].ravel() if s else mag[inner].ravel(),
                        ref[inner][:, :ref[inner].shape[1] - s].ravel() if s else ref[inner].ravel())[0, 1]
        if c > best_s:
            best, best_s = s, c
    assert best == 5
