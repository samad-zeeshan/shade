# shade

A planner for outdoor work in Gulf summer heat. It uses the real shadows of nearby towers, so each work spot has its own heat index every 15 minutes.

Live site: https://samad-zeeshan.github.io/shade/ (code: https://github.com/samad-zeeshan/shade)

## Run it

1. `uv run pytest` runs the tests.
2. `uv run python -m shade.build` plans every site and day. It writes `web/runs.json` and one `web/runs/<site>-<date>.json` per day. The solver works up to 60 seconds per plan, so this can take several minutes.
3. `python -m http.server -d web 8000`, then open http://localhost:8000.

Step 2 is only needed to rebuild the plans. The home page, `web/index.html`, tells the story with a results table. The planner is `web/plan.html`. It has a picker for site and day, a map layer that shows where work is safe, and a download of the plan as a CSV file.

## Sites

There are two made-up jobs, each planned from 05:00 to 17:00. Work after 17:00 is overtime.

- `plot7`, "Plot 7 podium", Dubai (Business Bay). Sixteen tasks and fourteen workers.
- `plot12`, "Plot 12 car park", Abu Dhabi. Twelve tasks and fourteen workers.

Each plan stops outdoor work from 12:30 to 15:00, as UAE rules require. Three plans are compared on every day:

- Ban only: the midday ban is the only rule. Workers can still be over the heat limit in other hours.
- Heat plan: heat limits apply, and every work spot is treated as if it is in full sun.
- Shade plan: heat limits apply, and each work spot uses its own shade.

Each spot and hour has two limits. The first limit says how many minutes of each hour a crew may work there. It comes from the NIOSH rule. The second limit says how long one work period may last before a rest. It comes from the PHS model.

## Real days

Weather comes from the Open-Meteo archive (ERA5). Plot 7 has five days and Plot 12 has two, all in `data/weather/<site>/`. One worker-hour is one worker working for one hour. Extra hours are overtime after 17:00 plus work that moves to a night shift. The solver ran for 60 seconds per plan, and for 240 seconds on 24 July 2025.

| Site | Day | Ban only: worker-hours over the heat limit | Extra hours, heat plan | Extra hours, shade plan |
|---|---|---|---|---|
| Plot 7 | 2025-06-20 | 38.75 | 0 | 0 |
| Plot 7 | 2025-07-24 | 39.25 | 11.25 | 11 |
| Plot 7 | 2026-06-14 | 38.5 | 0 | 0 |
| Plot 7 | 2026-06-28 | 38.25 | 3.5 | 1 |
| Plot 7 | 2026-06-30 | 28.75 | 0.75 | 0 |
| Plot 12 | 2025-06-20 | 12 | 0 | 0 |
| Plot 12 | 2026-06-28 | 23 | 0 | 0 |

1. The midday ban alone is not safe. On every day we tested, workers still went over the heat limit. The total was about 29 to 39 worker-hours a day at Plot 7, and about 12 to 23 at Plot 12. The safe amount is none.
2. Both heat plans fix that. Every worker stays under the limit. On five of the seven days, both plans need less than one extra hour.
3. The shade plan helps most on the hottest day. On 28 June 2026 it needed about 1 extra hour, and the heat plan needed about 3.5. The shade plan also finished 15 of the 16 tasks by 17:00. The heat plan finished 12. That is a clear gain.
4. The humid day, 24 July 2025, is hard for both plans. Each needs about 11 extra hours, because humid air limits work even in the shade. The solver did not prove these two plans are the best possible, so treat this day as a rough result.
5. On the other days, the two heat plans differ by less than one hour. There, the gain from shade is small.

## Build options

- `--only plot7/2026-06-28` rebuilds one run and keeps the other run files.
- `--time-limit 20` sets the solver limit in seconds per plan. The default is 60.
- `--live 2026-10-20 --site plot7` gets that day's hourly weather from Open-Meteo, saves it to `data/weather/plot7/2026-10-20.json` and builds it. Open-Meteo needs no key. The date must be in 2022 or later and at most 16 days from today. A date more than 90 days back comes from the archive.
- `uv run python -m shade.osm --site plot7` downloads building outlines to `data/buildings/plot7.geojson`. It is the only step besides `--live` that needs a network.

Each run file also holds a grid of where work is safe in each 15-minute slot, and how good the solver result is (its status and gap).

## Add a site

A site is one JSON file in `sites/`. Use `sites/plot7.json` as the example. Its fields:

- `id`, `name`, `city`: the short name, the label shown on the page and the city.
- `center` as `[lon, lat]` and `bbox_half_deg` as `[lon, lat]`: the box around the center where building outlines are downloaded.
- `plot_center`, and an optional `plot` outline as a ring of `[lon, lat]` points.
- `shift_end_slot`: the slot where the shift ends. Slot 0 is 05:00 and each slot is 15 minutes, so 48 is 17:00.
- `ban_slots`: the first and last slot of the midday ban. `[30, 39]` is 12:30 to 15:00.
- `tasks`: each has `id`, `name`, `lat`, `lon`, `cls` (`light`, `moderate` or `heavy` work), `crew` (people needed), `slots` (length in slots), `trade` and `after` (ids of tasks that must finish first).
- `workers`: each has `id`, `name` and `trades`.

Then run `uv run python -m shade.osm --site <id>`, add weather files to `data/weather/<id>/`, and run the build. A site must be in UTC+4 and between 54°E and 60°E. The map projection covers only that zone, and the midday ban is a UAE rule. Doha and Riyadh are not supported yet.

## Sources

Building outlines and heights come from OpenStreetMap through the Overpass API.

1. Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R (2008). Modeling the wet bulb globe temperature using standard meteorological measurements. Journal of Occupational and Environmental Hygiene 5(10):645-655. This paper gives the model for the heat index (WBGT) at each spot.
2. Brimicombe C, Di Napoli C, Quintino T, Pappenberger F, Cornforth R, Cloke HL (2022). thermofeel: a python thermal comfort indices library. SoftwareX 18:101005. This library calculates the model from source 1.
3. NIOSH (2016). Criteria for a recommended standard: occupational exposure to heat and hot environments. DHHS (NIOSH) Publication 2016-106, chapter 8, page 125. This document gives the heat limit for each work rate, as a 1-hour average.
4. Garzon-Villalba XP, Wu Y, Ashley CD, Bernard TE (2017). Ability to discriminate between sustainable and unsustainable heat stress exposures, part 1: WBGT exposure limits. Annals of Work Exposures and Health 61(6):611-620. This study shows that limits of this type separate safe and unsafe heat.
5. Malchaire J, Piette A, Kampmann B, Mehnert P, Gebhardt H, Havenith G, den Hartog E, Holmer I, Parsons K, Alfano G, Griefahn B (2001). Development and validation of the predicted heat strain model. Annals of Occupational Hygiene 45(2):123-135. This model (PHS) gives the time until body core temperature reaches 38 C.
6. Open-Meteo archive (ERA5 reanalysis) for the weather of each real day.

Not built: clothing factors, workers new to the heat, per-worker heat history, task editing in the page, Doha and Riyadh.
