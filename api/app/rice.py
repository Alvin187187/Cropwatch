"""Rice context around the existing risk record.

Provincial production figures come from stored agricultural statistics.
Municipality rice area, crop stage, and satellite values are shown only when
those rows exist. Hazard is never turned into damaged hectares, pesos, or a
rice-health score.
"""

from __future__ import annotations

from app.analytics import _actions, driver_counts
from app.command import CLASS_LABELS, TYPE_LABELS, _action_type, brief_is_grounded, priority_band
from app.map_intel import factor_rows, points

ELEVATED = {"high", "very_high"}
BOUNDARY = (
    "Rice exposure is not estimated crop damage. "
    "A high hazard score does not mean the rice crop is damaged."
)
PERIOD_NOTE = (
    "Production, harvested area, and yield keep the period stored with that dataset. "
    "The hazard score is the current run. They are not measurements from the same period."
)
METRIC_LABELS = {
    "farmers": "Rice farmers",
    "production": "Production",
    "harvested_area": "Harvested area",
    "yield": "Average yield",
}


def rice_is_grounded(text: str) -> bool:
    if not brief_is_grounded(text):
        return False
    lowered = text.lower()
    banned = (
        "crop damage",
        "crop loss",
        "damaged rice",
        "hectares damaged",
        "peso",
        "potential loss",
        "farmers are at risk",
        "farmers at risk",
        "caused the",
        "caused by",
        "rice health",
        "yield loss",
        "financial loss",
    )
    return not any(phrase in lowered for phrase in banned)


def build_rice(context: dict) -> dict:
    places = context.get("places") or []
    threat = context.get("threat") or {}
    threat_name = threat.get("name") or "The selected threat"
    stats = context.get("stats") or []
    hours = int(context.get("hours") or 0)
    hours_available = bool(context.get("hours_available"))
    band = priority_band(places)
    rising = [place for place in places if (place.get("trend") or {}).get("direction") == "rising"]
    fastest = None
    if rising:
        top = max(rising, key=lambda place: (place.get("trend") or {}).get("points") or 0)
        fastest = {
            "slug": top["slug"],
            "name": top["name"],
            "points": int((top.get("trend") or {}).get("points") or 0),
            "from_points": points((top.get("trend") or {}).get("earlier_score")),
            "to_points": points(top.get("score")),
        }
    profiles = [_profile(place, threat, hours_available) for place in places]
    profiles.sort(key=lambda row: (-(row.get("priority_points") or -1), row["name"]))
    exposure = _exposure(profiles, threat_name)
    crop = _crop_section(profiles, threat)
    metrics = [_metric(row) for row in stats if row.get("metric") in METRIC_LABELS and row.get("value") is not None]
    farmers = next((row for row in metrics if row["id"] == "farmers"), None)
    conditions = _conditions(context)
    climate = _climate(context, threat)
    actions = _actions(_action_places(places))
    focus = profiles[0] if profiles else None
    validation = [item for item in actions if item["type"] == "field_validation"]
    lines = _summary_lines(
        context,
        metrics,
        farmers,
        band,
        fastest,
        exposure,
        rising,
        validation,
        threat_name,
    )
    return {
        "boundary": BOUNDARY,
        "period_note": PERIOD_NOTE,
        "scope": {
            "role": context.get("role"),
            "label": context.get("scope_label") or "Nueva Ecija",
            "province_label": "Nueva Ecija",
            "can_plan": context.get("role") != "guest",
            "shows_other_municipalities": context.get("role") != "municipal",
        },
        "threat": {"id": threat.get("id"), "name": threat_name},
        "season": context.get("season"),
        "forecast_day": context.get("forecast_day"),
        "forecast_date": context.get("forecast_date"),
        "situation": {
            "place": "Nueva Ecija",
            "scope_note": (
                "These are Nueva Ecija provincial statistics. They are not this municipality."
                if context.get("role") == "municipal"
                else "Provincial statistics. They are not calculated from hazard scores."
            ),
            "metrics": metrics,
        },
        "exposure": exposure,
        "profiles": profiles,
        "crop": crop,
        "conditions": conditions,
        "climate": climate,
        "risk_context": _risk_context(focus, threat_name, hours, hours_available, context),
        "actions": actions,
        "counts": {
            "band": band["count"],
            "rising": len(rising),
            "elevated": sum(1 for row in profiles if row.get("risk_class") in ELEVATED),
            "field_validation": len(validation),
            "fastest": fastest,
        },
        "coverage": _coverage(context, metrics, profiles),
        "questions": _questions(exposure, crop, profiles, focus, context),
        "summary_text": " ".join(lines),
        "summary_lines": lines,
        "damage_ha": None,
        "loss_estimate": None,
        "rice_health_score": None,
        "narration_input": {
            "threat": threat_name,
            "scope": context.get("scope_label") or "Nueva Ecija",
            "metrics": [{"label": row["label"], "display": row["display"], "period": row["period"]} for row in metrics],
            "exposure": exposure["sentence"],
            "band_count": band["count"],
            "rising": len(rising),
            "fastest": fastest,
            "crop": crop["sentence"],
            "favorable_factors": (context.get("drivers") or [])[:4],
            "enso": climate["enso"]["sentence"],
            "note": BOUNDARY,
        },
    }


def _metric(row: dict) -> dict:
    value = row.get("value")
    metric = row["metric"]
    if metric == "yield":
        display = f"{float(value):.2f} t/ha"
    elif metric == "farmers":
        display = f"{int(round(float(value))):,}"
    elif metric == "production":
        display = f"{int(round(float(value))):,} metric tons"
    else:
        display = f"{int(round(float(value))):,} ha"
    return {
        "id": metric,
        "label": METRIC_LABELS[metric],
        "value": value,
        "display": display,
        "unit": row.get("unit"),
        "source": row.get("source_name"),
        "period": row.get("period"),
        "retrieved_on": _date(row.get("retrieved_on")),
    }


def _profile(place: dict, threat: dict, hours_available: bool) -> dict:
    trend = place.get("trend") or {}
    rice_ha = place.get("rice_ha")
    stage = _stage_reading(threat.get("rule") or {}, place.get("days_after_planting"))
    horizon = None
    if hours_available and place.get("score") is not None and place.get("horizon_score") is not None:
        horizon = {
            "from_points": points(place.get("score")),
            "to_points": points(place.get("horizon_score")),
            "to_class": CLASS_LABELS.get(place.get("horizon_class") or "", place.get("horizon_class")),
        }
    factors = factor_rows(place)
    kind = _action_type(
        {
            "risk_class": place.get("risk_class") or "insufficient_data",
            "trend": trend,
            "priority_points": place.get("priority_points"),
            "horizon_score": place.get("horizon_score"),
            "horizon_class": place.get("horizon_class"),
            "score": place.get("score"),
            "note_count": 0,
        }
    )
    return {
        "slug": place["slug"],
        "name": place["name"],
        "hazard_points": points(place.get("score")),
        "priority_points": place.get("priority_points"),
        "risk_class": place.get("risk_class"),
        "risk_label": CLASS_LABELS.get(place.get("risk_class") or "", place.get("risk_class")),
        "trend_direction": trend.get("direction"),
        "trend_arrow": trend.get("arrow") or "",
        "trend_points": trend.get("points") if trend.get("available") else None,
        "rice_ha": rice_ha,
        "rice_label": "Not loaded" if rice_ha is None else f"{float(rice_ha):,.0f} ha",
        "rice_source": place.get("rice_source"),
        "planting_date": _date(place.get("planting_date")),
        "crop_stage": stage,
        "horizon": horizon,
        "factors": [{"id": item.get("id"), "label": item["label"], "status": item["status"]} for item in factors],
        "action": None if not kind or kind == "data_required" else kind,
        "action_label": None if not kind or kind == "data_required" else TYPE_LABELS.get(kind, kind),
    }


def _stage_reading(rule: dict, days) -> dict:
    if days is None:
        return {
            "available": False,
            "days": None,
            "relevant": None,
            "approaching": False,
            "sentence": "Crop stage unavailable.",
        }
    stages = _stages(rule)
    if not stages:
        return {
            "available": False,
            "days": int(days),
            "relevant": None,
            "approaching": False,
            "sentence": "Crop stage unavailable. This threat has no crop-stage factor.",
        }
    current, upcoming = _bands(int(days), stages)
    relevant = bool(current and current["score"] >= 0.6)
    approaching = bool(
        current
        and not relevant
        and upcoming
        and upcoming["score"] >= 0.6
        and 0 < upcoming["start"] - int(days) <= 7
    )
    if relevant:
        sentence = "The selected threat's crop-stage factor treats this day count as a high-relevance band."
    elif approaching:
        sentence = (
            f"{upcoming['start'] - int(days)} days from a crop-stage band the selected threat treats as high relevance."
        )
    else:
        sentence = "The selected threat's crop-stage factor does not treat this day count as a high-relevance band."
    return {
        "available": True,
        "days": int(days),
        "relevant": relevant,
        "approaching": approaching,
        "sentence": sentence,
    }


def _stages(rule: dict) -> list[dict]:
    spec = next((item for item in rule.get("factors") or [] if item.get("id") == "crop_stage"), None)
    return list(spec.get("stages") or []) if spec else []


def _bands(days: int, stages: list[dict]) -> tuple[dict | None, dict | None]:
    start = 0
    current = None
    upcoming = None
    for band in stages:
        end = int(band["max_day"])
        item = {"start": start, "end": end, "score": float(band["score"])}
        if current is None and days <= end:
            current = item
        elif current is not None and upcoming is None and item["score"] >= 0.6:
            upcoming = item
            break
        start = end + 1
    return current, upcoming


def _crop_section(profiles: list[dict], threat: dict) -> dict:
    known = [row for row in profiles if row["crop_stage"]["available"]]
    approaching = [row for row in known if row["crop_stage"]["approaching"]]
    if not known:
        sentence = (
            "Crop stage unavailable. No planting date or start-of-season date is stored. "
            "The season setting is not used in its place."
        )
    elif approaching:
        sentence = (
            f"{len(approaching)} "
            f"{'municipality is' if len(approaching) == 1 else 'municipalities are'} "
            "within 7 days of a crop-stage band the selected threat treats as high relevance."
        )
    else:
        sentence = f"Planting dates are stored for {len(known)} {'municipality' if len(known) == 1 else 'municipalities'}."
    has_factor = any(item.get("id") == "crop_stage" for item in (threat.get("rule") or {}).get("factors") or [])
    return {
        "available": bool(known),
        "approaching": [
            {"slug": row["slug"], "name": row["name"], "days": row["crop_stage"]["days"], "sentence": row["crop_stage"]["sentence"]}
            for row in approaching
        ],
        "sentence": sentence,
        "rule_uses_stage": has_factor,
        "rule_note": (
            f"{threat.get('name')} includes a crop-stage factor. It is used only where a planting or start-of-season date is stored."
            if has_factor
            else f"{threat.get('name')} has no crop-stage factor."
        ),
    }


def _exposure(profiles: list[dict], threat_name: str) -> dict:
    loaded = [row for row in profiles if row.get("rice_ha") is not None]
    elevated = [row for row in loaded if row.get("risk_class") in ELEVATED]
    if not loaded:
        return {
            "available": False,
            "hectares": None,
            "municipalities": 0,
            "label": "Rice area within elevated-risk areas",
            "sentence": (
                "Rice area within elevated-risk areas is unavailable. "
                "No municipality rice-area layer is loaded, so hectares are not taken from the hazard score."
            ),
        }
    hectares = round(sum(float(row["rice_ha"]) for row in elevated), 1)
    return {
        "available": True,
        "hectares": hectares,
        "municipalities": len(elevated),
        "label": "Rice area within elevated-risk areas",
        "sentence": (
            f"{hectares:,.0f} ha of loaded rice area sits in municipalities currently classed high or very high for {threat_name}. "
            "This is rice area within elevated-risk areas. It is not rice affected and it is not estimated crop damage."
        ),
    }


def _conditions(context: dict) -> dict:
    weather = context.get("weather") or {}
    satellite = context.get("satellite") or {}
    sat_ready = bool(satellite.get("observations"))
    return {
        "weather": {
            "available": bool(weather.get("places")),
            "temp_c": _round(weather.get("temp_c"), 1),
            "rain_mm": _round(weather.get("rain_mm"), 1),
            "rh_pct": _round(weather.get("rh_pct"), 1),
            "soil_moisture": _round(weather.get("soil_moisture"), 3),
            "soil_places": weather.get("soil_places") or 0,
            "source": weather.get("source"),
            "date": _date(weather.get("forecast_date")),
            "note": "Mean of the stored municipal forecasts for this day. This is agricultural weather context.",
        },
        "satellite": {
            "available": sat_ready,
            "ndvi": satellite.get("ndvi") if sat_ready else None,
            "evi": satellite.get("evi") if sat_ready else None,
            "ndwi": satellite.get("ndwi") if sat_ready else None,
            "lswi": satellite.get("lswi") if sat_ready else None,
            "flood_fraction": satellite.get("flood_fraction") if sat_ready else None,
            "rice_fraction": satellite.get("rice_fraction") if sat_ready else None,
            "ndvi_change": satellite.get("ndvi_change") if sat_ready else None,
            "observed_on": _date(satellite.get("observed_on")) if sat_ready else None,
            "note": (
                "Vegetation-index change is an observation. It does not identify a cause."
                if sat_ready
                else "Satellite indicators are not loaded. A vegetation-index change is not shown."
            ),
        },
        "water_note": (
            "Flood fraction and drought area are not loaded."
            if not sat_ready and not context.get("drought_rows")
            else "Water figures use only the stored flood fraction or drought area."
        ),
        "drivers": context.get("drivers") or [],
        "driver_note": (
            "Favorable conditions are the factor statuses stored by the rule engine for this threat. "
            "This page does not make a separate reading from the weather values."
        ),
    }


def _climate(context: dict, threat: dict) -> dict:
    enso = context.get("enso") or {}
    anomaly = enso.get("anomaly_c")
    label = enso.get("label")
    season_name = "Wet" if context.get("season") == "wet" else "Dry"
    uses_season = (threat.get("rule") or {}).get("season_role") == "modifier"
    users = context.get("season_modifiers") or []
    if anomaly is None:
        enso_sentence = "No Oceanic Nino Index value is stored."
    else:
        enso_sentence = (
            f"Latest ONI {float(anomaly):+.2f}"
            f"{f' ({enso.get('season')})' if enso.get('season') else ''}. "
            f"National ENSO signal: {label or 'stored value'}. Source: NOAA Oceanic Nino Index."
        )
    if uses_season:
        threat_sentence = f"Used as a scoring modifier by {threat.get('name')}."
    else:
        threat_sentence = f"Not used by {threat.get('name')} scoring."
    return {
        "season": context.get("season"),
        "season_label": season_name,
        "season_sentence": (
            "The season control is agricultural context. It changes the score only when the selected threat uses it as a modifier."
        ),
        "used_by_selected": uses_season,
        "modifier_threats": users,
        "threat_sentence": threat_sentence,
        "enso": {
            "anomaly_c": anomaly,
            "label": label,
            "season": enso.get("season"),
            "source": "NOAA Oceanic Nino Index",
            "sentence": enso_sentence,
        },
    }


def _risk_context(focus: dict | None, threat_name: str, hours: int, hours_available: bool, context: dict) -> dict:
    if focus is None:
        return {"available": False, "sentence": "No municipality score is stored for this scope."}
    favorable = [item["label"] for item in focus["factors"] if item["status"] == "Favorable"]
    if focus.get("horizon"):
        outlook = (
            f"Stored hazard {focus['horizon']['from_points']} → {focus['horizon']['to_points']} "
            f"over the next {hours} hours."
        )
    elif not hours_available:
        outlook = "This is the last stored forecast day, so a 72-hour step is not in the data."
    else:
        outlook = "A stored forecast score is not available for this municipality."
    rice = focus["rice_label"]
    stage = focus["crop_stage"]["sentence"]
    surveillance = context.get("surveillance") or "Missing"
    return {
        "available": True,
        "slug": focus["slug"],
        "name": focus["name"],
        "threat": threat_name,
        "hazard_points": focus["hazard_points"],
        "priority_points": focus["priority_points"],
        "risk_label": focus["risk_label"],
        "trend_direction": focus["trend_direction"],
        "trend_points": focus["trend_points"],
        "rice_label": rice,
        "crop_sentence": stage,
        "outlook": outlook,
        "favorable_factors": favorable,
        "surveillance": surveillance,
        "action_label": focus.get("action_label"),
        "sentence": (
            f"{focus['name']} has hazard {focus['hazard_points'] if focus['hazard_points'] is not None else '—'} "
            f"and inspection priority {focus['priority_points'] if focus['priority_points'] is not None else '—'} for {threat_name}. "
            f"Rice area: {rice}. {stage}"
        ),
    }


def _coverage(context: dict, metrics: list[dict], profiles: list[dict]) -> list[dict]:
    by_id = {row["id"]: row for row in metrics}
    rows = []
    for metric, label in (
        ("production", "Rice production"),
        ("harvested_area", "Harvested area"),
        ("yield", "Yield"),
        ("farmers", "Rice farmers"),
    ):
        item = by_id.get(metric)
        rows.append(
            {
                "dataset": label,
                "status": "Available" if item else "Missing",
                "period": item["period"] if item else None,
                "source": item["source"] if item else None,
            }
        )
    loaded = [row for row in profiles if row.get("rice_ha") is not None]
    if not profiles:
        rice_status = "Missing"
    elif len(loaded) == len(profiles):
        rice_status = "Available"
    elif loaded:
        rice_status = "Partial"
    else:
        rice_status = "Missing"
    planted = [row for row in profiles if row["crop_stage"]["available"]]
    if not profiles or not planted:
        plant_status = "Missing"
    elif len(planted) == len(profiles):
        plant_status = "Available"
    else:
        plant_status = "Partial"
    satellite = context.get("satellite") or {}
    weather = context.get("weather") or {}
    rows.extend(
        [
            {"dataset": "Rice area", "status": rice_status, "period": None, "source": loaded[0]["rice_source"] if loaded else None},
            {"dataset": "Planting", "status": plant_status, "period": context.get("forecast_date"), "source": None},
            {
                "dataset": "Satellite",
                "status": "Available" if satellite.get("observations") else "Missing",
                "period": _date(satellite.get("observed_on")),
                "source": None,
            },
            {
                "dataset": "Weather",
                "status": "Available" if weather.get("places") else "Missing",
                "period": _date(weather.get("forecast_date")),
                "source": weather.get("source"),
            },
            {
                "dataset": "ENSO",
                "status": "Available" if (context.get("enso") or {}).get("anomaly_c") is not None else "Missing",
                "period": (context.get("enso") or {}).get("season"),
                "source": "NOAA Oceanic Nino Index",
            },
            {
                "dataset": "Surveillance",
                "status": context.get("surveillance") or "Missing",
                "period": None,
                "source": None,
            },
        ]
    )
    return rows


def _questions(exposure: dict, crop: dict, profiles: list[dict], focus: dict | None, context: dict) -> list[dict]:
    ranked = [row for row in profiles if row.get("rice_ha") is not None and row.get("risk_class") in ELEVATED]
    ranked.sort(key=lambda row: (-(row.get("rice_ha") or 0), row["name"]))
    if ranked:
        highest = "Highest loaded rice area inside high or very high municipalities: " + ", ".join(
            f"{row['name']} {row['rice_label']}" for row in ranked[:3]
        ) + "."
    elif exposure["available"]:
        highest = "No loaded rice area is inside a high or very high municipality."
    else:
        highest = exposure["sentence"]
    compare = "A second municipality is not in this scope."
    if len(profiles) >= 2 and focus:
        other = profiles[1]
        compare = (
            f"{focus['name']}: hazard {focus['hazard_points']}, inspection priority {focus['priority_points']}, "
            f"rice area {focus['rice_label']}, {focus['crop_stage']['sentence']} "
            f"{other['name']}: hazard {other['hazard_points']}, inspection priority {other['priority_points']}, "
            f"rice area {other['rice_label']}, {other['crop_stage']['sentence']}"
        )
    surveillance = context.get("surveillance") or "Missing"
    before = "No municipality is in this scope."
    if focus:
        before = (
            f"Before field work in {focus['name']}: hazard {focus['hazard_points']}, "
            f"inspection priority {focus['priority_points']}, rice area {focus['rice_label']}. "
            f"{focus['crop_stage']['sentence']} Surveillance: {surveillance}."
        )
    return [
        {"id": "exposure", "prompt": "How much rice is in the current high-risk areas?", "answer": exposure["sentence"]},
        {"id": "highest", "prompt": "Which municipalities have the highest rice exposure?", "answer": highest},
        {"id": "stage", "prompt": "Which areas are approaching a relevant crop stage?", "answer": crop["sentence"]},
        {"id": "compare", "prompt": "Compare the leading municipalities.", "answer": compare},
        {"id": "before", "prompt": "What rice context should I consider before field validation?", "answer": before},
    ]


def _summary_lines(context, metrics, farmers, band, fastest, exposure, rising, validation, threat_name) -> list[str]:
    lines = [BOUNDARY, "Production figures are the stored agricultural statistics. They are not calculated from hazard scores."]
    production = next((row for row in metrics if row["id"] == "production"), None)
    harvested = next((row for row in metrics if row["id"] == "harvested_area"), None)
    if production and harvested:
        lines.append(
            f"Nueva Ecija, {production['period']}: production {production['display']}, harvested area {harvested['display']}. "
            f"Source: {production['source']}."
        )
    scope = context.get("scope_label") or "Nueva Ecija"
    lines.append(
        f"{band['count']} {'municipality is' if band['count'] == 1 else 'municipalities are'} "
        f"in the top inspection-priority band for {threat_name} in {scope}."
    )
    if fastest:
        lines.append(
            f"Fastest-rising hazard score: {fastest['name']}"
            + (f", from {fastest['from_points']} to {fastest['to_points']}" if fastest["from_points"] is not None else "")
            + f", {fastest['points']:+d} points over the available comparison period."
        )
    lines.append(exposure["sentence"])
    lines.append(
        f"{len(rising)} {'municipality has' if len(rising) == 1 else 'municipalities have'} a rising hazard score."
    )
    lines.append(
        f"{len(validation)} {'municipality is' if len(validation) == 1 else 'municipalities are'} "
        "on the field-validation list for this threat."
    )
    if farmers:
        lines.append(
            f"{farmers['display']} rice farmers are associated with Nueva Ecija in the {farmers['period']} snapshot. "
            "This count is not a count of farmers at risk."
        )
    lines.append(PERIOD_NOTE)
    return lines


def _action_places(places: list[dict]) -> list[dict]:
    return [
        {
            "slug": place["slug"],
            "name": place["name"],
            "score": place.get("score"),
            "risk_class": place.get("risk_class"),
            "trend": place.get("trend") or {},
            "priority_points": place.get("priority_points"),
            "horizon_score": place.get("horizon_score"),
            "horizon_class": place.get("horizon_class"),
        }
        for place in places
    ]


def _round(value, digits: int):
    if value is None:
        return None
    return round(float(value), digits)


def _date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def rice(threat_id: str, season: str, forecast_day: int, role: str, municipality_slug: str | None) -> dict:
    from app.command import _rule
    from app.db import connect
    from app.insights import load_board
    from app.paths import rules_dir
    from app.scoring import load_rules

    rules = {rule["id"]: rule for rule in load_rules(rules_dir())}
    rule = rules.get(threat_id) or _rule(threat_id)
    ahead = min(6, forecast_day + 3)
    modifiers = [item.get("name") or item["id"] for item in rules.values() if item.get("season_role") == "modifier"]
    with connect() as conn:
        scope_id = None
        scope_name = None
        if municipality_slug:
            scope = conn.execute("SELECT id, name FROM municipalities WHERE slug = %s", (municipality_slug,)).fetchone()
            if scope:
                scope_id = scope["id"]
                scope_name = scope["name"]
            else:
                scope_name = "This municipality"
        stats = [
            dict(row)
            for row in conn.execute(
                """
                SELECT DISTINCT ON (metric)
                  metric, period, value, unit, source_name, source_url, retrieved_on, note
                FROM provincial_stats
                ORDER BY metric, id DESC
                """
            ).fetchall()
        ]
        datasets = {row["dataset"]: row["state"] for row in conn.execute("SELECT dataset, state FROM dataset_status").fetchall()}
        enso_row = conn.execute(
            "SELECT season_code, year, anomaly_c FROM enso_oni ORDER BY year DESC, season_code DESC LIMIT 1"
        ).fetchone()
        weather = conn.execute(
            """
            SELECT AVG(temp_c) AS temp_c, AVG(rh_pct) AS rh_pct, AVG(rain_mm) AS rain_mm,
                   AVG(soil_moisture) AS soil_moisture,
                   COUNT(soil_moisture) AS soil_places,
                   COUNT(temp_c) AS places,
                   MIN(source) AS source,
                   MIN(forecast_date) AS forecast_date
            FROM weather_forecast
            WHERE place_type = 'municipality' AND day_offset = %s
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (forecast_day, scope_id, scope_id),
        ).fetchone()
        satellite = conn.execute(
            """
            SELECT AVG(ndvi) AS ndvi, AVG(evi) AS evi, AVG(ndwi) AS ndwi, AVG(lswi) AS lswi,
                   AVG(flood_fraction) AS flood_fraction, AVG(rice_fraction) AS rice_fraction,
                   AVG(ndvi_change) AS ndvi_change, COUNT(ndvi) AS observations, MAX(observed_on) AS observed_on
            FROM satellite
            WHERE place_type = 'municipality'
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()
        rice_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, r.source, r.rice_ha, r.planting_date, r.harvested_ha, r.yield_t_ha, r.drought_ha
                FROM municipalities m
                JOIN rice_area r ON r.place_id = m.id AND r.place_type = 'municipality'
                WHERE (%s::int IS NULL OR m.id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchall()
        ]
        barangay_rice = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM rice_area r
            JOIN barangays b ON b.id = r.place_id
            WHERE r.place_type = 'barangay' AND (%s::int IS NULL OR b.municipality_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()["n"]
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, rule.get("name") or threat_id)
        if scope_id is not None:
            board = [row for row in board if row["slug"] == municipality_slug]
        elif municipality_slug and scope_id is None:
            board = []
        horizon_rows = {
            row["slug"]: row
            for row in conn.execute(
                """
                SELECT m.slug, r.score, r.risk_class
                FROM risk_score r
                JOIN municipalities m ON m.id = r.place_id
                WHERE r.place_type = 'municipality' AND r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
                  AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (threat_id, season, ahead, scope_id, scope_id),
            ).fetchall()
        }
        forecast_date = weather["forecast_date"] if weather else None
    rice_by_slug = {}
    for row in rice_rows:
        current = rice_by_slug.get(row["slug"])
        if current is None or (current.get("rice_ha") is None and row.get("rice_ha") is not None):
            rice_by_slug[row["slug"]] = row
    places = []
    for row in board:
        area = rice_by_slug.get(row["slug"]) or {}
        horizon = horizon_rows.get(row["slug"]) if ahead != forecast_day else None
        planting = area.get("planting_date")
        days = None
        if planting is not None and forecast_date is not None:
            days = (_as_date(forecast_date) - _as_date(planting)).days
        places.append(
            {
                "slug": row["slug"],
                "name": row["name"],
                "score": row.get("score"),
                "risk_class": row.get("risk_class"),
                "priority_points": (row.get("priority") or {}).get("points"),
                "trend": row.get("trend") or {},
                "horizon_score": None if horizon is None else horizon["score"],
                "horizon_class": None if horizon is None else horizon["risk_class"],
                "rice_ha": area.get("rice_ha") if area.get("rice_ha") is not None else row.get("exposure_ha"),
                "rice_source": area.get("source") or row.get("exposure_source"),
                "planting_date": planting,
                "days_after_planting": days,
                "factors_used": row.get("factors_used"),
                "factors_skipped": row.get("factors_skipped"),
            }
        )
    anomaly = enso_row["anomaly_c"] if enso_row else None
    if anomaly is None:
        enso_label = None
    elif anomaly >= 0.5:
        enso_label = "El Nino"
    elif anomaly <= -0.5:
        enso_label = "La Nina"
    else:
        enso_label = "Neutral"
    surveillance_state = datasets.get("occurrences") or "missing"
    report = build_rice(
        {
            "role": role,
            "scope_label": scope_name or "Nueva Ecija",
            "season": season,
            "forecast_day": forecast_day,
            "forecast_date": _date(forecast_date),
            "hours": (ahead - forecast_day) * 24,
            "hours_available": ahead > forecast_day,
            "threat": {"id": threat_id, "name": rule.get("name") or threat_id, "rule": rule},
            "places": places,
            "stats": stats,
            "weather": dict(weather) if weather else {},
            "satellite": dict(satellite) if satellite else {},
            "drought_rows": sum(1 for row in rice_rows if row.get("drought_ha") is not None),
            "enso": {
                "anomaly_c": anomaly,
                "label": enso_label,
                "season": f"{enso_row['season_code']} {enso_row['year']}" if enso_row else None,
            },
            "season_modifiers": modifiers,
            "drivers": [item["label"] for item in driver_counts(places)],
            "surveillance": "Available" if surveillance_state == "loaded" else "Missing",
            "barangay_rice": barangay_rice,
        }
    )
    report["barangay_note"] = (
        "Barangay rice figures are loaded for this scope."
        if barangay_rice
        else "Barangay rice figures are not loaded."
    )
    return report


def _as_date(value):
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    from datetime import date

    return date.fromisoformat(str(value)[:10])
