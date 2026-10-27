"""Assemble the 4K demo video: chapters, callouts and burned-in captions, so it explains itself
with the sound off.

    python video/assemble4k.py --assets .build/v4k --out .build/v4k/telltale_4k.mp4

Assets (all captured from the live product at device scale 2, i.e. 3840x2160):
  cards/*.png       video/cards.py --scale 2
  replay/r00..r35   the demo slope at each epoch (?epoch=n)
  live/f*.png       a real live run on AWS, captured while it ran
  stills/*.png      about, evidence (tall), mukilteo, setup, final
  terminal/t*.png   the real verify_claims.py output

Writes the MP4, an SRT of the captions, and a JSON of shot timings that video/finish.py reads.
Callout boxes are given in the dashboard's 1920x1080 page coordinates and scaled by 2.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, S = 3840, 2160, 30, 2          # S: page px -> frame px
HUE = (191, 95, 29)                        # BGR of #1d5fbf
GROUND = (241, 243, 244)
FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_B = "C:/Windows/Fonts/segoeuib.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def fit(img):
    h, w = img.shape[:2]
    s = min(W / w, H / h)
    r = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    out = np.full((H, W, 3), GROUND, np.uint8)
    y, x = (H - r.shape[0]) // 2, (W - r.shape[1]) // 2
    out[y:y + r.shape[0], x:x + r.shape[1]] = r
    return out


def callout(img, box, label, side="below"):
    """A rounded box in the data hue around `box` (page coords) and a label pill beside it."""
    x0, y0, x1, y1 = [int(v * S) for v in box]
    out = img.copy()
    pil = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10], radius=22, outline=(29, 95, 191), width=10)
    f = font(58, True)
    tw = d.textlength(label, font=f)
    pad = 30
    bw, bh = tw + 2 * pad, 104
    if side == "below":
        bx, by = x0 - 10, y1 + 30
    elif side == "above":
        bx, by = x0 - 10, y0 - 30 - bh
    elif side == "right":
        bx, by = x1 + 34, y0
    else:  # left
        bx, by = x0 - 34 - bw, y0
    bx = max(24, min(W - bw - 24, bx))
    by = max(24, min(H - bh - 330, by))
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=52, fill=(29, 95, 191))
    d.text((bx + pad, by + bh / 2), label, font=f, fill=(255, 255, 255), anchor="lm")
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def overlay(frame, chapter, caption):
    """Chapter tag top-left and a caption band at the bottom, drawn after any camera move."""
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if caption:
        f = font(76)
        words, lines, cur = caption.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > W - 640:
                lines.append(cur); cur = w
            else:
                cur = t
        lines.append(cur)
        lh = 100
        bh = lh * len(lines) + 70
        top = H - bh - 70
        widest = max(d.textlength(l, font=f) for l in lines)
        d.rounded_rectangle([(W - widest) / 2 - 56, top, (W + widest) / 2 + 56, top + bh], radius=36,
                            fill=(10, 10, 10, 205))
        for i, l in enumerate(lines):
            d.text((W / 2, top + 35 + lh * i + lh / 2), l, font=f, fill=(255, 255, 255, 255), anchor="mm")
    else:
        top = H - 70
    if chapter:
        f = font(46, True)
        tw = d.textlength(chapter, font=f)
        y = top - 92 - 26
        d.rounded_rectangle([60, y, 60 + tw + 64, y + 92], radius=46, fill=(29, 95, 191, 235))
        d.text((92, y + 46), chapter, font=f, fill=(255, 255, 255, 255), anchor="lm")
    return cv2.cvtColor(np.asarray(Image.alpha_composite(pil, layer).convert("RGB")), cv2.COLOR_RGB2BGR)


def push(img, n, zoom=1.0, focus=(0.5, 0.5)):
    for k in range(n):
        if zoom == 1.0:
            yield img
            continue
        z = 1 + (zoom - 1) * k / max(1, n - 1)
        cw, ch = W / z, H / z
        cx = min(max(focus[0] * W, cw / 2), W - cw / 2)
        cy = min(max(focus[1] * H, ch / 2), H - ch / 2)
        m = np.float32([[z, 0, -(cx - cw / 2) * z], [0, z, -(cy - ch / 2) * z]])
        yield cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR)


def seq(imgs, n):
    for k in range(n):
        yield imgs[min(len(imgs) - 1, k * len(imgs) // n)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--assets", default=".build/v4k")
    p.add_argument("--out", default=".build/v4k/telltale_4k.mp4")
    a = p.parse_args(argv)
    A = Path(a.assets)
    rd = lambda rel: cv2.imread(str(A / rel))
    card = lambda n: fit(rd(f"cards/{n}.png"))
    replay = [fit(cv2.imread(str(f))) for f in sorted((A / "replay").glob("r*.png"))]
    live = [fit(cv2.imread(str(f))) for f in sorted((A / "live").glob("f*.png"))]
    term = [fit(cv2.imread(str(f))) for f in sorted((A / "terminal").glob("t*.png"))]
    final = fit(rd("stills/final.png"))
    about = fit(rd("stills/about.png"))
    muk = fit(rd("stills/mukilteo.png"))
    setup = fit(rd("stills/setup.png"))
    arch = fit(cv2.imread("docs/gallery/06-architecture.png"))

    ev = rd("stills/evidence_tall.png")            # 3840 wide, page scale 2
    g = cv2.cvtColor(ev, cv2.COLOR_BGR2GRAY)
    col = g[:, 220]
    tops = [y for y in range(1000, 2400) if col[y] < 236 and col[y - 2] >= 240]
    y0 = tops[0] if tops else 1640
    ev_crop = ev[y0:y0 + 1740, 144:2360]
    evidence = fit(ev_crop)
    health = fit(rd("stills/final.png")[1400:1928, 2072:3432])

    # dashboard boxes in page px (1920x1080 layout of the demo-slope view)
    WINDOW, FORECAST, APPROVE, CAMERA, AGENT = (84, 150, 452, 252), (82, 270, 752, 690), (1458, 22, 1700, 62), (1312, 270, 1712, 690), (80, 704, 1024, 960)
    r_mid, r_end = replay[18], replay[-1]

    # (chapter, seconds, frames, [(t_from, caption)])
    shots = [
        ("1 · The problem", 13, push(card("01_bingham"), 13 * FPS, 1.03),
         [(0, "In 2013 a copper mine in Utah knew when its slope would collapse."), (6.5, "It cleared the pit in time. No one was hurt.")]),
        ("1 · The problem", 13, push(card("02_wayanad"), 13 * FPS, 1.03),
         [(0, "In 2024 nobody was measuring the hills above Wayanad, India."), (6.5, "Hundreds of people died. The slopes had given the same warning.")]),
        ("", 12, push(card("04_team"), 12 * FPS),
         [(0, "We're Ground Truth. We built TellTale, which reads that warning with a camera a village can afford.")]),
        ("2 · What TellTale does", 18, push(card("09_how"), 18 * FPS, 1.02),
         [(0, "A slope that is about to fail creeps first, and speeds up."), (6, "TellTale watches it with an ordinary camera and measures the movement with OpenCV."),
          (12, "It forecasts when the slope will fail, checks itself, and asks a person to decide.")]),
        ("3 · A real landslide", 14, push(callout(about, (772, 182, 1620, 816), "Blue = ground that moved", "below"), 14 * FPS, 1.06, (0.62, 0.45)),
         [(0, "This is a real landslide, filmed by the US Geological Survey on a day it moved."), (7, "TellTale coloured the ground that moved blue, measured to a hundredth of a pixel.")]),
        ("4 · Watch a slope fail", 16, seq(replay, 16 * FPS),
         [(0, "Now a slope from quiet to failure, one photo at a time."), (8, "Each photo, TellTale measures how far the ground has moved.")]),
        ("4 · Watch a slope fail", 9, push(callout(r_end, CAMERA, "The moving ground", "below"), 9 * FPS),
         [(0, "The blue block is creeping downhill, a few millimetres at a time.")]),
        ("4 · Watch a slope fail", 13, push(callout(r_end, FORECAST, "Forecast: when it fails", "below"), 13 * FPS, 1.04, (0.2, 0.45)),
         [(0, "As it speeds up, the dots fall in a straight line toward zero."), (6.5, "Where the line hits zero is the failure. TellTale gives a window, not a guess.")]),
        ("4 · Watch a slope fail", 12, push(callout(callout(r_end, WINDOW, "Fails between day 49 and 51", "right"), APPROVE, "A person decides", "below"), 12 * FPS),
         [(0, "Here: the slope will fail between day 49 and day 51. It failed on day 50."), (6, "Nothing reaches the public unless a person presses Approve.")]),
        ("5 · Why you can trust it", 24, push(evidence, 24 * FPS, 1.05, (0.45, 0.55)),
         [(0, "Before waking anyone, an AI agent, Claude on Amazon Bedrock, checks the warning."),
          (8, "It measures again two different ways. Real movement gives the same answer both times."),
          (16, "Only then does it page the duty officer, once, with these pictures as evidence.")]),
        ("5 · Why you can trust it", 16, seq(live, 16 * FPS),
         [(0, "This is a live run on AWS, started from the dashboard."), (8, "Anyone can press the button and watch it happen, in about three minutes.")]),
        ("6 · The proof", 20, push(muk, 20 * FPS, 1.05, (0.3, 0.45)),
         [(0, "On the real landslide record it also knows when to stay quiet."), (10, "147 quiet days, zero false alarms. Both movement periods the camera could see were flagged.")]),
        ("6 · The proof", 12, push(card("05_real_failures"), 12 * FPS, 1.02),
         [(0, "We replayed it on six real slopes that collapsed."), (6, "It warned before every one. It also raised early alarms, so a person always decides.")]),
        ("6 · The proof", 10, push(card("06_numbers"), 10 * FPS),
         [(0, "On a public benchmark it measures to five thousandths of a pixel, ahead of OpenCV's standard methods.")]),
        ("6 · The proof", 8, seq(term, 8 * FPS),
         [(0, "Every number in this video is checked by one command in the code.")]),
        ("7 · How it runs", 18, push(arch, 18 * FPS, 1.04),
         [(0, "Photos go to Amazon S3, a queue feeds a Graviton server running COOL, the cloud-optimised OpenCV."),
          (9, "When there's nothing to do, it switches itself off. A watched slope costs cents a day.")]),
        ("7 · How it runs", 10, push(setup, 10 * FPS, 1.05, (0.35, 0.55)),
         [(0, "Setting up a slope takes one photo: mark the stable ground, and the slope to watch.")]),
        ("8 · Why it matters", 14, push(card("10_impact"), 14 * FPS, 1.02),
         [(0, "Today, one sensor in one borehole costs five thousand euros or more."), (7, "TellTale watches a whole slope for about a dollar forty a month.")]),
        ("8 · Why it matters", 9, push(card("07_limits"), 9 * FPS),
         [(0, "It can't warn of sudden collapses, and it can't see at night. It says so.")]),
        ("", 7, push(card("08_end"), 7 * FPS),
         [(0, "TellTale. The dashboard is live. Try it yourself.")]),
    ]

    out = Path(a.out)
    ff = shutil.which("ffmpeg") or exit("ffmpeg not found")
    proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "faster", "-crf", "18",
                             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    srt, timings, t = [], [], 0.0
    stamp = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round((s % 1) * 1000)):03d}"
    for chapter, sec, frames, caps in shots:
        n = int(sec * FPS)
        caps = sorted(caps)
        cache = {}
        last = None
        for k, f in enumerate(frames):
            if k >= n:
                break
            ts = k / FPS
            cap = [c for c in caps if c[0] <= ts][-1][1]
            last = overlay(f, chapter, cap)
            proc.stdin.write(last.tobytes())
        for _ in range(n - (k + 1 if last is not None else 0)):
            proc.stdin.write(last.tobytes())
        for i, (c0, text) in enumerate(caps):
            c1 = caps[i + 1][0] if i + 1 < len(caps) else sec
            srt.append(f"{len(srt) + 1}\n{stamp(t + c0)} --> {stamp(t + c1 - 0.15)}\n{text}\n")
        timings.append({"chapter": chapter, "start": t, "seconds": sec})
        t += sec
        print(f"{t:6.1f}s  {chapter or '(team / end)'}", flush=True)
    proc.stdin.close(); proc.wait()
    out.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    team = next(x for x in timings if x["chapter"] == "" and x["start"] > 0)
    out.with_suffix(".json").write_text(json.dumps({"total": t, "team_at": team["start"], "team_len": team["seconds"],
                                                    "outro_len": timings[-1]["seconds"], "shots": timings}, indent=1))
    print(f"wrote {out} ({t:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
