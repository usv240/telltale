"""Voice the video's captions and lay the voice under the cut.

    python video/narrate.py --video .build/v4k/telltale_4k.mp4 --out telltale_4k_voiced.mp4 \
        [--voice en-US-AndrewNeural]

Reads the captions next to the video (same name, .srt), synthesises each line with a neural
voice (edge-tts), speeds a line up slightly only if it would overrun its caption, places every
line at its caption's start, and muxes the result with the picture unchanged (no re-encode).
Also writes the narration on its own (.m4a), which video/finish.py accepts as --voice. The
narration is synthetic; say so if asked, and replace it with your own voice the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


def parse_srt(path: Path):
    """(start, end, text) per caption; tolerant of CRLF and doubled line endings."""
    t = lambda s: sum(float(x) * m for x, m in zip(s.replace(",", ".").split(":"), (3600, 60, 1)))
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^(\d+:\d+:\d+[,.]\d+) --> (\d+:\d+:\d+[,.]\d+)$", lines[i])
        if not m:
            i += 1
            continue
        i += 1
        text = []
        while i < len(lines) and lines[i] and not re.match(r"^\d+$", lines[i]) and "-->" not in lines[i]:
            text.append(lines[i]); i += 1
        out.append((t(m.group(1)), t(m.group(2)), " ".join(text)))
    return out


def duration(path: Path) -> float:
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


async def _synth(text, voice, rate, out):
    await edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(str(out))


def synth(text, voice, rate, out):
    """The speech service drops a request now and then; retry before giving up."""
    import time
    for k in range(5):
        try:
            return asyncio.run(_synth(text, voice, rate, out))
        except Exception:
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"could not synthesise: {text[:50]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", default=".build/v4k/telltale_4k.mp4")
    p.add_argument("--out", default="telltale_4k_voiced.mp4")
    p.add_argument("--voice", default="en-US-AndrewNeural")
    p.add_argument("--lead", type=float, default=0.25, help="seconds after a caption appears before its line starts")
    a = p.parse_args(argv)
    video = Path(a.video)
    caps = parse_srt(video.with_suffix(".srt"))
    ff = shutil.which("ffmpeg")
    narration = Path(a.out).with_suffix(".m4a")
    with tempfile.TemporaryDirectory() as td:
        clips = []
        for i, (t0, t1, text) in enumerate(caps):
            slot = t1 - t0 - a.lead - 0.15
            f = Path(td) / f"l{i:02d}.mp3"
            rate = 0
            synth(text, a.voice, rate, f)
            d = duration(f)
            while d > slot and rate < 30:          # fit the line to its caption, never past it
                rate = min(30, rate + max(4, int((d / slot - 1) * 100) + 2))
                synth(text, a.voice, rate, f)
                d = duration(f)
            clips.append((t0 + a.lead, f, d, slot, rate))
            print(f"{t0:6.1f}s  {d:4.1f}/{slot:4.1f}s  rate {rate:+d}%  {text[:60]}")
        total = duration(video)
        inputs, chains, labels = [], [], ""
        for k, (start, f, *_ ) in enumerate(clips):
            inputs += ["-i", str(f)]
            chains.append(f"[{k}:a]aresample=48000,adelay={int(start * 1000)}:all=1[a{k}]")
            labels += f"[a{k}]"
        graph = ";".join(chains) + f";{labels}amix=inputs={len(clips)}:duration=longest:normalize=0,apad,atrim=0:{total},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,pan=stereo|c0=c0|c1=c0[out]"
        subprocess.run([ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]",
                        "-c:a", "aac", "-b:a", "192k", str(narration)], check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", "-t", str(total), a.out], check=True)
    over = [c for c in clips if c[2] > c[3]]
    print(f"wrote {a.out} and {narration}; {len(clips)} lines, {len(over)} still longer than their caption")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
