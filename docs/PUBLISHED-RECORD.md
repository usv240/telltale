# Who needs this, from the published record

This is evidence that the need exists and that the method works. It is not an endorsement:
no agency, mine or researcher has evaluated TellTale. Every source below was opened and read
in October 2026. Text in quotation marks is copied from the source; the rest is close
paraphrase. Where a publisher blocked access to the full text, the finding comes from the
abstract and says so. "PDF p." is the page of the PDF file.

## What the record asks for, and where TellTale answers it

| The published need | Source | TellTale |
|---|---|---|
| "simple and low-cost early warning equipment" | Sendai Framework, para 33(b) (2.1) | a 30 to 50 USD camera; cloud cost 0.038 USD per 1,000 epochs |
| Half of people hit by landslides got no warning | World Risk Poll 2023 via UNDRR/WMO (2.4) | warning from surface creep, days to weeks ahead |
| Slope-scale timing information is "mostly lacking" in India; low-cost monitoring pilots wanted | NDMA strategy 2019 (2.6) | per-slope failure window from inverse velocity |
| LEWS rarely reach informal settlements "due to their high costs and complex operation" | Gamperl et al. 2021 (3.1) | one camera, no drilling, a setup page instead of JSON |
| Camera correlation can serve early warning; weather, light and camera motion are its limits | Travelletti et al. 2012 (4.1) | burst stacking, BLIND and BLURRED epochs, CAMERA_EVENT verdict |
| A low-cost camera reported precursor motion before a road-blocking failure | Khan et al. 2021 (4.2) | the same measurement, with a forecast on top |
| Forecasts stated as a window with uncertainty; politicians decide on evacuation | Loew et al. 2025, Brienz (5.1, 6.2) | a bootstrap window, never a timestamp; a person approves every public alert |
| False alarms erode trust; uncertainty estimates improve decisions | Sawada et al. 2022; LeClerc & Joslyn 2015 (6.3, 6.5) | 0 false alarms in 147 quiet days on real data; the agent re-measures before anyone is paged |
| Systems run by trained staff, scientists and practitioners together | Stähli et al. 2015 (6.1) | the duty contact's approve / dismiss links; every decision logged |

## Two corrections this research made to our own claims

- **Radar price.** We had written "radar costing 100k to 500k USD per site" without a source we
  could open. We now say what the sources support: ground-based radar's "relatively high
  operational costs ... often limit their implementation" (Muhammad et al. 2022), mines rarely
  deploy more than one radar per zone "due to the expense" (CSIRO), and a single chain
  inclinometer starts at about 5,000 EUR before drilling (Gamperl et al. 2021).
- **Wayanad toll.** Counts differ by source and date: 392 dead and 150 missing a week after
  (Petley 2024), "over 290 lives" in a 2025 government broadcast. We now write "about 290 to
  400 people died".

---

## 1. The problem is large

**1.1 World Health Organization. *Landslides* (health topic).** https://www.who.int/health-topics/landslides
"Between 1998-2017, landslides affected an estimated 4.8 million people and cause more than
18 000 deaths."

**1.2 Petley, D. (2024). The 30 July 2024 Wayanad landslides in Kerala, India. *The Landslide Blog*, Eos (AGU).** https://eos.org/thelandslideblog/wayanad-landslides
"392 people are known to have died in channelised debris flows, with a further 150 people
reported to be missing"; about 570 mm of rain in two days; 8 km runout. All India Radio gave
"over 290 lives" on 27 March 2025 (https://www.newsonair.gov.in/kerala-foundation-stone-of-township-laid-for-wayanand-survivors).

**1.3 National Disaster Management Authority, India (2019). *National Landslide Risk Management Strategy*.** https://nidm.mha.gov.in/PDF/pubs/NDMA/26.pdf
About 0.42 million km², 12.6% of India's land area, is landslide-prone across 22 states and 2
union territories (PDF p.7), spread over more than 65,000 villages (PDF p.19).

**1.4 USGS (2005). *Landslide Hazards: A National Threat*. Fact Sheet 2005-3156.** https://pubs.usgs.gov/fs/2005/3156/
Landslides "Cost $3.5 billion per year, in 2005 dollars, in damage repair" and "Cause between
25 and 50 deaths in United States annually."

**1.5 McHugh, E.L., Long, D.G., Sabine, C. *Applications of Ground-Based Radar to Mine Slope Monitoring*. NIOSH.** https://stacks.cdc.gov/view/cdc/8543/cdc_8543_DS1.pdf
"While less than 1% of reported mine accidents are associated with slope stability problems,
slope failure accidents were responsible for about 15% of U.S. surface mine fatalities between
1995 and 2003."

**1.6 UNDRR and WMO (2024). *Global Status of Multi-Hazard Early Warning Systems 2024*.** https://www.mhewc.org/wp-content/uploads/2025/12/Global-Status-of-EWS-2024-_opt.pdf
Landslides to end of July 2024 "logged over a thousand fatalities across 95 events" (PDF
p.19-20): "These hazards, which are inherently hard to monitor and predict, are a stark
reminder of the need to improve risk monitoring and forecasting capabilities."

Also cited in the report: Froude, M.J., Petley, D.N. (2018). Global fatal landslide occurrence
2004 to 2016. *NHESS* 18, 2161. doi:10.5194/nhess-18-2161-2018.

## 2. Agencies ask for local, low-cost warning

**2.1 United Nations (2015). *Sendai Framework for Disaster Risk Reduction 2015-2030*, A/RES/69/283.** https://documents.un.org/doc/undoc/gen/n15/167/16/pdf/n1516716.pdf
Target G: "Substantially increase the availability of and access to multi-hazard early warning
systems ... to people by 2030." Para 33(b): develop warning systems "through a participatory
process; tailor them to the needs of users ... promote the application of simple and low-cost
early warning equipment and facilities."

**2.2 WMO (12 November 2025). Early warning systems reach new heights, but critical gaps jeopardize global progress.** https://wmo.int/news/media-centre/early-warning-systems-reach-new-heights-critical-gaps-jeopardize-global-progress
"119 countries, or 60% of all countries, now reporting the existence of a Multi-Hazard Early
Warning System"; disaster deaths are "nearly six times lower in countries with more
comprehensive Multi-Hazard Early Warning System capabilities."

**2.3 United Nations. *Early Warnings for All*.** https://www.un.org/en/climatechange/early-warnings-for-all
Everyone protected by "life-saving early warning systems by the end of 2027"; one of four
pillars is "Detection, observation, monitoring, analysis, and forecasting"; "48 per cent of
least developed countries and 57 per cent of small island developing states" lack adequate
systems.

**2.4 UNDRR and WMO (2024), Box 24, PDF p.87, citing the Lloyd's Register Foundation World Risk Poll 2023.** Same report as 1.6.
Of people who experienced a mudslide or landslide in the past five years, 50% received no
warning, close to earthquakes (49%) and far behind heatwaves (94% warned).

**2.5 Guzzetti, F., Gariano, S.L., Peruccacci, S., et al. (2020). Geographical landslide early warning systems. *Earth-Science Reviews* 200, 102973.** doi:10.1016/j.earscirev.2019.102973 (abstract)
"currently only five nations, 13 regions, and four metropolitan areas benefit from LEWSs, while
many areas with numerous fatal landslides, where landslide risk to the population is high, lack
LEWSs"; "there is no accepted standard to check the performance and forecasting skills of a
LEWS."

**2.6 NDMA (2019), early-warning chapter.** Same document as 1.3.
Information on the precise time of a landslide, which needs instrumentation and real-time
monitoring, is mostly lacking (PDF p.30). India has had hardly any successful real-time
landslide monitoring; the first wired attempt was Mansa Devi, Haridwar, 2006 (PDF p.31).
Rainfall thresholds suit large areas "where there is no possibility to monitor each landslide
individually" (PDF p.32). The task force's outputs include a pilot on "Development and
Evaluation of Low-Cost Landslide Monitoring Solutions" (PDF p.18).

**2.7 ISO 22327:2018. Guidelines for implementation of a community-based landslide early warning system.** Preview: https://cdn.standards.iteh.ai/samples/50064/dd7d5f4a24954dd6a21a30be4023ea96/ISO-22327-2018.pdf
Built on four elements (risk knowledge; monitoring and warning; dissemination; response);
written for communities and for government at province, district, subdistrict and village
level, with the local authority's commitment to keep the system running.

**2.8 Fathani, T.F., Karnawati, D., Wilopo, W. (2016). An integrated methodology to develop a standard for landslide early warning systems. *NHESS* 16, 2123.** doi:10.5194/nhess-16-2123-2016
A seven-sub-system standard, including monitoring and local commitment to operate and maintain
it, used since 2012 in 20 landslide-prone Indonesian provinces and composed "by considering the
limitations of local communities". It is the origin of ISO 22327.

## 3. Conventional monitoring costs too much for these users

**3.1 Gamperl, M., Singer, J., Thuro, K. (2021). Internet of Things Geosensor Network for Cost-Effective Landslide Early Warning Systems. *Sensors* 21, 2609.** doi:10.3390/s21082609 · https://pmc.ncbi.nlm.nih.gov/articles/PMC8068166/
"LEWS have only rarely been implemented in informal settlements due to their high costs and
complex operation." A chain inclinometer starts at "approx. 5000 € excl. drilling"; GB-InSAR,
laser scanning and drone photogrammetry are too complex or too expensive for the Medellín site.

**3.2 Muhammad, M., Williams-Jones, G., Stead, D., et al. (2022). Applications of Image-Based Computer Vision for Remote Surveillance of Slope Instability. *Frontiers in Earth Science* 10, 909078.** doi:10.3389/feart.2022.909078
For ground-based radar and lidar, "the relatively high operational costs of such techniques
often limit their implementation", so "introducing a lower cost technique comparable to
ground-based Lidar and Radar is of great interest."

**3.3 Chidburee, P., Mills, J.P., Miller, P.E., Fieber, K.D. (2016). Towards a low-cost, real-time photogrammetric landslide monitoring system utilising mobile and cloud computing technology. *ISPRS Archives* XLI-B5, 791.** https://isprs-archives.copernicus.org/articles/XLI-B5/791/2016/isprs-archives-XLI-B5-791-2016.pdf
"GB-InSAR is only suitable for application by expert users, is costly, and requires significant
post-processing"; for photogrammetry "the costs associated with instrumentation and maintenance
are considerably lower".

**3.4 CSIRO. Slope monitoring technologies.** https://www.csiro.au/en/work-with-us/industries/mining-resources/mining/slope-monitoring
Several radars on one zone is "rarely done" "due to the expense"; "Often, only a single monitor
is available at a given site." CSIRO's radar-plus-camera prototype is "much more cost-effective
than buying or renting multi-radar monitoring systems."

**3.5 Liu, E., Kull, D., Chaponda, M. (2024). The Triple Dividends of Early Warning Systems and Climate Services. *WMO Bulletin* 73(2).** https://wmo.int/resources/wmo-bulletin/wmo-bulletin-vol-73-2-2024/triple-dividends-of-early-warning-systems-and-climate-services
Citing the Global Commission on Adaptation, early warning has "a cost-benefit ratio of 1:9";
"a US$ 800 million investment in such systems in developing countries" "could prevent annual
losses of US$ 3 billion-US$ 16 billion". These figures are for weather warnings, not landslides.

## 4. Fixed cameras with image correlation measure real slope motion

**4.1 Travelletti, J., Delacourt, C., Allemand, P., et al. (2012). Correlation of multi-temporal ground-based optical images for landslide monitoring: Application, potential and limitations. *ISPRS J. Photogramm. Remote Sens.* 70, 39.** doi:10.1016/j.isprsjprs.2012.03.007 (abstract)
"a low-cost methodology to monitor the displacement of continuously active landslides from
ground-based optical images analyzed with a normalized image correlation technique", checked
against differential GPS at Super-Sauze. "The strongest limitations ... are related to the
meteorological, illumination and ground surface conditions"; "Small movements of the camera ...
are the most important factors affecting the accuracy"; it "offers promising perspectives for
operational applications like, for instance, in early warning systems."

**4.2 Khan, M.W., Dunning, S.A., Bainbridge, R., et al. (2021). Low-Cost Automatic Slope Monitoring Using Vector Tracking Analyses on Live-Streamed Time-Lapse Imagery. *Remote Sensing* 13, 893.** doi:10.3390/rs13050893 (abstract)
At the Rest and Be Thankful (A83, Scotland), a camera every 15 minutes "indicated precursor
slope movement initiated by a rainfall event, a period of quiescence for 10 days, followed by a
large landslide failure" that put "over 3000 tons of sediment" on the road; the approach
"correctly detect[s] and, importantly, report[s] precursor slope movement, allowing early
warning".

**4.3 Hendrickx, H., Elias, M., Blanch, X., Delaloye, R., Eltner, A. (2025). AI-based tracking of fast-moving alpine landforms using high-frequency monoscopic time-lapse imagery. *Earth Surface Dynamics* 13, 705.** doi:10.5194/esurf-13-705-2025
Validated against GNSS and total station at Grabengufer; level of detection "about 0.007 m d−1";
it "did not achieve the millimetre to centimetre accuracy of GNSS and TS measurements". The
camera showed an acceleration seen by the GNSS station was not shared by the whole mass, the
argument for a field over a point.

**4.4 Muhammad et al. (2022)** (3.2). A camera 1.5 km from Plinth Peak (12 images a day)
agreed with satellite InSAR to "less than 20% difference in displacement rate" (20 mm against
16.9 mm over 22 days).

**4.5 Smith, J.B., Delius, I., Mirus, B.B., Baum, R.L. (2020). Time-lapse photography of an active coastal-bluff landslide, Mukilteo, Washington, August 2015 - May 2016. USGS data release.** doi:10.5066/P99QOYL2
Photos "three times daily", motion during "December 8-9, 2015; January 21-30, 2016; and March
9-14, 2016", one of four sites studying "landslide hazards affecting the railway corridor"
between Seattle and Everett. This is the record TellTale runs on in the product.

**4.6 Dematteis, N., Troilo, F., Scotti, R., et al. (2024). The use of terrestrial monoscopic time-lapse cameras for surveying glacier flow velocity. *Cold Regions Sci. Technol.* 222, 104185.** doi:10.1016/j.coldregions.2024.104185 (abstract)
Six Alpine sites using image correlation on fixed cameras: "the high benefit-to-cost ratio of
terrestrial time-lapse cameras". Glaciers, same method.

**4.7 Hermle, D., Keuschnig, M., Krautblatter, M., Bickel, V. (2023). Systematic Quantification and Assessment of Digital Image Correlation Performance for Landslide Monitoring. *Geosciences* 13, 371.** doi:10.3390/geosciences13120371 (abstract)
DIC "can accurately monitor ground displacements", but "DIC algorithms still rely on significant
amounts of expert input", which TellTale's automatic quality control and setup tool address.

## 5. Displacement-based failure forecasts have worked in practice

**5.1 Loew, S., Schneider, S., Josuran, M., et al. (2025). Early warning and dynamics of compound rockslides: lessons learnt from the Brienz/Brinzauls 2023 rockslope failure. *Landslides* 22, 283.** doi:10.1007/s10346-024-02380-z
A Voight velocity model, compared with linear inverse velocity. On 8 May 2023, with more than
half the monitoring points past the 15-day velocity threshold, "it was recommended to the
political decision-makers to evacuate the village of Brienz"; 2 million m³ fell on 15 June;
"the geological and early warning model proved to be correct and applicable also under very
high-risk conditions." Short-term thresholds deviated from the classical creep model because of
spatial heterogeneity.

**5.2 Loew, S., Gschwind, S., Gischig, V., Keller-Signer, A., Valenti, G. (2017). Monitoring and early warning of the 2012 Preonzo catastrophic rockslope failure. *Landslides* 14, 141.** doi:10.1007/s10346-016-0701-y (abstract)
Thresholds from about ten years of displacement data triggered evacuation of an industrial
facility and road closures days before the 210,000 m³ failure of 15 May 2012.

**5.3 Pankow, K.L., Moore, J.R., Hale, J.M., et al. (2014). Massive landslide at Utah copper mine generates wealth of geophysical data. *GSA Today* 24(1), 4.** doi:10.1130/GSATG191A.1
Bingham Canyon, April 2013: "mine operators were aware of the instability and had previously
evacuated the area"; "Fortunately, there were no fatalities or injuries." Williams et al. (2019,
ARMA 19-2881, https://stacks.cdc.gov/view/cdc/225985/cdc_225985_DS1.pdf): "the timing of the
slope failure was predicted, and the subsequent failure was managed with no injuries or loss of
life." Neither source names inverse velocity as the method.

**5.4 Carlà, T., Intrieri, E., Raspini, F., et al. (2019). Perspectives on the prediction of catastrophic slope failures from satellite InSAR. *Scientific Reports* 9, 14137.** doi:10.1038/s41598-019-50792-y
Three failures (open-pit slope, alpine rock slope, tailings dam) showed clear acceleration in
Sentinel-1 data; inverse-velocity fits indicate they could have been anticipated days to weeks
ahead.

**5.5 Intrieri, E., Carlà, T., Gigli, G. (2019). Forecasting the time of failure of landslides at slope-scale: A literature review. *Earth-Science Reviews* 193, 333.** doi:10.1016/j.earscirev.2019.03.019 (abstract)
Two main uses: public safety near landslides and cut slopes over roads and railways, and open-pit
mines, where warnings protect workers without needless stops to extraction.

Also cited in the report: Fukuzono (1985); Carlà, Intrieri et al. (2017) *Landslides* 14, 517.

## 6. People own the decision, and false alarms cost trust

**6.1 Stähli, M., Sättele, M., Huggel, C., et al. (2015). Monitoring and prediction in early warning systems for rapid mass movements. *NHESS* 15, 905.** doi:10.5194/nhess-15-905-2015
Advances become reliable operational systems only with "an adequate well-instructed dedicated
staff", "an intense dialog between scientists, engineers and those in charge of warning", and
systems "jointly operated by scientists and practitioners".

**6.2 Loew et al. (2025)** (5.1). The evacuation letter "makes explicit statements about the
model prediction uncertainty, i.e., a failure of the Insel compartment was expected not on May
23, but between May 15 and June 1, 2023." Scientists recommended; politicians decided.

**6.3 Sawada, Y., Kanai, R., Kotani, H. (2022). Impact of cry wolf effects on social preparedness and the efficiency of flood early warning systems. *HESS* 26, 4265.** doi:10.5194/hess-26-4265-2022
"many false alarms undermine the credibility of the early warning systems"; as skill improves,
efficiency "gets more sensitive to the behavior of social collective trust", so "forecasters
need to determine their warning threshold by considering the social aspects."

**6.4 Sättele, M., Bründl, M., Straub, D. (2015). Reliability and effectiveness of early warning systems for natural hazards. *Reliab. Eng. Syst. Saf.* 142, 192.** doi:10.1016/j.ress.2015.05.003 (abstract)
Reliability is the probability of detection and of false alarm; effectiveness depends on both,
applied to an operating debris-flow warning system.

**6.5 LeClerc, J.E., Joslyn, S.L. (2015). The Cry Wolf Effect and Weather-Related Decision Making. *Risk Analysis* 35, 385.** doi:10.1111/risa.12336 (abstract)
Both very high and very low false-alarm rates worsened decisions; adding a probabilistic
uncertainty estimate improved compliance and decision quality. Evidence on cry-wolf is mixed
across hazards; we treat it as a risk, not a settled fact.

**6.6 Intrieri, E., Gigli, G., Casagli, N., Nadim, F. (2013). Landslide Early Warning System: toolbox and general concepts. *NHESS* 13, 85.** doi:10.5194/nhess-13-85-2013
"practical guidelines to assist end-users with limited experience" in designing a LEWS "at
single slope scale", adapted "to local peculiarities".

## What the record does not say, and how we word it

- Bingham Canyon proves a displacement-based timing prediction with no injuries, not that inverse
  velocity specifically was used.
- Brienz proves velocity forecasts plus a human decision worked; its authors report short-term
  thresholds departing from the creep model, which is why TellTale publishes a window.
- Camera studies report weather, light and camera motion as the main limits, and centimetre (not
  millimetre) field accuracy. TellTale reports the same limits as measured properties.
- The 1:9 benefit-to-cost figure is for weather warnings.
- Opened but not used: Pecoraro et al. (2019) *Landslides* 16, 213 (the claim we wanted is not in
  the abstract). Not opened: Rose and Hungr (2007); the ISO 22328-2:2024 revision page.
