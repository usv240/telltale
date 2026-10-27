"""Render the verify_claims.py output as terminal frames, one more claim per frame.

    python video/terminal.py --log .build/video/verify.txt --out .build/video/terminal

The text is the real output of `python evaluation/verify_claims.py`, captured to a file.
"""

from __future__ import annotations

import argparse
import html
import os
import subprocess
import tempfile
from pathlib import Path

CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
 html,body{{width:1920px;height:1080px;margin:0;overflow:hidden;background:#0b0b0a}}
 .win{{position:absolute;inset:60px 120px;background:#151514;border:1px solid #262624;border-radius:14px;padding:36px 44px;
       font-family:"Geist Mono",ui-monospace,monospace;font-size:22px;line-height:1.45;color:#d9d8d4;white-space:pre-wrap;overflow:hidden}}
 .bar{{display:flex;gap:10px;margin-bottom:22px}} .bar i{{width:14px;height:14px;border-radius:50%;background:#3a3a37}}
 .p{{color:#5a9bf0}} .pass{{color:#7cc48a;font-weight:600}} .m{{color:#8e8d88}} .ok{{color:#7cc48a;font-weight:600}}
</style></head><body><div class="win"><div class="bar"><i></i><i></i><i></i></div>{body}</div></body></html>"""


def fmt(lines):
    out = ['<span class="p">$</span> python evaluation/verify_claims.py\n']
    for l in lines:
        e = html.escape(l)
        if l.startswith("PASS"):
            out.append('<span class="pass">PASS</span>' + e[4:])
        elif l.strip().startswith("measured:"):
            out.append('<span class="m">' + e + "</span>")
        elif "all claims hold" in l:
            out.append('<span class="ok">' + e + "</span>")
        else:
            out.append(e)
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--log", required=True)
    p.add_argument("--out", default=".build/video/terminal")
    p.add_argument("--scale", type=int, default=1)
    a = p.parse_args(argv)
    lines = [l.rstrip() for l in Path(a.log).read_text(encoding="utf-8", errors="replace").splitlines()]
    # keep each claim's title line and shorten its measured line so a claim fits on two lines
    keep = []
    for l in lines:
        if l.strip().startswith("measured:"):
            l = "      " + l.strip()[:130]
        keep.append(l)
    claims = [i for i, l in enumerate(keep) if l.startswith(("PASS", "FAIL"))]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cuts = [c + 2 for c in claims] + [len(keep)]
    with tempfile.TemporaryDirectory() as td:
        for k, end in enumerate(cuts):
            page = Path(td) / f"t{k}.html"
            page.write_text(PAGE.format(body=fmt(keep[:end])), encoding="utf-8")
            png = out / f"t{k:02d}.png"
            for _ in range(3):              # Chrome occasionally stalls when another instance is busy
                try:
                    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                    "--window-size=1920,1080", f"--force-device-scale-factor={a.scale}", "--virtual-time-budget=4000",
                                    f"--screenshot={png}", page.as_uri()], capture_output=True, timeout=90)
                    break
                except subprocess.TimeoutExpired:
                    continue
    print(len(cuts), "frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
