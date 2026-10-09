# Second-idea research, October 9, 2026

Planning exercise only; TellTale is the entry. Four parallel web-research passes on
October 9 (sources at the end of each section). Criteria, in the order the rubric weights them:
classical OpenCV 5 depth, measurable real-world impact with a citable number, a public dataset
with ground truth that two people can validate against in two weeks, low collision with other
entrants and with products, and a credible COOL (classical imgproc at scale) and agentic
(vision result changes the next action) story.

## 0. What the field looks like (scan of 33 public entry repos, October 9)

The Devpost gallery is hidden until the deadline and the hashtag has no indexed posts, so the
only signal is GitHub. Crowded themes: inspection agents with accept, retake, escalate loops
(about nine teams), workplace-safety cameras (four), road and traffic (five), healthcare and
eldercare (five). Thin: wildlife, water quality, rip currents, sports form, dataset auditing.
Empty: agriculture, energy, SLAM and digital twins, physics-informed video prediction,
geohazards. No other landslide, slope or DIC entry was found. Nearest neighbour:
`TusharTechs/tremorcv`, machine vibration from handheld video by phase correlation with a
measurement-quality agent and COOL on Graviton, i.e. the same technique family and the same two
special awards. TellTale's separation from it is the forecast (a failure time, not a spectrum),
the geoscience validation on a real landslide, and the human-approval loop.

## 1. Candidates examined

### 1.1 Crowd-crush precursor from the physics of dense crowds

The science is new and real: Gu, Guiselin, Bain, Zuriguel and Bartolo, "Emergence of
collective oscillations in massive human crowds", Nature 638:112 (February 2025, open access).
Above about 4 people per square metre, a dense crowd starts to oscillate collectively with a
period near 18 seconds, about half an hour before the San Fermín opening ceremony, and the same
oscillations appear in the Love Parade 2010 footage. The authors propose monitoring that
spectral peak on raw video, which is a classical-CV measurement (optical flow or PIV on a
homography-corrected grid, a sliding spectrum) that COOL would accelerate and an agent could act
on (re-task cameras, escalate to stewards). Impact is beyond doubt: 7,069 deaths in 215 events
from 1980 to 2007 (Hsieh 2009), Itaewon 2022 (159), Mina 2015 (769 official), and at least 250
deaths in 2024 and about 185 in 2025. Collision is moderate: density alerting is commoditised
(Seoul runs over a thousand people-counting cameras; several vendors), Krausz and Bauckhage 2012
did optical flow on Love Parade footage, but no published system implements the oscillation
precursor from video, and no hackathon project since 2017 touches crowd crush. The weakness is
validation: the Zenodo release (CC BY 4.0) contains one 51 MB positive video plus the paper's
spectra, no negative-control footage, and no public dataset anywhere pairs incident ground truth
with density. A false-positive rate, the one number that pattern 4 demands, cannot be measured;
camera shake mimics the oscillation; and the authors themselves say other venues are untested.
Verdict: the best new-science idea in the set and the one I would pick for a future competition
with more time to film negatives, but it cannot be made honest in two weeks.

### 1.2 Glacial lake outburst flood warning from fixed cameras

Impact is real and large: about 15 million people live within reach of a glacial-lake flood
path (Taylor et al. 2023, Nature Communications); South Lhonak, October 2023, released tens of
millions of cubic metres, killed dozens, destroyed a 1,200 MW dam, and had no warning system at
the lake. Classical CV precedent exists (ISPRS 2014: edge-detected waterline from stereo
time-lapse, decimetre precision against a gauge). But there is no public image archive to
validate on: the only recurring public ice-dammed-lake camera (Suicide Basin, Juneau) shows
only the latest image, and ICIMOD material is satellite-only. Operational systems in Nepal,
Pakistan, Bhutan and Peru are sensor-and-siren, not vision. Verdict: strongest impact number
of the set, near-zero validation data; a proposal, not a two-week build.

### 1.3 Glide-snow avalanche precursor from webcam archives

Public data exists (Fox et al. 2024, University of Innsbruck, 4,090 labelled photos, GPL-3
code) but it is single photos of released avalanches, not time series; the 14-year SLF Dorfberg
archive is not public. The decisive finding is scientific: Fees et al. 2023 report that 54
percent of glide avalanches released with no visible prior crack, which undercuts the
days-of-warning premise. Detection is already covered by Hafner 2024 and a commercial camera
system (CADS). Verdict: better data than GLOF, weaker physics, and the warning claim cannot be
made honestly.

### 1.4 Camera as accelerometer: video modal analysis for structural health

The classical lineage is exactly what the judges like (Eulerian magnification 2012,
phase-based motion processing 2013, Chen et al. 2015 modal identification against nine
accelerometers), and a CC BY 4.0 dataset with video plus accelerometers plus impact hammer
exists (CAMELOT, Zenodo 10412857, 3.9 GB). Impact numbers are easy: 47,052 structurally
deficient US bridges carrying 178 million crossings a day (ARTBA 2025), wired monitoring at
more than 15,000 USD per channel. The problem is collision: RDI Technologies' Iris M is a mature
patented product, there are at least five open-source implementations, and at least two
hackathon projects (Smart India Hackathon 2023, a Devpost entry around 2024) built
magnified-video-plus-FFT already. One entrant in this competition (tremorcv) is adjacent.
Verdict: scores on depth and datasets, loses on originality unless the novelty is calibrated
metric displacement plus an agent that re-aims and re-measures, which is TellTale's own recipe
applied to a crowded field.

### 1.5 Six unexpected candidates from the scout pass

| Idea | Physics | Public dataset | Impact number | Collision |
|---|---|---|---|---|
| Sky-camera solar ramp nowcasting | cloud motion vectors by optical flow, sun-occlusion geometry, 5 to 15 min PV forecast | SKIPP'D (Stanford), sky video at 20 fps with 1-min PV power, CC BY 4.0 | 25 percent better solar forecast is about 46.5 M USD/yr lower CAISO generation cost (Yang et al. 2017) | heavy academic and commercial (Reuniwatt); no hackathon projects |
| Infant respiratory-rate instrument | chest optical flow, spectral peak, breaths per minute for the WHO fast-breathing test | AIR-125 / AIR-400 (Northeastern), 400 videos with breathing waveforms; dataset terms unstated | pneumonia kills over 700,000 under-fives a year (UNICEF 2024) | research and products (Nanit); no hackathon projects |
| Hand-tremor frequency and amplitude from phone video | phase correlation of the hand region, FFT peak at 3 to 7 Hz | TIM-Tremor, 910 videos, 55 patients, wrist accelerometer truth; licence unconfirmed, landing page down | over 10 million people with Parkinson's (Parkinson's Foundation) | tremorcv does machines; no hand-tremor hackathon projects found |
| Camera as fog visibility meter | Koschmieder contrast decay of landmarks at known range | Brno Fog Visibility Dataset, fixed road scene, CC BY 4.0; DENSE fog-chamber frames | 38,700 fog crashes and about 600 deaths a year in the US (FHWA) | patents exist; no hackathon projects |
| Shoreline-retreat rate from citizen photos | homography rectification of oblique shots, waterline detection, metres per year | SCLabels and SCShores (Zenodo 10159978), GNSS-validated shorelines | 24 percent of sandy beaches eroding over 0.5 m/yr (Luijendijk 2018) | CoastSnap exists (MATLAB); no hackathon projects, no agent |
| Wind speed from flag and tree motion | optical-flow spectral energy against an anemometer | "Seeing the Wind" (Stanford), flags and canopy with 1-min anemometer | Africa has one eighth of the WMO minimum station density | one NeurIPS paper; nothing else |

## 2. Scoring against the criteria

Scores 1 to 5. "Validation" means a public ground truth two people could score against in two
weeks; "collision" is inverted (5 = empty field).

| Idea | Classical depth | Impact | Validation | Collision | COOL fit | Agentic fit | Total |
|---|---|---|---|---|---|---|---|
| TellTale (for reference) | 5 | 5 | 4 (real USGS record, physical E2 and E3 pending) | 5 | 5 | 5 | 29 |
| Crowd-crush precursor | 4 | 5 | 2 (one positive video, no negative control) | 4 | 4 | 4 | 23 |
| GLOF camera warning | 4 | 5 | 1 | 5 | 4 | 4 | 23 |
| Glide-avalanche precursor | 3 | 3 | 2 | 4 | 3 | 3 | 18 |
| Camera as accelerometer | 5 | 4 | 5 | 1 | 5 | 4 | 24 |
| Solar ramp nowcasting | 4 | 4 | 5 | 2 | 4 | 4 | 23 |
| Infant respiratory rate | 3 | 5 | 4 (terms unclear) | 3 | 3 | 4 | 22 |
| Hand tremor from video | 3 | 4 | 3 (licence unconfirmed) | 4 | 3 | 3 | 20 |
| Fog visibility meter | 4 | 4 | 4 | 4 | 4 | 4 | 24 |
| Shoreline retreat from photos | 4 | 4 | 5 | 3 | 4 | 3 | 23 |
| Wind from flag motion | 3 | 3 | 4 | 5 | 3 | 3 | 21 |

## 3. Reading of the table

- Nothing researched beats the entry we have. Every alternative gives up at least one of:
  public validation data (GLOF, glide), an empty field (vibration, solar), or impact
  (wind, shoreline). TellTale is the only one with all six.
- The crowd-crush precursor is the most exciting science in the set and the one to revisit
  when a negative-control recording can be arranged; without it the headline would be a claim,
  not a measurement.
- The two ideas worth keeping on file for a future competition are the fog visibility meter
  (clean physics, open dataset, lethal problem, empty hackathon field, obvious cloud deployment
  on highway cameras) and shoreline retreat from citizen photos (open GNSS-validated data, a
  measurement, and a homography story Bradski would enjoy), followed by solar ramp nowcasting
  if the sponsor is an energy company rather than OpenCV.
- The judge's-eye test applied to the whole table: the idea that reads as "a camera became an
  instrument that was right about the real world and quiet when it should have been" wins.
  Only TellTale can say that today, with numbers.

## 4. What this exercise changes about TellTale

- Name tremorcv in our own positioning and make the forecast-plus-geoscience separation
  explicit on the submission page.
- Keep the real-landslide-in-the-product demo as the centrepiece; it is the thing no entrant
  in the scan has.
- The fog meter and shoreline ideas stay in this file as the next competition's candidates.
