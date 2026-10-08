# Demo Rig Design: The Tabletop Collapse

Sub-project: `demo-rig/`. Purpose: a repeatable physical slope failure, on camera, that the
pipeline forecasts live. This is the centerpiece of the 5-minute video and E3.

## 1. Build (target cost under 60 USD)

- Tank: clear acrylic or glass container, roughly 60 x 30 x 40 cm (an aquarium works).
- Slope material: play sand mixed with 10 to 20 percent fine soil or clay for cohesion;
  surface dusted with contrasting speckle (dry coffee grounds or dark sand) so DIC has texture.
- Trigger: slow water infiltration from a drip line or gravity bottle at the crest; flow rate
  controls time-to-failure. Target: quiet phase 10+ minutes, creep phase 5 to 15 minutes,
  collapse. Slower is better for the forecast story.
- Camera: phone or webcam on tripod, locked exposure and focus, 1 to 2 m away, slight
  side-on angle so downslope motion is visible in-image.
- Lighting: two LED work lights at fixed positions; no window light (shadow drift would be a
  confounder we test separately, not accidentally).
- Optional confounder props for E5 captures: a hand-bump of the tripod, a lamp dimmer, a small
  fan with paper foliage at frame edge.

## 2. Capture protocol

- Burst of 7 frames every 20 seconds (scripted; `demo-rig/capture.py` for webcam, or phone
  interval app with burst).
- Scale reference: ruler fixed in-frame on the tank rim (stable region) for mm-per-px.
- Stable regions: tank rim and backboard marked in the site config; target zone: slope face.
- Each run gets a run id; raw frames archived to `evaluation/` storage before any processing.

## 3. Run protocol (per E3 run)

1. Build slope to the marked template lines (repeatability), photograph the dry profile.
2. Start capture, record 10 minutes of quiet baseline.
3. Start drip at the standard rate; do not touch the rig again.
4. Pipeline processes epochs live; dashboard on a second screen shows series and forecast.
5. After collapse, stop capture; both team members independently mark the true failure frame;
   disagreement over 2 frames triggers a joint review.
6. Log: water rate, mix ratio, room temperature, anything anomalous.

## 4. What must be visible in the video cut

- The quiet baseline (nothing moving, system says QUIET).
- The first OOA declaration, with the displacement overlay blooming on the slope face while
  the naked-eye view still looks static. This is the "seeing the invisible" moment.
- The 1 / v line descending, the forecast window appearing, the agent's verification log, the
  approval request.
- The collapse, timestamped, inside the predicted window, side by side with the forecast chart.
- One honest failure clip from an earlier run if a forecast missed, with the explanation.

## 5. Files

```
demo-rig/
  DESIGN.md        this file
  capture.py       webcam burst capture on a timer
  runlog.md        one entry per run: parameters, outcome, true failure time, notes
```
