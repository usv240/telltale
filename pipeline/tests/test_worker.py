"""The worker's local path: artifacts, states, approval, events and the rule-based agent."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "worker"))
sys.path.insert(0, str(ROOT))

import worker as W  # noqa: E402
from agent.supervisor import _event_from  # noqa: E402
from telltale.config import ForecastConfig, GridConfig, SiteConfig  # noqa: E402
from telltale.stack import translate  # noqa: E402
from telltale.synthetic import perturb, simulate_collapse  # noqa: E402


class CountingAlerting:
    topic = "counter"

    def __init__(self):
        self.pages = []

    def links(self, site, t):
        return {"approve": f"approve://{site}/{t}", "dismiss": f"dismiss://{site}/{t}"}

    def publish(self, subject, message):
        self.pages.append(subject)


@pytest.fixture
def scene():
    return simulate_collapse(h=192, w=192, n_epochs=22, tf=50.0, t_end=47.0, amp=2.0, noise=0.0, seed=5)


def _bursts(scene, rng):
    for t, frame in zip(scene.times, scene.frames):
        yield float(t), [np.clip(perturb(translate(frame, rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)),
                                         noise=0.01, rng=rng) * 255, 0, 255).astype(np.uint8) for _ in range(3)]


def test_local_worker_end_to_end(tmp_path, scene, monkeypatch):
    monkeypatch.setenv("TELLTALE_AGENT", "rules")
    counter = CountingAlerting()
    W._ALERTING = counter
    store = W.LocalStore(tmp_path)
    cfg = SiteConfig(name="t", mm_per_px=0.5, stable_polys=[scene.stable_poly],
                     target_zones={"slope": scene.zone_poly},
                     grid=GridConfig(template=41, stride=16, search=16), forecast=ForecastConfig())
    rng = np.random.default_rng(1)
    recs = [W.process_epoch(store, "t", t, fr, asdict(cfg) if i == 0 else None)
            for i, (t, fr) in enumerate(_bursts(scene, rng))]
    assert recs[0]["reason"] == "REFERENCE" and all(r["usable"] for r in recs)
    fc = json.loads(store.get("public/sites/t/forecast.json"))
    assert fc["state"] == "CRITICAL" and fc["zones"]["slope"]["tf"] is not None
    assert abs(fc["zones"]["slope"]["tf"] - 50.0) < 2.5
    assert fc["approval"]["required"] and fc["approval"]["status"] == "pending"
    assert fc["approval"]["links"]["approve"].startswith("approve://")
    # per-epoch snapshots and agent traces exist
    assert store.get(f"public/sites/t/epochs/{recs[-1]['t']:g}/forecast.json") is not None
    log = json.loads(store.get("public/sites/t/agentlog.json"))
    assert log["events"] and all(e["verdict"] == "CONFIRMED" for e in log["events"])
    assert any(e["paged_human"] for e in log["events"])
    assert counter.pages, "a human must have been paged"
    # A model passes rounded epoch times; "previous" must still mean the epoch before, not
    # the epoch itself (which reads as zero motion and closed real creep as a false alarm).
    from agent.tools import Toolbox
    tb = Toolbox(store, "t", None)
    t_last = recs[-1]["t"]
    exact = tb.remeasure(t_last, "previous")
    rounded = tb.remeasure(round(t_last - 1e-4, 4) + 4e-5, "previous")
    assert exact["reference_t"] < t_last and rounded["reference_t"] == exact["reference_t"]
    assert rounded["zones"]["slope"]["magnitude"] > 0.05
    # unknown site keys from a newer client are tolerated
    assert SiteConfig.from_json_dict({**asdict(cfg), "future": 1}).name == "t"


def test_event_detection_dedupes_runs():
    quiet = {"reason": "OK", "field": {"coverage": 0.9}}
    assert _event_from(quiet, "QUIET", "QUIET") is None
    assert _event_from(quiet, "MOVING", "ACCELERATING") == "E_ANOMALY"
    assert _event_from(quiet, "ACCELERATING", "ACCELERATING") is None
    cam = {"reason": "CAMERA_EVENT"}
    assert _event_from(cam, "QUIET", "QUIET") == "E_CAMERA"
    assert _event_from(cam, "QUIET", "QUIET", prev_reason="CAMERA_EVENT") is None
    low = {"reason": "OK", "field": {"coverage": 0.2}}
    assert _event_from(low, "QUIET", "QUIET") == "E_QUALITY"
    assert _event_from(low, "QUIET", "QUIET", prev_reason="LOW_COVERAGE") is None


def test_blind_epoch_is_recorded_not_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("TELLTALE_AGENT", "off")
    W._ALERTING = CountingAlerting()
    store = W.LocalStore(tmp_path)
    cfg = SiteConfig(name="b", target_zones={"z": [(10, 10), (100, 10), (100, 100), (10, 100)]})
    flat = [np.full((128, 128), 128, np.uint8)] * 3
    rec = W.process_epoch(store, "b", 0.0, flat, asdict(cfg))
    assert rec["usable"] is False and rec["reason"] == "BLIND"
    series = json.loads(store.get("public/sites/b/series.json"))
    assert len(series["records"]) == 1 and series["records"][0]["reason"] == "BLIND"


class FakeSQS:
    """Hands out queued messages in a shuffled order, ten at a time, like SQS standard."""

    def __init__(self, ts):
        rng = np.random.default_rng(3)
        self.waiting = [{"ReceiptHandle": f"h{t}", "Body": json.dumps(
            {"Records": [{"s3": {"object": {"key": f"ingest/demo-slope/{t:g}/manifest.json"}}}]})}
            for t in rng.permutation(ts)]
        self.hold = []

    def receive_message(self, QueueUrl, MaxNumberOfMessages, WaitTimeSeconds, VisibilityTimeout):
        out, self.waiting = self.waiting[:MaxNumberOfMessages], self.waiting[MaxNumberOfMessages:]
        return {"Messages": out} if out else {}

    def change_message_visibility(self, QueueUrl, ReceiptHandle, VisibilityTimeout):
        self.hold.append(VisibilityTimeout)


def test_backlog_is_processed_in_time_order():
    ts = [i * 1.342857 for i in range(36)]
    sqs = FakeSQS(ts)
    first = sqs.receive_message("q", 10, 20, 600)["Messages"]
    msgs = W.drain_in_order(sqs, "q", first)
    got = [W._message_epoch(m)[1] for m in msgs]
    assert len(got) == 36 and got == sorted(got)
    assert min(sqs.hold) >= 600 + 60 * 36, "the whole batch must stay invisible while it is processed"
