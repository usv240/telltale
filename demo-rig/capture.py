"""Tabletop rig capture: a burst of frames every N seconds from a webcam, saved per epoch and
optionally uploaded straight to the deployed stack.

    python demo-rig/capture.py --run run01 --every 20 --burst 7 --camera 0
    python demo-rig/capture.py --run run01 --every 20 --upload telltale-123 --site rig-run01 \
        --site-config demo-rig/site_rig.json

Epoch time t is minutes since the run started (so forecasts read in minutes). When uploading,
the script polls the site's control.json after every epoch, so a cadence change made by the
supervising agent (set_capture_cadence) takes effect on the camera within one epoch. Frames are saved
as PNG (lossless) under demo-rig/captures/<run>/<t>/frame_XX.png. Exposure and focus are
locked where the camera driver allows it; shadow drift from windows is a confounder to test
deliberately, not accidentally, so use fixed LED lighting.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra" / "scripts"))


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # manual on many UVC drivers
    if not cap.isOpened():
        raise SystemExit(f"cannot open camera {index}")
    for _ in range(10):  # let exposure settle
        cap.read()
    return cap


def grab_burst(cap: cv2.VideoCapture, n: int, gap_s: float):
    frames = []
    for _ in range(n):
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
        time.sleep(gap_s)
    return frames


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--every", type=float, default=20.0, help="seconds between epochs")
    p.add_argument("--burst", type=int, default=7)
    p.add_argument("--gap", type=float, default=0.15, help="seconds between burst frames")
    p.add_argument("--max-epochs", type=int, default=0, help="0 = until Ctrl+C")
    p.add_argument("--upload", default=None, help="bucket name to upload each epoch")
    p.add_argument("--site", default=None)
    p.add_argument("--site-config", default=None, help="site.json sent with the first epoch")
    p.add_argument("--preview", action="store_true", help="show a live window")
    a = p.parse_args(argv)

    out = ROOT / "demo-rig" / "captures" / a.run
    out.mkdir(parents=True, exist_ok=True)
    log = out / "runlog.jsonl"
    cap = open_camera(a.camera, a.width, a.height)
    cfg = json.loads(Path(a.site_config).read_text()) if a.site_config else None
    t_start = time.time()
    k = 0
    print(f"capturing run {a.run}: burst {a.burst} every {a.every}s; Ctrl+C to stop")
    try:
        while True:
            t_min = (time.time() - t_start) / 60.0
            frames = grab_burst(cap, a.burst, a.gap)
            ep = out / f"{t_min:.3f}"
            ep.mkdir(exist_ok=True)
            paths = []
            for i, f in enumerate(frames):
                pth = ep / f"frame_{i:02d}.png"
                cv2.imwrite(str(pth), f)
                paths.append(str(pth))
            rec = {"k": k, "t_min": round(t_min, 3), "n_frames": len(frames),
                   "wall": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if a.upload:
                from upload_epoch import upload
                key = upload(a.upload, a.site or a.run, round(t_min, 3), paths,
                             cfg if k == 0 else None)
                rec["s3"] = key
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec))
            if a.preview and frames:
                cv2.imshow("telltale capture", cv2.resize(frames[-1], None, fx=0.5, fy=0.5))
                cv2.waitKey(1)
            k += 1
            if a.max_epochs and k >= a.max_epochs:
                break
            # Close the loop: the supervising agent may have changed the cadence (control.json).
            every = a.every
            if a.upload:
                try:
                    import boto3
                    body = boto3.client("s3").get_object(Bucket=a.upload, Key=f"public/sites/{a.site or a.run}/control.json")["Body"].read()
                    ctrl = json.loads(body)
                    every = 86400.0 / max(1, int(ctrl.get("epochs_per_day", 86400 / a.every)))
                    if abs(every - a.every) > 1:
                        print(f"cadence set by {ctrl.get('by')}: {ctrl.get('epochs_per_day')} per day ({ctrl.get('reason')})")
                except Exception:
                    pass
            time.sleep(max(0.0, every - a.burst * a.gap))
    except KeyboardInterrupt:
        print("stopped")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
