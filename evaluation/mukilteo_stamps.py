"""Read the burned-in "MM/DD/YYYY HH:MM" stamp of every Mukilteo frame with template matching.

The camera renders the stamp in a fixed font at the bottom right. Glyph templates are harvested
from frames whose stamps were verified by eye, then every frame's stamp is segmented into
glyphs and each glyph is matched (ZNCC) against the templates. Any glyph with a weak best match
is reported so the mapping can be trusted or fixed.

    python evaluation/mukilteo_stamps.py --photos <dir> --out evaluation/results/mukilteo_stamps.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Verified by eye (frame index -> stamp). Frames 10 and 13 follow from three frames per day
# with no gap in the first week; they are checked below by match score like every other frame.
KNOWN = {
    1: "08/20/2015 08:59",
    3: "08/20/2015 15:59",
    10: "08/23/2015 08:59",
    13: "08/24/2015 08:59",
    332: "12/08/2015 08:58",
    500: "02/01/2016 11:57",
    843: "05/25/2016 15:55",
}


def strip(img: np.ndarray) -> np.ndarray:
    # The stamp is right-aligned at a fixed position; the first glyph starts at x = 1546.
    # Starting at 1540 keeps bright scene pixels to the left of the text out of the strip.
    return img[1290:1356, 1540:2048]


def text_mask(s: np.ndarray) -> np.ndarray:
    """White text pixels gated by proximity to the glyphs' dark outline, so bright background
    (wet gravel, pipes) does not read as text."""
    g = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)
    outline = (g < 60).astype(np.uint8)
    near = cv2.dilate(outline, np.ones((5, 5), np.uint8))
    return ((g > 200) & (near > 0)).astype(np.uint8)


def glyph_boxes(s: np.ndarray) -> list[tuple[int, int]]:
    white = text_mask(s)
    col = white.sum(axis=0)
    boxes, start = [], None
    for x, v in enumerate(col):
        if v > 0 and start is None:
            start = x
        elif v == 0 and start is not None:
            boxes.append((start, x))
            start = None
    if start is not None:
        boxes.append((start, len(col)))
    # Real glyphs are at least 6 px wide and span at least 15 text rows; bright scene pixels
    # (pebbles, pipes) leaking into the strip are small and are dropped here.
    keep = []
    for x0, x1 in boxes:
        rows = int((white[:, x0:x1].sum(axis=1) > 0).sum())
        if x1 - x0 >= 6 and rows >= 15:
            keep.append((x0, x1))
    return keep


CANVAS_W, CANVAS_H = 32, 40
LAYOUT = "MM/DD/YYYYHH:MM"  # glyph roles by position (15 glyphs, no space)


def glyph_image(s: np.ndarray, box: tuple[int, int]) -> np.ndarray:
    """Binary glyph scaled to a fixed height, centred on a fixed canvas (aspect preserved,
    so a narrow '/' cannot be confused with a wide '7')."""
    white = text_mask(s)
    x0, x1 = box
    rows = np.nonzero(white[:, x0:x1].sum(axis=1))[0]
    y0, y1 = rows.min(), rows.max() + 1
    crop = white[y0:y1, x0:x1].astype(np.float32)
    h, w = crop.shape
    nw = max(2, min(CANVAS_W, int(round(w * CANVAS_H / h))))
    crop = cv2.resize(crop, (nw, CANVAS_H), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((CANVAS_H, CANVAS_W), np.float32)
    x = (CANVAS_W - nw) // 2
    canvas[:, x:x + nw] = crop
    return canvas


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photos", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    photos = Path(a.photos)

    # harvest templates
    templates: dict[str, list[np.ndarray]] = {}
    for k, text in KNOWN.items():
        s = strip(cv2.imread(str(photos / f"mukilteo-{k:03d}.jpg")))
        boxes = glyph_boxes(s)
        chars = text.replace(" ", "")
        if len(boxes) != len(chars):
            print(f"frame {k}: expected {len(chars)} glyphs, found {len(boxes)}; boxes={boxes}")
            return 1
        for ch, box in zip(chars, boxes):
            templates.setdefault(ch, []).append(glyph_image(s, box))
    print("templates:", {ch: len(v) for ch, v in sorted(templates.items())})
    missing = set("0123456789/:") - set(templates)
    if missing:
        print("missing templates for", missing)
        return 1

    digits = [c for c in templates if c.isdigit()]

    def classify(g: np.ndarray, role: str) -> tuple[str, float]:
        """Separators are fixed by layout; digit positions are matched among digit templates."""
        if role == "/":
            return "/", 1.0
        if role == ":":
            return ":", 1.0
        best, score = "?", -1.0
        for ch in digits:
            for t in templates[ch]:
                r = float(cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)[0, 0])
                if r > score:
                    best, score = ch, r
        return best, score

    out, weak, last_key = {}, [], None
    for f in sorted(photos.glob("mukilteo-*.jpg")):
        k = int(f.stem.split("-")[1])
        s = strip(cv2.imread(str(f)))
        boxes = glyph_boxes(s)
        chars, scores = [], []
        if len(boxes) == 15:
            for box, role in zip(boxes, LAYOUT):
                ch, sc = classify(glyph_image(s, box), role)
                chars.append(ch)
                scores.append(sc)
        text = "".join(chars)
        if len(text) == 15:
            text = f"{text[:10]} {text[10:]}"
        minscore = min(scores) if scores else 0.0
        valid = len(boxes) == 15 and minscore > 0.5
        if valid:
            mo, dd, yy, hh, mi = int(text[0:2]), int(text[3:5]), int(text[6:10]), int(text[11:13]), int(text[14:16])
            key = (yy, mo, dd, hh, mi)
            valid = (yy in (2015, 2016) and 1 <= mo <= 12 and 1 <= dd <= 31 and hh < 24 and mi < 60
                     and (last_key is None or key >= last_key))
            if valid:
                last_key = key
        out[k] = {"stamp": text, "min_score": round(minscore, 3), "valid": valid}
        if not valid:
            weak.append((k, text, round(minscore, 3), len(boxes)))
    n_read = sum(v["valid"] for v in out.values())
    # Fill unreadable stamps from valid neighbours when the frame count between them equals
    # the number of capture slots between them (three slots per day, fixed hours).
    import datetime as _dt
    slots = [9, 12, 16]

    def parse(text):
        return _dt.datetime(int(text[6:10]), int(text[0:2]), int(text[3:5]), int(text[11:13]), int(text[14:16]))

    def slot_index(t: _dt.datetime) -> int:
        return min(range(3), key=lambda i: abs(t.hour - slots[i]))

    def step(d: _dt.date, si: int, n: int):
        si += n
        return d + _dt.timedelta(days=si // 3), si % 3

    keys = sorted(out)
    valid_keys = [k for k in keys if out[k]["valid"]]
    filled = 0
    for i, k in enumerate(keys):
        if out[k]["valid"]:
            continue
        before = [v for v in valid_keys if v < k]
        after = [v for v in valid_keys if v > k]
        if not before or not after:
            continue
        kb, ka = before[-1], after[0]
        tb, ta = parse(out[kb]["stamp"]), parse(out[ka]["stamp"])
        db, sb = tb.date(), slot_index(tb)
        da, sa = ta.date(), slot_index(ta)
        n_slots = (da - db).days * 3 + (sa - sb)
        if n_slots == ka - kb:
            d, si = step(db, sb, k - kb)
            hh = slots[si]
            out[k] = {"stamp": f"{d.month:02d}/{d.day:02d}/{d.year} {hh:02d}:{tb.minute:02d}",
                      "min_score": 0.0, "valid": True, "filled": True}
            filled += 1
    Path(a.out).write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"{len(out)} frames, {n_read} read, {filled} filled from neighbours, "
          f"{sum(v['valid'] for v in out.values())} valid; weak: {weak[:10]}")
    for k, text in KNOWN.items():
        print(f"check frame {k}: {out[k]['stamp']}  (expected {text})  {'OK' if out[k]['stamp'] == text else 'MISMATCH'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
