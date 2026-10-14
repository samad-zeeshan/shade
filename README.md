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

Sources. Building outlines and heights come from OpenStreetMap (Overpass API). Heat index (WBGT) uses the Ono and Tonouchi (2014) outdoor formula. Work and rest limits come from the ACGIH heat stress screening table, as reproduced by CCOHS. The WBGT formula coefficients were taken from memory and not checked against the paper. The weather is a typical clear July day, written by hand in `data/weather.json`.

Not built: live weather, live map downloads at demo time, clothing factors, workers new to the heat, per-worker heat history, phone layout, a server, task editing.
