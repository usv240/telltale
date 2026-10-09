"""TellTale: camera-based slope deformation measurement and failure-time forecasting.

Team Ground Truth, OpenCV AI Competition 2026.
Local-first pipeline: the same package runs on a laptop and in the cloud worker.
"""

__version__ = "0.1.0"

from .config import ForecastConfig, GridConfig, SiteConfig, polygon_mask
from .dic import DisplacementField, ZoneMeasure, compute_field, compute_field_pyramid, zone_displacement
from .forecast import ForecastResult, forecast, rolling_forecast
from .stabilize import StabilizeResult, stabilize
from .stack import StackResult, stack_burst, to_gray32

__all__ = [
    "GridConfig", "SiteConfig", "ForecastConfig", "polygon_mask",
    "DisplacementField", "ZoneMeasure", "compute_field", "compute_field_pyramid", "zone_displacement",
    "ForecastResult", "forecast", "rolling_forecast",
    "StabilizeResult", "stabilize",
    "StackResult", "stack_burst", "to_gray32",
]
