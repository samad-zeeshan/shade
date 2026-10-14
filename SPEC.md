# shade: heat-dose scheduling with a moving shadow map

A hackathon demo. A construction site in Dubai. The sun moves, building shadows move, every task location has its own hourly heat index. A solver assigns workers to tasks so nobody breaks the heat limit, and the schedule beats the blanket midday ban on both safety and overtime.

The demo must look expensive and must work offline. Everything is precomputed into one JSON. The web page is static.

## Repo

`c:\Users\samad\Desktop\projects\Test\shade` (already created with `uv init`, Python 3.12, deps: ortools, shapely, pyproj, numpy, httpx, pytest). Use `uv run` for everything. Do not add dependencies beyond these without a one-line reason in your report. Node is available but there is no build step: the web page uses pinned CDN scripts only.

```
shade/
  SPEC.md                 this file
  pyproject.toml
  src/shade/
    __init__.py
    sun.py                solar position
    osm.py                Overpass fetch -> data/buildings.geojson  (run once)
    shadow.py             shadow polygons and per-task shade fraction
    wbgt.py               weather profile and WBGT model
    limits.py             ACGIH work/rest table -> per-slot load
    scenario.py           site definition: tasks, workers, shift, ban
    solve.py              CP-SAT model, three scenarios
    build.py              orchestrates everything -> web/data.json
  tests/
  data/
    buildings.geojson     real OSM footprints with heights, committed
    weather.json          hourly profile for the demo day, committed
  web/
    index.html  app.js  style.css  data.json
  README.md
```

Entry points:

```
uv run python -m shade.osm        # fetch buildings once (needs network)
uv run python -m shade.build      # everything else, offline, writes web/data.json
uv run pytest
python -m http.server -d web 8080 # open http://localhost:8080
```

Git: repo is initialised. Executors never commit. The integrator commits.

## Shared constants

- Site centre: lat 25.1860, lon 55.2650 (Business Bay, Dubai). Bounding box: centre ± 0.0035 deg lat, ± 0.0040 deg lon (about 780 m by 800 m).
- Demo day: 2026-07-15. Timezone fixed offset UTC+4. No DST.
- Projected CRS for all metre geometry: EPSG:32640 (UTM 40N). Output back to EPSG:4326 for the web.
- Time grid: 15-minute slots from 05:00 to 20:00 inclusive start times. Slot index `s` in 0..59, slot start = 05:00 + 15·s min. Slot 0 = 05:00, slot 28 = 12:00, slot 48 = 17:00.
- Shift: 05:00 to 17:00 (slots 0..47). Slots 48..59 are overtime.
- UAE midday ban: no outdoor work 12:30 to 15:00 (slots 30..39 inclusive, since 12:30 = slot 30, 15:00 = slot 40). Applies in every scenario.
- Rolling-hour budget: any 4 consecutive slots.

## Physics and tables

### sun.py

`sun_position(lat, lon, dt_utc) -> (azimuth_deg, elevation_deg)`. Azimuth clockwise from north, 0..360. Use the NOAA solar calculator equations (fractional year, equation of time, declination, hour angle, then elevation and azimuth). No library. Precision 0.5 deg is enough.

Test anchors (tolerance 1.5 deg): Dubai 2026-07-15, 12:20 local (08:20 UTC) solar noon elevation about 86. 06:00 local elevation about 3 to 8 and azimuth about 65. 18:00 local elevation about 15 to 20 and azimuth about 290. Sunset about 19:10 local.

`sun_table()` returns a list of 60 dicts `{slot, azimuth, elevation}` evaluated at slot midpoints (start + 7.5 min).

### shadow.py

Input: buildings as list of `(shapely Polygon in metres, height_m)`. For sun elevation `el > 1 deg`: shadow length `L = h / tan(el)`, capped at 600 m. Shadow direction vector points away from the sun: `d = L · (−sin(az), −cos(az))` in east-north metres (sun at azimuth az means shadow goes toward az+180).

Shadow polygon of one building = union of the footprint, the footprint translated by d, and for every edge (p_i, p_{i+1}) the quad (p_i, p_{i+1}, p_{i+1}+d, p_i+d). Do not use convex hull (L-shaped towers would be wrong). Union all buildings per slot into one MultiPolygon, simplify with tolerance 0.5 m. When elevation ≤ 1 deg the shadow is "everything": return a flag `night=True` and no polygons.

`shade_fraction(point_m, shadow_union, radius=6.0)`: area of the 6 m disc around the point that lies inside the shadow union, divided by disc area, in 0..1. Night → 1.0.

Tests: a 10 m by 10 m box 30 m tall at elevation 45, azimuth 180 (sun due south) casts a shadow whose northern edge is at y = 10 + 30 = 40. A point at (5, 25) has shade fraction 1.0. A point at (5, 60) has 0.0. At azimuth 90 the shadow extends toward −x.

### wbgt.py

Weather profile `data/weather.json`: hourly values 05:00..20:00 for a typical clear July day in Dubai. Fields per hour: `ta_c`, `rh_pct`, `wind_ms`, `ghi_wm2`. Target shape: Ta 32 at 05:00, 34 at 07:00, 39 at 10:00, 42 at 13:00, 43 at 15:00, 40 at 18:00, 36 at 20:00. RH 62 at 05:00 falling to 28 at 15:00, back to 45 at 20:00. Wind 2.5 to 5 m/s, peaks mid afternoon. GHI 0 before sunrise, 950 at 12:00, bell shaped, 0 after 19:15. Linear interpolation to slot midpoints.

WBGT model: Ono and Tonouchi (2014), outdoor regression,

```
WBGT = 0.735·Ta + 0.0374·RH + 0.00292·Ta·RH + 7.619·SR − 4.557·SR² − 0.0572·WS − 4.064
```

Ta in °C, RH in %, SR solar radiation in kW/m², WS wind in m/s. Verify the coefficients with one web lookup and cite the paper in a comment. If you cannot verify, keep these values and say so in your report.

Effective solar radiation at a task location: `SR = ghi·(1 − f) + 0.15·ghi·f` where `f` is shade fraction (diffuse light still reaches shade). Wind in shade: unchanged.

`wbgt_table(tasks, shade_fractions) -> wbgt[t][s]` in °C, one decimal.

Sanity anchors at 13:00, full sun: WBGT 34 to 36. In full shade at 13:00: 31.5 to 33. At 06:00: 28 to 30. If outside these bands, say so in the report rather than tuning the weather silently.

### limits.py

Metabolic classes and ACGIH TLV screening thresholds for acclimatised workers (WBGT °C). Work fraction allowed per hour given WBGT:

| class  | M (W) | 100% | 75% | 50% | 25% |
|--------|-------|------|-----|-----|-----|
| light  | 180   | 31.0 | 31.5 | 32.0 | 32.5 |
| moderate | 300 | 28.0 | 29.0 | 30.0 | 31.0 |
| heavy  | 415   | 26.0 | 27.5 | 29.0 | 30.0 |
| very_heavy | 520 | 25.0 | 26.0 | 27.5 | 29.0 |

Rule: the allowed work fraction is the largest column whose threshold ≥ WBGT. Above the 25% column: 0% (no work). Verify the table once against the ACGIH TLV 2017 heat stress table; adjust if it differs and say so.

`load(wbgt, cls) -> int` in twelfths of an hour: 100% → 12, 75% → 16, 50% → 24, 25% → 48, 0% → None (forbidden). Meaning: one 15-minute slot of work costs this much of a 48-unit rolling-hour budget. This makes the solver constraint linear: for every worker and every window of 4 consecutive slots, sum of loads ≤ 48.

Worked check: at 50% allowed, a slot costs 24, so 2 of 4 slots fit. At 25%, 1 of 4.

## Scenario (scenario.py)

Fictional project: "Plot 7 podium, structural stage". 14 workers, 16 tasks. Every task is a point inside the open plot (no building footprint within 8 m; assert this against data/buildings.geojson). Spread task points so that at least 5 are in the shadow of a tall neighbour before 09:00 and at least 4 are shaded after 16:00, and 3 or more are never shaded. Choose the plot by looking at the fetched footprints: find the largest open area inside the bbox that has towers taller than 60 m within 150 m to its east and west. If no such area exists, pick the best one and state the compromise.

Task fields: `id, name, lat, lon, cls (light|moderate|heavy|very_heavy), crew, slots (duration in 15-min slots of crew-work), trade (steel|concrete|general|electrical), after (list of task ids that must fully finish before this starts)`. Keep 3 precedence pairs total, no chains longer than 2.

Suggested mix: 4 very_heavy or heavy rebar/formwork tasks (crew 3, 12 to 16 slots), 6 moderate (crew 2, 8 to 12), 6 light (crew 1 or 2, 4 to 8, e.g. survey, inspection, cable pulling, snag list). Total crew-slots about 430 against a capacity of 14 workers × 48 shift slots = 672 before heat and ban losses.

Worker fields: `id, name, trades (list)`. 5 steel, 4 concrete, 3 general, 2 electrical. Names: short first names from South Asian and Arab countries, realistic, no jokes.

Tune the numbers so that the final metrics land roughly: ban-only finishes everything by 17:00 but has 40+ worker-hours of heat violation; sun-blind has 0 violations but 20+ overtime worker-hours or unfinished work; shade-aware has 0 violations and under a third of the sun-blind overtime. Iterate on task sizes, not on the physics. Report the final numbers.

## Solver (solve.py)

CP-SAT. Variables `x[w,t,s]` boolean for worker w, task t, slot s, created only when the worker has the trade and the slot is not banned and the slot is not forbidden by the heat rule for that scenario. `a[t,s]` boolean "task t active in slot s". `u[t]` integer unscheduled crew-slots (slack).

Constraints:

1. Each worker does at most one task per slot.
2. `sum_w x[w,t,s] == crew[t] · a[t,s]` (full crew or nothing).
3. `sum_s a[t,s] · crew[t] + u[t] == slots[t] · crew[t]` (work done plus slack equals demand).
4. Precedence: `end[A] ≤ start[B]` using AddMaxEquality / AddMinEquality over active slots, or the linear form `a[B,s] ≤ 1 − a[A,s']` for all `s' ≥ s`. Pick what solves faster.
5. Heat (scenarios 2 and 3 only): for every worker and every window of 4 consecutive slots, `sum load[t][s]·x[w,t,s] ≤ 48`.
6. No work in ban slots (all scenarios).
7. Workers may rest any slot. Resting costs nothing.

Objective, lexicographic by weights: `1000·sum u[t] + 10·(overtime worker-slots, s ≥ 48) + 1·(sum over tasks of last active slot)`. Time limit 60 s per scenario, 8 workers. Log the status and objective. Report if any scenario ends without an OPTIMAL or FEASIBLE status.

Scenarios:

- `ban_only`: no heat constraint. Post-hoc evaluate violations using the true per-task shade WBGT.
- `sun_blind`: heat constraint with every task at shade fraction 0 (whole site treated as full sun).
- `shade_aware`: heat constraint with true per-task shade fractions.

Post-hoc metrics for all three, computed identically from the resulting assignment and the true WBGT:

- `overtime_hours`: worker-slots with s ≥ 48 divided by 4.
- `unscheduled_hours`: sum u[t] / 4.
- `violation_hours`: worker-slots inside any rolling-hour window whose load sum exceeds 48, counted once per slot, divided by 4.
- `tasks_done_by_17`: count of tasks with all work in slots < 48 and u[t] == 0.
- `peak_wbgt_worked`: max WBGT in any worked slot.
- `mean_shade_worked`: mean shade fraction over worked slots.

Also store, per worker, per slot: `task id or null`, `wbgt`, `shade`, `load`.

## Output: web/data.json

The frontend is built against this schema. Both agents treat it as fixed. If the backend must change it, update SPEC.md and tell the integrator.

```json
{
  "meta": {"site": "Plot 7 podium", "city": "Dubai", "date": "2026-07-15", "tz": "+04:00",
           "center": [55.2650, 25.1860], "slot_minutes": 15, "first_slot": "05:00",
           "shift_end_slot": 48, "ban_slots": [30, 39], "n_slots": 60},
  "weather": [{"slot": 0, "ta": 32.0, "rh": 62, "wind": 2.5, "ghi": 0}, ...60],
  "sun": [{"slot": 0, "azimuth": 64.2, "elevation": 2.1}, ...60],
  "buildings": { GeoJSON FeatureCollection, EPSG:4326, properties: {"height": 84.0, "name": "..."} },
  "shadows": [ {"slot": 0, "night": false, "geometry": GeoJSON MultiPolygon or null}, ...60 ],
  "tasks": [{"id": "T01", "name": "Tie rebar, grid A", "lon": 55.26, "lat": 25.18, "cls": "very_heavy",
             "crew": 3, "slots": 14, "trade": "steel", "after": [],
             "shade": [0.0, ...60], "wbgt": [29.1, ...60], "load": [24, ...60 or null]}],
  "workers": [{"id": "W01", "name": "Rafiq", "trades": ["steel"]}],
  "scenarios": {
    "ban_only":    {"label": "Blanket ban", "metrics": {...}, "assign": [[task id or null ×60] per worker]},
    "sun_blind":   {"label": "Heat limits, one site temperature", ...},
    "shade_aware": {"label": "Heat limits, per-spot shade", ...}
  }
}
```

Metrics object keys exactly: `overtime_hours, unscheduled_hours, violation_hours, tasks_done_by_17, peak_wbgt_worked, mean_shade_worked`.

Size budget: under 6 MB. Shadow geometries dominate. Simplify to 0.5 m and round coordinates to 6 decimals.

## Frontend (web/)

One page, no build step, works from `python -m http.server`. CDN scripts pinned by exact version: MapLibre GL JS 4.7.1 from unpkg or jsdelivr. Basemap: `https://tiles.openfreemap.org/styles/positron` (free, no key). If that style fails to load, fall back to no basemap with a pale ground colour so the demo still runs. Fonts: Geist and Geist Mono via Google Fonts, falling back to system sans and mono.

Look: an engineering drawing on light paper. Near-white background, thin hairlines, dark ink text, mono numerals. Two accents only: heat orange `#e4572e` scaled by WBGT, shade blue `#2c6e9b` at low alpha for shadows. No gradients on UI chrome, no drop shadows, no rounded cards. Whitespace does the work. Load the `dataviz` skill before writing the timeline and KPI tiles, and the `karpathy-guidelines` skill before writing any code.

Layout, desktop 1440 wide first, degrade gracefully to 1024:

```
┌────────────────────────────────────────────────────────────────┐
│ shade   Plot 7 podium, Dubai, 15 July 2026        [scenario ◦ ◦ ◦]│
├──────────────────────────────┬─────────────────────────────────┤
│                              │  KPI row: overtime h, violation  │
│   MAP (3D buildings,         │  h, tasks done by 17:00, peak    │
│   shadow layer for the       │  WBGT. Big mono numbers, one    │
│   current slot, task dots    │  sentence under each.            │
│   coloured by WBGT, sun      ├─────────────────────────────────┤
│   direction tick on the      │  TIMELINE: one row per worker,  │
│   compass)                   │  60 slot columns, bars coloured │
│                              │  by task, rest blank, ban band  │
│                              │  grey, overtime zone hatched,   │
│                              │  playhead at current slot.      │
├──────────────────────────────┴─────────────────────────────────┤
│  ◀ ▶  05:00 ──────────●──────────────── 20:00   WBGT strip      │
└────────────────────────────────────────────────────────────────┘
```

Behaviour:

- Map: MapLibre with `fill-extrusion` buildings from `data.buildings` (height property), light grey with hairline outline. Shadow layer: a GeoJSON source whose data is swapped to `shadows[slot].geometry` on every slot change, fill shade blue at 0.22 alpha. Tasks: circle layer, radius 7, colour by current WBGT on a white-to-orange ramp over 26..36, stroke 1 px ink. Hover shows name, class, WBGT, shade %. Pitch 55, bearing −20, zoom about 16.5 centred on the plot. A small compass with a sun tick at the current azimuth.
- Scrubber: play button, slider over 60 slots, time readout. Play advances 1 slot every 350 ms. Under the slider a 60-column strip showing site-mean WBGT as colour.
- Scenario switch: three segmented buttons. Switching re-renders the KPI numbers with a count-up over 400 ms and the timeline with a 300 ms crossfade. The map does not change (same physics in every scenario); only task dot ring thickness shows "worked in this slot in this scenario".
- Timeline: SVG. Rows = workers, grouped by trade with a hairline between groups. Each worked slot is a 1-slot-wide rect in the task colour (assign one of 16 distinct desaturated inks per task, avoid red and blue so they do not fight the accents). Violation slots get a 1 px orange underline. Ban band is a light grey column block. Overtime zone has a diagonal hatch pattern. Playhead is a 1 px vertical ink line. Hovering a bar highlights the task dot on the map and dims the rest; clicking a task dot highlights its bars.
- KPI tiles: 4 numbers. The sentence under each must stand alone without the number and must say whether it is good or bad, for example "Nobody worked past the heat limit." or "Heat limits were broken for most of the morning." Write these sentences from the data with simple thresholds; keep every string in one `copy()` function so it is easy to review.
- A single comparison line above the KPIs that reads like the pitch, built from the three scenarios' metrics: "Blanket ban: 46 worker-hours over the heat limit. Sun-blind limits: 31 hours of overtime. Shade-aware: 8 hours, nobody over the limit." Numbers rounded to integers.
- Keyboard: space plays, left/right steps a slot, 1/2/3 switches scenario.
- Performance: slot change must not allocate new layers; use `setData` and `setPaintProperty`. 60 fps during play on an integrated GPU.
- No console errors. Test in Chromium via Playwright screenshot at 1440×900 and attach the path in the report.

Text rules (from the user's CLAUDE.md, applies to every visible string): full sentences, no jargon not already on screen, no definite article for a thing not yet introduced, round to two significant figures in prose, say the verdict.

## Tests (tests/)

- `test_sun.py`: anchors above.
- `test_shadow.py`: box tests above, plus shade fraction edge cases.
- `test_wbgt.py`: formula against one hand-computed value, band checks at 06:00, 13:00 sun, 13:00 shade.
- `test_limits.py`: the worked check and the forbidden case.
- `test_solve.py`: tiny instance, 2 workers 2 tasks 8 slots, asserts crew constraint, ban slots empty, rolling budget respected, precedence respected. Runs under 5 s.
- `test_build.py`: builds with the committed data and asserts the JSON schema keys, array lengths of 60, size under 6 MB, and that every shade_aware worked slot has load not None.

## Split of work

Three executors run in parallel. Each reads this file first. Each loads `andrej-karpathy-skills:karpathy-guidelines` before writing code.

### A. Sonnet: site data (osm.py, weather.json, scenario.py skeleton)

1. `src/shade/osm.py`: Overpass query for `way["building"]` and `relation["building"]` in the bbox, output `data/buildings.geojson` with `height` (metres, from `height` tag, else `building:levels` × 3.2, else 12.0) and `name`. Try `https://overpass-api.de/api/interpreter` then `https://overpass.kumi.systems/api/interpreter`. Multipolygon relations: outer ring only is fine. Drop footprints under 20 m². Run it and commit the output file to the working tree (do not git commit). Report how many buildings and the max height.
2. `data/weather.json` per the profile above.
3. `src/shade/scenario.py` with the full task and worker lists and the plot choice, following the Scenario section. Include an `assert_tasks_in_open_ground(buildings)` helper and run it. Give the integrator lat/lon of the plot centre and the tallest neighbours east and west with their heights.
4. `README.md`: 15 lines, how to run, what the three scenarios mean, the two tables' sources.

### B. Opus: physics and solver (sun, shadow, wbgt, limits, solve, build, tests)

Build against the interfaces above. If `data/buildings.geojson` is not present yet when you reach build.py, generate a synthetic set of 6 towers (40 to 120 m) around the centre so you can test end to end, keep that generator in `tests/` as a fixture, and switch to the real file when it lands. Same for scenario.py: if A's version is not there, write a minimal one with the field names above and let A's file replace it (coordinate through the integrator, do not overwrite A's file if it exists).

Deliver `web/data.json` from the real data. Report the three scenarios' metrics, solver statuses and wall time.

### C. Opus: frontend (web/index.html, app.js, style.css)

Build against the schema. Until the real `web/data.json` exists, write `tests/mock_data.py` that emits a plausible mock with 6 synthetic towers, 60 slots, 14 workers and 16 tasks, random but seeded, and develop against that. Use the dataviz skill for the timeline and KPI design. Screenshot with Playwright. Do not touch any `src/shade` file.

## Integrator checklist (Fable)

1. A lands → B switches to real buildings and scenario.
2. B lands → run `uv run pytest`, check metrics band, regenerate `web/data.json`.
3. C lands → serve, open, play through all 60 slots, switch scenarios, check copy.
4. Commit in order: scaffold, data, physics and solver, frontend, docs.

## Out of scope

Live weather fetch, live Overpass at demo time, clothing adjustment factors, unacclimatised workers, per-worker acclimatisation, mobile layout, a backend server, user editing of tasks. Each is one sentence in the README under "Not built".
