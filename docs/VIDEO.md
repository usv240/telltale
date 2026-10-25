# Five-minute video: shot list and script

Rules: at most five minutes; it must show the team, the application working, the architecture
and the principal results. Target 4:30 so the upload never clips. Record the screen at 1080p
and the team on camera at 1080p, and add the voice after the cut. No music under speech.

Three tests the cut must pass:

- **Mute test.** With the sound off, a viewer should still see the product working:
  - the overlay turning blue where the ground moves
  - the forecast window appearing and narrowing
  - the agent opening its two re-measured fields before it pages a person
  - the approve button
- **First four shots are the product,** not infrastructure. The architecture comes after the
  viewer has seen it work.
- **Open with a story the viewer already knows,** and put the result in days and dollars,
  not pixels.

Everything below is on the live site; no tabletop rig is needed. Use
`https://d30le2uwgaimao.cloudfront.net/`. The `?event=latest` link opens the newest
investigation directly.

| Time | Shot (screen) | Voice |
|---|---|---|
| 0:00 | Black, then the Bingham Canyon pit wall (archival photo, credited), then the date "10 April 2013" | "In April 2013, a copper mine in Utah knew when its pit wall would fall. They cleared the pit. Sixty-five million cubic metres came down, and no one was hurt." |
| 0:14 | Wayanad, Kerala, July 2024 (news photo, credited), then the number "about 290 to 400 dead" | "In July 2024, nobody was measuring the hills above Wayanad. Hundreds of people died. The slopes gave the same warning. Nobody was watching." |
| 0:28 | Both team members on camera, one line each | "We're Ground Truth. We built TellTale, which reads that warning with a camera a village can afford." |
| 0:40 | About page hero: the real Mukilteo bluff, blue where the ground moved | "This is a real landslide, the USGS camera on a coastal bluff in Washington, on a day it moved. The blue is the ground TellTale measured moving, to a hundredth of a pixel." |
| 0:58 | Dashboard, demo slope. Press Play on the replay. Overlay goes from grey to blue; displacement curve bends upward | "Here's a slope from quiet to failure. TellTale stacks each burst of photos, removes the camera's own shake, and measures the surface at three thousand points." |
| 1:20 | The failure-forecast chart: dots line up and the window appears and narrows | "When the creep accelerates, one over velocity falls in a straight line toward zero. Where it hits zero is the failure. TellTale publishes a window, not a date, the way the Swiss did at Brienz." |
| 1:42 | The title row: "Zone slope is forecast to fail between t = 49.2 and 51.0, 3.6 days from the last epoch ... a person decides" and the Approve button | "One sentence for the duty officer. Nothing reaches the public unless a person presses this." |
| 1:55 | Agent investigations: open the newest. The two evidence images appear side by side with their numbers | "Before anyone is woken, Claude on Amazon Bedrock checks the warning. It re-runs OpenCV against the previous photo and against the reference: 0.75 pixels, then 5.6, same direction, coherence 0.98. Real motion agrees with itself. Only then does it page a person, and only once for the whole episode." |
| 2:25 | Scroll the trace: remeasure, motion_coherence, check_stabilization, request_human_approval | "Every call, argument and result is in the trace. In our tests, this check paged a person 42 time units before failure, against 3 for alarm thresholds alone, with zero false pages." |
| 2:45 | Mukilteo dashboard: daily motion chart with the confirmed steps in blue; agent list with false alarms | "On the real record it also says no. A hundred and forty-seven quiet days, zero false acceleration alarms. Camera on moving ground, a wet lens: reported as such, never as motion." |
| 3:10 | Setup page: Load an example site; the stable ground and zones appear on the real frame | "An operator sets up a site once from one photo: stable ground here, the slope they care about there." |
| 3:22 | Architecture diagram, left to right | "Bursts go to S3. A queue feeds a Graviton worker running COOL, the cloud-optimised OpenCV from AWS Marketplace. When there's nothing to do, the worker switches itself off and a small function wakes it." |
| 3:45 | Instrument health panel: the COOL build path and the AMI | "Every record names the OpenCV build that ran, on which instance. We measured COOL against stock OpenCV on the same machine and report what we found: faster on features, slightly slower on our warps." |
| 4:00 | A text card: "about 1.40 USD per slope per month · 0 false alarms in 147 quiet days · 0.005 px on the public DIC Challenge" | "About a dollar forty a slope a month. A single borehole sensor starts at five thousand euros." |
| 4:12 | Terminal: `python evaluation/verify_claims.py` scrolling PASS lines | "Every number in this video is checked by one command in the repo." |
| 4:20 | A limits card: "Creep-type failures, in daylight. A person approves every alert." | "It can't warn of brittle collapses, and it can't see at night. It says so." |
| 4:28 | Both team members, the URL | "TellTale. The dashboard is live. Thank you." |

## Assets to collect

- **Archival photos for 0:00 and 0:14.** Use only images whose licence allows reuse, and credit
  them on screen. Wikimedia Commons has Bingham Canyon photos; for Wayanad, use a government or
  agency photo with a credit, or a map.
- **Screen recordings:** the dashboard replay at 1080p (demo slope, Play from the start), the
  newest investigation opened (`?event=latest`), the Mukilteo dashboard, the setup page with
  the example, and the terminal running `verify_claims.py`.
- **Stills:** `docs/gallery/06-architecture.png` and the about-page hero.
- **The motion-magnified clip** (`web/dashboard/figures/magnified.webm`) can replace the 0:58
  overlay shot if it reads better.
