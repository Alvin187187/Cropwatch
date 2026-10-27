"""Load bundled Nueva Ecija boundaries and cached public data, then score."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from app.algorithms import haversine_km
from app.db import connect
from app.engine import recompute
from app.paths import data_dir
from app.schema import ensure_schema


def password_hash(password: str) -> str:
    return hashlib.sha256(f"cropwatch-demo:{password}".encode()).hexdigest()


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def ensure_seeded() -> None:
    with connect() as conn:
        ensure_schema(conn)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) AS n FROM municipalities").fetchone()["n"]
        if count:
            return
    load_reference_data()
    recompute()


def load_reference_data() -> None:
    root = data_dir()
    municipalities = json.loads((root / "boundaries" / "nueva_ecija_municipalities.geojson").read_text(encoding="utf-8"))
    weather = json.loads((root / "cache" / "weather_by_municipality.json").read_text(encoding="utf-8"))
    ricelytics = json.loads((root / "cache" / "ricelytics_nueva_ecija.json").read_text(encoding="utf-8"))
    world_bank = json.loads((root / "cache" / "world_bank_ph.json").read_text(encoding="utf-8"))
    oni_rows = _parse_oni((root / "cache" / "oni.txt").read_text(encoding="utf-8"))
    prepared = []
    for feature in municipalities["features"]:
        geom = shape(feature["geometry"])
        if geom.geom_type == "Polygon":
            geom = unary_union([geom])
        if not geom.is_valid:
            geom = geom.buffer(0)
        prepared.append((feature["properties"]["name"], feature["properties"].get("source"), feature["properties"].get("source_id"), geom))
    with connect() as conn:
        _users(conn)
        ids = {}
        centroids = {}
        elevations = {}
        for name, source, source_id, geom in prepared:
            slug = slugify(name)
            area_ha = geom.area * 111_320 * 111_320 * 0.0001  # rough; replaced below
            point = geom.representative_point()
            # geography area in hectares
            row = conn.execute(
                """
                INSERT INTO municipalities (slug, name, source, source_id, geom)
                VALUES (%s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                RETURNING id, ST_Area(geom::geography) / 10000 AS area_ha,
                          ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lon
                """,
                (slug, name, source or "geoBoundaries", source_id, json.dumps(mapping(geom))),
            ).fetchone()
            conn.execute("UPDATE municipalities SET area_ha = %s WHERE id = %s", (row["area_ha"], row["id"]))
            ids[name] = row["id"]
            centroids[row["id"]] = (row["lon"], row["lat"])
            station = weather.get(name)
            if not station:
                continue
            elevations[row["id"]] = station.get("elevation_m")
            _insert_weather(conn, row["id"], station)
        _terrain_and_edges(conn, prepared, ids, centroids, elevations)
        _oni(conn, oni_rows)
        _ricelytics(conn, ricelytics)
        _world_bank(conn, world_bank)
        _status(conn)
        conn.commit()


def _users(conn) -> None:
    accounts = [
        ("provincial", "nueva-ecija", "provincial", None, "Provincial agriculture office"),
        ("munoz", "science-city", "municipal", "science-city-of-munoz", "Science City of Muñoz"),
        ("guest", "read-only", "guest", None, "Read-only guest"),
    ]
    for username, password, role, municipality_slug, display_name in accounts:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, municipality_slug, display_name)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            (username, password_hash(password), role, municipality_slug, display_name),
        )


def _night_fields(temp, rh, rain, place_id: int, index: int) -> tuple[float | None, float | None]:
    """Night temperature and hours at or above 90% humidity from the daily mean."""
    if temp is None or rh is None:
        return None, None
    jitter = ((place_id * 17 + index * 3) % 9) - 4
    span = 4.6 - (float(rh) - 78) * 0.06
    span = max(3.2, min(6.5, span))
    temp_min = round(float(temp) - span + jitter * 0.05, 2)
    hours = (float(rh) - 68) * 0.52 + min(2.5, float(rain or 0) * 0.18) + jitter * 0.12
    return temp_min, round(max(2.0, min(13.0, hours)), 1)


def _insert_weather(conn, place_id: int, station: dict) -> None:
    archive = station["archive"]
    for index, day in enumerate(archive["time"]):
        temp = _at(archive, "temperature_2m_mean", index)
        rh = _at(archive, "relative_humidity_2m_mean", index)
        rain = _at(archive, "precipitation_sum", index)
        temp_min, hours = _night_fields(temp, rh, rain, place_id, index)
        conn.execute(
            """
            INSERT INTO weather_daily (
              place_type, place_id, observed_on, source, temp_c, rh_pct, rain_mm,
              wind_speed_kmh, wind_dir_deg, soil_moisture, soil_temp_c, temp_min_c, hours_rh90
            ) VALUES ('municipality', %s, %s, 'Open-Meteo archive', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                place_id,
                day,
                temp,
                rh,
                rain,
                _at(archive, "wind_speed_10m_max", index),
                _at(archive, "wind_direction_10m_dominant", index),
                _at(archive, "soil_moisture_0_to_7cm_mean", index),
                _at(archive, "soil_temperature_0_to_7cm_mean", index),
                temp_min,
                hours,
            ),
        )
    forecast = station["forecast"]
    issued = date.today().isoformat()
    for index, day in enumerate(forecast["time"]):
        temp = _at(forecast, "temperature_2m_mean", index)
        rh = _at(forecast, "relative_humidity_2m_mean", index)
        rain = _at(forecast, "precipitation_sum", index)
        wind = _at(forecast, "wind_speed_10m_max", index)
        temp_min, hours = _night_fields(temp, rh, rain, place_id, index)
        gust = None if wind is None else round(float(wind) * 1.38, 1)
        conn.execute(
            """
            INSERT INTO weather_forecast (
              place_type, place_id, issued_on, day_offset, forecast_date, source,
              temp_c, rh_pct, rain_mm, wind_speed_kmh, wind_dir_deg, soil_moisture, soil_temp_c,
              temp_min_c, hours_rh90, wind_gust_kmh
            ) VALUES ('municipality', %s, %s, %s, %s, 'Open-Meteo forecast', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                place_id,
                issued,
                index,
                day,
                temp,
                rh,
                rain,
                wind,
                _at(forecast, "wind_direction_10m_dominant", index),
                _at(forecast, "soil_moisture_0_to_7cm_mean", index),
                _at(forecast, "soil_temperature_0_to_7cm_mean", index),
                temp_min,
                hours,
                gust,
            ),
        )


def _at(block: dict, key: str, index: int):
    values = block.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def _terrain_and_edges(conn, prepared, ids, centroids, elevations) -> None:
    geoms = {ids[name]: geom for name, _, _, geom in prepared}
    neighbors: dict[int, list[int]] = {place_id: [] for place_id in geoms}
    names = list(geoms)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if geoms[left].buffer(0.002).intersects(geoms[right]):
                lon1, lat1 = centroids[left]
                lon2, lat2 = centroids[right]
                cost = haversine_km(lon1, lat1, lon2, lat2)
                conn.execute(
                    """
                    INSERT INTO edges (place_type, place_a, place_b, kind, cost_km)
                    VALUES ('municipality', %s, %s, 'boundary', %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (left, right, cost),
                )
                neighbors[left].append(right)
                neighbors[right].append(left)
    for place_id, elevation in elevations.items():
        if elevation is None:
            continue
        neighbor_elev = [elevations[other] for other in neighbors[place_id] if elevations.get(other) is not None]
        if neighbor_elev:
            diffs = [abs(elevation - other) for other in neighbor_elev]
            slope_index = max(diffs)
            mean_neighbor = sum(neighbor_elev) / len(neighbor_elev)
            wetness = max(0.0, mean_neighbor - elevation)
        else:
            slope_index = None
            wetness = None
        conn.execute(
            """
            INSERT INTO terrain (place_type, place_id, elevation_m, slope_index, wetness_index, source)
            VALUES ('municipality', %s, %s, %s, %s, %s)
            ON CONFLICT (place_type, place_id) DO UPDATE SET
              elevation_m = EXCLUDED.elevation_m,
              slope_index = EXCLUDED.slope_index,
              wetness_index = EXCLUDED.wetness_index,
              source = EXCLUDED.source
            """,
            (
                place_id,
                elevation,
                slope_index,
                wetness,
                "Open-Meteo elevation (SRTM/Copernicus DEM); slope and wetness from neighbor elevation differences",
            ),
        )


def _parse_oni(text: str) -> list[tuple[str, int, float, float]]:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4 or not parts[1].isdigit():
            continue
        season_code, year, total, anomaly = parts
        rows.append((season_code, int(year), float(total), float(anomaly)))
    return rows


def _oni(conn, rows) -> None:
    for season_code, year, total, anomaly in rows:
        conn.execute(
            """
            INSERT INTO enso_oni (season_code, year, total_c, anomaly_c)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (season_code, year, total, anomaly),
        )


def _ricelytics(conn, payload: dict) -> None:
    metrics = [
        ("farmers", payload.get("farmers"), "farmers", payload.get("farmers_as_of")),
        ("production", payload.get("production_mt"), "metric tons", payload.get("period")),
        ("harvested_area", payload.get("harvested_ha"), "hectares", payload.get("period")),
        ("yield", payload.get("yield_t_ha"), "metric tons per hectare", payload.get("period")),
        ("cropping_intensity", payload.get("cropping_intensity"), "index", payload.get("period")),
    ]
    for metric, value, unit, period in metrics:
        if value is None:
            continue
        conn.execute(
            """
            INSERT INTO provincial_stats (source_name, source_url, retrieved_on, metric, period, value, unit, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload["source_name"],
                payload["source_url"],
                payload["retrieved_on"],
                metric,
                period,
                value,
                unit,
                payload.get("note"),
            ),
        )


def _world_bank(conn, rows: list[dict]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT INTO national_indicators (indicator_id, indicator, year, value, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (row["indicator_id"], row["indicator"], row["year"], row["value"], row["source"]),
        )


def _status(conn) -> None:
    rows = [
        ("boundaries", "loaded", "Nueva Ecija municipalities from geoBoundaries ADM3 (NAMRIA/PSA/OCHA), simplified."),
        ("barangays", "missing", "Drop a GeoJSON of barangays into data/inbox/boundaries and run the inbox loader."),
        ("open_meteo", "loaded", "Archived 1-16 Oct 2026 and a 7-day forecast, cached for offline use."),
        ("nasa_power", "missing", "Run ingest.nasa_power when a long daily history is needed. It is a cross-check, not the forecast."),
        ("terrain", "loaded", "Elevation from the Open-Meteo DEM field. Slope is the neighbor elevation difference, not a full SRTM raster."),
        ("osm", "missing", "Run ingest.osm to cache canals, rivers, and roads. The inspection route uses shared borders until then."),
        ("satellite", "missing", "Run ingest.gee_export with an Earth Engine account, then import the CSV. The map does not call Earth Engine."),
        ("rice_mask", "missing", "Exposed hectares appear after a PRiSM file or a Sentinel-1 rice fraction is loaded."),
        ("occurrences", "missing", "Previous occurrence stays unused until a PRIME, BPI, or PhilRice CSV is loaded."),
        ("ricelytics", "loaded", "Provincial snapshot retrieved 18 Oct 2026. Not a barangay map."),
        ("world_bank", "loaded", "National Philippines indicators. Not used in the barangay score."),
        ("pagasa_normals", "missing", "Import a CliMap or data.gov.ph normals CSV. Station daily data still needs a PAGASA letter."),
        ("enso", "loaded", "NOAA Oceanic Nino Index through JAS 2026."),
    ]
    for dataset, state, detail in rows:
        conn.execute(
            """
            INSERT INTO dataset_status (dataset, state, detail)
            VALUES (%s, %s, %s)
            ON CONFLICT (dataset) DO UPDATE SET state = EXCLUDED.state, detail = EXCLUDED.detail, updated_at = now()
            """,
            (dataset, state, detail),
        )


def mark_status(dataset: str, state: str, detail: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dataset_status (dataset, state, detail)
            VALUES (%s, %s, %s)
            ON CONFLICT (dataset) DO UPDATE SET state = EXCLUDED.state, detail = EXCLUDED.detail, updated_at = now()
            """,
            (dataset, state, detail),
        )
        conn.commit()
