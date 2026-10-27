# CROPWATCH

Local decision-support map for rice pest and disease risk in Nueva Ecija. It shows where conditions are favorable for monitoring. It does not declare that a pest or disease is present, and it does not estimate pesos or exact yield loss.

## Run on the presentation laptop

```bash
docker compose up --build
```

Open http://localhost:3000.

Demo accounts, also listed on the sign-in screen:

| Account | Password | Role |
| --- | --- | --- |
| provincial | nueva-ecija | Whole province, can recompute |
| munoz | science-city | Science City of Muñoz, can add a field note |
| guest | read-only | View only |

Optional assistant: copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Without it, the chat panel says the assistant is not configured. The map and priority list still read the database.

## What is already loaded

- Nueva Ecija municipality polygons from geoBoundaries (NAMRIA/PSA/OCHA), simplified.
- Open-Meteo archive for 1–16 October 2026 and a 7-day forecast, cached for offline use.
- Elevation from the Open-Meteo DEM field. Slope is the difference with neighboring municipalities.
- NOAA Oceanic Niño Index through JAS 2026.
- A Ricelytics provincial snapshot retrieved 18 October 2026 (harvested area, yield, production, farmers).
- World Bank national fertilizer, cereal yield, and agricultural land figures. These are briefing context, not municipal scores.

Barangay polygons, PRiSM rice masks, PRIME or BPI observations, Earth Engine indices, PAGASA normals, and OSM lines are empty until you load them. The map says so.

## Load more data

```bash
docker compose exec api python -m ingest.inbox
docker compose exec api python -m ingest.osm
docker compose exec api python -m ingest.nasa_power
docker compose exec api python -m ingest.portals
docker compose exec api python -m ingest.gee_export
```

`gee_export` needs `earthengine authenticate` and the `earthengine-api` package. Put returned CSVs in `data/inbox/` and run the inbox loader. Templates in that folder are not imported.

Threats scored: rice black bug, brown planthopper, rice blast, bacterial leaf blight.
