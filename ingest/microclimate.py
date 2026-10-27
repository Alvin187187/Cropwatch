"""Hourly leaf-wetness weather on a 1 km grid, scored up to barangays.

Open-Meteo supplies the hourly forecast on an 11 km-scale grid. Each 1 km
cell shifts that temperature with the Copernicus DEM elevation and a lapse
rate of 0.65 C per 100 m. A barangay takes the cell with the longest
leaf-wetness run, and rice blast stays Low until that run reaches 6 hours.
"""

from __future__ import annotations

import json
import socket
import time
from collections import defaultdict
from datetime import timedelta, timezone

import httpx

from app.db import connect
from app.schema import ensure_schema
from app.scoring import apply_infection_gate, lapse_adjust, leaf_wetness_by_day, load_rules, score_place
from app.seed import mark_status

GRID_STEP = 0.009
LOCK_KEY = 40420
SOURCE = "Open-Meteo hourly, lapse-adjusted"


def load() -> dict:
    _prefer_ipv4()
    with connect() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (LOCK_KEY,)).fetchone()["ok"]:
            return {"skipped": "already running"}
        try:
            _ensure_schema(conn)
            cells = _build_grid(conn)
            conn.commit()
            elevations = _fill_elevations(conn)
            conn.commit()
            points = _ensure_met_points(conn)
            hours = _fill_hourly(conn, points)
            _assign_met(conn, points)
            conn.commit()
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
            conn.commit()
    scored = score_stored()
    detail = (
        f"1 km cells {cells}, elevations filled {elevations}, "
        f"hourly rows {hours}, barangay blast scores {scored}."
    )
    mark_status("microclimate", "loaded", detail)
    return {"cells": cells, "elevations": elevations, "hourly": hours, "scores": scored}


def score_stored() -> int:
    """Write rice-blast barangay scores from hourly rows already in the database."""
    _prefer_ipv4()
    with connect() as conn:
        _ensure_schema(conn)
        ensure_schema(conn)
        hourly_count = conn.execute("SELECT COUNT(*) AS n FROM met_hourly").fetchone()["n"]
        if not hourly_count:
            return 0
        rule = next(item for item in load_rules(_rules()) if item["id"] == "rice_blast")
        gate = rule["gate"]
        hours = _hours_by_met(conn)
        cells = conn.execute(
            """
            SELECT g.id, g.barangay_id, g.elevation_m, g.met_id, m.elevation_m AS model_elevation_m
            FROM grid_cells g
            JOIN met_points m ON m.id = g.met_id
            WHERE g.met_id IS NOT NULL
            """
        ).fetchall()
        places = conn.execute(
            """
            SELECT b.id, b.municipality_id, b.name, m.name AS municipality
            FROM barangays b JOIN municipalities m ON m.id = b.municipality_id
            """
        ).fetchall()
        recent = {
            row["place_id"]: row["rain_sum"]
            for row in conn.execute(
                """
                SELECT place_id, SUM(rain_mm) AS rain_sum
                FROM weather_daily
                WHERE place_type = 'municipality'
                  AND source = 'Open-Meteo archive'
                  AND observed_on >= (SELECT MAX(observed_on) - INTERVAL '6 days' FROM weather_daily WHERE source = 'Open-Meteo archive')
                GROUP BY place_id
                """
            ).fetchall()
        }
        oni = conn.execute("SELECT anomaly_c FROM enso_oni ORDER BY year DESC, season_code DESC LIMIT 1").fetchone()
        oni_value = oni["anomaly_c"] if oni else None
        ndvi = {
            row["place_id"]: row["ndvi"]
            for row in conn.execute(
                """
                SELECT DISTINCT ON (place_id) place_id, ndvi
                FROM satellite
                WHERE place_type = 'barangay' AND ndvi IS NOT NULL
                ORDER BY place_id, observed_on DESC NULLS LAST
                """
            ).fetchall()
        }
        pocket = _pockets(cells, hours, gate)
        conn.execute("DELETE FROM risk_score WHERE place_type = 'barangay' AND threat_id = 'rice_blast'")
        conn.execute("DELETE FROM weather_forecast WHERE place_type = 'barangay' AND source = %s", (SOURCE,))
        written = 0
        counts: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for place in places:
            days = pocket.get(place["id"]) or {}
            surface = _mean_elevation(cells, place["id"])
            if surface is not None:
                conn.execute(
                    """
                    INSERT INTO terrain (place_type, place_id, elevation_m, slope_index, wetness_index, source)
                    VALUES ('barangay', %s, %s, NULL, NULL, 'Copernicus DEM via Open-Meteo elevation')
                    ON CONFLICT (place_type, place_id) DO UPDATE SET
                      elevation_m = EXCLUDED.elevation_m, source = EXCLUDED.source
                    """,
                    (place["id"], surface),
                )
            if not days:
                continue
            for offset, day in enumerate(sorted(days)):
                if offset > 6:
                    break
                summary = days[day]
                conn.execute(
                    """
                    INSERT INTO weather_forecast (
                      place_type, place_id, issued_on, day_offset, forecast_date, source,
                      temp_c, rh_pct, rain_mm
                    ) VALUES ('barangay', %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (place_type, place_id, day_offset, source) DO UPDATE SET
                      issued_on = EXCLUDED.issued_on,
                      forecast_date = EXCLUDED.forecast_date,
                      temp_c = EXCLUDED.temp_c,
                      rh_pct = EXCLUDED.rh_pct,
                      rain_mm = EXCLUDED.rain_mm
                    """,
                    (
                        place["id"],
                        sorted(days)[0],
                        offset,
                        day,
                        SOURCE,
                        summary["temp_c"],
                        summary["rh_pct"],
                        summary["rain_mm"],
                    ),
                )
                factors = {
                    "temp_c": summary["temp_c"],
                    "temp_min_c": summary.get("temp_min_c"),
                    "rh_pct": summary["rh_pct"],
                    "rain_mm": summary["rain_mm"],
                    "rain_sum_7d": recent.get(place["municipality_id"]),
                    "hours_rh90": summary["lwd_hours"],
                    "leaf_wetness_assumed": 0.0,
                    "oni": oni_value,
                    "ndvi": ndvi.get(place["id"]),
                }
                for season in ("wet", "dry"):
                    result = apply_infection_gate(
                        score_place(rule, factors, season),
                        summary["lwd_hours"],
                        rule,
                        ndvi=ndvi.get(place["id"]),
                    )
                    _insert_score(conn, place["id"], season, offset, result, ndvi.get(place["id"]))
                    counts[(season, offset)][result["risk_class"]] += 1
                    written += 1
        for (season, offset), class_counts in counts.items():
            payload = dict(class_counts)
            payload["unit"] = "barangay"
            conn.execute(
                """
                INSERT INTO run_log (threat_id, season, forecast_day, class_counts)
                VALUES ('rice_blast', %s, %s, %s::jsonb)
                """,
                (season, offset, json.dumps(payload)),
            )
        conn.commit()
    return written


def _rules():
    from app.paths import rules_dir

    return rules_dir()


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS met_points (
          id SERIAL PRIMARY KEY,
          lon DOUBLE PRECISION NOT NULL,
          lat DOUBLE PRECISION NOT NULL,
          elevation_m DOUBLE PRECISION,
          UNIQUE (lon, lat)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS met_hourly (
          met_id INTEGER NOT NULL REFERENCES met_points(id) ON DELETE CASCADE,
          valid_time TIMESTAMPTZ NOT NULL,
          temp_c DOUBLE PRECISION,
          rh_pct DOUBLE PRECISION,
          rain_mm DOUBLE PRECISION,
          PRIMARY KEY (met_id, valid_time)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_cells (
          id SERIAL PRIMARY KEY,
          barangay_id INTEGER NOT NULL REFERENCES barangays(id) ON DELETE CASCADE,
          lon DOUBLE PRECISION NOT NULL,
          lat DOUBLE PRECISION NOT NULL,
          elevation_m DOUBLE PRECISION,
          met_id INTEGER REFERENCES met_points(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS grid_cells_barangay_idx ON grid_cells (barangay_id)")


def _build_grid(conn) -> int:
    existing = conn.execute("SELECT COUNT(*) AS n FROM grid_cells").fetchone()["n"]
    if existing:
        return existing
    conn.execute("SET statement_timeout = '10min'")
    conn.execute(
        """
        CREATE TEMP TABLE squares ON COMMIT DROP AS
        SELECT (ST_SquareGrid(%s, env.geom)).geom AS geom
        FROM (SELECT ST_Envelope(ST_Collect(geom)) AS geom FROM municipalities) env
        """,
        (GRID_STEP,),
    )
    conn.execute("CREATE INDEX squares_gix ON squares USING GIST (geom)")
    conn.execute(
        """
        INSERT INTO grid_cells (barangay_id, lon, lat)
        SELECT id, ST_X(p), ST_Y(p)
        FROM (
          SELECT b.id, ST_PointOnSurface(ST_Intersection(s.geom, b.geom)) AS p
          FROM squares s
          JOIN barangays b ON ST_Intersects(s.geom, b.geom)
        ) q
        WHERE p IS NOT NULL AND NOT ST_IsEmpty(p)
        """
    )
    conn.execute(
        """
        INSERT INTO grid_cells (barangay_id, lon, lat)
        SELECT b.id, ST_X(ST_PointOnSurface(b.geom)), ST_Y(ST_PointOnSurface(b.geom))
        FROM barangays b
        WHERE NOT EXISTS (SELECT 1 FROM grid_cells g WHERE g.barangay_id = b.id)
        """
    )
    return conn.execute("SELECT COUNT(*) AS n FROM grid_cells").fetchone()["n"]


def _fill_elevations(conn) -> int:
    """One DEM sample per barangay. The 1 km elevation API quota rejects a sample on every cell."""
    rows = conn.execute(
        """
        SELECT b.id,
               ST_Y(ST_PointOnSurface(b.geom)) AS lat,
               ST_X(ST_PointOnSurface(b.geom)) AS lon
        FROM barangays b
        WHERE EXISTS (
          SELECT 1 FROM grid_cells g
          WHERE g.barangay_id = b.id AND g.elevation_m IS NULL
        )
        ORDER BY b.id
        """
    ).fetchall()
    filled = 0
    for start in range(0, len(rows), 40):
        batch = rows[start : start + 40]
        payload = _get(
            "https://api.open-meteo.com/v1/elevation?latitude="
            + ",".join(f"{row['lat']:.5f}" for row in batch)
            + "&longitude="
            + ",".join(f"{row['lon']:.5f}" for row in batch)
        )
        values = payload.get("elevation") or []
        for row, value in zip(batch, values):
            if value is None:
                continue
            conn.execute(
                """
                UPDATE grid_cells
                SET elevation_m = %s
                WHERE barangay_id = %s AND elevation_m IS NULL
                """,
                (value, row["id"]),
            )
            filled += 1
        conn.commit()
        print(f"barangay elevations {start + len(batch)}/{len(rows)}", flush=True)
        time.sleep(1.5)
    return filled


def _ensure_met_points(conn) -> list[dict]:
    for lat_i in range(11):
        for lon_i in range(11):
            lat = round(15.15 + lat_i * 0.1, 4)
            lon = round(120.35 + lon_i * 0.1, 4)
            conn.execute(
                "INSERT INTO met_points (lon, lat) VALUES (%s, %s) ON CONFLICT (lon, lat) DO NOTHING",
                (lon, lat),
            )
    return conn.execute("SELECT id, lon, lat, elevation_m FROM met_points ORDER BY id").fetchall()


def _fill_hourly(conn, points: list[dict]) -> int:
    existing = conn.execute("SELECT COUNT(*) AS n FROM met_hourly").fetchone()["n"]
    if existing:
        print(f"hourly already stored {existing}", flush=True)
        return existing
    conn.execute("DELETE FROM met_hourly")
    written = 0
    for start in range(0, len(points), 20):
        batch = points[start : start + 20]
        url = (
            "https://api.open-meteo.com/v1/forecast?latitude="
            + ",".join(f"{row['lat']:.4f}" for row in batch)
            + "&longitude="
            + ",".join(f"{row['lon']:.4f}" for row in batch)
            + "&hourly=temperature_2m,relative_humidity_2m,precipitation"
            + "&forecast_days=7&timezone=Asia%2FManila"
        )
        payload = _get(url)
        if isinstance(payload, dict):
            payload = [payload]
        for point, block in zip(batch, payload):
            if block.get("elevation") is not None:
                conn.execute("UPDATE met_points SET elevation_m = %s WHERE id = %s", (block["elevation"], point["id"]))
                point["elevation_m"] = block["elevation"]
            hourly = block.get("hourly") or {}
            times = hourly.get("time") or []
            for index, stamp in enumerate(times):
                conn.execute(
                    """
                    INSERT INTO met_hourly (met_id, valid_time, temp_c, rh_pct, rain_mm)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (met_id, valid_time) DO UPDATE SET
                      temp_c = EXCLUDED.temp_c, rh_pct = EXCLUDED.rh_pct, rain_mm = EXCLUDED.rain_mm
                    """,
                    (
                        point["id"],
                        _local_stamp(stamp),
                        _at(hourly, "temperature_2m", index),
                        _at(hourly, "relative_humidity_2m", index),
                        _at(hourly, "precipitation", index),
                    ),
                )
                written += 1
        conn.commit()
        print(f"hourly points {start + len(batch)}/{len(points)}", flush=True)
        time.sleep(0.25)
    return written


def _assign_met(conn, points: list[dict]) -> None:
    cells = conn.execute("SELECT id, lon, lat FROM grid_cells").fetchall()
    updates = []
    for cell in cells:
        nearest = min(points, key=lambda point: (point["lon"] - cell["lon"]) ** 2 + (point["lat"] - cell["lat"]) ** 2)
        updates.append((nearest["id"], cell["id"]))
    with conn.cursor() as cur:
        cur.executemany("UPDATE grid_cells SET met_id = %s WHERE id = %s", updates)


def _hours_by_met(conn) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    rows = conn.execute(
        """
        SELECT met_id, valid_time, temp_c, rh_pct, rain_mm
        FROM met_hourly
        ORDER BY met_id, valid_time
        """
    ).fetchall()
    for row in rows:
        local = row["valid_time"].astimezone(timezone(timedelta(hours=8)))
        grouped[row["met_id"]].append(
            {
                "temp_c": row["temp_c"],
                "rh_pct": row["rh_pct"],
                "rain_mm": row["rain_mm"] or 0,
                "date": local.date().isoformat(),
            }
        )
    return grouped


def _pockets(cells, hours_by_met, gate) -> dict[int, dict[str, dict]]:
    by_barangay: dict[int, dict[str, dict]] = defaultdict(dict)
    for cell in cells:
        series = hours_by_met.get(cell["met_id"]) or []
        if not series:
            continue
        model_elevation = cell["model_elevation_m"] if cell["model_elevation_m"] is not None else cell["elevation_m"] or 0
        surface = cell["elevation_m"] if cell["elevation_m"] is not None else model_elevation
        adjusted = []
        for hour in series:
            temp = hour["temp_c"]
            if temp is not None:
                temp = lapse_adjust(temp, model_elevation, surface)
            adjusted.append({**hour, "temp_c": temp})
        wet_days = leaf_wetness_by_day(adjusted, gate)
        daily: dict[str, list] = defaultdict(list)
        for hour in adjusted:
            daily[hour["date"]].append(hour)
        for date, day_hours in daily.items():
            temps = [hour["temp_c"] for hour in day_hours if hour["temp_c"] is not None]
            humid = [hour["rh_pct"] for hour in day_hours if hour["rh_pct"] is not None]
            summary = {
                "lwd_hours": wet_days.get(date, 0),
                "temp_c": round(sum(temps) / len(temps), 2) if temps else None,
                "temp_min_c": round(min(temps), 2) if temps else None,
                "rh_pct": round(sum(humid) / len(humid), 1) if humid else None,
                "rain_mm": round(sum(hour["rain_mm"] for hour in day_hours), 2),
            }
            current = by_barangay[cell["barangay_id"]].get(date)
            if current is None or (summary["lwd_hours"], summary["rh_pct"] or 0) > (current["lwd_hours"], current["rh_pct"] or 0):
                by_barangay[cell["barangay_id"]][date] = summary
    return by_barangay


def _mean_elevation(cells, barangay_id: int) -> float | None:
    values = [cell["elevation_m"] for cell in cells if cell["barangay_id"] == barangay_id and cell["elevation_m"] is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _insert_score(conn, place_id: int, season: str, forecast_day: int, result: dict, ndvi) -> None:
    exposure_ha = 0 if ndvi is not None and ndvi < 0.2 else None
    exposure_source = "Sentinel-2 NDVI below 0.2" if exposure_ha == 0 else None
    conn.execute(
        """
        INSERT INTO risk_score (
          place_type, place_id, threat_id, season, forecast_day, score, risk_class,
          factors_used, factors_skipped, explanation, exposure_ha, exposure_source,
          confidence, assumption_note
        ) VALUES (
          'barangay', %s, 'rice_blast', %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s
        )
        ON CONFLICT (place_type, place_id, threat_id, season, forecast_day)
        DO UPDATE SET
          score = EXCLUDED.score,
          risk_class = EXCLUDED.risk_class,
          factors_used = EXCLUDED.factors_used,
          factors_skipped = EXCLUDED.factors_skipped,
          explanation = EXCLUDED.explanation,
          exposure_ha = EXCLUDED.exposure_ha,
          exposure_source = EXCLUDED.exposure_source,
          confidence = EXCLUDED.confidence,
          assumption_note = EXCLUDED.assumption_note,
          computed_at = now()
        """,
        (
            place_id,
            season,
            forecast_day,
            result["score"],
            result["risk_class"],
            json.dumps(result["factors_used"]),
            json.dumps(result["factors_skipped"]),
            result["explanation"],
            exposure_ha,
            exposure_source,
            result.get("confidence"),
            result.get("assumption_note"),
        ),
    )


def _get(url: str):
    last_error = None
    for attempt in range(4):
        try:
            response = httpx.get(url, timeout=180, headers={"User-Agent": "CROPWATCH-school-project"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            wait = 25 if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429 else 2 + attempt * 3
            time.sleep(wait)
    raise last_error


def _local_stamp(stamp: str) -> str:
    if stamp.endswith("Z") or "+" in stamp[10:]:
        return stamp
    return stamp + "+08:00"


def _at(block, key, index):
    values = block.get(key) or []
    if index >= len(values) or values[index] is None:
        return None
    return values[index]


def _prefer_ipv4() -> None:
    if getattr(socket, "_cropwatch_ipv4", False):
        return
    original = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:
            family = socket.AF_INET
        return original(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo
    socket._cropwatch_ipv4 = True


if __name__ == "__main__":
    print(load())
