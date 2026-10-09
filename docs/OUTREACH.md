# Pilot outreach

Send from the team lead's address. Two versions: a disaster-management office and a researcher.
Keep it under 200 words; the dashboard link does the talking. Ask for a 20-minute call, not a
commitment. Any written reply is impact evidence for the report.

## A. District or state disaster-management office

Subject: Low-cost slope-movement early warning: 20 minutes for a pilot conversation?

Dear [name / office],

I am part of a two-person team building TellTale, an open early-warning instrument for
creep-type slope failures. It uses a fixed camera (a phone or existing CCTV) and classical
computer vision to measure ground movement of a few millimetres, then applies the
inverse-velocity method that mines use with radar to forecast a failure window. A person
approves every alert; nothing goes to the public automatically.

It is running now on a cloud instance and on public USGS imagery of an active bluff:
https://d30le2uwgaimao.cloudfront.net/about.html

We are entering it in the OpenCV AI Competition 2026 and would like to ground it in a real
need. Could we have 20 minutes with someone who deals with hillside, road-cut or retaining-wall
monitoring in [district]? We would like to understand which slopes you worry about, what a
useful warning looks like to you, and whether a camera pilot on one slope this season would be
welcome. There is no cost; the hardware is a camera and a mount.

Thank you for your time,
[name], Team Ground Truth
[phone] · [email] · https://github.com/usv240/telltale

## B. Researcher (USGS landslide hazards, state geological survey, university geotechnics)

Subject: Camera DIC on the Mukilteo time-lapse: results and a question

Dear Dr [name],

We ran a dense sub-pixel image-correlation pipeline over the public Mukilteo coastal-bluff
time-lapse (ScienceBase 5ef2388382ced62aaae3bbbe). Chaining consecutive noon frames, the
landslide body shows daily motion of about 0.9 px on 9 December 2015 and 1.2 px on 23 January
2016 against a quiet-day median of 0.13 px, with coherent downslope vectors; the wet-lens
period from February is rejected automatically. Figures and method:
https://github.com/usv240/telltale/blob/master/docs/REPORT.md

The pipeline is part of TellTale, a low-cost early-warning instrument we are building for the
OpenCV AI Competition 2026 (inverse-velocity forecasting, human-approved alerts).

Two questions, if you have a moment: do the dates above match your record of movement at the
site, and is there a slope you would want watched by a camera this season where our results
could be compared with your instruments? We would be glad to share data and code.

With thanks,
[name], Team Ground Truth
[email] · https://d30le2uwgaimao.cloudfront.net/
