import numpy as np

from telltale.stack import STATUS_BLIND, STATUS_OK, STATUS_UNSTABLE, shift_of, stack_burst, translate
from telltale.synthetic import make_texture


def test_shift_of_recovers_known_translation():
    tex = make_texture(160, 160, seed=1)
    moved = translate(tex, 2.5, -1.25)
    dx, dy, resp = shift_of(tex, moved, downscale=1)
    assert abs(dx - 2.5) < 0.1 and abs(dy + 1.25) < 0.1
    assert resp > 0.3


def test_stack_registers_and_reduces_noise():
    rng = np.random.default_rng(0)
    tex = make_texture(160, 160, seed=2)
    frames = []
    for k in range(7):
        f = translate(tex, rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)) if k else tex
        frames.append(np.clip(f + rng.standard_normal(f.shape).astype(np.float32) * 0.05, 0, 1))
    res = stack_burst(frames, max_shift=3.0)
    assert res.status == STATUS_OK
    assert res.shifts.shape == (7, 2)
    inner = (slice(20, -20), slice(20, -20))
    noise_single = np.abs(frames[0][inner] - tex[inner]).mean()
    noise_stack = np.abs(res.image[inner] - tex[inner]).mean()
    assert noise_stack < 0.6 * noise_single


def test_blurred_flag():
    import cv2
    from telltale.stack import STATUS_BLURRED
    tex = make_texture(160, 160, seed=9)
    assert stack_burst([tex, tex]).status == STATUS_OK
    wet = cv2.GaussianBlur(tex, (0, 0), 2.0)     # contrast stays above the BLIND floor
    assert wet.std() > 0.02
    assert stack_burst([wet, wet]).status == STATUS_BLURRED


def test_blind_and_unstable_flags():
    flat = np.full((64, 64), 0.5, np.float32)
    assert stack_burst([flat, flat]).status == STATUS_BLIND
    tex = make_texture(160, 160, seed=3)
    res = stack_burst([tex, translate(tex, 6.0, 0.0)], max_shift=3.0)
    assert res.status == STATUS_UNSTABLE
    assert res.max_shift > 5.0
