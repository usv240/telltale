import numpy as np

from telltale.scale import PlaneScale


def test_plane_scale_recovers_oblique_metric():
    # a 10 m x 6 m ground rectangle imaged obliquely: far edge is smaller in the image
    import cv2
    world4 = np.float32([[0, 0], [10000, 0], [10000, 6000], [0, 6000]])
    image4 = np.float32([[100, 600], [1200, 600], [1000, 200], [300, 200]])
    Hwi = cv2.getPerspectiveTransform(world4, image4)          # a consistent oblique view
    world = np.float32([[0, 0], [10000, 0], [10000, 6000], [0, 6000], [5000, 3000], [2500, 1500], [7500, 4500], [2500, 4500], [7500, 1500]])
    image = cv2.perspectiveTransform(world.reshape(-1, 1, 2), Hwi).reshape(-1, 2)
    ps = PlaneScale(image.tolist(), world.tolist())
    assert ps.rms_mm < 1.0
    # 1 px near the far edge must be more millimetres than 1 px near the near edge
    assert ps.mm_per_px_at(650, 220) > ps.mm_per_px_at(650, 580)
    d = ps.displacement_mm([650], [580], [1.0], [0.0])
    assert 8.0 < d[0, 0] < 11.0   # about 1100 px across 10 m near the bottom edge -> ~9 mm/px


def test_plane_scale_needs_four_points():
    import pytest
    with pytest.raises(ValueError):
        PlaneScale([[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1]])
