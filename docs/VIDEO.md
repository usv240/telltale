# Five-minute video: shot list

Rules: at most five minutes; must show the team, the application working, the architecture,
and the principal results. Target 4:40 so the upload never clips. Record screen at 1080p,
camera at 1080p, voice-over after the cut. No music under speech.

| Time | Shot | Voice (plain language) | On screen |
|---|---|---|---|
| 0:00 | Both team members to camera, one line each | "We are Ground Truth. TellTale turns any camera into an instrument that says when the ground will fail." | Names, roles |
| 0:12 | Three stills: Bingham Canyon, Brienz, Wayanad | "When slopes are watched, nobody dies. Watching costs half a million dollars a site. Wayanad was not watched. Four hundred people died." | Dates, outcomes, sources |
| 0:40 | Tabletop rig, wide shot, quiet phase | "This is a slope in a tank. Nothing is moving that you can see." | Rig, camera, drip line |
| 0:55 | Dashboard, Status panel, QUIET | "TellTale compares bursts of photos and measures movement a hundredth of a pixel wide." | Overlay flat blue |
| 1:10 | Split screen: rig video and dashboard overlay blooming red | "Water goes in. The surface starts to creep, millimetres, invisible to the eye, obvious to the instrument." | Overlay colour spreading, arrows |
| 1:35 | Displacement chart with onset marker | "When the creep accelerates, physics takes over. Velocity goes up; one over velocity falls in a straight line toward zero." | Series chart, OOA line |
| 1:55 | Inverse-velocity chart with window | "Where that line hits the axis is the forecast. The band is our honest uncertainty." | Forecast t, window |
| 2:10 | Rig collapse, timestamped, chart beside it | "The slope failed here, inside the window the system published before it moved visibly." | Collapse frame, forecast chart |
| 2:35 | Architecture diagram, pan across lanes | "A camera uploads bursts to S3. An SQS queue feeds a Graviton worker running OpenCV 5. Classical vision only: no neural network anywhere. Results go to a static dashboard through CloudFront." | docs/architecture.svg |
| 3:00 | Instrument health panel | "Every epoch records which OpenCV build ran, on which instance, with which AMI. This is the COOL evidence: the core workload on Graviton." | cv2 path, build hash, c8g.large |
| 3:15 | E6 table | "Stock OpenCV versus COOL on the same c8g instance, same pixels. Epochs per hour, cost per thousand epochs, nights of monitoring per dollar." | E6 numbers |
| 3:35 | E1 and E5 tables | "Synthetic accuracy: a hundredth of a pixel. Camera bump, lighting change, fog: zero false alarms. Lens distortion: partially caught, documented as a failure." | Result tables |
| 4:00 | Mukilteo real imagery with overlay | "On USGS time-lapse of a real coastal bluff, the measured motion lines up with the documented movement periods." (only if E4 holds up; otherwise cut) | Overlay on real frame |
| 4:20 | Limitations card | "What it cannot do: brittle failures, nights, fog. It never alerts the public on its own; a person approves." | Bullet card |
| 4:35 | Dashboard URL, repo, both members | "The dashboard is live. The code is pinned and reproducible. Thank you." | URL |

Assets to capture before editing: rig run with clean collapse (E3 run 1 or best run), screen
recordings of the dashboard at three states, architecture SVG exported to PNG at 1920 wide,
result tables rendered from the JSON in `evaluation/results/`.
