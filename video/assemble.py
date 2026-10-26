"""Assemble the silent draft cut of the five-minute video from captured assets.

    python video/assemble.py --assets .build/video --out .build/video/telltale_draft.mp4

Every shot is footage or a still of the real product (captured from the live site), a text
card (video/cards.py) or the real verifier output (video/terminal.py). The team records the
two on-camera shots and the voice-over; their slots are marked by placeholder cards, and
`telltale_draft.srt` carries the script as captions with the same timings.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 1920, 1080, 30


def fit(img: np.ndarray, bg=(241, 243, 244)) -> np.ndarray:
    """Letterbox an image into 1920x1080 on the page ground colour."""
    h, w = img.shape[:2]
    s = min(W / w, H / h)
    r = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    out = np.full((H, W, 3), bg, np.uint8)
    y, x = (H - r.shape[0]) // 2, (W - r.shape[1]) // 2
    out[y:y + r.shape[0], x:x + r.shape[1]] = r
    return out


def push(img: np.ndarray, frames: int, zoom=1.06, focus=(0.5, 0.5)):
    """A slow push-in toward `focus` (fractions of width and height)."""
    for k in range(frames):
        z = 1 + (zoom - 1) * k / max(1, frames - 1)
        cw, ch = W / z, H / z
        cx = min(max(focus[0] * W, cw / 2), W - cw / 2)
        cy = min(max(focus[1] * H, ch / 2), H - ch / 2)
        m = np.float32([[z, 0, -(cx - cw / 2) * z], [0, z, -(cy - ch / 2) * z]])
        yield cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR)


def hold(img, frames):
    for _ in range(frames):
        yield img


def sequence(imgs, seconds_each):
    for im in imgs:
        yield from hold(im, int(seconds_each * FPS))


def crop(img, x0, y0, x1, y1):
    return fit(img[y0:y1, x0:x1])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--assets", default=".build/video")
    p.add_argument("--out", default=".build/video/telltale_draft.mp4")
    a = p.parse_args(argv)
    A = Path(a.assets)
    rd = lambda rel: cv2.imread(str(A / rel))
    card = lambda n: fit(rd(f"cards/{n}.png"))
    replay = [fit(cv2.imread(str(f))) for f in sorted((A / "replay").glob("r*.png"))]
    live = [fit(cv2.imread(str(f))) for f in sorted((A / "live").glob("f*.png"))]
    term = [fit(cv2.imread(str(f))) for f in sorted((A / "terminal").glob("t*.png"))]
    ev = rd("stills/evidence_tall.png")
    # the investigations panel, located by its heading row in the tall capture
    g = cv2.cvtColor(ev, cv2.COLOR_BGR2GRAY)
    col = g[:, 110]
    tops = [y for y in range(500, 1200) if col[y] < 236 and col[y - 1] >= 240]
    y0 = tops[0] if tops else 820
    evidence = crop(ev, 72, y0, 1180, y0 + 870)
    arch = fit(cv2.imread(str(Path("docs/gallery/06-architecture.png"))))
    final = fit(rd("stills/final.png"))
    health = crop(rd("stills/final.png"), 1036, 700, 1716, 964)   # the Instrument health panel

    # (seconds, frames generator, caption)  -- follows docs/VIDEO.md
    shots = [
        (14, push(card("01_bingham"), 14 * FPS, 1.04), "In April 2013 a copper mine in Utah knew when its pit wall would fall. They cleared the pit. Sixty-five million cubic metres came down, and no one was hurt."),
        (14, push(card("02_wayanad"), 14 * FPS, 1.04), "In July 2024 nobody was measuring the hills above Wayanad. Hundreds of people died. The slopes gave the same warning. Nobody was watching."),
        (12, hold(card("04_team"), 12 * FPS), "We're Ground Truth. We built TellTale, which reads that warning with a camera a village can afford."),
        (18, push(fit(rd("stills/about.png")), 18 * FPS, 1.10, (0.66, 0.5)), "This is a real landslide: the USGS camera on a coastal bluff in Washington, on a day it moved. The blue is the ground TellTale measured moving."),
        (22, sequence(replay, 22 / len(replay)), "Here's a slope from quiet to failure. TellTale stacks each burst of photos, removes the camera's own shake, and measures the surface at three thousand points."),
        (22, push(replay[-2], 22 * FPS, 1.35, (0.2, 0.55)), "When the creep accelerates, one over velocity falls in a straight line toward zero. Where it hits zero is the failure. TellTale publishes a window, not a date."),
        (13, push(final, 13 * FPS, 1.25, (0.3, 0.08)), "One sentence for the duty officer. Nothing reaches the public unless a person presses this."),
        (30, push(evidence, 30 * FPS, 1.08, (0.4, 0.55)), "Before anyone is woken, Claude on Amazon Bedrock checks the warning. It re-runs OpenCV against the previous photo and against the reference. Real motion agrees with itself. Only then does it page a person, once for the whole episode."),
        (20, sequence(live, 20 / len(live)), "This is a live run on AWS, started from the dashboard: the queue, the Graviton worker running COOL, and the agent, processing a collapse as it arrives."),
        (25, push(fit(rd("stills/mukilteo.png")), 25 * FPS, 1.08, (0.25, 0.45)), "On the real Mukilteo record it also says no: a hundred and forty-seven quiet days, zero false acceleration alarms. A camera on moving ground or a wet lens is reported as such, never as motion."),
        (12, push(card("05_real_failures"), 12 * FPS, 1.04), "We replayed the forecast on six real slopes that failed. It reached CRITICAL before every one, and it raised early alarms that settled. That is why a person always decides."),
        (12, push(fit(rd("stills/setup.png")), 12 * FPS, 1.08, (0.35, 0.6)), "An operator sets up a site once, from one photo: stable ground here, the slope they care about there."),
        (23, push(arch, 23 * FPS, 1.06), "Bursts go to S3. An ordered queue feeds a Graviton worker running COOL, the cloud-optimised OpenCV from AWS Marketplace. When there's nothing to do, the worker switches itself off and a small function wakes it."),
        (15, push(health, 15 * FPS, 1.05), "Every record names the OpenCV build that ran, on which instance. We measured COOL against stock OpenCV on the same machine and report what we found."),
        (12, hold(card("06_numbers"), 12 * FPS), "Zero false alarms on a real landslide record. Five thousandths of a pixel on a public benchmark. About a dollar forty of cloud cost per slope per month."),
        (10, sequence(term, 10 / len(term)), "Every number in this video is checked by one command in the repository."),
        (9, hold(card("07_limits"), 9 * FPS), "It can't warn of brittle collapses, and it can't see at night. It says so."),
        (7, hold(card("08_end"), 7 * FPS), "TellTale. The dashboard is live. Thank you."),
    ]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("ffmpeg not found")
    proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                            stdin=subprocess.PIPE)
    srt, t = [], 0.0
    fmt = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round((s % 1) * 1000)):03d}"
    for n, (sec, frames, cap) in enumerate(shots, 1):
        count = 0
        for f in frames:
            proc.stdin.write(f.tobytes()); count += 1
        last = f
        while count < int(sec * FPS):          # pad sequences that came out a frame short
            proc.stdin.write(last.tobytes()); count += 1
        srt.append(f"{n}\n{fmt(t)} --> {fmt(t + sec - 0.2)}\n{cap}\n")
        t += sec
    proc.stdin.close()
    proc.wait()
    out.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"{out}  {t:.0f} s, {len(shots)} shots; captions {out.with_suffix('.srt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
