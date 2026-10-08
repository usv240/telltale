"""Zone time-series store: one JSON record per line, append-only, trivially diffable."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class SeriesStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=_json_default) + "\n")

    def records(self, zone: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if zone is None or rec.get("zone") == zone:
                    out.append(rec)
        out.sort(key=lambda r: r["t"])
        return out

    def arrays(self, zone: str, usable_only: bool = True):
        """times, magnitude, sigma arrays for a zone (usable epochs only by default)."""
        recs = self.records(zone)
        if usable_only:
            recs = [r for r in recs if r.get("usable", True)]
        t = np.array([r["t"] for r in recs], dtype=np.float64)
        d = np.array([r["magnitude"] for r in recs], dtype=np.float64)
        s = np.array([r.get("sigma", np.nan) for r in recs], dtype=np.float64)
        return t, d, s


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serializable: {type(o)}")
