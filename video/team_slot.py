"""Put a silent webcam portrait beside the names in the team slot of the finished video.

    python video/team_slot.py --cam webcam.mp4 --video TellTale_demo_4K.mp4 --out TellTale_demo_4K_team.mp4 \
        [--cam-start 4] [--crop 880:880:510:20]

For a clip with no usable sound: the narration keeps playing and is copied unchanged. The
card from video/cards.py (04_team_cam) and the cropped portrait are laid over the slot above
the burned-in caption bar, so the captions stay. --crop is width:height:x:y in the webcam
frame; the default keeps head and shoulders of a 1920x1080 clip.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

CAP_TOP = 1780          # first row of the caption bar in the 4K frame; the overlay stops above it


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cam", required=True)
    p.add_argument("--video", default="TellTale_demo_4K.mp4")
    p.add_argument("--out", default="TellTale_demo_4K_team.mp4")
    p.add_argument("--card", default=".build/v4k/cards/04_team_cam.png")
    p.add_argument("--timings", default=".build/v4k/telltale_4k.json")
    p.add_argument("--cam-start", type=float, default=4.0)
    p.add_argument("--crop", default="880:880:510:20")
    a = p.parse_args(argv)
    m = json.loads(Path(a.timings).read_text())
    at, n = float(m["team_at"]), float(m["team_len"])
    on = f"enable='between(t,{at},{at + n})'"
    graph = ";".join([
        f"[1:v]crop=3840:{CAP_TOP}:0:0,format=yuv420p,setpts=PTS-STARTPTS+{at}/TB[card]",
        f"[2:v]crop={a.crop},scale=1200:1200:flags=lanczos,eq=gamma=0.96:contrast=1.04,"
        f"format=yuv420p,setpts=PTS-STARTPTS+{at}/TB[cam]",
        f"[0:v][card]overlay=0:0:{on}:eof_action=pass[a]",
        f"[a][cam]overlay=320:440:{on}:eof_action=pass,format=yuv420p[v]",
    ])
    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-loglevel", "error",
           "-i", a.video,
           "-loop", "1", "-framerate", "30", "-t", str(n), "-i", a.card,
           "-ss", str(a.cam_start), "-t", str(n), "-i", a.cam,
           "-filter_complex", graph, "-map", "[v]", "-map", "0:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "30",
           "-c:a", "copy", "-movflags", "+faststart", a.out]
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print(f"wrote {a.out}: portrait and names from {at:.0f} s to {at + n:.0f} s, narration unchanged")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
