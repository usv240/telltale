import cv2
import numpy as np

from telltale.config import GridConfig, polygon_mask
from telltale.dic import compute_field, zone_displacement
from telltale.stabilize import VERDICT_CAMERA_EVENT, VERDICT_OK, stabilize
from telltale.synthetic import make_texture

H, W = 256, 256
STABLE = [(0, 0), (110, 0), (110, H - 1), (0, H - 1)]
TARGET = [(130, 0), (W - 1, 0), (W - 1, H - 1), (130, H - 1)]
GRID = GridConfig(template=41, stride=16, search=8)


def _scene():
    return make_texture(H, W, seed=7)


def test_injected_homography_is_removed():
    ref = _scene()
    rot = cv2.getRotationMatrix2D((W / 2, H / 2), 0.4, 1.002)
    rot[:, 2] += (2.3, -1.7)
    cur = cv2.warpAffine(ref, rot, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    mask = polygon_mask(ref.shape, [STABLE])
    st = stabilize(ref, cur, mask)
    assert st.verdict == VERDICT_OK, st.to_dict()
    assert st.n_inliers >= 12
    assert st.mount_moved
    assert abs(st.rotation_deg) > 0.2
    fld = compute_field(ref, st.image, GRID)
    zm = zone_displacement(fld, "t", TARGET)
    assert zm.n_valid >= 10
    assert abs(zm.u) < 0.1 and abs(zm.v) < 0.1


def test_ground_motion_survives_stabilization():
    ref = _scene()
    shift = np.array([[1.0, 0.0, 1.5], [0.0, 1.0, 0.0]], dtype=np.float32)
    cur = ref.copy()
    moved = cv2.warpAffine(ref, shift, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    tmask = polygon_mask(ref.shape, [TARGET]) > 0
    cur[tmask] = moved[tmask]
    mask = polygon_mask(ref.shape, [STABLE])
    st = stabilize(ref, cur, mask)
    assert st.verdict == VERDICT_OK, st.to_dict()
    assert not st.mount_moved
    zm = zone_displacement(compute_field(ref, st.image, GRID), "t", TARGET)
    assert abs(zm.u - 1.5) < 0.1 and abs(zm.v) < 0.1


def test_non_rigid_camera_distortion_is_a_camera_event():
    ref = _scene()
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    map_x = xx + 1.5 * np.sin(yy / 12.0)
    map_y = yy + 1.5 * np.cos(xx / 12.0)
    cur = cv2.remap(ref, map_x, map_y, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    mask = polygon_mask(ref.shape, [STABLE])
    st = stabilize(ref, cur, mask)
    assert st.verdict == VERDICT_CAMERA_EVENT, st.to_dict()
    assert st.scatter > 0.3
