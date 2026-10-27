"""Build factor rows from PostGIS and write risk_score."""

from __future__ import annotations

import json
from collections import defaultdict

from app.db import connect
from app.schema import ensure_schema
from app.scoring import apply_infection_gate, climate_score, leaf_wetness_hours, load_rules, score_place


def rules():
    from app.paths import rules_dir

    return load_rules(rules_dir())


def recompute() -> dict:
    rule_list = rules()
    with connect() as conn:
        ensure_schema(conn)
        occurrence_count = conn.execute("SELECT COUNT(*) AS n FROM occurrence").fetchone()["n"]
        places = _places(conn)
        forecasts = _grouped(
            conn,
            """
            SELECT place_id, day_offset, temp_c, temp_min_c, rh_pct, hours_rh90, rain_mm,
                   wind_speed_kmh, wind_gust_kmh, wind_dir_deg, soil_moisture, soil_temp_c, forecast_date
            FROM weather_forecast
            WHERE place_type = 'municipality'
            ORDER BY place_id, day_offset
            """,
        )
        recent = _recent_rain(conn)
        planting = _planting_dates(conn)
        recent_wind = _recent_wind(conn)
        terrain = {row["place_id"]: row for row in conn.execute("SELECT * FROM terrain WHERE place_type = 'municipality'")}
        satellite = _latest_satellite(conn)
        rice = _best_rice(conn)
        management = {
            row["place_id"]: row
            for row in conn.execute("SELECT * FROM management WHERE place_type = 'municipality'")
        }
        canals = _canal_places(conn)
        oni = conn.execute(
            "SELECT anomaly_c FROM enso_oni ORDER BY year DESC, season_code DESC LIMIT 1"
        ).fetchone()
        oni_value = oni["anomaly_c"] if oni else None
        occurrences = _occurrences(conn) if occurrence_count else {}
        conn.execute("DELETE FROM risk_score WHERE place_type = 'municipality'")
        written = 0
        for place in places:
            rain_row = recent.get(place["id"]) or {}
            factors_base = {
                "rain_sum_7d": rain_row.get("sum"),
                "rain_max_7d": rain_row.get("max"),
                "soil_moisture": _soil(forecasts.get(place["id"]), recent_soil=None),
                "oni": oni_value,
                "canal_link": 1.0 if place["id"] in canals else 0.0 if canals else None,
                "nitrogen_kg_ha": (management.get(place["id"]) or {}).get("nitrogen_kg_ha"),
            }
            sat = satellite.get(place["id"]) or {}
            factors_base.update(
                {
                    "ndvi": sat.get("ndvi"),
                    "evi": sat.get("evi"),
                    "ndwi": sat.get("ndwi"),
                    "lswi": sat.get("lswi"),
                    "swir": sat.get("swir"),
                    "lst_c": sat.get("lst_c"),
                    "flood_fraction": sat.get("flood_fraction"),
                }
            )
            exposure_ha, exposure_source = _exposure(place, rice.get(place["id"]), sat)
            for rule in rule_list:
                threat_hits = occurrences.get(rule["id"], set()) if occurrence_count else None
                place_factors = dict(factors_base)
                if threat_hits is not None:
                    place_factors["previous_occurrence"] = 1.0 if place["id"] in threat_hits else 0.0
                days = forecasts.get(place["id"]) or []
                strong_dates = _strong_dates(recent_wind.get(place["id"], []), days)
                for season in ("wet", "dry"):
                    if rule.get("season_role") == "modifier":
                        place_factors["climate_score"] = climate_score(season, oni_value, rule["id"])
                    if not days:
                        result = apply_infection_gate(
                            score_place(rule, {**place_factors, "temp_c": None, "rh_pct": None, "rain_mm": None}, season),
                            None,
                            rule,
                            ndvi=place_factors.get("ndvi"),
                        )
                        _insert(conn, place["id"], rule["id"], season, 0, result, exposure_ha, exposure_source)
                        written += 1
                        continue
                    for day in days:
                        day_factors = dict(place_factors)
                        hours, wetness_assumed = leaf_wetness_hours(day.get("hours_rh90"), day.get("rh_pct"))
                        day_factors.update(
                            {
                                "temp_c": day["temp_c"],
                                "temp_min_c": day.get("temp_min_c"),
                                "rh_pct": day["rh_pct"],
                                "hours_rh90": hours,
                                "leaf_wetness_assumed": 1.0 if wetness_assumed else 0.0,
                                "rain_mm": day["rain_mm"],
                                "wind_speed_kmh": day["wind_speed_kmh"],
                                "wind_gust_kmh": day.get("wind_gust_kmh"),
                                "wind_dir_deg": day["wind_dir_deg"],
                                "soil_temp_c": day["soil_temp_c"],
                                "storm_active": _storm_active(day.get("forecast_date"), strong_dates),
                                "days_after_planting": _crop_days(planting.get(place["id"]), day.get("forecast_date")),
                            }
                        )
                        if day["soil_moisture"] is not None:
                            day_factors["soil_moisture"] = day["soil_moisture"]
                        day_factors["blb_spread"] = _blb_spread(
                            day_factors.get("canal_link"),
                            day_factors.get("flood_fraction"),
                            day_factors.get("soil_moisture"),
                        )
                        wet_hours = None if day_factors.get("leaf_wetness_assumed") else day_factors.get("hours_rh90")
                        result = apply_infection_gate(
                            score_place(rule, day_factors, season),
                            wet_hours,
                            rule,
                            ndvi=day_factors.get("ndvi"),
                        )
                        _insert(
                            conn,
                            place["id"],
                            rule["id"],
                            season,
                            day["day_offset"],
                            result,
                            exposure_ha,
                            exposure_source,
                        )
                        written += 1
        for rule in rule_list:
            for season in ("wet", "dry"):
                for day_offset in range(7):
                    counts = conn.execute(
                        """
                        SELECT risk_class, COUNT(*) AS n
                        FROM risk_score
                        WHERE threat_id = %s AND season = %s AND forecast_day = %s
                          AND place_type = 'municipality'
                        GROUP BY risk_class
                        """,
                        (rule["id"], season, day_offset),
                    ).fetchall()
                    if counts:
                        conn.execute(
                            """
                            INSERT INTO run_log (threat_id, season, forecast_day, class_counts)
                            VALUES (%s, %s, %s, %s::jsonb)
                            """,
                            (
                                rule["id"],
                                season,
                                day_offset,
                                json.dumps({row["risk_class"]: row["n"] for row in counts}),
                            ),
                        )
        from app.insights import rebuild_history

        rebuild_history(conn)
        conn.commit()
    from ingest.microclimate import score_stored

    barangay_scores = score_stored()
    return {
        "scores_written": written,
        "threats": [rule["id"] for rule in rule_list],
        "barangay_blast_scores": barangay_scores,
    }


def _insert(conn, place_id, threat_id, season, forecast_day, result, exposure_ha, exposure_source):
    conn.execute(
        """
        INSERT INTO risk_score (
          place_type, place_id, threat_id, season, forecast_day, score, risk_class,
          factors_used, factors_skipped, explanation, exposure_ha, exposure_source,
          confidence, assumption_note
        ) VALUES (
          'municipality', %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s
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
            threat_id,
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


def _places(conn):
    return conn.execute("SELECT id, name, slug, area_ha FROM municipalities ORDER BY name").fetchall()


def _grouped(conn, sql):
    grouped = defaultdict(list)
    for row in conn.execute(sql):
        grouped[row["place_id"]].append(row)
    return grouped


def _recent_rain(conn):
    rows = conn.execute(
        """
        SELECT place_id, SUM(rain_mm) AS rain_sum, MAX(rain_mm) AS rain_max
        FROM weather_daily
        WHERE place_type = 'municipality'
          AND observed_on >= (SELECT MAX(observed_on) - INTERVAL '6 days' FROM weather_daily)
        GROUP BY place_id
        """
    ).fetchall()
    return {row["place_id"]: {"sum": row["rain_sum"], "max": row["rain_max"]} for row in rows}


def _soil(days, recent_soil):
    if not days:
        return recent_soil
    values = [day["soil_moisture"] for day in days if day["soil_moisture"] is not None]
    if not values:
        return recent_soil
    return values[0]


def _latest_satellite(conn):
    rows = conn.execute(
        """
        SELECT DISTINCT ON (place_id) *
        FROM satellite
        WHERE place_type = 'municipality'
        ORDER BY place_id, observed_on DESC NULLS LAST
        """
    ).fetchall()
    return {row["place_id"]: row for row in rows}


def _best_rice(conn):
    rows = conn.execute(
        """
        SELECT DISTINCT ON (place_id) *
        FROM rice_area
        WHERE place_type = 'municipality'
        ORDER BY place_id, CASE WHEN source ILIKE '%prism%' THEN 0 ELSE 1 END, source
        """
    ).fetchall()
    return {row["place_id"]: row for row in rows}


def _canal_places(conn):
    rows = conn.execute(
        "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind IN ('canal', 'river')"
    ).fetchall()
    places = set()
    for row in rows:
        places.add(row["place_a"])
        places.add(row["place_b"])
    return places


def _occurrences(conn):
    grouped = defaultdict(set)
    rows = conn.execute(
        "SELECT place_id, threat_id FROM occurrence WHERE place_type = 'municipality'"
    ).fetchall()
    for row in rows:
        grouped[row["threat_id"]].add(row["place_id"])
    return grouped


def _planting_dates(conn):
    dates = {}
    rows = conn.execute(
        """
        SELECT place_id, planting_date FROM rice_area
        WHERE place_type = 'municipality' AND planting_date IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        dates[row["place_id"]] = row["planting_date"]
    rows = conn.execute(
        """
        SELECT DISTINCT ON (place_id) place_id, sos_date
        FROM satellite
        WHERE place_type = 'municipality' AND sos_date IS NOT NULL
        ORDER BY place_id, observed_on DESC NULLS LAST
        """
    ).fetchall()
    for row in rows:
        dates.setdefault(row["place_id"], row["sos_date"])
    return dates


def _recent_wind(conn):
    rows = conn.execute(
        """
        SELECT place_id, observed_on, wind_speed_kmh
        FROM weather_daily
        WHERE place_type = 'municipality'
          AND observed_on >= (SELECT MAX(observed_on) - INTERVAL '13 days' FROM weather_daily)
        """
    ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["place_id"]].append(row)
    return grouped


def _strong_dates(recent_rows, forecast_days):
    dates = []
    for row in recent_rows:
        if _is_storm(row.get("wind_speed_kmh"), None):
            dates.append(row["observed_on"])
    for day in forecast_days:
        if _is_storm(day.get("wind_speed_kmh"), day.get("wind_gust_kmh")):
            dates.append(day.get("forecast_date"))
    return [stamp for stamp in dates if stamp is not None]


def _is_storm(wind, gust) -> bool:
    if wind is not None and float(wind) >= 40:
        return True
    if gust is not None and float(gust) >= 60:
        return True
    return False


def _storm_active(day_date, strong_dates) -> float:
    if day_date is None:
        return 0.0
    for stamp in strong_dates:
        delta = (day_date - stamp).days
        if 0 <= delta <= 14:
            return 1.0
    return 0.0


def _crop_days(anchor, forecast_date):
    if anchor is None or forecast_date is None:
        return None
    return (forecast_date - anchor).days


def _blb_spread(canal, flood_fraction, soil):
    parts = []
    if canal is not None:
        parts.append(float(canal))
    if flood_fraction is not None:
        parts.append(min(1.0, float(flood_fraction) / 0.25))
    if soil is not None:
        parts.append(max(0.0, min(1.0, (float(soil) - 0.22) / 0.20)))
    if not parts:
        return None
    return round(max(parts), 3)


def _exposure(place, rice_row, satellite_row):
    if rice_row and rice_row.get("rice_ha") is not None:
        return rice_row["rice_ha"], rice_row["source"]
    fraction = satellite_row.get("rice_fraction") if satellite_row else None
    if fraction is not None and place.get("area_ha"):
        return round(float(fraction) * float(place["area_ha"]), 1), "Sentinel-1 estimate"
    return None, None
