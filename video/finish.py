"""Put the team's recordings into the draft and write the final video.

    python video/finish.py --team team.mp4 --voice voice.m4a [--outro outro.mp4] \
        --draft .build/video/telltale_draft.mp4 --out telltale_final.mp4

--team   the two of you on camera, about 12 s, one line each. It replaces 0:28 to 0:40 of the
         draft, with its own sound.
--voice  the narration, recorded while watching the draft from 0:00 (read the captions in
         telltale_draft.srt). Leave 0:28 to 0:40 silent; that is the team clip's own sound.
--outro  optional: the two of you saying thank you, up to 7 s, replacing the end card.

Any phone video works; it is scaled into 1920x1080 without cropping. The result stays under
five minutes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

TEAM_AT, TEAM_LEN, TOTAL, OUTRO_LEN = 28.0, 12.0, 290.0, 7.0
FIT = ("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xf1f3f4,"
       "fps=30,setsar=1,format=yuv420p")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--draft", default=".build/video/telltale_draft.mp4")
    p.add_argument("--team", required=True)
    p.add_argument("--voice", default=None)
    p.add_argument("--outro", default=None)
    p.add_argument("--out", default="telltale_final.mp4")
    a = p.parse_args(argv)
    ff = shutil.which("ffmpeg") or sys.exit("ffmpeg not found")

    inputs = ["-i", a.draft, "-i", a.team]
    if a.voice:
        inputs += ["-i", a.voice]
    if a.outro:
        inputs += ["-i", a.outro]
    vi = 2 + (1 if a.voice else 0)            # index of the outro input, if any
    end = TOTAL - (OUTRO_LEN if a.outro else 0)

    def clip(idx, length, label):
        # scale the clip into frame, then hold its last frame if it is shorter than its slot
        return (f"[{idx}:v]{FIT},trim=0:{length},setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={length},trim=0:{length},setpts=PTS-STARTPTS[{label}]")

    v = [f"[0:v]trim=0:{TEAM_AT},setpts=PTS-STARTPTS,format=yuv420p[v0]",
         clip(1, TEAM_LEN, "v1"),
         f"[0:v]trim={TEAM_AT + TEAM_LEN}:{end},setpts=PTS-STARTPTS,format=yuv420p[v2]"]
    parts = "[v0][v1][v2]"
    n = 3
    if a.outro:
        v.append(clip(vi, OUTRO_LEN, "v3"))
        parts += "[v3]"
        n = 4
    v.append(f"{parts}concat=n={n}:v=1:a=0[v]")

    # sound: the narration from 0:00, the team clip's own sound at 0:28, the outro's at the end
    au = [f"[1:a]atrim=0:{TEAM_LEN},asetpts=PTS-STARTPTS,adelay={int(TEAM_AT * 1000)}:all=1[ta]"]
    mix = "[ta]"
    k = 1
    if a.voice:
        au.append("[2:a]asetpts=PTS-STARTPTS[va]")
        mix += "[va]"; k += 1
    if a.outro:
        au.append(f"[{vi}:a]atrim=0:{OUTRO_LEN},asetpts=PTS-STARTPTS,adelay={int(end * 1000)}:all=1[oa]")
        mix += "[oa]"; k += 1
    au.append(f"{mix}amix=inputs={k}:duration=longest:normalize=0,apad,atrim=0:{TOTAL}[a]" if k > 1
              else f"{mix}apad,atrim=0:{TOTAL}[a]")

    cmd = [ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(v + au),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-t", str(TOTAL), "-movflags", "+faststart", a.out]
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print(f"wrote {a.out} ({TOTAL:.0f} s). Upload it to YouTube as unlisted, with telltale_draft.srt as captions.")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
