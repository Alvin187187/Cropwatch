# CROPWATCH

Decision-support map for rice pest and disease **conditions** in Nueva Ecija. It shows where to look. It does not say a pest or disease is present, and it does not estimate pesos or exact yield loss.

**See where the rice is at risk.** Favorable conditions, not a diagnosis.

Built for the provincial agriculture office, municipal agriculture staff, and field inspection teams.

## What it does

CROPWATCH scores each municipality for four rice threats, then ranks where an inspection team should go first. A high score means the weather and setting are favorable for that threat. It is not a confirmation that the pest or disease is in the field.

The four threats are rice black bug, brown planthopper, rice blast, and bacterial leaf blight. Wet and dry season are separate. The map can step through the current day and the next six forecast days.

Two numbers stay separate:

- **Hazard** is how favorable conditions are for the selected threat, from 0 to 100, in the classes Low, Moderate, High, Very high, or Insufficient data.
- **Inspection priority** ranks where to send people. It combines hazard, recent trend, rice exposure, neighboring hotspots, and a prior occurrence when one is on file.

A municipal account sees only its own municipality. The provincial account sees the whole province and can recompute scores. The guest account can look, and cannot add notes, photos, or inspection stops.

## How it works

```text
weather, boundaries, rice context, optional satellite and field files
        ↓
PostGIS
        ↓
rule files in rules/*.yaml  →  hazard score per place, threat, season, and day
        ↓
inspection priority, command actions, analytics
        ↓
FastAPI  →  Next.js map and boards at http://localhost:3000
```

1. Loaders write municipality polygons, weather, elevation, ENSO, and rice context into PostGIS. Optional files (barangay polygons, rice masks, satellite indices, canals, rivers, roads, field observations) stay empty until they are loaded. The map says when a layer has no data.
2. Each threat is a YAML rule. A factor is scored only when its input exists. A missing optional factor is skipped. It is not filled in. Thresholds are unchecked starting points, not PhilRice or IRRI guidance.
3. The engine writes a hazard score for every municipality, threat, season, and forecast day. Inspection priority is a separate reading on top of that score.
4. The API serves the map, command center, weather, rice context, risk board, analytics, operations, alerts, and reports. A municipal session is filtered to that municipality.
5. About every six hours the API refreshes the Open-Meteo forecast, the barangay microclimate, and the scores.
6. Ask CROPWATCH is optional. Set `GEMINI_API_KEY` and it can rephrase the numbers already on screen. Without a key, the map, scores, and priority list still run. The assistant does not invent a diagnosis.

## Features

**Monitor**

- **Command.** The situation for the selected threat, season, and day: recommended actions (field validation, monitor, prepare, review, follow-up, data required), go / hold / escalate, watches, and team capacity.
- **Map.** Municipality shapes, and barangay shapes when those polygons are loaded. Layers for risk, inspection priority, change, temperature, rain, humidity, wind, soil moisture, leaf wetness, rice area, and satellite indices (canopy, EVI, water, LSWI, flood, surface temperature). Canals, rivers, and roads draw when OpenStreetMap lines are loaded. Forecast playback runs from now through six days ahead.
- **Weather.** A board of the model forecast behind the scores. It is an Open-Meteo field, not a live sensor.
- **Rice.** Provincial rice context (harvested area, yield, production, farmers) and municipal rice area when a rice file is loaded.

**Analyze**

- **Risk.** Class counts, ranking, and what pushed a place into its band.
- **Analytics.** Drivers, coverage gaps, how classes shift across the forecast, and places where more than one threat is elevated.

**Act**

- **Operations.** An inspection list that moves from listed, to planned, routed, in the field, observed, validated, and follow-up. Field notes and a photo reading stay labeled as observations. A pest is recorded only after it is seen.
- **Alerts.** Places and watches that need a look, opened from the current scores.
- **Reports.** Provincial, municipality, threat, inspection, and validation briefings.
- **Administration.** Which datasets are loaded. The provincial account can recompute scores.

**Assist**

- **Ask CROPWATCH.** Questions against the current threat, season, and forecast day.
- **Briefing slides.** A short readout of the same situation.

## Run

```bash
docker compose up --build
```

Open http://localhost:3000.

The stack is PostGIS, a FastAPI service on port 8000, and the Next.js app on port 3000.

Demo accounts, also listed on the sign-in screen:

| Account | Password | Role |
| --- | --- | --- |
| provincial | nueva-ecija | Whole province, can recompute |
| munoz | science-city | Science City of Muñoz, can add a field note |
| guest | read-only | View only |

Optional assistant: copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Without it, the chat panel says the assistant is not configured.

## What is already loaded

- Nueva Ecija municipality polygons from geoBoundaries (NAMRIA/PSA/OCHA), simplified.
- Open-Meteo archive for 1–16 October 2026 and a 7-day forecast, cached for offline use.
- Elevation from the Open-Meteo DEM field. Slope is the difference with neighboring municipalities.
- NOAA Oceanic Niño Index through JAS 2026.
- A Ricelytics provincial snapshot retrieved 18 October 2026 (harvested area, yield, production, farmers).
- World Bank national fertilizer, cereal yield, and agricultural land figures. These are briefing context, not municipal scores.

Barangay polygons, PRiSM rice masks, PRIME or BPI observations, Earth Engine indices, PAGASA normals, and OSM lines are empty until you load them.

## Load more data

```bash
docker compose exec api python -m ingest.inbox
docker compose exec api python -m ingest.osm
docker compose exec api python -m ingest.nasa_power
docker compose exec api python -m ingest.portals
docker compose exec api python -m ingest.gee_export
```

`gee_export` needs `earthengine authenticate` and the `earthengine-api` package. Put returned CSVs in `data/inbox/` and run the inbox loader. Templates in that folder are not imported.

## Author

[Alvin187187](https://github.com/Alvin187187). No other collaborators.
