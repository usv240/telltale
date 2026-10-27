"""Render the video's text cards as 1920x1080 PNGs in the dashboard's own visual system.

    python video/cards.py --out .build/video/cards

Each card is one HTML page rendered by headless Chrome. Text only: no third-party photographs,
so nothing in the cut needs a licence beyond the project's own material and the public-domain
USGS frames.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root { --ground: #f4f3f1; --text: #0a0a0a; --muted: #5f5f5c; --hue: #1d5fbf; --neg: #b4232a; --rule: #e4e3e0; }
  * { box-sizing: border-box; margin: 0; }
  html, body { width: 1920px; height: 1080px; overflow: hidden; }
  body { background: var(--ground); color: var(--text); font-family: Geist, system-ui, sans-serif;
         display: flex; flex-direction: column; justify-content: center; padding: 0 160px; }
  .dark { background: #0b0b0a; color: #f2f1ee; --muted: #a8a7a2; --hue: #5a9bf0; --rule: #262624; }
  .eyebrow { font-size: 30px; color: var(--muted); font-weight: 500; margin-bottom: 28px; letter-spacing: 0.01em; }
  h1 { font-size: 96px; line-height: 1.04; letter-spacing: -0.03em; font-weight: 700; max-width: 1500px; }
  h2 { font-size: 64px; line-height: 1.1; letter-spacing: -0.02em; font-weight: 600; max-width: 1500px; }
  p.lead { font-size: 40px; line-height: 1.35; color: var(--muted); margin-top: 32px; max-width: 1400px; }
  .big { font-size: 220px; font-weight: 700; letter-spacing: -0.04em; line-height: 1; color: var(--hue); font-variant-numeric: tabular-nums; }
  .neg { color: var(--neg); }
  .row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; margin-top: 56px; border-top: 2px solid var(--rule); }
  .cell { padding: 40px 40px 0 0; }
  .cell + .cell { padding-left: 40px; border-left: 2px solid var(--rule); }
  .num { font-size: 104px; font-weight: 700; letter-spacing: -0.03em; color: var(--hue); line-height: 1; font-variant-numeric: tabular-nums; }
  .lab { font-size: 32px; color: var(--muted); margin-top: 18px; line-height: 1.3; }
  .mark { display: flex; align-items: center; gap: 28px; margin-bottom: 48px; }
  .mark svg { width: 96px; height: 96px; }
  .name { font-size: 64px; font-weight: 700; letter-spacing: -0.02em; }
  .src { position: absolute; left: 160px; top: 64px; font-size: 24px; color: var(--muted); }
  .url { font-family: "Geist Mono", ui-monospace, monospace; font-size: 40px; color: var(--hue); margin-top: 40px; }
  ul.lim { list-style: none; padding: 0; margin-top: 48px; display: grid; gap: 26px; }
  ul.lim li { font-size: 44px; line-height: 1.3; padding-left: 44px; position: relative; }
  ul.lim li::before { content: ""; position: absolute; left: 0; top: 22px; width: 18px; height: 3px; background: var(--hue); }

  .flow { display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px; margin-top: 64px; }
  .step { background: #ffffff; border: 2px solid var(--rule); border-radius: 22px; padding: 36px 32px; }
  .step .n { width: 56px; height: 56px; border-radius: 50%; background: var(--hue); color: #fff; font-weight: 700;
             font-size: 30px; display: grid; place-items: center; margin-bottom: 26px; }
  .step h3 { font-size: 40px; line-height: 1.15; font-weight: 700; letter-spacing: -0.01em; }
  .step p { font-size: 27px; line-height: 1.38; color: var(--muted); margin-top: 14px; }
  .vs { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 56px; }
  .vs .box { border-radius: 24px; padding: 44px; background: #ffffff; border: 2px solid var(--rule); }
  .vs .box.hi { border-color: var(--hue); }
  .vs .k { font-size: 30px; color: var(--muted); }
  .vs .v { font-size: 92px; font-weight: 700; letter-spacing: -0.03em; margin-top: 10px; line-height: 1; }
  .vs .box.hi .v { color: var(--hue); }
  .vs .d { font-size: 28px; color: var(--muted); margin-top: 16px; line-height: 1.35; }
</style></head><body class="{cls}">{body}</body></html>"""

MARK = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#0a0a0a"/>'
        '<path d="M7 23 C 12 22, 15 17, 18 13 S 23 8, 26 8" stroke="#f4f3f1" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        '<path d="M7 25 L26 10" stroke="#5a9bf0" stroke-width="2.4" stroke-linecap="round"/></svg>')

CARDS = {
    "09_how": ("", """<div class="eyebrow">How TellTale works</div>
<h2>A slope warns before it fails. TellTale reads it.</h2>
<div class="flow">
  <div class="step"><div class="n">1</div><h3>Watch</h3><p>Any fixed camera photographs the slope a few times a day.</p></div>
  <div class="step"><div class="n">2</div><h3>Measure</h3><p>OpenCV finds how far the ground moved, to a hundredth of a pixel.</p></div>
  <div class="step"><div class="n">3</div><h3>Forecast</h3><p>When movement speeds up, physics gives a window for when it fails.</p></div>
  <div class="step"><div class="n">4</div><h3>Check, then ask a person</h3><p>An AI agent measures again. Only a person can warn the public.</p></div>
</div>"""),
    "10_impact": ("", """<div class="eyebrow">Why it matters</div>
<h2>Half of the people hit by landslides got no warning at all.</h2>
<div class="vs">
  <div class="box"><div class="k">Today: one borehole sensor</div><div class="v">€5,000+</div><div class="d">before drilling, and it watches one point (Gamperl et al. 2021)</div></div>
  <div class="box hi"><div class="k">TellTale: a whole slope</div><div class="v">$1.40</div><div class="d">of cloud cost per slope per month, with a camera a village can buy</div></div>
</div>"""),
    "01_bingham": ("", """<div class="eyebrow">Bingham Canyon copper mine, Utah · 10 April 2013</div>
<h1>The mine knew when its wall would fall.</h1>
<p class="lead">The pit was cleared beforehand. About 65 million cubic metres came down. No one was hurt.</p>
<div class="src">Pankow et al. 2014, GSA Today 24(1)</div>"""),
    "02_wayanad": ("dark", """<div class="eyebrow">Wayanad, Kerala · 30 July 2024</div>
<h1>Nobody was measuring these hills.</h1>
<p class="lead">About 290 to 400 people died, depending on the count. Half of the people hit by landslides in the last five years got no warning at all.</p>
<div class="src">Petley 2024, Eos; World Risk Poll 2023 in UNDRR and WMO 2024</div>"""),
    "03_title": ("", f"""<div class="mark">{MARK}<span class="name">TellTale</span></div>
<h2>A camera that forecasts landslides.</h2>
<p class="lead">Stacks bursts from any fixed camera, removes the camera's own motion, measures ground creep to a hundredth of a pixel, forecasts the failure window, re-measures to verify it, and pages a person.</p>"""),
    "04_team": ("", f"""<div class="mark">{MARK}<span class="name">Team Ground Truth</span></div>
<h2>Ujwal Suresh Vanjare<br>Arpita Madhukar Kalburgi</h2>
<p class="lead">We built TellTale for the OpenCV AI Competition 2026, powered by AWS: classical OpenCV 5 vision, a Claude agent on Amazon Bedrock, and a human who always decides.</p>"""),
    # the team card with the left third left empty for a webcam portrait (video/team_slot.py)
    "04_team_cam": ("", f"""<div style="margin-left:780px">
<div class="mark">{MARK}<span class="name">Team Ground Truth</span></div>
<h2>Ujwal Suresh Vanjare<br>Arpita Madhukar Kalburgi</h2>
<p class="lead" style="font-size:34px">We built TellTale for the OpenCV AI Competition 2026, powered by AWS: classical OpenCV 5 vision, a Claude agent on Amazon Bedrock, and a human who always decides.</p>
</div>"""),
    "05_real_failures": ("","""<div class="eyebrow">The forecast, replayed on six real slopes that failed</div>
<div class="big">6 of 6</div>
<p class="lead">reached CRITICAL before the collapse: Preonzo 2012, Arvigo 2007, Vajont 1963, Hogarth 1975, Veslemannen 2019. It also raised twelve early alarms that settled, so a person always decides.</p>
<div class="src">Leinauer et al. 2023, mediaTUM doi:10.14459/2023mp1688868; Kristensen et al. 2021</div>"""),
    "06_numbers": ("", """<div class="eyebrow">What it measured</div>
<div class="row">
  <div class="cell"><div class="num">0</div><div class="lab">false acceleration alarms in 147 quiet days on a real USGS landslide</div></div>
  <div class="cell"><div class="num">0.005 px</div><div class="lab">error on the public SEM DIC Challenge, ahead of Farneback and Lucas-Kanade</div></div>
  <div class="cell"><div class="num">$1.40</div><div class="lab">cloud cost per slope per month in a 50-slope district</div></div>
</div>"""),
    "07_limits": ("dark", """<div class="eyebrow">What it cannot do</div>
<ul class="lim">
  <li>Warn of brittle collapses that do not creep first.</li>
  <li>See at night, in fog or through a wet lens. It says so instead of reporting no movement.</li>
  <li>Send a public alert. Only a person can.</li>
</ul>"""),
    "08_end": ("", f"""<div class="mark">{MARK}<span class="name">TellTale</span></div>
<h2>The dashboard is live. Run a collapse yourself.</h2>
<div class="url">d30le2uwgaimao.cloudfront.net/?site=live-demo</div>
<div class="url" style="font-size:32px;color:var(--muted)">github.com/usv240/telltale · python evaluation/verify_claims.py</div>"""),
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=".build/video/cards")
    p.add_argument("--scale", type=int, default=1, help="2 renders 3840x2160")
    a = p.parse_args(argv)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        for name, (cls, body) in CARDS.items():
            html = Path(td) / f"{name}.html"
            html.write_text(BASE.replace("{cls}", cls).replace("{body}", body), encoding="utf-8")
            png = out / f"{name}.png"
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=1920,1080", f"--force-device-scale-factor={a.scale}", "--virtual-time-budget=5000",
                            f"--screenshot={png}", html.as_uri()], capture_output=True, timeout=60)
            print(name, png.exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
