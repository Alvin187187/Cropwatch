"""Decision-support readings around the hazard score.

Hazard risk stays in the rule engine. Trend, weather baseline, neighbor
hotspots, and inspection priority are separate readings. A missing input is
named and left out. It is not filled in.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev

from app.scoring import CLASS_LABELS, apply_infection_gate, climate_score, leaf_wetness_hours, load_rules, score_place

PRIORITY_WEIGHTS = {
    "risk": 0.45,
    "trend": 0.15,
    "exposure": 0.25,
    "hotspot": 0.15,
    "occurrence": 0.05,
}
TREND_WINDOW_DAYS = 4
WEEK_WINDOW_DAYS = 2
ARROW = {"rising": "↑", "falling": "↓", "stable": "→"}


def rebuild_history(conn) -> int:
    """Score each saved weather day so later briefings can compare dates."""
    from app.paths import rules_dir
    from app.schema import ensure_schema

    ensure_schema(conn)
    rule_list = load_rules(rules_dir())
    daily = conn.execute(
        """
        SELECT place_id, observed_on, temp_c, temp_min_c, rh_pct, hours_rh90, rain_mm,
               wind_speed_kmh, soil_moisture
        FROM weather_daily
        WHERE place_type = 'municipality'
        ORDER BY place_id, observed_on
        """
    ).fetchall()
    if not daily:
        return 0
    grouped: dict[int, list] = defaultdict(list)
    for row in daily:
        grouped[row["place_id"]].append(row)
    satellite = {
        row["place_id"]: row
        for row in conn.execute(
            """
            SELECT DISTINCT ON (place_id) place_id, ndvi, ndvi_change, flood_fraction
            FROM satellite
            WHERE place_type = 'municipality'
            ORDER BY place_id, observed_on DESC NULLS LAST
            """
        ).fetchall()
    }
    planting = {}
    for row in conn.execute(
        """
        SELECT place_id, planting_date FROM rice_area
        WHERE place_type = 'municipality' AND planting_date IS NOT NULL
        """
    ).fetchall():
        planting[row["place_id"]] = row["planting_date"]
    canals = set()
    for row in conn.execute(
        "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind IN ('canal', 'river')"
    ).fetchall():
        canals.add(row["place_a"])
        canals.add(row["place_b"])
    canal_known = bool(canals)
    oni_row = conn.execute("SELECT anomaly_c FROM enso_oni ORDER BY year DESC, season_code DESC LIMIT 1").fetchone()
    oni = oni_row["anomaly_c"] if oni_row else None
    occurrence_rows = conn.execute(
        "SELECT place_id, threat_id FROM occurrence WHERE place_type = 'municipality'"
    ).fetchall()
    hits: dict[str, set] = defaultdict(set)
    for row in occurrence_rows:
        hits[row["threat_id"]].add(row["place_id"])
    conn.execute("DELETE FROM risk_history WHERE place_type = 'municipality'")
    written = 0
    for place_id, days in grouped.items():
        sat = satellite.get(place_id) or {}
        for index, day in enumerate(days):
            window = days[max(0, index - 6) : index + 1]
            rains = [item["rain_mm"] for item in window if item["rain_mm"] is not None]
            observed = _as_date(day["observed_on"])
            hours, wetness_assumed = leaf_wetness_hours(day.get("hours_rh90"), day.get("rh_pct"))
            anchor = planting.get(place_id)
            factors = {
                "temp_c": day["temp_c"],
                "temp_min_c": day.get("temp_min_c"),
                "rh_pct": day["rh_pct"],
                "hours_rh90": hours,
                "leaf_wetness_assumed": 1.0 if wetness_assumed else 0.0,
                "rain_mm": day["rain_mm"],
                "rain_sum_7d": sum(rains) if rains else None,
                "rain_max_7d": max(rains) if rains else None,
                "wind_speed_kmh": day["wind_speed_kmh"],
                "soil_moisture": day["soil_moisture"],
                "ndvi": sat.get("ndvi"),
                "ndvi_change": sat.get("ndvi_change"),
                "flood_fraction": sat.get("flood_fraction"),
                "oni": oni,
                "canal_link": 1.0 if place_id in canals else 0.0 if canal_known else None,
                "days_after_planting": (observed - _as_date(anchor)).days if anchor else None,
            }
            factors["blb_spread"] = _spread(factors.get("canal_link"), factors.get("flood_fraction"), factors.get("soil_moisture"))
            for rule in rule_list:
                if occurrence_rows:
                    factors["previous_occurrence"] = 1.0 if place_id in hits.get(rule["id"], set()) else 0.0
                for season in ("wet", "dry"):
                    scored = dict(factors)
                    if rule.get("season_role") == "modifier":
                        scored["climate_score"] = climate_score(season, oni, rule["id"])
                    wet_hours = None if wetness_assumed else hours
                    result = apply_infection_gate(score_place(rule, scored, season), wet_hours, rule, ndvi=scored.get("ndvi"))
                    if result["score"] is None:
                        continue
                    conn.execute(
                        """
                        INSERT INTO risk_history (
                          place_type, place_id, threat_id, season, observed_on, score, risk_class
                        ) VALUES ('municipality', %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (place_type, place_id, threat_id, season, observed_on)
                        DO UPDATE SET score = EXCLUDED.score, risk_class = EXCLUDED.risk_class
                        """,
                        (place_id, rule["id"], season, observed, result["score"], result["risk_class"]),
                    )
                    written += 1
    return written


def ensure_history(conn) -> None:
    from app.schema import ensure_schema

    ready = conn.execute("SELECT to_regclass('public.risk_history') AS name").fetchone()["name"]
    if not ready:
        ensure_schema(conn)
    count = conn.execute("SELECT COUNT(*) AS n FROM risk_history").fetchone()["n"]
    if count:
        return
    weather = conn.execute("SELECT COUNT(*) AS n FROM weather_daily").fetchone()["n"]
    if not weather:
        return
    rebuild_history(conn)


def trend_from_series(current_score, current_on, series: list[dict]) -> dict:
    """Compare today's score with the saved score about three and seven days earlier."""
    if current_score is None or current_on is None or not series:
        return _empty_trend("Earlier daily scores are not saved yet, so a rise or fall is not shown.")
    current_on = _as_date(current_on)
    earlier = _nearest(series, current_on - timedelta(days=3), TREND_WINDOW_DAYS)
    if earlier is None or earlier["score"] is None:
        return _empty_trend("No saved score within four days of the date three days before this forecast.")
    delta = round(float(current_score) - float(earlier["score"]), 3)
    direction, arrow = _direction(delta)
    points = int(round(delta * 100))
    earlier_on = _as_date(earlier["observed_on"])
    sentence = (
        f"{arrow} {direction.capitalize()} from {float(earlier['score']):.2f} on {_short_date(earlier_on)}"
        f" ({points:+d} points over {(current_on - earlier_on).days} days)."
    )
    week = _nearest(series, current_on - timedelta(days=7), WEEK_WINDOW_DAYS)
    week_delta = None
    if week is not None and week["score"] is not None and _as_date(week["observed_on"]) != earlier_on:
        week_delta = round(float(current_score) - float(week["score"]), 3)
        sentence += f" Seven-day change {int(round(week_delta * 100)):+d} points."
    return {
        "available": True,
        "direction": direction,
        "arrow": arrow,
        "delta": delta,
        "points": points,
        "days": (current_on - earlier_on).days,
        "earlier_score": float(earlier["score"]),
        "earlier_on": earlier_on.isoformat(),
        "week_delta": week_delta,
        "sentence": sentence,
    }


def driver_lines(factors) -> dict:
    """Turn stored factor contributions into points out of 100."""
    rows = []
    if isinstance(factors, str):
        import json

        factors = json.loads(factors)
    for item in factors or []:
        if item.get("contribution") is None:
            continue
        rows.append(
            {
                "id": item.get("id"),
                "label": item.get("label") or item.get("id"),
                "points": int(round(float(item["contribution"]) * 100)),
                "partial": item.get("partial"),
                "assumed": bool(item.get("assumed")),
            }
        )
    rows.sort(key=lambda item: item["points"], reverse=True)
    strong = [item["label"].lower() for item in rows if (item.get("partial") or 0) >= 0.6 and not item["assumed"]][:3]
    if strong:
        sentence = (
            "Why this class: "
            + ", ".join(strong)
            + " sit in a favorable part of this threat's rules and add the largest shares. "
            "Points are that factor's share of the 0–1 score, shown out of 100."
        )
    elif rows:
        sentence = "No factor is strongly favorable. The points below are each factor's share of the score."
    else:
        sentence = "Factor contributions are not stored for this place."
    return {"items": rows, "sentence": sentence}


def weather_anomaly(current: dict, history: list[dict]) -> dict:
    """Compare the selected day with earlier years of the same calendar month."""
    current_on = _as_date(current.get("observed_on"))
    if current_on is None:
        return {"available": False, "sentence": "The forecast date is missing, so a weather baseline is not shown."}
    prior = []
    for row in history:
        observed = _as_date(row.get("observed_on"))
        if observed is None or observed.month != current_on.month or observed.year >= current_on.year:
            continue
        prior.append(row)
    years = { _as_date(row["observed_on"]).year for row in prior }
    if len(years) < 2 or len(prior) < 20:
        return {
            "available": False,
            "sentence": (
                "A multi-year normal for this month is not loaded. "
                "The values shown are the Open-Meteo forecast and the short saved archive, not a historical October baseline. "
                "NASA POWER daily history is the series that would support that comparison."
            ),
        }
    rh_values = [float(row["rh_pct"]) for row in prior if row.get("rh_pct") is not None]
    rain_values = [float(row["rain_mm"]) for row in prior if row.get("rain_mm") is not None]
    parts = [f"Baseline uses {len(years)} earlier years of this calendar month."]
    if current.get("rh_pct") is not None and len(rh_values) >= 20:
        center = mean(rh_values)
        delta = float(current["rh_pct"]) - center
        spread = pstdev(rh_values) if len(rh_values) > 1 else 0
        z_text = f", z {delta / spread:.1f}" if spread else ""
        parts.append(f"Humidity {float(current['rh_pct']):.0f}% is {delta:+.0f} points versus that mean{z_text}.")
    rain_sum = current.get("rain_sum_7d")
    if rain_sum is not None and rain_values:
        normal = mean(rain_values) * 7
        if normal > 0:
            parts.append(f"Rainfall over 7 days is {float(rain_sum):.0f} mm, {float(rain_sum) / normal:.1f}× the historical 7-day scale.")
    return {"available": True, "sentence": " ".join(parts)}


def hotspot_reading(name: str, risk_class: str, threat_name: str, neighbors: list[dict]) -> dict:
    """Describe a neighbor pattern. The mean is not fed back into the hazard score."""
    scored = [item for item in neighbors if item.get("score") is not None]
    neighbor_mean = round(mean(float(item["score"]) for item in scored), 3) if scored else None
    high = [item for item in neighbors if item.get("risk_class") in ("high", "very_high")]
    elevated = [item for item in neighbors if item.get("risk_class") in ("moderate", "high", "very_high")]
    own_high = risk_class in ("high", "very_high")
    if own_high and len(high) >= 1:
        names = [name] + [item["name"] for item in high]
        kind = "cluster"
        sentence = (
            f"Spatial hotspot: elevated {threat_name} suitability in {', '.join(names)}. "
            "Neighbor scores are a separate reading and are not added to the hazard formula."
        )
    elif own_high and neighbors:
        kind = "isolated"
        sentence = (
            f"Isolated hotspot: {name} is {CLASS_LABELS.get(risk_class, risk_class)} "
            f"while neighboring municipalities stay lower ({_class_list(neighbors)})."
        )
    elif not own_high and len(elevated) >= 2:
        kind = "adjacent"
        sentence = (
            f"{name} is next to elevated municipalities: {', '.join(item['name'] for item in elevated)}."
        )
    elif neighbors:
        kind = "none"
        sentence = f"No neighboring hotspot. Nearby classes: {_class_list(neighbors)}."
    else:
        kind = "none"
        sentence = "Municipal neighbors are not loaded, so a hotspot is not assessed."
    return {"kind": kind, "assessed": bool(neighbors), "neighbor_risk": neighbor_mean, "sentence": sentence}


def inspection_priority(parts: dict) -> dict:
    """Separate from hazard risk. Missing parts are dropped and the rest are rescaled."""
    scores = {}
    notes = []
    risk = parts.get("risk")
    if risk is None:
        return {
            "available": False,
            "points": None,
            "score": None,
            "reasons": [],
            "skipped": ["hazard risk"],
            "sentence": "Inspection priority needs a hazard score.",
        }
    scores["risk"] = max(0.0, min(1.0, float(risk)))
    trend = parts.get("trend")
    if trend in ARROW:
        scores["trend"] = {"rising": 1.0, "stable": 0.35, "falling": 0.0}[trend]
        if trend == "rising":
            notes.append("Risk is rising")
    else:
        notes.append("Trend is not in the priority because an earlier score is missing")
    exposure = parts.get("exposure_share")
    if exposure is not None:
        scores["exposure"] = max(0.0, min(1.0, float(exposure)))
        if exposure >= 0.5:
            notes.append("Large exposed rice area")
        elif exposure > 0:
            notes.append("Exposed rice area is loaded")
    else:
        notes.append("Exposed rice hectares are not loaded")
    hotspot = parts.get("hotspot")
    if hotspot is not None:
        scores["hotspot"] = {"cluster": 1.0, "isolated": 0.55, "adjacent": 0.4, "none": 0.0}.get(hotspot, 0.0)
        if hotspot == "cluster":
            notes.append("Part of a municipal hotspot")
        elif hotspot == "isolated":
            notes.append("Isolated high class")
    occurrence = parts.get("occurrence")
    if occurrence is None:
        notes.append("Surveillance records are not loaded")
    else:
        scores["occurrence"] = 1.0 if occurrence else 0.0
        if occurrence:
            notes.append("A loaded occurrence record exists for this threat")
    weight_sum = sum(PRIORITY_WEIGHTS[key] for key in scores)
    total = sum(PRIORITY_WEIGHTS[key] / weight_sum * value for key, value in scores.items())
    points = int(round(total * 100))
    sentence = f"Inspection priority {points}/100. This mixes hazard risk with trend, rice area, hotspot, and surveillance when those exist. It is not the hazard score."
    return {
        "available": True,
        "points": points,
        "score": round(total, 3),
        "reasons": [note for note in notes if not note.endswith("not loaded") and "not in the priority" not in note],
        "limits": [note for note in notes if note.endswith("not loaded") or "not in the priority" in note],
        "sentence": sentence,
    }


def narrative(name: str, threat_name: str, score: dict, trend: dict, drivers: dict, anomaly: dict, hotspot: dict, priority: dict, exposure_sentence: str, context_notes: list[str]) -> str:
    points = int(round(float(score["score"]) * 100)) if score and score.get("score") is not None else None
    klass = CLASS_LABELS.get((score or {}).get("risk_class"), "No class")
    head = f"{name} — {threat_name}. {klass}"
    if points is not None:
        head += f", {points}/100"
    if trend.get("available"):
        head += f", {trend['arrow']} {trend['direction']}"
    head += "."
    lines = [
        head,
        trend.get("sentence") or "",
        drivers.get("sentence") or "",
        anomaly.get("sentence") or "",
        hotspot.get("sentence") or "",
        exposure_sentence,
        *context_notes,
        priority.get("sentence") or "",
        "Recommended action: inspect rice in this municipality if the class is high or rising. This does not mean the pest or disease is present.",
    ]
    return " ".join(line for line in lines if line)


def attach_board(places: list[dict], edges: list[tuple[int, int]], history: dict[int, list], forecast_on, threat_name: str, occurrences: set[int] | None) -> list[dict]:
    """Add trend, hotspot, and inspection priority to municipality rows."""
    by_id = {row["id"]: row for row in places}
    neighbors: dict[int, list[int]] = defaultdict(list)
    for left, right in edges:
        if left == right:
            continue
        neighbors[left].append(right)
        neighbors[right].append(left)
    max_exposure = max((float(row["exposure_ha"]) for row in places if row.get("exposure_ha") is not None), default=None)
    enriched = []
    for row in places:
        series = history.get(row["id"], [])
        trend = trend_from_series(row.get("score"), forecast_on, series)
        neighbor_rows = []
        for other_id in neighbors.get(row["id"], []):
            other = by_id.get(other_id)
            if other:
                neighbor_rows.append(other)
        hotspot = hotspot_reading(row["name"], row.get("risk_class") or "insufficient_data", threat_name, neighbor_rows)
        share = None
        if max_exposure and row.get("exposure_ha") is not None and max_exposure > 0:
            share = float(row["exposure_ha"]) / max_exposure
        occurrence = None if occurrences is None else row["id"] in occurrences
        priority = inspection_priority(
            {
                "risk": row.get("score"),
                "trend": trend["direction"] if trend["available"] else None,
                "exposure_share": share,
                "hotspot": hotspot["kind"] if hotspot.get("assessed") else None,
                "occurrence": occurrence,
            }
        )
        item = dict(row)
        item["trend"] = trend
        item["hotspot"] = hotspot
        item["occurrence"] = occurrence
        item["priority"] = priority
        enriched.append(item)
    enriched.sort(key=lambda item: (-(item["priority"]["points"] or -1), item["name"]))
    for index, item in enumerate(enriched, start=1):
        item["inspection_rank"] = index
    return enriched


def load_board(conn, threat_id: str, season: str, forecast_day: int, threat_name: str) -> tuple[list[dict], object]:
    """Municipality rows with trend, hotspot, and inspection priority."""
    ensure_history(conn)
    forecast = conn.execute(
        "SELECT MIN(forecast_date) AS start_date FROM weather_forecast WHERE day_offset = %s",
        (forecast_day,),
    ).fetchone()
    forecast_on = forecast["start_date"] if forecast else None
    places = [
        dict(row)
        for row in conn.execute(
            """
            SELECT m.id, m.slug, m.name, r.risk_class, r.score, r.exposure_ha, r.exposure_source,
                   r.factors_used, r.explanation
            FROM municipalities m
            JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
            WHERE r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
            """,
            (threat_id, season, forecast_day),
        ).fetchall()
    ]
    edges = [
        (row["place_a"], row["place_b"])
        for row in conn.execute(
            "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind = 'boundary'"
        ).fetchall()
    ]
    history: dict[int, list] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT place_id, observed_on, score
        FROM risk_history
        WHERE place_type = 'municipality' AND threat_id = %s AND season = %s
        ORDER BY observed_on
        """,
        (threat_id, season),
    ).fetchall():
        history[row["place_id"]].append(row)
    occurrence_count = conn.execute("SELECT COUNT(*) AS n FROM occurrence").fetchone()["n"]
    occurrences = None
    if occurrence_count:
        occurrences = {
            row["place_id"]
            for row in conn.execute(
                "SELECT place_id FROM occurrence WHERE place_type = 'municipality' AND threat_id = %s",
                (threat_id,),
            ).fetchall()
        }
    return attach_board(places, edges, history, forecast_on, threat_name, occurrences), forecast_on


def fastest_rising(board: list[dict]) -> dict | None:
    rising = [item for item in board if item["trend"].get("available") and item["trend"]["direction"] == "rising"]
    if not rising:
        return None
    top = max(rising, key=lambda item: item["trend"]["points"])
    return {
        "name": top["name"],
        "slug": top["slug"],
        "from_score": top["trend"]["earlier_score"],
        "to_score": top.get("score"),
        "days": top["trend"]["days"],
        "points": top["trend"]["points"],
        "sentence": (
            f"{top['name']} rose from {top['trend']['earlier_score']:.2f} to {float(top['score']):.2f} "
            f"over {top['trend']['days']} days."
        ),
    }


def _spread(canal, flood_fraction, soil):
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


def _empty_trend(sentence: str) -> dict:
    return {
        "available": False,
        "direction": None,
        "arrow": "",
        "delta": None,
        "points": None,
        "days": None,
        "earlier_score": None,
        "earlier_on": None,
        "week_delta": None,
        "sentence": sentence,
    }


def _direction(delta: float) -> tuple[str, str]:
    if delta >= 0.03:
        return "rising", ARROW["rising"]
    if delta <= -0.03:
        return "falling", ARROW["falling"]
    return "stable", ARROW["stable"]


def _nearest(series: list[dict], target: date, window: int):
    best = None
    best_gap = None
    for item in series:
        observed = _as_date(item["observed_on"])
        gap = abs((observed - target).days)
        if gap <= window and (best_gap is None or gap < best_gap):
            best = item
            best_gap = gap
    return best


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _short_date(value: date) -> str:
    return value.strftime("%d %b")


def _class_list(neighbors: list[dict]) -> str:
    return ", ".join(f"{item['name']} {CLASS_LABELS.get(item.get('risk_class'), item.get('risk_class'))}" for item in neighbors[:4])
