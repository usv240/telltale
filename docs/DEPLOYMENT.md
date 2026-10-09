# Field deployment guide

What we learned from the synthetic sweeps, the USGS Mukilteo record and the confounder tests,
written as instructions for whoever installs the first camera.

## Camera and lens

- Any fixed camera with manual or locked exposure and focus: an old phone with an interval
  app, a Raspberry Pi camera, or an existing CCTV with an RTSP feed. Resolution matters less
  than stability; 1080p is enough.
- Expected precision scales with pixels per millimetre. For a 26 mm-equivalent phone lens at
  1920 px width, one pixel is about 1.4 mm at 100 m and 0.7 mm at 50 m; the estimator's noise
  is a few hundredths of a pixel, so the field floor is set by atmosphere and texture, not the
  camera. A 2x or 3x telephoto halves or thirds those numbers. Run the E2 target test once per
  camera and lens to get the real figure.
- Protect the lens. Mukilteo lost its last three months to a wet lens. Use a hood, a heated
  enclosure where frost or condensation occur, and a wiper or a cloth on the visit schedule.

## Placement

- **Off the slide.** The camera must stand on ground that is not part of the moving mass.
  A camera in the crown (as at Mukilteo) produces CAMERA_EVENT verdicts on exactly the days
  that matter. Opposite slope, a building, bedrock, or a pole set in undisturbed ground.
- Oblique view with a visible stable area in frame: bedrock, buildings, a road surface, a wall
  off the slide. The stabiliser needs it, and so does the operator (next section).
- Distance 20 to 300 m. Closer gives finer displacement but a smaller field of view; the
  target zone should fill a quarter or more of the frame.
- Mount rigidity beats everything. A mount that flexes in wind produces UNSTABLE bursts and
  CAMERA_EVENT epochs; both are reported, neither is useful.

## Site configuration

Use `web/dashboard/setup.html`: load a reference image, draw the STABLE polygons (ground that
cannot move), draw one or more TARGET zones (the slope you care about), enter the scale (two
points of known separation, or the E2 figure), and export `site.json`. Send it with the first
epoch (`upload_epoch.py --site-config site.json`).

- Stable polygons: at least two, in different parts of the frame, each with visible texture.
- Target zones: bare soil or rock face; keep dense vegetation out or let the variance mask
  (`mask_window` in site.json) exclude it after a few epochs.
- Reference mode: `fixed` for scenes that keep their texture for months (rock, built
  structures); `chained` for vegetated or eroding slopes where the scene decorrelates.

## Cadence

- Daily cadence catches creep that takes days to weeks; six epochs a day gives the forecast
  enough points within a day of acceleration; the supervising agent raises cadence on a
  confirmed acceleration through `control.json`.
- Compare like with like: bursts at the same times of day avoid shadow drift. Noon and
  mid-afternoon are the most repeatable.
- Bursts of seven frames a few hundred milliseconds apart; the median stack removes rain
  streaks, birds and single-frame glints.

## What the states mean for the duty contact

| State | Meaning | Action |
|---|---|---|
| QUIET | no displacement above the noise floor | none |
| MOVING | steady creep, no acceleration | note the rate; plan a visit if it is new |
| ACCELERATING | sustained acceleration confirmed over three epochs; agent has investigated | review the evidence; consider raising cadence and warning stakeholders |
| CRITICAL | forecast horizon inside the site threshold with a good fit; a page with approve / dismiss links has been sent | decide; nothing reaches the public until a person approves |
| BLIND / BLURRED / CAMERA_EVENT epochs | the instrument could not measure; the forecast's uncertainty widens | check the camera if it persists; the queue-age and worker alarms cover the cloud side |

## Cost

One c8g.large processes about 50,000 epochs a day; a district fleet of 50 sites at 24 epochs a
day uses under 3 percent of it (about 1.2 USD per site per month if the instance is dedicated,
cents if shared). Storage is a few MB per site per day with raw bursts expiring after 30 days.
Agent investigations cost a few cents each and happen only on events.

## Limits, stated plainly

Creep-type failures in daylight. Brittle and liquefaction collapses can fail without surface
creep. Snow cover, flowing water and dense vegetation decorrelate the image; coverage drops and
the dashboard shows it. This is a warning aid for a person, not a replacement for a geotechnical
assessment.
