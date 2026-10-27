"""Read models shared by the map and the assistant. Both see the same rows."""

from __future__ import annotations

import json

from app.algorithms import build_adjacency, connected_components, inspection_route, rank_places
from app.db import connect
from app.insights import (
    driver_lines,
    fastest_rising,
    inspection_priority,
    load_board,
    narrative,
    weather_anomaly,
)
from app.paths import rules_dir
from app.scoring import CLASS_LABELS, load_rules
from app.seed import slugify


def threat_list() -> list[dict]:
    return [
        {
            "id": rule["id"],
            "name": rule["name"],
            "summary": rule["summary"],
            "confidence": rule.get("confidence", "moderate"),
            "season_role": rule.get("season_role", "none"),
        }
        for rule in load_rules(rules_dir())
    ]


def dataset_status() -> list[dict]:
    with connect() as conn:
        return conn.execute(
            "SELECT dataset, state, detail FROM dataset_status ORDER BY dataset"
        ).fetchall()


def map_features(threat_id: str, season: str, forecast_day: int) -> dict:
    with connect() as conn:
        barangays = conn.execute("SELECT COUNT(*) AS n FROM barangays").fetchone()["n"]
        if not barangays:
            rows = _municipality_rows(conn, threat_id, season, forecast_day)
            return _with_trend(conn, _collection(rows, "municipality"), threat_id, season, forecast_day)
        rows = conn.execute(
            """
            SELECT m.slug || '--' || b.slug AS slug,
                   b.name,
                   m.name AS municipality,
                   ST_AsGeoJSON(b.geom) AS geometry,
                   COALESCE(rb.risk_class, rm.risk_class, 'insufficient_data') AS risk_class,
                   COALESCE(rb.score, rm.score) AS score,
                   CASE
                     WHEN rb.score IS NOT NULL THEN 'barangay'
                     WHEN rm.score IS NOT NULL THEN 'municipality'
                     ELSE 'none'
                   END AS score_origin,
                   COALESCE(rb.exposure_ha, rm.exposure_ha) AS exposure_ha,
                   COALESCE(rb.exposure_source, rm.exposure_source) AS exposure_source,
                   COALESCE(rb.explanation, rm.explanation) AS explanation,
                   COALESCE(wb.temp_c, wm.temp_c) AS temp_c,
                   COALESCE(wb.rh_pct, wm.rh_pct) AS rh_pct,
                   COALESCE(wb.rain_mm, wm.rain_mm) AS rain_mm,
                   COALESCE(wb.wind_speed_kmh, wm.wind_speed_kmh) AS wind_speed_kmh,
                   COALESCE(wb.soil_moisture, wm.soil_moisture) AS soil_moisture,
                   COALESCE(wb.hours_rh90, wm.hours_rh90) AS hours_rh90,
                   COALESCE(tb.elevation_m, tm.elevation_m) AS elevation_m,
                   COALESCE(sb.ndvi, sm.ndvi) AS ndvi,
                   COALESCE(sb.ndwi, sm.ndwi) AS ndwi,
                   COALESCE(sb.ndvi_change, sm.ndvi_change) AS ndvi_change,
                   COALESCE(sb.flood_fraction, sm.flood_fraction) AS flood_fraction,
                   COALESCE(sb.evi, sm.evi) AS evi,
                   COALESCE(sb.lswi, sm.lswi) AS lswi,
                   COALESCE(sb.lst_c, sm.lst_c) AS lst_c,
                   COALESCE(sb.rice_fraction, sm.rice_fraction) AS rice_fraction
            FROM barangays b
            JOIN municipalities m ON m.id = b.municipality_id
            LEFT JOIN risk_score rb
              ON rb.place_id = b.id AND rb.place_type = 'barangay'
             AND rb.threat_id = %s AND rb.season = %s AND rb.forecast_day = %s
            LEFT JOIN risk_score rm
              ON rm.place_id = m.id AND rm.place_type = 'municipality'
             AND rm.threat_id = %s AND rm.season = %s AND rm.forecast_day = %s
            LEFT JOIN LATERAL (
              SELECT temp_c, rh_pct, rain_mm, wind_speed_kmh, soil_moisture, hours_rh90
              FROM weather_forecast
              WHERE place_type = 'barangay' AND place_id = b.id AND day_offset = %s
              LIMIT 1
            ) wb ON true
            LEFT JOIN LATERAL (
              SELECT temp_c, rh_pct, rain_mm, wind_speed_kmh, soil_moisture, hours_rh90
              FROM weather_forecast
              WHERE place_type = 'municipality' AND place_id = m.id AND day_offset = %s
              LIMIT 1
            ) wm ON true
            LEFT JOIN terrain tb ON tb.place_type = 'barangay' AND tb.place_id = b.id
            LEFT JOIN terrain tm ON tm.place_type = 'municipality' AND tm.place_id = m.id
            LEFT JOIN LATERAL (
              SELECT ndvi, ndwi, ndvi_change, flood_fraction, evi, lswi, lst_c, rice_fraction
              FROM satellite
              WHERE place_type = 'barangay' AND place_id = b.id
              ORDER BY observed_on DESC NULLS LAST
              LIMIT 1
            ) sb ON true
            LEFT JOIN LATERAL (
              SELECT ndvi, ndwi, ndvi_change, flood_fraction, evi, lswi, lst_c, rice_fraction
              FROM satellite
              WHERE place_type = 'municipality' AND place_id = m.id
              ORDER BY observed_on DESC NULLS LAST
              LIMIT 1
            ) sm ON true
            ORDER BY m.name, b.name
            """,
            (threat_id, season, forecast_day, threat_id, season, forecast_day, forecast_day, forecast_day),
        ).fetchall()
        return _with_trend(conn, _collection(rows, "barangay"), threat_id, season, forecast_day)


def place_detail(slug: str, threat_id: str, season: str, forecast_day: int) -> dict | None:
    with connect() as conn:
        barangay = _barangay_place(conn, slug)
        if barangay:
            place = {
                "id": barangay["id"],
                "slug": slug,
                "name": barangay["name"],
                "municipality": barangay["municipality"],
                "source": barangay["source"],
                "area_ha": barangay["area_ha"],
            }
            place_type = "barangay"
            score = conn.execute(
                """
                SELECT * FROM risk_score
                WHERE place_type = 'barangay' AND place_id = %s
                  AND threat_id = %s AND season = %s AND forecast_day = %s
                """,
                (barangay["id"], threat_id, season, forecast_day),
            ).fetchone()
            if not score:
                score = conn.execute(
                    """
                    SELECT * FROM risk_score
                    WHERE place_type = 'municipality' AND place_id = %s
                      AND threat_id = %s AND season = %s AND forecast_day = %s
                    """,
                    (barangay["municipality_id"], threat_id, season, forecast_day),
                ).fetchone()
                note = "This outline is the barangay. This threat still uses the municipality score. Rice blast is scored on the barangay itself."
            else:
                note = (
                    "The class is the 1 km cell inside this barangay with the longest leaf-wetness run. "
                    "Temperature is shifted from the Open-Meteo grid by 0.65 C per 100 m, using the barangay's Copernicus DEM elevation. "
                    "Rice blast stays Low until 6 consecutive hours are humid enough for spores. "
                    "Sentinel-2 canopy is still empty, so fallow land is not masked out yet."
                )
            forecast_place = (place_type, barangay["id"]) if score and score["place_type"] == "barangay" else ("municipality", barangay["municipality_id"])
            terrain_place = ("barangay", barangay["id"])
        else:
            place_row = conn.execute(
                """
                SELECT id, slug, name, source, area_ha FROM municipalities
                WHERE slug = %s OR slug = %s OR name ILIKE %s
                """,
                (slug, slugify(slug), slug),
            ).fetchone()
            if not place_row:
                return None
            place = dict(place_row)
            place["municipality"] = None
            place_type = "municipality"
            score = conn.execute(
                """
                SELECT * FROM risk_score
                WHERE place_type = 'municipality' AND place_id = %s
                  AND threat_id = %s AND season = %s AND forecast_day = %s
                """,
                (place["id"], threat_id, season, forecast_day),
            ).fetchone()
            forecast_place = ("municipality", place["id"])
            terrain_place = ("municipality", place["id"])
            barangay_count = conn.execute(
                "SELECT COUNT(*) AS n FROM barangays WHERE municipality_id = %s",
                (place["id"],),
            ).fetchone()["n"]
            note = (
                f"{barangay_count} barangay outlines are on the map."
                if barangay_count
                else "Official barangay polygons are not loaded. The score is for the whole municipality."
            )
        forecast = conn.execute(
            """
            SELECT day_offset, forecast_date, temp_c, temp_min_c, rh_pct, hours_rh90, rain_mm,
                   wind_speed_kmh, wind_gust_kmh, soil_moisture, soil_temp_c
            FROM weather_forecast
            WHERE place_type = %s AND place_id = %s
            ORDER BY day_offset
            """,
            forecast_place,
        ).fetchall()
        terrain = conn.execute(
            "SELECT elevation_m, slope_index, wetness_index, source FROM terrain WHERE place_type = %s AND place_id = %s",
            terrain_place,
        ).fetchone()
        if not terrain and barangay:
            terrain = conn.execute(
                "SELECT elevation_m, slope_index, wetness_index, source FROM terrain WHERE place_type = 'municipality' AND place_id = %s",
                (barangay["municipality_id"],),
            ).fetchone()
        notes = conn.execute(
            """
            SELECT n.body, n.created_at, u.display_name
            FROM field_notes n JOIN users u ON u.id = n.user_id
            WHERE n.place_type = %s AND n.place_id = %s
            ORDER BY n.created_at DESC
            LIMIT 8
            """,
            (place_type, place["id"]),
        ).fetchall()
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, _threat_name(threat_id))
        board_by_slug = {row["slug"]: row for row in board}
        municipality_slug = barangay["municipality_slug"] if barangay else place["slug"]
        municipality_id = barangay["municipality_id"] if barangay else place["id"]
        parent = board_by_slug.get(municipality_slug)
        rain_row = conn.execute(
            """
            SELECT SUM(rain_mm) AS rain_sum
            FROM weather_daily
            WHERE place_type = 'municipality' AND place_id = %s
              AND observed_on >= (
                SELECT MAX(observed_on) - INTERVAL '6 days' FROM weather_daily WHERE place_type = 'municipality'
              )
            """,
            (municipality_id,),
        ).fetchone()
        history_days = conn.execute(
            """
            SELECT observed_on, rh_pct, rain_mm
            FROM weather_daily
            WHERE place_type = 'municipality' AND place_id = %s
            """,
            (municipality_id,),
        ).fetchall()
        satellite_change = conn.execute(
            """
            SELECT ndvi_change FROM satellite
            WHERE place_type = 'municipality' AND place_id = %s AND ndvi_change IS NOT NULL
            ORDER BY observed_on DESC NULLS LAST
            LIMIT 1
            """,
            (municipality_id,),
        ).fetchone()
        exposure_share = None
        if barangay and score and score.get("exposure_ha") is not None:
            peer = conn.execute(
                """
                SELECT MAX(exposure_ha) AS max_ha FROM risk_score
                WHERE place_type = 'barangay' AND threat_id = %s AND season = %s AND forecast_day = %s
                """,
                (threat_id, season, forecast_day),
            ).fetchone()
            if peer and peer["max_ha"]:
                exposure_share = float(score["exposure_ha"]) / float(peer["max_ha"])
    selected_forecast = next((row for row in forecast if row["day_offset"] == forecast_day), None)
    anomaly = weather_anomaly(
        {
            "observed_on": selected_forecast["forecast_date"] if selected_forecast else None,
            "rh_pct": selected_forecast["rh_pct"] if selected_forecast else None,
            "rain_sum_7d": rain_row["rain_sum"] if rain_row else None,
        },
        history_days,
    )
    insight = _insight(
        place["name"],
        _threat_name(threat_id),
        score,
        parent,
        anomaly,
        barangay is not None,
        satellite_change["ndvi_change"] if satellite_change else None,
        exposure_share,
    )
    from app.map_intel import factor_rows, score_origin, why_line, why_now

    origin, origin_note = score_origin(barangay is not None, score["place_type"] if score else None)
    payload = dict(place)
    payload["barangay_note"] = note
    payload["score_origin"] = origin
    payload["score_origin_note"] = origin_note
    payload["factor_rows"] = factor_rows(score)
    payload["why_line"] = why_line(_threat_name(threat_id), score)
    payload["why_now"] = why_now(parent["trend"] if parent else None, score)
    payload["score"] = _jsonable(score) if score else None
    payload["forecast"] = [_jsonable(row) for row in forecast]
    payload["terrain"] = _jsonable(terrain) if terrain else None
    payload["notes"] = [_jsonable(row) for row in notes]
    payload["insight"] = insight
    return _jsonable(payload)


def priority(threat_id: str, season: str, forecast_day: int, municipality_slug: str | None = None) -> list[dict]:
    with connect() as conn:
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, _threat_name(threat_id))
        by_slug = {row["slug"]: row for row in board}
        barangay_rows = conn.execute(
            """
            SELECT b.id, m.slug AS municipality_slug, m.slug || '--' || b.slug AS slug,
                   b.name || ', ' || m.name AS name,
                   r.risk_class, r.exposure_ha, r.exposure_source, r.score
            FROM barangays b
            JOIN municipalities m ON m.id = b.municipality_id
            JOIN risk_score r ON r.place_id = b.id AND r.place_type = 'barangay'
            WHERE r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
            """,
            (threat_id, season, forecast_day),
        ).fetchall()
        if barangay_rows:
            if municipality_slug:
                barangay_rows = [row for row in barangay_rows if row["municipality_slug"] == municipality_slug]
            max_exposure = max((float(row["exposure_ha"]) for row in barangay_rows if row["exposure_ha"] is not None), default=None)
            ranked_rows = []
            for row in barangay_rows:
                parent = by_slug.get(row["municipality_slug"])
                share = None
                if max_exposure and row["exposure_ha"] is not None and max_exposure > 0:
                    share = float(row["exposure_ha"]) / max_exposure
                trend = parent["trend"] if parent else {"available": False, "direction": None, "arrow": "", "sentence": ""}
                hotspot = parent["hotspot"] if parent else {"kind": None, "assessed": False}
                ranked_rows.append(
                    {
                        "slug": row["slug"],
                        "name": row["name"],
                        "risk_class": row["risk_class"],
                        "score": row["score"],
                        "exposure_ha": row["exposure_ha"],
                        "exposure_source": row["exposure_source"],
                        "trend": trend,
                        "priority": inspection_priority(
                            {
                                "risk": row["score"],
                                "trend": trend["direction"] if trend.get("available") else None,
                                "exposure_share": share,
                                "hotspot": hotspot["kind"] if hotspot.get("assessed") else None,
                                "occurrence": parent.get("occurrence") if parent else None,
                            }
                        ),
                    }
                )
            ranked_rows.sort(key=lambda item: (-(item["priority"]["points"] or -1), item["name"]))
            return [_priority_row(index, item) for index, item in enumerate(ranked_rows[:40], start=1)]
    result = [_priority_row(row["inspection_rank"], row) for row in board]
    if municipality_slug:
        result = [row for row in result if row["slug"] == municipality_slug]
    return result


def algorithms(threat_id: str, season: str, forecast_day: int) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.slug, m.name, r.risk_class, r.exposure_ha
            FROM municipalities m
            JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
            WHERE r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
            """,
            (threat_id, season, forecast_day),
        ).fetchall()
        road_count = conn.execute(
            "SELECT COUNT(*) AS n FROM edges WHERE place_type = 'municipality' AND kind = 'road'"
        ).fetchone()["n"]
        kind = "road" if road_count else "boundary"
        edge_rows = conn.execute(
            "SELECT place_a, place_b, cost_km FROM edges WHERE place_type = 'municipality' AND kind = %s",
            (kind,),
        ).fetchall()
        canal_count = conn.execute(
            "SELECT COUNT(*) AS n FROM edges WHERE kind IN ('canal', 'river')"
        ).fetchone()["n"]
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, _threat_name(threat_id))
    ranked_input = [dict(row) for row in rows]
    ranked = rank_places(ranked_input)
    by_id = {row["id"]: row for row in rows}
    high_ids = [row["id"] for row in rows if row["risk_class"] in ("high", "very_high")]
    components = connected_components(high_ids, [(row["place_a"], row["place_b"]) for row in edge_rows])
    adjacency = build_adjacency([(row["place_a"], row["place_b"], row["cost_km"]) for row in edge_rows])
    # Isolated municipalities still need a node so a one-stop list does not crash.
    for row in rows:
        adjacency.setdefault(row["id"], [])
    route = inspection_route(
        [row["id"] for row in board if row.get("risk_class") != "insufficient_data"],
        adjacency,
    )
    return {
        "graph": (
            "OSM road links between municipalities."
            if road_count
            else "Shared municipal borders. OSM roads are not loaded, so this is an inspection order across neighboring municipalities, not turn-by-turn road navigation."
        ),
        "canal_note": (
            "Canal or river links are loaded and can be mentioned as a possible movement path."
            if canal_count
            else "Canal and river links are not loaded, so spread along waterways is not part of this run."
        ),
        "priority": [
            {
                "rank": item["rank"],
                "name": by_id[item["id"]]["name"],
                "slug": by_id[item["id"]]["slug"],
                "risk_class": by_id[item["id"]]["risk_class"],
                "risk_label": CLASS_LABELS.get(by_id[item["id"]]["risk_class"]),
                "exposure_ha": by_id[item["id"]]["exposure_ha"],
            }
            for item in ranked
        ],
        "clusters": [
            {
                "size": len(component),
                "names": [by_id[place_id]["name"] for place_id in component if place_id in by_id],
                "zone": len(component) > 1,
            }
            for component in components
        ],
        "route": {
            "distance_km": route["distance_km"],
            "stops": [by_id[place_id]["name"] for place_id in route["stops"] if place_id in by_id],
            "path": [by_id[place_id]["name"] for place_id in route["path"] if place_id in by_id],
        },
    }


def briefing(threat_id: str, season: str, forecast_day: int) -> dict:
    with connect() as conn:
        stats = conn.execute(
            "SELECT metric, period, value, unit, source_name, source_url, retrieved_on, note FROM provincial_stats"
        ).fetchall()
        barangay_scores = conn.execute(
            """
            SELECT COUNT(*) AS n FROM risk_score
            WHERE place_type = 'barangay' AND threat_id = %s AND season = %s AND forecast_day = %s
            """,
            (threat_id, season, forecast_day),
        ).fetchone()["n"]
        place_type = "barangay" if barangay_scores else "municipality"
        scores = conn.execute(
            """
            SELECT risk_class, COUNT(*) AS n,
                   SUM(exposure_ha) AS exposure_ha,
                   MAX(exposure_source) AS exposure_source
            FROM risk_score
            WHERE place_type = %s AND threat_id = %s AND season = %s AND forecast_day = %s
            GROUP BY risk_class
            """,
            (place_type, threat_id, season, forecast_day),
        ).fetchall()
        logs = conn.execute(
            """
            SELECT class_counts, computed_at FROM run_log
            WHERE threat_id = %s AND season = %s AND forecast_day = %s
            ORDER BY id DESC LIMIT 2
            """,
            (threat_id, season, forecast_day),
        ).fetchall()
        bank = conn.execute(
            """
            SELECT indicator, year, value, source FROM national_indicators
            WHERE indicator_id = 'AG.CON.FERT.ZS'
            ORDER BY year DESC LIMIT 1
            """
        ).fetchone()
        normals = conn.execute("SELECT COUNT(*) AS n FROM climate_normals").fetchone()["n"]
        enso = conn.execute(
            "SELECT season_code, year, anomaly_c FROM enso_oni ORDER BY year DESC, season_code DESC LIMIT 1"
        ).fetchone()
        forecast_date = conn.execute(
            "SELECT MIN(forecast_date) AS start_date FROM weather_forecast WHERE day_offset = %s",
            (forecast_day,),
        ).fetchone()
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, _threat_name(threat_id))
        rising = fastest_rising(board)
    by_class = {row["risk_class"]: row for row in scores}
    high_count = sum(by_class.get(name, {}).get("n", 0) for name in ("high", "very_high"))
    exposure_known = any(row["exposure_ha"] is not None for row in scores)
    change = "No earlier run to compare."
    if len(logs) >= 2:
        change = _change_sentence(logs[1]["class_counts"], logs[0]["class_counts"])
    anomaly = enso["anomaly_c"] if enso else None
    if anomaly is None:
        enso_label = None
    elif anomaly >= 0.5:
        enso_label = "El Nino"
    elif anomaly <= -0.5:
        enso_label = "La Nina"
    else:
        enso_label = "Neutral"
    return {
        "threat_id": threat_id,
        "season": season,
        "forecast_day": forecast_day,
        "forecast_date": forecast_date["start_date"].isoformat() if forecast_date and forecast_date["start_date"] else None,
        "ricelytics": [_jsonable(row) for row in stats],
        "risk_counts": {key: by_class.get(key, {}).get("n", 0) for key in CLASS_LABELS},
        "high_or_above": high_count,
        "exposure": {
            "available": exposure_known,
            "by_class_ha": {
                row["risk_class"]: row["exposure_ha"] for row in scores if row["exposure_ha"] is not None
            },
            "source": next((row["exposure_source"] for row in scores if row["exposure_source"]), None),
            "note": (
                "Hectares use the loaded rice layer."
                if exposure_known
                else "Exposed hectares are unavailable until a PRiSM file or a Sentinel-1 rice estimate is loaded. The risk map still shows where conditions are favorable."
            ),
        },
        "change_note": change,
        "world_bank": _jsonable(bank) if bank else None,
        "world_bank_note": "National Philippines figure. It is context for the briefing, not an input to the municipal score.",
        "pagasa_normals_loaded": normals > 0,
        "pagasa_note": (
            "A station climate baseline is loaded."
            if normals
            else "PAGASA normals are not loaded. This week's forecast is Open-Meteo, separate from a climate baseline."
        ),
        "enso": {
            "season": f"{enso['season_code']} {enso['year']}" if enso else None,
            "anomaly_c": anomaly,
            "label": enso_label,
            "source": "NOAA Oceanic Nino Index",
        },
        "fastest_rising": rising,
    }


def line_features(kind: str) -> dict:
    from shapely.geometry import mapping, shape
    from shapely.ops import linemerge, unary_union

    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, name, geojson FROM osm_features WHERE kind = %s",
            (kind,),
        ).fetchall()
    parts = []
    for row in rows:
        geometry = row["geojson"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if geometry:
            parts.append(shape(geometry))
    if not parts:
        return {"type": "FeatureCollection", "features": [], "loaded": False}
    merged = linemerge(unary_union(parts))
    lines = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    features = [
        {"type": "Feature", "geometry": mapping(line), "properties": {"kind": kind}}
        for line in lines
        if not line.is_empty
    ]
    return {"type": "FeatureCollection", "features": features, "loaded": bool(features)}


def _threat_name(threat_id: str) -> str:
    for rule in load_rules(rules_dir()):
        if rule["id"] == threat_id:
            return rule["name"]
    return threat_id


def _priority_row(rank: int, item: dict) -> dict:
    trend = item.get("trend") or {}
    priority = item.get("priority") or {}
    return {
        "rank": rank,
        "slug": item["slug"],
        "name": item["name"],
        "risk_class": item["risk_class"],
        "risk_label": CLASS_LABELS.get(item["risk_class"], item["risk_class"]),
        "score": item.get("score"),
        "exposure_ha": item.get("exposure_ha"),
        "exposure_source": item.get("exposure_source"),
        "trend_arrow": trend.get("arrow") or "",
        "trend_direction": trend.get("direction"),
        "trend_sentence": trend.get("sentence"),
        "priority_points": priority.get("points"),
        "priority_reasons": priority.get("reasons") or [],
    }


def _with_trend(conn, collection: dict, threat_id: str, season: str, forecast_day: int) -> dict:
    from app.command import _rule
    from app.map_intel import change_bucket

    board, _forecast_on = load_board(conn, threat_id, season, forecast_day, _threat_name(threat_id))
    by_slug = {row["slug"]: row for row in board}
    cuts = _rule(threat_id).get("cuts") or {}
    for feature in collection["features"]:
        parent = by_slug.get(str(feature["properties"]["slug"]).split("--", 1)[0])
        trend = parent["trend"] if parent else {}
        score = feature["properties"].get("score")
        feature["properties"]["trend_arrow"] = trend.get("arrow") or ""
        feature["properties"]["trend_direction"] = trend.get("direction")
        feature["properties"]["hazard_points"] = None if score is None else int(round(float(score) * 100))
        feature["properties"]["priority_points"] = (parent.get("priority") or {}).get("points") if parent else None
        feature["properties"]["change_bucket"] = change_bucket(feature["properties"].get("risk_class"), trend, cuts)
        feature["properties"]["change_scope"] = "municipality"
    return collection


def _insight(name, threat_name, score, parent, anomaly, barangay_outline, ndvi_change, exposure_share) -> dict:
    factors = score.get("factors_used") if score else []
    drivers = driver_lines(factors)
    trend = dict(parent["trend"]) if parent else {
        "available": False,
        "arrow": "",
        "direction": None,
        "sentence": "Trend is unavailable until daily scores are saved.",
    }
    if barangay_outline and trend.get("available"):
        trend["sentence"] = "Municipality trend: " + trend["sentence"]
    hotspot = parent["hotspot"] if parent else {
        "kind": None,
        "assessed": False,
        "neighbor_risk": None,
        "sentence": "Hotspot is unavailable.",
    }
    exposure_ha = score.get("exposure_ha") if score else None
    exposure_source = score.get("exposure_source") if score else None
    if exposure_ha is not None:
        exposure_sentence = (
            f"Exposed rice area on record: {exposure_ha} ha ({exposure_source or 'loaded source'}). "
            "Area stays separate from the hazard score."
        )
    else:
        exposure_sentence = "Exposed rice area is not loaded, so inspection priority does not use hectares."
    used_ids = {item.get("id") for item in (factors or []) if isinstance(item, dict)}
    context_notes = []
    if "crop_stage" in used_ids:
        context_notes.append("Crop stage is one of the hazard factors for this score.")
    else:
        context_notes.append("Crop stage is not in this score because no planting date or Sentinel start-of-season is loaded.")
    if ndvi_change is not None:
        context_notes.append(
            f"Loaded NDVI change is {float(ndvi_change):+.2f}. A decline does not identify the cause and does not mean pest damage."
        )
    else:
        context_notes.append("Satellite change is not loaded, so this briefing does not describe a vegetation decline.")
    if parent and not barangay_outline:
        priority = parent["priority"]
    else:
        priority = inspection_priority(
            {
                "risk": score.get("score") if score else None,
                "trend": trend.get("direction") if trend.get("available") else None,
                "exposure_share": exposure_share,
                "hotspot": hotspot.get("kind") if hotspot.get("assessed") else None,
                "occurrence": parent.get("occurrence") if parent else None,
            }
        )
    text = narrative(
        name,
        threat_name,
        score or {},
        trend,
        drivers,
        anomaly,
        hotspot,
        priority,
        exposure_sentence,
        context_notes,
    )
    return {
        "trend": trend,
        "drivers": drivers["items"],
        "driver_sentence": drivers["sentence"],
        "anomaly": anomaly,
        "hotspot": hotspot,
        "exposure_sentence": exposure_sentence,
        "context_notes": context_notes,
        "priority": priority,
        "action": "Inspect rice in this municipality when the class is high or rising. This does not mean the pest or disease is present.",
        "narrative": text,
    }


def _municipality_rows(conn, threat_id: str, season: str, forecast_day: int):
    return conn.execute(
        """
        SELECT m.slug, m.name, NULL AS municipality, ST_AsGeoJSON(m.geom) AS geometry,
               r.risk_class, r.score,
               CASE WHEN r.score IS NOT NULL THEN 'municipality' ELSE 'none' END AS score_origin,
               r.exposure_ha, r.exposure_source, r.explanation,
               w.temp_c, w.rh_pct, w.rain_mm, w.wind_speed_kmh, w.soil_moisture, w.hours_rh90,
               t.elevation_m, s.ndvi, s.ndwi, s.ndvi_change, s.flood_fraction,
               s.evi, s.lswi, s.lst_c, s.rice_fraction
        FROM municipalities m
        LEFT JOIN risk_score r
          ON r.place_id = m.id AND r.place_type = 'municipality'
         AND r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
        LEFT JOIN LATERAL (
          SELECT temp_c, rh_pct, rain_mm, wind_speed_kmh, soil_moisture, hours_rh90
          FROM weather_forecast
          WHERE place_type = 'municipality' AND place_id = m.id AND day_offset = %s
          LIMIT 1
        ) w ON true
        LEFT JOIN terrain t ON t.place_type = 'municipality' AND t.place_id = m.id
        LEFT JOIN LATERAL (
          SELECT ndvi, ndwi, ndvi_change, flood_fraction, evi, lswi, lst_c, rice_fraction
          FROM satellite
          WHERE place_type = 'municipality' AND place_id = m.id
          ORDER BY observed_on DESC NULLS LAST
          LIMIT 1
        ) s ON true
        ORDER BY m.name
        """,
        (threat_id, season, forecast_day, forecast_day),
    ).fetchall()


def _collection(rows, level: str) -> dict:
    features = []
    for row in rows:
        risk_class = row["risk_class"] or "insufficient_data"
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "slug": row["slug"],
                    "name": row["name"],
                    "municipality": row["municipality"],
                    "parent_slug": str(row["slug"]).split("--", 1)[0],
                    "level": level,
                    "risk_class": risk_class,
                    "risk_label": CLASS_LABELS.get(risk_class),
                    "score": row["score"],
                    "exposure_ha": row["exposure_ha"],
                    "exposure_source": row["exposure_source"],
                    "explanation": row["explanation"],
                    "temp_c": row["temp_c"],
                    "rh_pct": row["rh_pct"],
                    "rain_mm": row["rain_mm"],
                    "wind_speed_kmh": row["wind_speed_kmh"],
                    "soil_moisture": row["soil_moisture"],
                    "elevation_m": row["elevation_m"],
                    "ndvi": row["ndvi"],
                    "ndwi": row["ndwi"],
                    "ndvi_change": row["ndvi_change"],
                    "flood_fraction": row["flood_fraction"],
                    "score_origin": row.get("score_origin") or "none",
                    "hours_rh90": row.get("hours_rh90"),
                    "evi": row.get("evi"),
                    "lswi": row.get("lswi"),
                    "lst_c": row.get("lst_c"),
                    "rice_fraction": row.get("rice_fraction"),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "level": level,
        "layer_sources": {
            "weather": "Open-Meteo forecast for the selected day, at the municipality point unless a barangay forecast is stored.",
            "elevation": "Open-Meteo elevation (SRTM/Copernicus DEM).",
            "satellite": "Sentinel-2 zonal values when a satellite row is loaded.",
        },
        "features": features,
    }


def _barangay_place(conn, slug: str):
    if "--" not in slug:
        return None
    municipality_slug, barangay_slug = slug.split("--", 1)
    return conn.execute(
        """
        SELECT b.id, b.name, b.source, b.area_ha, b.municipality_id, m.name AS municipality, m.slug AS municipality_slug
        FROM barangays b
        JOIN municipalities m ON m.id = b.municipality_id
        WHERE m.slug = %s AND b.slug = %s
        """,
        (municipality_slug, barangay_slug),
    ).fetchone()


def _change_sentence(previous, current) -> str:
    if isinstance(previous, str):
        previous = json.loads(previous)
    if isinstance(current, str):
        current = json.loads(current)
    if current.get("unit") == "barangay" and previous.get("unit") != "barangay":
        return "These counts are barangays."
    parts = []
    for key in ("very_high", "high", "moderate", "low"):
        delta = int(current.get(key, 0)) - int(previous.get(key, 0))
        if delta:
            parts.append(f"{CLASS_LABELS[key]} {delta:+d}")
    return "Change since the previous run: " + ", ".join(parts) + "." if parts else "No class counts changed since the previous run."


def _jsonable(row):
    if row is None:
        return None
    payload = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return payload
