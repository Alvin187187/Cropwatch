"""Refresh the Open-Meteo forecast. Historical rows already cached are left in place."""

from __future__ import annotations

import httpx

from app.db import connect
from app.schema import ensure_schema
from app.scoring import leaf_wetness_by_day

BLAST_WET_GATE = {"rh_min": 90, "temp_min": 20, "temp_max": 28}


def refresh() -> int:
    with connect() as conn:
        places = conn.execute(
            """
            SELECT id, ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lon
            FROM municipalities ORDER BY id
            """
        ).fetchall()
    if not places:
        return 0
    lats = ",".join(f"{row['lat']:.4f}" for row in places)
    lons = ",".join(f"{row['lon']:.4f}" for row in places)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        "&daily=temperature_2m_mean,temperature_2m_min,relative_humidity_2m_mean,precipitation_sum,"
        "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,soil_moisture_0_to_7cm_mean,"
        "soil_temperature_0_to_7cm_mean"
        "&hourly=relative_humidity_2m,temperature_2m"
        "&forecast_days=7&timezone=Asia%2FManila"
    )
    response = httpx.get(url, timeout=90, headers={"User-Agent": "CROPWATCH-school-project"})
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload = [payload]
    written = 0
    with connect() as conn:
        ensure_schema(conn)
        for place, block in zip(places, payload):
            daily = block["daily"]
            wet_hours = _hours_rh90(block.get("hourly") or {})
            issued = daily["time"][0]
            for index, day in enumerate(daily["time"]):
                conn.execute(
                    """
                    INSERT INTO weather_forecast (
                      place_type, place_id, issued_on, day_offset, forecast_date, source,
                      temp_c, temp_min_c, rh_pct, hours_rh90, rain_mm, wind_speed_kmh,
                      wind_gust_kmh, wind_dir_deg, soil_moisture, soil_temp_c
                    ) VALUES ('municipality', %s, %s, %s, %s, 'Open-Meteo forecast', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (place_type, place_id, day_offset, source) DO UPDATE SET
                      issued_on = EXCLUDED.issued_on,
                      forecast_date = EXCLUDED.forecast_date,
                      temp_c = EXCLUDED.temp_c,
                      temp_min_c = EXCLUDED.temp_min_c,
                      rh_pct = EXCLUDED.rh_pct,
                      hours_rh90 = EXCLUDED.hours_rh90,
                      rain_mm = EXCLUDED.rain_mm,
                      wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                      wind_gust_kmh = EXCLUDED.wind_gust_kmh,
                      wind_dir_deg = EXCLUDED.wind_dir_deg,
                      soil_moisture = EXCLUDED.soil_moisture,
                      soil_temp_c = EXCLUDED.soil_temp_c
                    """,
                    (
                        place["id"],
                        issued,
                        index,
                        day,
                        _at(daily, "temperature_2m_mean", index),
                        _at(daily, "temperature_2m_min", index),
                        _at(daily, "relative_humidity_2m_mean", index),
                        wet_hours.get(day),
                        _at(daily, "precipitation_sum", index),
                        _at(daily, "wind_speed_10m_max", index),
                        _at(daily, "wind_gusts_10m_max", index),
                        _at(daily, "wind_direction_10m_dominant", index),
                        _at(daily, "soil_moisture_0_to_7cm_mean", index),
                        _at(daily, "soil_temperature_0_to_7cm_mean", index),
                    ),
                )
                written += 1
            if block.get("elevation") is not None:
                conn.execute(
                    """
                    INSERT INTO terrain (place_type, place_id, elevation_m, source)
                    VALUES ('municipality', %s, %s, 'Open-Meteo elevation (SRTM/Copernicus DEM)')
                    ON CONFLICT (place_type, place_id) DO UPDATE SET elevation_m = EXCLUDED.elevation_m
                    """,
                    (place["id"], block["elevation"]),
                )
        conn.execute(
            """
            INSERT INTO dataset_status (dataset, state, detail)
            VALUES ('open_meteo', 'loaded', 'Forecast refreshed from Open-Meteo.')
            ON CONFLICT (dataset) DO UPDATE SET state = 'loaded', detail = EXCLUDED.detail, updated_at = now()
            """
        )
        conn.commit()
    return written


def _hours_rh90(hourly: dict) -> dict:
    times = hourly.get("time") or []
    humidity = hourly.get("relative_humidity_2m") or []
    temperatures = hourly.get("temperature_2m") or []
    rows = []
    for index, stamp in enumerate(times):
        if not stamp:
            continue
        rows.append(
            {
                "date": stamp[:10],
                "rh_pct": humidity[index] if index < len(humidity) else None,
                "temp_c": temperatures[index] if index < len(temperatures) else None,
            }
        )
    if rows and any(row["temp_c"] is not None for row in rows):
        return leaf_wetness_by_day(rows, BLAST_WET_GATE)
    counts: dict[str, int] = {}
    for row in rows:
        if row["rh_pct"] is None:
            continue
        counts.setdefault(row["date"], 0)
        if float(row["rh_pct"]) >= 90:
            counts[row["date"]] += 1
    return counts


def _at(block, key, index):
    values = block.get(key) or []
    if index >= len(values):
        return None
    return values[index]


if __name__ == "__main__":
    print(refresh())
