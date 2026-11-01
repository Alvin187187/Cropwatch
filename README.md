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

## Mathematics and principles

The hazard score is a **weighted linear combination**: each weather or setting input is mapped to a suitability in `[0, 1]`, then combined with weights that are rescaled so the factors actually present still sum to 1. That is the usual form of a multi-criteria suitability index. A missing optional factor is left out. A missing required factor (temperature, and humidity for every threat) makes the place **Insufficient data** and stores no score.

The numeric bands in `rules/*.yaml` are **unchecked starting points**. They encode the agronomic direction of each threat. They are not a calibrated PhilRice or IRRI model, and they are not a probability that the organism is present. Rice black bug is marked low confidence because its weather response is less documented than the other three.

Displayed hazard points are the 0–1 score times 100. The same class cuts apply to every threat:

| Score `S` | Class |
| --- | --- |
| `S < 0.35` | Low |
| `0.35 ≤ S < 0.55` | Moderate |
| `0.55 ≤ S < 0.72` | High |
| `S ≥ 0.72` | Very high |

### Hazard index

For the factors that have data, with weights `w_i` and suitability `p_i`:

$$
S = \sum_i \frac{w_i}{\sum_j w_j}\, p_i
$$

Each factor's contribution is its rescaled weight times `p_i`. The boards show that contribution in points out of 100. A factor is called strongly favorable when `p_i ≥ 0.6` and the value was measured, not assumed.

If assumed factors carry half or more of the weight used, confidence drops to low and the explanation says the score rests mostly on assumptions. Nitrogen, when no municipal rate is loaded, is assumed at 110 kg/ha and labeled as a regional assumption. An estimated leaf-wetness hour count is labeled the same way.

### Suitability curves

Each threat has its own curve. A temperature that is ideal for one organism can be ordinary for another. The curves are piecewise linear.

**Peak** (temperature, and brown planthopper humidity). Full suitability inside a core, zero outside a hard range, linear on the two shoulders:

$$
p(x) =
\begin{cases}
0 & x \le h_{\min} \text{ or } x \ge h_{\max} \\
1 & c_{\min} \le x \le c_{\max} \\
(x - h_{\min}) / (c_{\min} - h_{\min}) & h_{\min} < x < c_{\min} \\
(h_{\max} - x) / (h_{\max} - c_{\max}) & c_{\max} < x < h_{\max}
\end{cases}
$$

Rice blast blends the daytime peak with the night minimum. With blend `b = 0.45`:

$$
p = (1 - b)\, p_{\text{day}}(T) + b\, p_{\text{night}}(T_{\min})
$$

The night term is dropped when the night minimum is missing. The principle is that blast suitability depends on mild days and cool nights together, so one temperature factor carries both.

**High** (humidity, rain totals, soil moisture, nitrogen, climate, canal link). Zero at or below the low end, 1 at or above the high end, linear between:

$$
p(x) = \operatorname{clamp}\left(\frac{x - L}{H - L},\, 0,\, 1\right)
$$

**Low** is the reverse ramp: 1 at or below `L`, 0 at or above `H`.

**Band** (rice blast rainfall over 7 days). Suitability is 1 inside `[L, H]`. Outside, it falls across a soft width `s`:

$$
p(x) =
\begin{cases}
1 & L \le x \le H \\
\max\left(0,\, 1 - (L - x)/s\right) & x < L \\
\max\left(0,\, 1 - (x - H)/s\right) & x > H
\end{cases}
$$

**Light rain** (rice blast forecast rain). A dry day stays low (0.15). Light rain rises toward 1. Rain past the favorable maximum falls, and a very heavy day is held at 0.2, because a washing rain is treated as less favorable for blast than a light wet day.

**Heavy penalty** (brown planthopper rain). Light rain stays near neutral (about 0.5 to 0.75). A very heavy day falls to 0. The principle is that heavy rain knocks planthoppers from the canopy, so the same rain that raises bacterial blight lowers this factor.

**Stage** (days after planting). A step function: the first stage whose maximum day is at least the crop age supplies `p`. Crop stage is omitted when no planting date is loaded. The wet/dry switch is not used in its place.

**Storm** (bacterial leaf blight). Wind speed is the faster of the mean and the gust. Suitability is 0 at or below 12 km/h, 1 at or above 40 km/h, and linear between:

$$
p = \operatorname{clamp}\left(\frac{v - 12}{28},\, 0,\, 1\right)
$$

A storm day is wind of at least 40 km/h or a gust of at least 60 km/h. If such a day falls in the previous 14 days, `p` is at least 0.85 on the following forecast days. Typhoon tracks are not loaded, so this persistence stands in for leaf wounding and wind-driven spread after a strong-wind day.

### What each rule is representing

These are the biological directions the weights follow. The cuts and the kilograms, hours, and degrees are the project's starting values.

| Threat | Principle encoded in the weights | Required inputs |
| --- | --- | --- |
| Rice blast | Mild days, cool nights, and a long near-saturated period. Light rain and early or mid crop stages raise suitability. High nitrogen raises it when a rate is known. | Temperature, humidity |
| Brown planthopper | Warm humid air without a washing rain. Later crop stages and a canal or river link raise suitability. Wet season raises a small climate term. | Temperature, humidity |
| Bacterial leaf blight | Warm humid weather, substantial rain, and wind that can wound leaves. Flooding or a canal link raises spread. | Temperature, humidity |
| Rice black bug | Mild wet weather and the wet-season climate term carry more of the weight. Soil moisture and a canal link are included. Confidence stays low. | Temperature, humidity |

Brown planthopper and rice black bug also take a climate modifier. Wet season base is 1. Dry season base is 0.35 for rice black bug and 0.50 for brown planthopper. The NOAA Oceanic Niño Index, a 3-month sea-surface temperature anomaly, nudges that base. A warm (El Niño) anomaly lowers it; a cool (La Niña) anomaly raises it. The nudge is national and does not separate municipalities:

$$
n = \operatorname{clamp}(-0.06 \times \mathrm{ONI},\, -0.12,\, 0.12), \qquad
C = \operatorname{clamp}(\text{base} + n,\, 0,\, 1)
$$

Bacterial leaf blight spread is the maximum of the parts that exist: canal or river link in `{0, 1}`, flood fraction scaled by `min(1, flood / 0.25)`, and soil moisture on a ramp from 0.22 to 0.42.

### Rice blast gate

Blast has a necessary-condition gate in front of the weighted score. A weighted index can still look high on temperature alone, so the class is held at Low and the stored score at 0 unless the wet run is long enough:

- An hour counts as wet when relative humidity is at least 90% and temperature is between 20°C and 28°C.
- The wet run is the longest consecutive run of such hours that touches the day, including a run that crosses midnight.
- Fewer than 6 wet hours holds the class at Low.
- When a canopy index is loaded, NDVI below 0.2 also holds the class at Low, on the principle that the greenness is below a rice canopy.

If only a daily mean humidity is available, wet hours are estimated and flagged as assumed: 0 when mean RH is below 78%, otherwise `min(14, (RH − 78) × 0.7)`.

### Elevation lapse rate

Barangay microclimate shifts the model temperature from the model elevation to the surface elevation with the average environmental lapse rate of the International Standard Atmosphere, 6.5°C per 1,000 m:

$$
T_{\text{surface}} = T_{\text{model}} - 0.0065\,(z_{\text{surface}} - z_{\text{model}})
$$

Higher ground is cooler. This adjustment is applied to barangay hourly temperature before the wet-hour count. Municipality scores use the municipality weather field directly.

Relative relief, stored beside elevation, is not a slope in degrees and not a topographic wetness index. For a municipality, the slope index is the largest absolute elevation difference to a neighbor that shares a boundary. The wetness index is how many meters the municipality sits below the mean elevation of those neighbors, floored at 0:

$$
\text{slope} = \max_j |z - z_j|, \qquad
\text{wetness} = \max\left(0,\, \overline{z}_{\text{neighbors}} - z\right)
$$

### Trend

Trend compares the current 0–1 score with the nearest saved daily score about three days earlier, searched inside a four-day window. A change of 0.03 or more (3 points on the 0–100 scale) is rising. A drop of 0.03 or more is falling. Anything inside that band is stable. A seven-day change is reported beside it and does not set the direction. This is a thresholded difference, not a fitted trend line.

### Weather baseline

When at least two earlier years and 20 days of the same calendar month are loaded, humidity is compared with that month by a z-score. The spread is the population standard deviation:

$$
z = \frac{x - \bar{x}}{s}, \qquad s = \sqrt{\frac{1}{N}\sum (x_k - \bar{x})^2}
$$

Seven-day rain is reported as a ratio to seven times the mean daily rain in that month. The archive shipped with the app is shorter than this, so the panel says a historical baseline is not loaded until a longer daily series, such as NASA POWER, is present.

### Inspection priority

Priority is a second weighted index. It answers where to send people. It does not replace the hazard score, and neighbor scores are not written back into the hazard formula.

| Part | Weight | Value |
| --- | --- | --- |
| Hazard | 0.45 | The 0–1 hazard score |
| Trend | 0.15 | Rising 1, stable 0.35, falling 0 |
| Rice exposure | 0.25 | Hectares divided by the largest hectare figure in the current scope |
| Hotspot | 0.15 | Cluster 1, isolated high 0.55, adjacent to elevated neighbors 0.40, none 0 |
| Prior occurrence | 0.05 | 1 if a loaded surveillance record exists for this threat, otherwise 0 |

A missing part is dropped and the remaining weights are rescaled to 1, the same way as the hazard index. Points are that total times 100.

A hotspot is read from the municipal neighbor graph. A place is a **cluster** when it is High or Very high and at least one neighbor is too. It is **isolated** when it is High or Very high and its neighbors are lower. It is **adjacent** when it is itself below High but at least two neighbors are Moderate or above. The mean of the neighbor scores is shown as context only.

The command center's top band is operational, not a fifth hazard class. The cutoff is the higher of 70 and five points below the leading priority in scope. The count is municipalities.

### Distance, clusters, and inspection order

Neighboring municipalities are those whose boundaries meet, with a small buffer so shared borders still count. The length of that link is the great-circle distance between centroids, Earth radius 6,371 km (haversine):

$$
\begin{align*}
a &= \sin^2(\Delta\phi / 2) + \cos\phi_1 \cos\phi_2 \sin^2(\Delta\lambda / 2) \\
d &= 2 \times 6371 \times \arcsin(\sqrt{a})
\end{align*}
$$

High and Very high municipalities that touch one another form connected components of that graph. The component is the spatial cluster.

The inspection path visits up to five leading places. Between two stops it uses Dijkstra's shortest path on the boundary graph, with distance in kilometers as the cost. The next stop is the remaining priority place with the shortest such path. That is a nearest-neighbor tour on shortest-path legs, not an exact solution of the traveling salesman problem.

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
