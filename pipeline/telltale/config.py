"""Site, grid, and forecast configuration.

A Site is one camera pointed at one scene. Polygons are lists of (x, y) pixel
coordinates in reference-image space. STABLE polygons mark regions assumed
motionless (bedrock, buildings off the landslide); TARGET zones mark regions
whose motion matters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class GridConfig:
    template: int = 41          # subset (template) side, odd, pixels
    stride: int = 24            # grid spacing, pixels
    search: int = 16            # search radius around zero displacement, pixels
    min_corr: float = 0.5       # minimum ZNCC peak to accept a match
    min_margin: float = 0.01    # peak minus second peak (outside 3 px), corr units
    min_texture: float = 1e-4   # minimum mean corner response (image scaled 0..1)
    max_disp: Optional[float] = None  # sanity bound on |displacement|, default search - 1
    refine_iters: int = 1       # sub-pixel re-sampling passes after the first peak estimate
    threads: int = 0            # worker threads for the subset loop; 0 = one per CPU
    pyramid_levels: int = 0     # coarse-to-fine levels (0 = single level); reach = search x 2^levels
    search_dtype: str = "float32"  # "uint8": integer search on 8-bit images, refinement stays float

    def __post_init__(self) -> None:
        if self.template % 2 == 0:
            raise ValueError("template size must be odd")
        if self.max_disp is None:
            self.max_disp = float(self.search - 1)


@dataclass
class ForecastConfig:
    sma_window: int = 3         # short moving average, epochs (Carla et al. 2017)
    lma_window: int = 7         # long moving average, epochs
    ooa_k: int = 3              # consecutive epochs of SMA > LMA to declare OOA
    noise_floor: float = 0.05   # displacement units below which motion is noise
    min_points_fit: int = 4     # minimum accelerating points for an IVM fit
    bootstrap: int = 500        # bootstrap draws for the failure-time window
    min_r2: float = 0.5         # fit quality floor to report a forecast
    critical_horizon: float = 5.0   # forecast horizon (time units) for CRITICAL
    alpha_grid: tuple = (1.5, 2.2, 0.05)  # Voight alpha search: lo, hi, step
    ooa_min_snr: float = 3.0    # SMA - LMA must exceed this many robust sigmas of its own jitter; 0 disables
    ooa_min_tstat: float = 4.0  # quadratic-fit acceleration must be this significant (t statistic); 0 disables
    noise_window: int = 14      # trailing epochs used for both onset gates


@dataclass
class SiteConfig:
    name: str = "site"
    mm_per_px: float = 1.0
    stable_polys: list = field(default_factory=list)   # list of [(x, y), ...]
    target_zones: dict = field(default_factory=dict)   # name -> [(x, y), ...]
    grid: GridConfig = field(default_factory=GridConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    burst_size: int = 7
    reference_mode: str = "fixed"   # "fixed": compare to the reference epoch; "chained": to the previous usable epoch and integrate
    mask_window: int = 0            # epochs of trailing variance mask for vegetation/water; 0 = off
    plane: Optional[dict] = None    # {"image_pts": [[x, y], ...], "world_pts_mm": [[X, Y], ...]} for metric scale across the slope
    notes: str = ""

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def from_json_dict(cls, raw: dict) -> "SiteConfig":
        """Build from a dict, ignoring keys this version does not know (forward compatible:
        a newer camera client must never stall an older worker)."""
        raw = _known(cls, dict(raw))
        raw["grid"] = GridConfig(**_known(GridConfig, raw.get("grid", {})))
        fc = _known(ForecastConfig, dict(raw.get("forecast", {})))
        if "alpha_grid" in fc:
            fc["alpha_grid"] = tuple(fc["alpha_grid"])
        raw["forecast"] = ForecastConfig(**fc)
        return cls(**raw)


def _known(dc, d: dict) -> dict:
    import dataclasses
    names = {f.name for f in dataclasses.fields(dc)}
    return {k: v for k, v in d.items() if k in names}

    @classmethod
    def from_json(cls, path: str | Path) -> "SiteConfig":
        return cls.from_json_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def polygon_mask(shape: tuple, polys: list) -> np.ndarray:
    """Rasterize polygons into a uint8 mask (255 inside)."""
    import cv2

    mask = np.zeros(shape[:2], dtype=np.uint8)
    for poly in polys:
        pts = np.asarray(poly, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [pts], 255)
    return mask
