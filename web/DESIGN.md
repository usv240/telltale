# Web Design: Landing Site and Dashboard

Sub-project: `web/`. Two deliverables served as one static site:

1. **Landing site** (`web/landing/`): the educational front door. A first-time visitor, judge or
   villager, should understand the problem, the physics, the system, and the evidence, end to
   end, without prior knowledge.
2. **Dashboard** (`web/dashboard/`): the instrument view. One screen answers "is this slope
   okay right now", with expert drill-down.

Both are plain HTML, CSS, and vanilla JavaScript. No build step, no framework: judges can open
the repo, open the file, and see everything. Deployed to S3 + CloudFront by the infra stack; the
same files open locally from disk for development and for offline judging.

## 1. Non-negotiable UX requirements (from the team brief)

- Light and dark mode: `prefers-color-scheme` default plus a persistent three-state toggle
  (system, light, dark) stored in localStorage. Every color comes from CSS custom properties;
  both themes meet WCAG AA contrast.
- Mobile and desktop: responsive from 320 px to wide desktop. Single column on phones,
  multi-column grids on desktop. Charts and diagrams scroll inside their own containers rather
  than stretching the page.
- Info buttons everywhere: every non-obvious term, metric, chart axis, and control carries a
  small "i" button that opens a short plain-language explainer. One popover component, keyboard
  accessible (Enter opens, Escape closes), screen-reader labeled, click-outside closes. The
  same content set doubles as the glossary page section.
- Plain language first: every section leads with one sentence a non-expert understands, then
  the detail. Reading order works aloud (semantic HTML, landmarks, alt text on every figure).
- No emojis. No em dashes. Consistent hyphen and comma punctuation.

## 2. Landing site: page structure

Single page with anchored sections plus the dashboard as a second page.

1. **Hero**: "See the ground move before it fails." One paragraph of what TellTale is. Two
   actions: "Open the live dashboard" and "How it works". A line acknowledging the competition
   context (OpenCV AI Competition 2026, powered by AWS).
2. **Three stories** (the case for the problem): Bingham Canyon 2013 (watched, evacuated, zero
   deaths), Brienz 2023 (watched, evacuated, zero deaths), Wayanad 2024 (unwatched, about 290 to 400
   deaths). Cards with dates, one-line outcomes, info buttons carrying sources.
3. **What TellTale does**: five-step walkthrough with simple inline SVG illustrations:
   capture bursts, stack, stabilize, measure sub-pixel motion, forecast. Each step has an info
   button with the deeper technical sentence and a link to the design doc.
4. **The physics, in one chart**: an explainer of the inverse-velocity method with an inline
   SVG chart: velocity accelerating, 1 / velocity descending toward zero, the intercept marked
   "predicted failure time", the uncertainty band shaded. Text explains why the method is
   trusted (used in mining for decades) and where it does not apply (brittle failures), with
   references.
5. **The evidence**: E1 through E6 as cards, each with status (planned, running, done), the
   headline number once measured, and a link to the method. This section is honest by design:
   it shows what is proven and what is pending.
6. **The system**: architecture diagram (responsive SVG version of the infra diagram), with
   info buttons on each node, plus the COOL and Agentic Vision paths explained.
7. **Try it**: how a judge can run the demo: open dashboard demo mode, or clone and
   `make demo`. Includes the sample-data note.
8. **Responsible use and limitations**: privacy by design, alert governance, creep-only scope,
   blindness reporting. Written as commitments, not marketing.
9. **FAQ**: native `details` accordions. "Why not satellites", "Why not just rain gauges",
   "What camera do I need", "What does it cost", "What happens at night".
10. **Glossary**: every info-button term in one alphabetical list.
11. **References**: the numbered bibliography with links (same set as the proposal and
    RESEARCH.md).
12. **Team footer**: Ground Truth, members, contact, repo link.

## 3. Dashboard: information design

Audience order: duty officer first, expert second, judge always.

- **Header**: site selector, alarm state chip (QUIET, MOVING, ACCELERATING, CRITICAL, BLIND),
  "agent online" badge, theme toggle, "guided tour" button that walks a new user through every
  panel with the info-popover system.
- **Panel 1, Status**: the one-sentence answer ("No significant movement in zone A for 62
  days" or "Zone A accelerating; forecast window Oct 12 to Oct 15; awaiting human approval"),
  with the current camera image and displacement overlay slider (before and after).
- **Panel 2, Series**: displacement and velocity charts per zone with uncertainty bands,
  rendered with a small dependency-free SVG chart helper (no chart framework). Axis info
  buttons explain units and smoothing.
- **Panel 3, Forecast**: the 1 / v chart with fit line, intercept, and shaded window, plus fit
  quality. Empty state explains what will appear here and why it is empty now.
- **Panel 4, Agent log**: the decision log rendered verbatim: events, tool calls, verdicts,
  evidence packet links, approval history. This panel is the Agentic award trace made public.
- **Panel 5, Instrument health**: valid-subset fraction, stabilization inliers, blindness
  calendar, capture cadence. The honesty panel.
- **Demo mode**: a toggle that replays the bundled synthetic collapse and Mukilteo excerpt so
  the dashboard is fully explorable with no cloud connection. Judges land here first.

Data contract: the dashboard reads static JSON artifacts (`site.json`, `series.json`,
`forecast.json`, `agentlog.json`, overlay PNGs) from either the local `demo-data/` folder or
the deployed read-only API. Same schema both ways; the pipeline CLI writes exactly this schema.

## 4. Visual system

- Typography: system font stack. Sizes step 14 to 40 px with a fluid scale.
- Color tokens: neutral slate ground, one earth-orange accent (the identity carried over from
  the proposal), semantic colors for alarm states with AA contrast in both themes
  (QUIET slate, MOVING blue, ACCELERATING amber, CRITICAL red, BLIND gray with pattern, so
  state is never conveyed by color alone: chips carry text labels always).
- Motion: none beyond small transitions; charts draw instantly. `prefers-reduced-motion`
  respected.
- Iconography: minimal inline SVG line icons; no icon font, no emoji.

## 5. Files

```
web/
  DESIGN.md            this file
  shared/
    theme.css          tokens, light/dark, layout primitives
    ui.js              theme toggle, info-popover component, tour
  landing/
    index.html
    landing.css
    landing.js
  dashboard/
    index.html
    dashboard.css
    dashboard.js
    charts.js          tiny SVG chart helper (line, band, intercept marker)
    demo-data/         bundled JSON + PNG artifacts for demo mode
```

## 6. Acceptance checklist

- Opens from file:// with no server and no network, in both themes, at 320 px and 1440 px.
- Keyboard-only pass: every control reachable, popovers open and close, tour completes.
- A person who has never heard of the project can answer, after five minutes: what problem
  this solves, how the measurement works, what the forecast chart means, what the agent does,
  and what the system cannot do. This is user-tested on at least three people before submission.
- Lighthouse accessibility score 95 or above on both pages.
