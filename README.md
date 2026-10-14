# shade

A demo that plans outdoor work in Dubai heat. It uses the real shadows of nearby towers, so each work spot has its own heat index every 15 minutes.
Run these in order. The first command needs a network. The others work offline.

1. `uv run python -m shade.osm` downloads building outlines to `data/buildings.geojson`.
2. `uv run python -m shade.build` writes `web/data.json`.
3. `uv run pytest` runs the tests.
4. `python -m http.server -d web 8080`, then open http://localhost:8080.

The site is a made-up concrete frame job, "Plot 7 podium", in Business Bay on 15 July 2026.
Sixteen tasks and fourteen workers are planned from 05:00 to 17:00. Work after 17:00 is overtime.
All three plans stop outdoor work from 12:30 to 15:00, as UAE rules require.

- Blanket ban: only the midday ban applies. Workers can still be over the heat limit in other hours.
- Sun-blind limits: heat limits apply, but the whole site is treated as full sun. Nobody is over the limit, and much work moves to overtime.
- Shade-aware limits: heat limits apply, and each task spot uses its own shade. Nobody is over the limit, and less work moves to overtime.

Each spot and hour has two limits. The first limit says how many minutes of each hour a crew may work there. It comes from the NIOSH rule. The second limit says how long one run may last before a rest. It comes from the PHS model.

## Live weather

The demo uses a clear, dry July day from `data/weather.json`. The file is written by hand. To use the weather of a real day, run this command:

`uv run python -m shade.build --live 2026-10-20`

The command gets hourly weather from Open-Meteo and writes it to `data/weather.live.json`. Open-Meteo needs no key. The date must be in 2022 or later, and at most 16 days from today. A date more than 90 days in the past comes from the Open-Meteo archive.

We ran the build on 4 real summer days of 2025 (15 July, 24 July, 25 July and 2 September). On those days the gain from shade was small. The morning air was already hot and wet, so the heat limits restricted work in the sun and in the shade alike. The demo day has a drier morning, so it shows a better case for shade. Shade helps most when the sun, not the wet air, sets the heat index.

## Sources

Building outlines and heights come from OpenStreetMap through the Overpass API.

1. Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R (2008). Modeling the wet bulb globe temperature using standard meteorological measurements. Journal of Occupational and Environmental Hygiene 5(10):645-655. This paper gives the model for the heat index (WBGT) at each spot.
2. Brimicombe C, Di Napoli C, Quintino T, Pappenberger F, Cornforth R, Cloke HL (2022). thermofeel: a python thermal comfort indices library. SoftwareX 18:101005. This library calculates the model from source 1.
3. NIOSH (2016). Criteria for a recommended standard: occupational exposure to heat and hot environments. DHHS (NIOSH) Publication 2016-106, chapter 8, page 125. This document gives the heat limit for each work rate, as a 1-hour average.
4. Garzon-Villalba XP, Wu Y, Ashley CD, Bernard TE (2017). Ability to discriminate between sustainable and unsustainable heat stress exposures, part 1: WBGT exposure limits. Annals of Work Exposures and Health 61(6):611-620. This study shows that limits of this type separate safe and unsafe heat.
5. Malchaire J, Piette A, Kampmann B, Mehnert P, Gebhardt H, Havenith G, den Hartog E, Holmer I, Parsons K, Alfano G, Griefahn B (2001). Development and validation of the predicted heat strain model. Annals of Occupational Hygiene 45(2):123-135. This model (PHS) gives the time until body core temperature reaches 38 C.

Not built: live map downloads at demo time, clothing factors, workers new to the heat, per-worker heat history, phone layout, a server, task editing.
