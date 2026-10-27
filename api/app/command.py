"""Command Center situation.

The rule engine builds the record. A later narration step may only rephrase it.
Hazard score and inspection priority stay separate.
"""

from __future__ import annotations

import json
from collections import defaultdict

from app.paths import rules_dir
from app.scoring import CLASS_LABELS, load_rules

RANK = {"insufficient_data": -1, "low": 0, "moderate": 1, "high": 2, "very_high": 3}
# Top inspection-priority band = within PRIORITY_BAND_GAP points of the highest
# inspection priority in this scope, and at least PRIORITY_BAND_FLOOR.
# The count is always municipalities. It is not a hazard class.
PRIORITY_BAND_GAP = 5
PRIORITY_BAND_FLOOR = 70
PRIORITY_BAND_DEFINITION = (
    "Top inspection-priority band = inspection priority within 5 points of the highest "
    "score in this scope, and at least 70. The count is municipalities. "
    "It is not a hazard class and it is not a chance of disease."
)
HIGH_PRIORITY = PRIORITY_BAND_FLOOR
WATCH_PRIORITY = 85
TYPE_ORDER = {
    "field_validation": 0,
    "monitor": 1,
    "prepare": 2,
    "review": 3,
    "follow_up": 4,
    "data_required": 5,
}
TYPE_LABELS = {
    "field_validation": "Field validation",
    "monitor": "Monitor",
    "prepare": "Prepare",
    "review": "Review",
    "data_required": "Data required",
    "follow_up": "Follow-up",
}
WEATHER_INPUTS = {
    "humidity": "humidity",
    "leaf_wetness": "leaf_wetness",
    "temperature": "temperature",
    "recent_rain": "rainfall",
    "forecast_rain": "rainfall",
    "storm": "wind",
}


def command_center(threat_id: str, season: str, forecast_day: int, role: str, municipality_slug: str | None) -> dict:
    """Operational situation for one threat, season, and forecast day."""
    from app.algorithms import connected_components
    from app.db import connect
    from app.insights import load_board

    rule = _rule(threat_id)
    horizon_day = min(6, forecast_day + 3)
    with connect() as conn:
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, rule["name"])
        scope_name = None
        scope_id = None
        if municipality_slug:
            scope = conn.execute(
                "SELECT id, name FROM municipalities WHERE slug = %s",
                (municipality_slug,),
            ).fetchone()
            if scope:
                scope_name = scope["name"]
                scope_id = scope["id"]
                board = [row for row in board if row["slug"] == municipality_slug]
            else:
                board = []
                scope_name = "This municipality"
        factors = _factor_rows(conn, threat_id, season, forecast_day, scope_id)
        horizon = _horizon_rows(conn, threat_id, season, horizon_day, scope_id)
        weather = _weather(conn, forecast_day, horizon_day, scope_id)
        north = None if scope_id else _north_rain(conn, forecast_day, horizon_day)
        datasets = [dict(row) for row in conn.execute("SELECT dataset, state, detail FROM dataset_status ORDER BY dataset").fetchall()]
        planting = conn.execute(
            """
            SELECT COUNT(*) AS n FROM rice_area
            WHERE place_type = 'municipality' AND planting_date IS NOT NULL
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()["n"]
        rice_places = conn.execute(
            """
            SELECT COUNT(*) AS n FROM rice_area
            WHERE place_type = 'municipality' AND rice_ha IS NOT NULL
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()["n"]
        satellite_places = conn.execute(
            """
            SELECT COUNT(*) AS n FROM satellite
            WHERE place_type = 'municipality' AND ndvi IS NOT NULL
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()["n"]
        occurrences = conn.execute(
            """
            SELECT COUNT(*) AS n FROM occurrence
            WHERE place_type = 'municipality' AND threat_id = %s
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (threat_id, scope_id, scope_id),
        ).fetchone()["n"]
        notes = _note_counts(conn, scope_id)
        new_notes = _notes_since(conn, scope_id, threat_id, season, forecast_day)
        logs = conn.execute(
            """
            SELECT class_counts, computed_at FROM run_log
            WHERE threat_id = %s AND season = %s AND forecast_day = %s
            ORDER BY id DESC LIMIT 12
            """,
            (threat_id, season, forecast_day),
        ).fetchall()
        edges = _edges(conn)
        forecast_date = conn.execute(
            """
            SELECT MIN(forecast_date) AS start_date FROM weather_forecast
            WHERE place_type = 'municipality' AND day_offset = %s
            """,
            (forecast_day,),
        ).fetchone()
        updated = conn.execute(
            """
            SELECT MAX(computed_at) AS computed_at FROM risk_score
            WHERE threat_id = %s AND season = %s AND forecast_day = %s AND place_type = 'municipality'
            """,
            (threat_id, season, forecast_day),
        ).fetchone()
    by_id = {row["id"]: row for row in board}
    high_ids = [row["id"] for row in board if row.get("risk_class") in ("high", "very_high")]
    clusters = []
    for component in connected_components(high_ids, edges):
        names = [by_id[place_id]["name"] for place_id in component if place_id in by_id]
        if names:
            clusters.append({"size": len(names), "names": names, "zone": len(names) > 1})
    places = [_normalize(row, factors.get(row["slug"]), horizon.get(row["slug"]), notes.get(row["slug"], 0)) for row in board]
    return build_situation(
        {
            "threat_id": threat_id,
            "threat_name": rule["name"],
            "threat_confidence": rule.get("confidence") or "moderate",
            "rule_factor_ids": [item["id"] for item in rule.get("factors") or []],
            "season": season,
            "forecast_day": forecast_day,
            "horizon_day": horizon_day,
            "horizon_hours": (horizon_day - forecast_day) * 24,
            "role": role,
            "scope_label": scope_name or "Nueva Ecija",
            "scope_level": "this municipality" if scope_name else "municipalities",
            "updated_at": updated["computed_at"].isoformat() if updated and updated["computed_at"] else None,
            "forecast_date": forecast_date["start_date"].isoformat() if forecast_date and forecast_date["start_date"] else None,
            "weather_today": weather.get(forecast_day),
            "weather_ahead": weather.get(horizon_day) if horizon_day != forecast_day else None,
            "north_rain": north,
            "datasets": datasets,
            "planting_dates": planting,
            "rice_places": rice_places,
            "satellite_places": satellite_places,
            "occurrence_rows": occurrences,
            "clusters": clusters,
            "class_delta": _class_delta([] if scope_id else logs, places),
            "new_notes": new_notes,
            "places": places,
        }
    )


def build_situation(context: dict) -> dict:
    places = sorted(context["places"], key=lambda item: (-(item.get("priority_points") or -1), item["name"]))
    shifts = _shifts(context.get("weather_today"), context.get("weather_ahead"), context.get("north_rain"))
    _apply_relevance(shifts, context.get("rule_factor_ids") or [])
    actions = _actions(places, context)
    band = priority_band(places)
    indicators = _indicators(places, actions, context, band)
    state = _state(indicators, actions)
    confidence = _confidence(context)
    priorities = [_priority_row(item, context["threat_name"]) for item in places[:8]]
    horizon = _horizon(places, shifts, context)
    changes = _changes(places, context, shifts)
    brief_lines = _brief(places, actions, context, confidence, horizon)
    today, upcoming = _split_windows(actions, horizon)
    prompts = _prompts(places, context)
    weather_block = _weather_block(shifts, context)
    role = context["role"]
    return {
        "threat": {"id": context["threat_id"], "name": context["threat_name"], "confidence": context["threat_confidence"]},
        "season": context["season"],
        "forecast_day": context["forecast_day"],
        "forecast_date": context.get("forecast_date"),
        "updated_at": context.get("updated_at"),
        "scope": {
            "role": role,
            "label": context["scope_label"],
            "level": context["scope_level"],
            "audience": _audience(role),
            "can_act": role != "guest",
            "can_plan": role != "guest",
            "can_recompute": role == "provincial",
        },
        "system_status": _system_status(places, context, confidence),
        "situation": {
            "state": state["id"],
            "label": state["label"],
            "summary": state["summary"],
            "indicators": indicators,
            "band": band,
        },
        "brief": {"source": "rules", "lines": brief_lines, "text": " ".join(brief_lines)},
        "today": today,
        "upcoming": upcoming,
        "actions": actions,
        "changes": changes,
        "horizon": horizon,
        "why_now": {
            "summary": weather_block["impact"],
            "signals": [item for item in weather_block["signals"] if item.get("relevant") or item["id"] == "canopy"],
        },
        "weather": weather_block,
        "priorities": priorities,
        "clusters": [item for item in context.get("clusters") or [] if item.get("zone")],
        "map_slugs": [item["slug"] for item in places if item["risk_class"] in ("high", "very_high")][:12],
        "confidence": confidence,
        "status_bar": _status_bar(context, confidence, indicators),
        "prompts": prompts,
        "narration_input": {
            "threat": context["threat_name"],
            "scope": context["scope_label"],
            "situation": state["summary"],
            "brief": brief_lines,
            "actions": [
                {
                    "type": item["type_label"],
                    "place": item.get("place"),
                    "hazard": item.get("hazard_points"),
                    "priority": item.get("priority_points"),
                    "trend": item.get("trend_direction"),
                    "why": item["why"],
                    "missing": item["missing"],
                    "window": item["window"],
                }
                for item in actions[:6]
            ],
            "changes": [{"value": item["value"], "label": item["label"]} for item in changes],
            "horizon": horizon.get("areas"),
            "weather_impact": weather_block["impact"],
            "confidence": confidence["label"],
            "missing": confidence["missing"],
        },
    }


def _actions(places: list[dict], context: dict) -> list[dict]:
    chosen = []
    for place in places:
        kind = _action_type(place)
        if kind is None or kind == "data_required":
            continue
        chosen.append(_place_action(kind, place, context))
    chosen.sort(key=lambda item: (TYPE_ORDER[item["type"]], -(item.get("priority_points") or -1), item.get("place") or ""))
    kept = []
    counts = defaultdict(int)
    for item in chosen:
        if counts[item["type"]] >= (3 if item["type"] == "field_validation" else 2):
            continue
        if len(kept) >= 5:
            break
        counts[item["type"]] += 1
        kept.append(item)
    for gap in _data_actions(context):
        kept.append(gap)
    return kept


def _action_type(place: dict) -> str | None:
    risk = place["risk_class"]
    trend = (place.get("trend") or {}).get("direction")
    priority = place.get("priority_points")
    horizon_points = _points(place.get("horizon_score"))
    hazard = _points(place.get("score"))
    if risk == "insufficient_data" or hazard is None:
        return None
    if risk == "very_high" or (risk == "high" and trend == "rising") or (priority is not None and priority >= WATCH_PRIORITY and trend == "rising"):
        return "field_validation"
    if trend == "rising" and risk in ("moderate", "high"):
        return "monitor"
    if horizon_points is not None and hazard is not None and (
        horizon_points - hazard >= 5 or RANK.get(place.get("horizon_class"), -1) > RANK.get(risk, -1)
    ) and risk in ("low", "moderate"):
        return "prepare"
    if place.get("note_count"):
        return "follow_up"
    if risk == "high" and trend in ("stable", "falling", None):
        return "review"
    return None


def _place_action(kind: str, place: dict, context: dict) -> dict:
    hazard = _points(place.get("score"))
    earlier = _points((place.get("trend") or {}).get("earlier_score"))
    priority = place.get("priority_points")
    trend = place.get("trend") or {}
    drivers = _strong_drivers(place)
    missing = _missing(place)
    why = []
    if trend.get("available") and earlier is not None and hazard is not None:
        why.append(f"Hazard score moved from {earlier} to {hazard}.")
    for driver in drivers:
        why.append(f"{driver['label']} is in a favorable part of this threat's rules.")
    ahead = _points(place.get("horizon_score"))
    hours = context["horizon_hours"]
    if ahead is not None and hazard is not None and hours:
        if ahead > hazard:
            why.append(f"On the {hours}-hour forecast the hazard score is {ahead}.")
        elif ahead < hazard:
            why.append(f"On the {hours}-hour forecast the hazard score is {ahead}, lower than today.")
        else:
            why.append(f"On the {hours}-hour forecast the hazard score stays at {ahead}.")
    if place.get("hotspot_kind") == "cluster" and place.get("hotspot_sentence"):
        why.append(place["hotspot_sentence"])
    if place.get("exposure_ha") is not None:
        why.append("Exposed rice area is loaded, so it can raise inspection priority. It is separate from the hazard score.")
    for limit in place.get("priority_limits") or []:
        if limit not in missing:
            missing.append(limit)
    window, recommendation = _window(kind, place, context, ahead, hazard)
    return {
        "id": f"{kind}:{place['slug']}",
        "type": kind,
        "type_label": TYPE_LABELS[kind],
        "verb": _verb(kind),
        "place": place["name"],
        "slug": place["slug"],
        "threat": context["threat_name"],
        "risk_class": place["risk_class"],
        "risk_label": CLASS_LABELS.get(place["risk_class"], place["risk_class"]),
        "trend_direction": trend.get("direction"),
        "trend_arrow": trend.get("arrow") or "",
        "hazard_points": hazard,
        "priority_points": priority,
        "priority_note": _priority_note(place),
        "why": why[:5],
        "confidence": _title(place.get("confidence") or context["threat_confidence"]),
        "missing": missing,
        "window": window,
        "recommendation": recommendation,
    }


def _window(kind: str, place: dict, context: dict, ahead, hazard) -> tuple[str, str]:
    name = place["name"]
    threat = context["threat_name"]
    hours = context["horizon_hours"] or 72
    priority = place.get("priority_points") or 0
    trend = (place.get("trend") or {}).get("direction")
    if kind == "field_validation":
        window = "Within 24–48 hours" if trend == "rising" and priority >= WATCH_PRIORITY else "Within 72 hours"
        text = (
            f"Validate rice in {name} {window.lower()}. "
            f"The recommendation follows the {threat} hazard score and inspection priority. "
            "It does not mean the pest or disease is present."
        )
        return window, text
    if kind == "monitor":
        return (
            f"Over the next {hours} hours",
            f"Keep watching {name} and reassess after the next forecast refresh. A visit is not the first step from this record.",
        )
    if kind == "prepare":
        movement = f" from {hazard} to {ahead}" if ahead is not None and hazard is not None else ""
        return (
            f"Before the {hours}-hour forecast",
            f"{name} may need attention within {hours} hours. The later hazard score moves{movement}.",
        )
    if kind == "follow_up":
        return (
            "On the next look at this record",
            f"A field note is already stored for {name}. Compare it with the current score before treating the note as still current.",
        )
    return (
        "When reviewing today's list",
        f"Review the {name} record. The class is {CLASS_LABELS.get(place['risk_class'], place['risk_class'])} and the trend is {trend or 'not saved'}, so it is not queued as a field visit.",
    )


def _data_actions(context: dict) -> list[dict]:
    actions = []
    factor_ids = set(context.get("rule_factor_ids") or [])
    if "crop_stage" in factor_ids and not context.get("planting_dates"):
        actions.append(
            {
                "id": "data:crop-stage",
                "type": "data_required",
                "type_label": TYPE_LABELS["data_required"],
                "verb": "Resolve data gap",
                "place": None,
                "slug": None,
                "threat": context["threat_name"],
                "risk_class": None,
                "risk_label": None,
                "trend_direction": None,
                "trend_arrow": "",
                "hazard_points": None,
                "priority_points": None,
                "priority_note": "Crop stage is a factor in this threat. With no planting date, that factor is left out and the other factors are rescaled.",
                "why": [
                    "No planting date or start-of-season date is stored for this scope.",
                    "The hazard score skips crop stage instead of assuming a growth stage.",
                ],
                "confidence": _title(context["threat_confidence"]),
                "missing": ["Crop-stage data"],
                "window": "Before relying on a stage-aware score",
                "recommendation": "Load planting or start-of-season data. Until then, treat the score as weather-led.",
            }
        )
    if not context.get("rice_places"):
        actions.append(
            {
                "id": "data:rice-area",
                "type": "data_required",
                "type_label": TYPE_LABELS["data_required"],
                "verb": "Resolve data gap",
                "place": None,
                "slug": None,
                "threat": context["threat_name"],
                "risk_class": None,
                "risk_label": None,
                "trend_direction": None,
                "trend_arrow": "",
                "hazard_points": None,
                "priority_points": None,
                "priority_note": "Inspection priority cannot use rice hectares until a rice-area file is loaded. The hazard score does not use hectares.",
                "why": ["Rice area is not loaded, so inspection priority drops that part and rescales the rest."],
                "confidence": _title(context["threat_confidence"]),
                "missing": ["Rice area"],
                "window": "Before ranking visits by exposed area",
                "recommendation": "Load a rice-area file if visit order should reflect hectares.",
            }
        )
    return actions[:2]


def priority_band(places) -> dict:
    """Municipalities in the locked top inspection-priority band."""
    leader = max((item.get("priority_points") or 0) for item in places) if places else 0
    cutoff = max(PRIORITY_BAND_FLOOR, leader - PRIORITY_BAND_GAP) if leader else PRIORITY_BAND_FLOOR
    members = [item for item in places if (item.get("priority_points") or -1) >= cutoff]
    return {
        "definition": PRIORITY_BAND_DEFINITION,
        "gap": PRIORITY_BAND_GAP,
        "floor": PRIORITY_BAND_FLOOR,
        "cutoff": cutoff,
        "leader": leader,
        "count": len(members),
        "unit": "municipality",
        "slugs": [item["slug"] for item in members if item.get("slug")],
    }


def _indicators(places, actions, context, band) -> list[dict]:
    rising = sum(1 for item in places if (item.get("trend") or {}).get("direction") == "rising")
    delta = context.get("class_delta") or {}
    if delta.get("comparable"):
        alerts = max(0, int(delta["current_high"]) - int(delta["previous_high"]))
        alert_detail = "High or very high municipalities added since the previous municipality score run."
    else:
        alerts = None
        alert_detail = "No earlier municipality score run is stored, so new high-class municipalities are not counted."
    recommended = sum(1 for item in actions if item["type"] in ("field_validation", "monitor", "prepare"))
    return [
        {
            "id": "priority",
            "value": band["count"],
            "label": "Municipalities in the top inspection-priority band",
            "detail": f"{band['definition']} This run's cutoff is {band['cutoff']} (highest inspection priority is {band['leader']}).",
        },
        {
            "id": "rising",
            "value": rising,
            "label": "Municipalities with a rising hazard score",
            "detail": "Count of municipalities whose hazard score is higher than the saved score about three days earlier. The unit is municipalities, not barangays.",
        },
        {
            "id": "alerts",
            "value": alerts,
            "label": "New high-class municipalities",
            "detail": alert_detail,
        },
        {
            "id": "actions",
            "value": recommended,
            "label": "Actions recommended",
            "detail": "Field validation, monitoring, and prepare items. Data gaps are counted separately.",
        },
    ]


def _state(indicators, actions) -> dict:
    priority = indicators[0]["value"]
    rising = indicators[1]["value"]
    validations = sum(1 for item in actions if item["type"] == "field_validation")
    if validations >= 2 or priority >= 4:
        label = "Attention required"
        state = "attention"
    elif validations or rising >= 3:
        label = "Heightened monitoring"
        state = "heightened"
    else:
        label = "Stable"
        state = "stable"
    parts = []
    band_rule = "inspection priority within 5 points of the highest, and at least 70"
    if priority:
        noun = "municipality is" if priority == 1 else "municipalities are"
        parts.append(f"{priority} {noun} in the top inspection-priority band ({band_rule})")
    else:
        parts.append(f"no municipality is in the top inspection-priority band ({band_rule})")
    if rising:
        noun = "municipality has" if rising == 1 else "municipalities have"
        parts.append(f"{rising} {noun} a rising hazard score")
    else:
        parts.append("no municipality has a rising hazard score")
    if validations:
        parts.append(f"{validations} field {'validation is' if validations == 1 else 'validations are'} recommended")
    elif state == "stable":
        parts.append("no critical escalation is showing for this threat")
    summary = _sentence(parts)
    return {"id": state, "label": label, "summary": summary}


def _brief(places, actions, context, confidence, horizon) -> list[str]:
    threat = context["threat_name"]
    scope = context["scope_label"]
    attention = [item for item in actions if item["type"] == "field_validation"]
    lines = []
    if context["role"] == "municipal":
        lines.append(f"This brief is limited to {scope}.")
    if not places:
        lines.append(f"No scores are loaded for {threat} in {scope} on this forecast day.")
        return lines
    if not attention:
        lines.append(f"No area needs field validation for {threat} today.")
    elif len(attention) == 1:
        lines.append(f"One area requires attention for {threat} today.")
    else:
        lines.append(f"{len(attention)} areas require attention for {threat} today.")
    top = places[0]
    hazard = _points(top.get("score"))
    priority = top.get("priority_points")
    trend = (top.get("trend") or {}).get("direction")
    if hazard is not None and priority is not None:
        trend_text = trend or "without a saved trend"
        lines.append(
            f"{top['name']} currently has the highest inspection priority at {priority}/100. "
            f"The hazard score is {hazard}/100 ({CLASS_LABELS.get(top['risk_class'], top['risk_class'])}) and is {trend_text}. "
            "Inspection priority is not the hazard score."
        )
    drivers = _strong_drivers(top)
    if drivers:
        lines.append(
            f"The largest favorable factors in the rules are {_join(item['label'].lower() for item in drivers)}. "
            "Those factors describe suitable conditions. This does not mean the pest or disease is present."
        )
    else:
        lines.append("No stored factor is strongly favorable. This does not mean the pest or disease is present.")
    others = []
    for item in places[1:3]:
        direction = (item.get("trend") or {}).get("direction")
        if direction:
            others.append(f"{item['name']} is {direction}")
    if others:
        lines.append(f"{_join(others)}.")
    if horizon.get("areas"):
        names = _join(area["name"] for area in horizon["areas"][:3])
        lines.append(f"Over the next {context['horizon_hours']} hours, the hazard score rises for {names}.")
    focus = _focus_sentence(actions)
    if focus:
        lines.append(focus)
    if confidence["missing"]:
        lines.append(f"Missing: {_join(confidence['missing'])}.")
    lines.append(f"Confidence in this brief is {confidence['label'].lower()}.")
    return lines


def _focus_sentence(actions: list[dict]) -> str:
    visits = [item["place"] for item in actions if item["type"] == "field_validation" and item.get("place")]
    watch = [item["place"] for item in actions if item["type"] == "monitor" and item.get("place")]
    if visits and watch:
        return f"Recommended focus: field validation in {_join(visits)}, and continued monitoring in {_join(watch)}."
    if visits:
        window = next(item["window"].lower() for item in actions if item["type"] == "field_validation")
        return f"Recommended focus: field validation in {_join(visits)} {window}."
    if watch:
        return f"Recommended focus: keep monitoring {_join(watch)}."
    prepare = [item["place"] for item in actions if item["type"] == "prepare" and item.get("place")]
    if prepare:
        return f"Recommended focus: prepare to watch {_join(prepare)} before the later forecast day."
    return "Recommended focus: review the score list. No field visit is queued from this record."


def _horizon(places, shifts, context) -> dict:
    hours = context["horizon_hours"]
    areas = []
    if not hours:
        return {"available": False, "hours": 0, "label": "Forecast horizon", "areas": [], "driver": "The selected day is already the last forecast day."}
    for place in places:
        hazard = _points(place.get("score"))
        ahead = _points(place.get("horizon_score"))
        if hazard is None or ahead is None:
            continue
        rank_up = RANK.get(place.get("horizon_class"), -1) > RANK.get(place["risk_class"], -1)
        if ahead - hazard < 5 and not rank_up:
            continue
        areas.append(
            {
                "slug": place["slug"],
                "name": place["name"],
                "from_points": hazard,
                "to_points": ahead,
                "from_class": CLASS_LABELS.get(place["risk_class"], place["risk_class"]),
                "to_class": CLASS_LABELS.get(place.get("horizon_class"), place.get("horizon_class")),
            }
        )
    areas.sort(key=lambda item: item["to_points"] - item["from_points"], reverse=True)
    forecast_up = 0
    class_up = 0
    for place in places:
        hazard = place.get("score")
        ahead = place.get("horizon_score")
        if hazard is None or ahead is None:
            continue
        if float(ahead) - float(hazard) >= 0.03:
            forecast_up += 1
        if RANK.get(place.get("horizon_class"), -1) > RANK.get(place["risk_class"], -1):
            class_up += 1
    up_noun = "municipality has" if forecast_up == 1 else "municipalities have"
    class_noun = "municipality is" if class_up == 1 else "municipalities are"
    rising_inputs = [
        item["label"].lower()
        for item in shifts
        if item["relevant"] and item["direction"] == "rising"
    ]
    if rising_inputs:
        driver = (
            f"Expected driver: higher {_join(rising_inputs)} on the {hours}-hour forecast. "
            f"{'That input is' if len(rising_inputs) == 1 else 'Those inputs are'} used by the {context['threat_name']} rules, "
            "and only inside the favorable band."
        )
    else:
        driver = f"No weather input used by {context['threat_name']} is higher on the {hours}-hour forecast than today."
    if not areas:
        driver = f"No hazard score rises by 5 points or more over {hours} hours. " + driver
    return {
        "available": True,
        "hours": hours,
        "label": f"Next {hours} hours",
        "areas": areas[:4],
        "driver": driver,
        "forecast_up": forecast_up,
        "class_up": class_up,
        "forecast_up_sentence": (
            f"{forecast_up} {up_noun} a hazard score at least 3 points higher over the next {hours} hours. "
            "That count uses the same 3-point threshold as the hazard trend."
        ),
        "class_up_sentence": (
            f"{class_up} {class_noun} projected to enter a higher risk class within {hours} hours."
        ),
    }


def _changes(places, context, shifts) -> list[dict]:
    items = []
    delta = context.get("class_delta") or {}
    if delta.get("comparable"):
        change = int(delta["current_high"]) - int(delta["previous_high"])
        items.append(
            {
                "id": "high-class",
                "value": f"{change:+d}",
                "label": "High or very high municipalities since the previous score run",
                "detail": "Hazard class count. This is not an inspection-priority change.",
            }
        )
    else:
        current = sum(1 for place in places if place["risk_class"] in ("high", "very_high"))
        items.append(
            {
                "id": "high-class",
                "value": str(current),
                "label": "High or very high municipalities now",
                "detail": "No earlier score run is stored, so this is a current count, not a change.",
            }
        )
    risers = [place for place in places if (place.get("trend") or {}).get("available") and (place["trend"].get("points") or 0) > 0]
    if risers:
        top = max(risers, key=lambda place: place["trend"]["points"])
        items.append(
            {
                "id": "hazard-rise",
                "value": f"{int(top['trend']['points']):+d}",
                "label": f"Largest hazard increase, {top['name']}",
                "detail": "Hazard points out of 100 since the earlier saved score. This is not the inspection priority.",
            }
        )
    rain = next((item for item in shifts if item["id"] == "rainfall" and item.get("relevant") and item.get("percent") is not None), None)
    if rain and abs(rain["percent"]) >= 10:
        north = " in the northern half" if rain.get("north") else ""
        items.append(
            {
                "id": "rain",
                "value": f"{rain['percent']:+d}%",
                "label": f"Forecast rainfall{north} versus this forecast day",
                "detail": rain["detail"],
            }
        )
    zones = [item for item in context.get("clusters") or [] if item.get("zone")]
    items.append(
        {
            "id": "clusters",
            "value": str(len(zones)),
            "label": "Neighboring high or very high clusters now",
            "detail": "An earlier cluster count is not stored, so this is the current grouping, not a count of new clusters.",
        }
    )
    notes = context.get("new_notes")
    if notes is None:
        items.append(
            {
                "id": "notes",
                "value": "—",
                "label": "Field notes since the last score run",
                "detail": "The last score time is not stored, so new notes are not counted.",
            }
        )
    else:
        items.append(
            {
                "id": "notes",
                "value": f"{notes:+d}",
                "label": "Field notes since the last score run",
                "detail": "Notes saved after the latest score time for this threat and day.",
            }
        )
    return items


def _weather_block(shifts, context) -> dict:
    today = context.get("weather_today") or {}
    relevant = [item for item in shifts if item["relevant"]]
    rising = [item["label"].lower() for item in relevant if item["direction"] == "rising"]
    threat = context["threat_name"]
    if not today:
        impact = "A forecast is not loaded, so this page does not describe a weather change."
    elif len(rising) == 1:
        impact = (
            f"{rising[0].capitalize()} is higher on the later forecast day than today. "
            f"That reading is an input to {threat}. "
            "A higher reading raises the hazard score only inside the favorable band, and only with the other factors that rule uses."
        )
    elif rising:
        impact = (
            f"{_join(item.capitalize() for item in rising)} are higher on the later forecast day than today. "
            f"Those readings are inputs to {threat}. "
            "A higher reading raises the hazard score only inside the favorable band, and only with the other factors that rule uses."
        )
    else:
        impact = f"The later forecast does not show a rise in the weather inputs used by {threat}."
    current = None
    if today:
        current = {
            "temp_c": _round(today.get("temp_c"), 0),
            "rh_pct": _round(today.get("rh_pct"), 0),
            "rain_mm": _round(today.get("rain_mm"), 0),
            "wind_speed_kmh": _round(today.get("wind_speed_kmh"), 0),
        }
    canopy_loaded = bool(context.get("satellite_places"))
    signals = list(shifts)
    signals.append(
        {
            "id": "canopy",
            "label": "Rice canopy",
            "arrow": "—",
            "direction": "unknown",
            "detail": "A canopy value is loaded. No second date is stored, so a canopy trend is not shown."
            if canopy_loaded
            else "Satellite canopy is not loaded, so no canopy trend is shown.",
            "percent": None,
            "north": False,
            "relevant": False,
        }
    )
    return {"current": current, "signals": signals, "impact": impact}


def _shifts(today, ahead, north) -> list[dict]:
    specs = [
        ("humidity", "Humidity", "rh_pct", "%", 2, 5),
        ("rainfall", "Rainfall", "rain_mm", "mm", 2, 5),
        ("temperature", "Temperature", "temp_c", "°C", 0.8, 1.5),
        ("leaf_wetness", "Leaf wetness", "hours_rh90", "h", 1, 3),
        ("wind", "Wind", "wind_speed_kmh", "km/h", 3, 8),
    ]
    rows = []
    for key, label, field, unit, step, strong in specs:
        now = _float((today or {}).get(field))
        later = _float((ahead or {}).get(field))
        arrow, direction = _movement(None if now is None or later is None else later - now, step, strong)
        percent = None
        detail = "Not loaded for this comparison."
        if now is not None and later is not None:
            detail = f"{_trim(now)} {unit} on this forecast day, {_trim(later)} {unit} later."
            if key == "rainfall" and now >= 0.5:
                percent = int(round((later - now) / now * 100))
                detail = f"{_trim(now)} mm on this forecast day, {_trim(later)} mm later ({percent:+d}%)."
        north_flag = False
        if key == "rainfall" and north and north.get("today") is not None and north.get("ahead") is not None:
            north_now = float(north["today"])
            north_later = float(north["ahead"])
            if north_now >= 0.5:
                north_percent = int(round((north_later - north_now) / north_now * 100))
                if abs(north_percent) >= 15 and (percent is None or abs(north_percent) > abs(percent)):
                    percent = north_percent
                    north_flag = True
                    arrow, direction = _movement(north_later - north_now, step, strong)
                    detail = (
                        f"Northern half: {_trim(north_now)} mm on this forecast day, {_trim(north_later)} mm later ({percent:+d}%)."
                    )
        rows.append(
            {
                "id": key,
                "label": label,
                "arrow": arrow,
                "direction": direction,
                "detail": detail,
                "percent": percent,
                "north": north_flag,
                "relevant": False,
            }
        )
    return rows


def _confidence(context: dict) -> dict:
    datasets = {item["dataset"]: item["state"] for item in context.get("datasets") or []}
    checks = [
        {"id": "weather", "label": "Weather forecast", "ok": datasets.get("open_meteo") == "loaded" or bool(context.get("weather_today"))},
        {"id": "rice", "label": "Rice area", "ok": bool(context.get("rice_places")) or datasets.get("rice_mask") == "loaded"},
        {"id": "satellite", "label": "Satellite", "ok": bool(context.get("satellite_places")) or datasets.get("satellite") == "loaded"},
        {"id": "stage", "label": "Crop-stage data", "ok": bool(context.get("planting_dates"))},
        {"id": "surveillance", "label": "Surveillance records", "ok": bool(context.get("occurrence_rows")) or datasets.get("occurrences") == "loaded"},
    ]
    missing = [item["label"] for item in checks if not item["ok"]]
    if not checks[0]["ok"]:
        level, label = "limited", "Limited"
    elif missing:
        level, label = "moderate", "Moderate"
    else:
        level, label = "good", "Good"
    return {
        "level": level,
        "label": label,
        "scope": context["scope_label"],
        "checks": checks,
        "missing": missing,
    }


def _status_bar(context, confidence, indicators) -> list[dict]:
    weather_ok = confidence["checks"][0]["ok"]
    rice_ok = confidence["checks"][1]["ok"]
    high_class = (context.get("class_delta") or {}).get("current_high")
    if high_class is None:
        high_class = 0
    if confidence["level"] == "good":
        data_label, data_level = "Good", "good"
    elif confidence["level"] == "limited":
        data_label, data_level = "Critical data unavailable", "bad"
    else:
        data_label, data_level = "Some datasets missing", "watch"
    return [
        {"id": "weather", "label": "Weather", "value": "Available" if weather_ok else "Unavailable", "level": "good" if weather_ok else "bad"},
        {"id": "risk", "label": "Risk", "value": f"{high_class} high", "level": "watch" if high_class else "good"},
        {"id": "rice", "label": "Rice", "value": "Loaded" if rice_ok else "Not loaded", "level": "good" if rice_ok else "watch"},
        {"id": "data", "label": "Data", "value": data_label, "level": data_level},
    ]


def _split_windows(actions, horizon) -> tuple[list[dict], list[dict]]:
    today = [
        {"slug": item.get("slug"), "name": item.get("place") or item["type_label"], "type": item["type"], "type_label": item["type_label"]}
        for item in actions
        if item["type"] in ("field_validation", "monitor")
    ]
    upcoming = [
        {"slug": item.get("slug"), "name": item.get("place") or item["type_label"], "type": item["type"], "type_label": item["type_label"]}
        for item in actions
        if item["type"] == "prepare"
    ]
    seen = {item.get("slug") for item in today + upcoming}
    for area in horizon.get("areas") or []:
        if area["slug"] in seen:
            continue
        upcoming.append(
            {
                "slug": area["slug"],
                "name": area["name"],
                "type": "prepare",
                "type_label": f"{area['from_points']} → {area['to_points']}",
            }
        )
    return today[:4], upcoming[:4]


def _prompts(places, context) -> list[dict]:
    threat = context["threat_name"]
    top = places[0]["name"] if places else None
    second = places[1]["name"] if len(places) > 1 else None
    prompts = []
    if top:
        prompts.append(
            {
                "id": "why",
                "label": f"Why is {top} first?",
                "message": f"Why does {top} have the highest inspection priority for {threat}? Keep hazard score separate from inspection priority.",
            }
        )
    prompts.append(
        {
            "id": "changed",
            "label": "What changed?",
            "message": f"What changed for {threat} since the previous score run? Use only stored comparisons.",
        }
    )
    prompts.append(
        {
            "id": "inspect",
            "label": "What should we inspect?",
            "message": f"Which places should be inspected first for {threat}, and which should only be monitored?",
        }
    )
    prompts.append(
        {
            "id": "forecast",
            "label": "Show the forecast.",
            "message": f"What does the next forecast window show for {threat}? Do not say a pest is present.",
        }
    )
    if top and second:
        prompts.append(
            {
                "id": "compare",
                "label": f"Compare {top} with {second}.",
                "message": f"Compare {top} and {second} for {threat}. Separate hazard score from inspection priority.",
            }
        )
    return prompts


def _system_status(places, context, confidence) -> str:
    if not places:
        return "Scores are not loaded for this selection"
    if not confidence["checks"][0]["ok"]:
        return "Forecast is missing"
    if confidence["missing"]:
        return "Scores available · some datasets missing"
    return "Scores available"


def _priority_row(place: dict, threat_name: str) -> dict:
    trend = place.get("trend") or {}
    return {
        "slug": place["slug"],
        "name": place["name"],
        "threat": threat_name,
        "risk_class": place["risk_class"],
        "risk_label": CLASS_LABELS.get(place["risk_class"], place["risk_class"]),
        "hazard_points": _points(place.get("score")),
        "priority_points": place.get("priority_points"),
        "trend_direction": trend.get("direction"),
        "trend_arrow": trend.get("arrow") or "",
        "trend_points": trend.get("points") if trend.get("available") else None,
        "priority_note": _priority_note(place),
    }


def _priority_note(place: dict) -> str:
    reasons = [item.strip() for item in (place.get("priority_reasons") or []) if item and item.strip()]
    lead = "Inspection priority is not the hazard score."
    if not reasons:
        return lead + " It uses the hazard score plus any loaded trend, rice area, hotspot, or surveillance."
    sentences = [reason if reason.endswith(".") else f"{reason}." for reason in reasons]
    return f"{lead} {' '.join(sentences)}"


def _strong_drivers(place: dict) -> list[dict]:
    rows = []
    for item in place.get("factors_used") or []:
        partial = item.get("partial")
        if item.get("assumed") or partial is None or float(partial) < 0.6:
            continue
        rows.append({"id": item.get("id"), "label": item.get("label") or item.get("id")})
    return rows[:3]


def _missing(place: dict) -> list[str]:
    missing = []
    for item in place.get("factors_skipped") or []:
        label = item.get("label") or item.get("id")
        if label and label not in missing:
            missing.append(label)
    for item in place.get("factors_used") or []:
        if item.get("assumed"):
            label = item.get("label") or item.get("id")
            note = f"{label} is estimated"
            if note not in missing:
                missing.append(note)
    return missing


def _normalize(row: dict, factors: dict | None, horizon: dict | None, note_count: int) -> dict:
    factors = factors or {}
    trend = row.get("trend") or {}
    priority = row.get("priority") or {}
    hotspot = row.get("hotspot") or {}
    return {
        "id": row.get("id"),
        "slug": row["slug"],
        "name": row["name"],
        "risk_class": row.get("risk_class") or "insufficient_data",
        "score": _float(row.get("score")),
        "priority_points": priority.get("points"),
        "priority_reasons": priority.get("reasons") or [],
        "priority_limits": priority.get("limits") or [],
        "trend": trend,
        "horizon_score": _float((horizon or {}).get("score")),
        "horizon_class": (horizon or {}).get("risk_class"),
        "factors_used": _as_list(factors.get("factors_used")),
        "factors_skipped": _as_list(factors.get("factors_skipped")),
        "hotspot_kind": hotspot.get("kind"),
        "hotspot_sentence": hotspot.get("sentence"),
        "exposure_ha": row.get("exposure_ha"),
        "note_count": note_count,
        "confidence": factors.get("confidence"),
    }


def _rule(threat_id: str) -> dict:
    for rule in load_rules(rules_dir()):
        if rule["id"] == threat_id:
            return rule
    return {"id": threat_id, "name": threat_id, "confidence": "moderate", "factors": []}


def _factor_rows(conn, threat_id, season, forecast_day, scope_id):
    rows = conn.execute(
        """
        SELECT m.slug, r.factors_used, r.factors_skipped, r.confidence
        FROM municipalities m
        JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
        WHERE r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
          AND (%s::int IS NULL OR m.id = %s::int)
        """,
        (threat_id, season, forecast_day, scope_id, scope_id),
    ).fetchall()
    return {row["slug"]: row for row in rows}


def _horizon_rows(conn, threat_id, season, horizon_day, scope_id):
    rows = conn.execute(
        """
        SELECT m.slug, r.score, r.risk_class
        FROM municipalities m
        JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
        WHERE r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
          AND (%s::int IS NULL OR m.id = %s::int)
        """,
        (threat_id, season, horizon_day, scope_id, scope_id),
    ).fetchall()
    return {row["slug"]: row for row in rows}


def _weather(conn, today: int, ahead: int, scope_id):
    rows = conn.execute(
        """
        SELECT day_offset,
               AVG(temp_c) AS temp_c,
               AVG(rh_pct) AS rh_pct,
               AVG(rain_mm) AS rain_mm,
               AVG(wind_speed_kmh) AS wind_speed_kmh,
               AVG(hours_rh90) AS hours_rh90
        FROM weather_forecast
        WHERE place_type = 'municipality' AND day_offset IN (%s, %s)
          AND (%s::int IS NULL OR place_id = %s::int)
        GROUP BY day_offset
        """,
        (today, ahead, scope_id, scope_id),
    ).fetchall()
    return {row["day_offset"]: {key: _float(row[key]) for key in ("temp_c", "rh_pct", "rain_mm", "wind_speed_kmh", "hours_rh90")} for row in rows}


def _north_rain(conn, today: int, ahead: int):
    try:
        conn.execute("SAVEPOINT north_rain")
        rows = conn.execute(
            """
            SELECT band, day_offset, AVG(rain_mm) AS rain_mm
            FROM (
              SELECT CASE
                       WHEN ST_Y(ST_Centroid(m.geom)) >= med.lat THEN 'north'
                       ELSE 'south'
                     END AS band,
                     w.day_offset,
                     w.rain_mm
              FROM municipalities m
              JOIN weather_forecast w
                ON w.place_id = m.id AND w.place_type = 'municipality' AND w.day_offset IN (%s, %s)
              CROSS JOIN (
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ST_Y(ST_Centroid(geom))) AS lat
                FROM municipalities
              ) med
            ) grouped
            GROUP BY band, day_offset
            """,
            (today, ahead),
        ).fetchall()
        conn.execute("RELEASE SAVEPOINT north_rain")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT north_rain")
        return None
    north = {}
    for row in rows:
        if row["band"] == "north":
            north[row["day_offset"]] = _float(row["rain_mm"])
    if today not in north or ahead not in north:
        return None
    return {"today": north[today], "ahead": north[ahead]}


def _note_counts(conn, scope_id) -> dict[str, int]:
    counts = defaultdict(int)
    municipal = conn.execute(
        """
        SELECT m.slug, COUNT(*) AS n
        FROM field_notes f
        JOIN municipalities m ON m.id = f.place_id
        WHERE f.place_type = 'municipality' AND (%s::int IS NULL OR m.id = %s::int)
        GROUP BY m.slug
        """,
        (scope_id, scope_id),
    ).fetchall()
    barangay = conn.execute(
        """
        SELECT m.slug, COUNT(*) AS n
        FROM field_notes f
        JOIN barangays b ON b.id = f.place_id
        JOIN municipalities m ON m.id = b.municipality_id
        WHERE f.place_type = 'barangay' AND (%s::int IS NULL OR m.id = %s::int)
        GROUP BY m.slug
        """,
        (scope_id, scope_id),
    ).fetchall()
    for row in list(municipal) + list(barangay):
        counts[row["slug"]] += row["n"]
    return counts


def _notes_since(conn, scope_id, threat_id, season, forecast_day):
    stamp = conn.execute(
        """
        SELECT MAX(computed_at) AS computed_at FROM risk_score
        WHERE threat_id = %s AND season = %s AND forecast_day = %s AND place_type = 'municipality'
        """,
        (threat_id, season, forecast_day),
    ).fetchone()
    if not stamp or not stamp["computed_at"]:
        return None
    return conn.execute(
        """
        SELECT COUNT(*) AS n FROM field_notes f
        WHERE f.created_at > %s
          AND (
            %s::int IS NULL
            OR (f.place_type = 'municipality' AND f.place_id = %s::int)
            OR (f.place_type = 'barangay' AND f.place_id IN (SELECT id FROM barangays WHERE municipality_id = %s::int))
          )
        """,
        (stamp["computed_at"], scope_id, scope_id, scope_id),
    ).fetchone()["n"]


def _edges(conn):
    road = conn.execute(
        "SELECT COUNT(*) AS n FROM edges WHERE place_type = 'municipality' AND kind = 'road'"
    ).fetchone()["n"]
    kind = "road" if road else "boundary"
    return [
        (row["place_a"], row["place_b"])
        for row in conn.execute(
            "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind = %s",
            (kind,),
        ).fetchall()
    ]


def _class_delta(logs, places) -> dict:
    current = sum(1 for place in places if place["risk_class"] in ("high", "very_high"))
    usable = []
    for row in logs:
        counts = row["class_counts"]
        if isinstance(counts, str):
            counts = json.loads(counts)
        if (counts or {}).get("unit") == "barangay":
            continue
        usable.append(counts or {})
        if len(usable) == 2:
            break
    if len(usable) < 2:
        return {"comparable": False, "current_high": current, "previous_high": None}
    return {"comparable": True, "current_high": _high_count(usable[0]), "previous_high": _high_count(usable[1])}


def _high_count(payload) -> int:
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = payload or {}
    return int(payload.get("high") or 0) + int(payload.get("very_high") or 0)


def _movement(delta, step, strong):
    if delta is None:
        return "—", "unknown"
    if delta >= strong:
        return "↑↑", "rising"
    if delta >= step:
        return "↑", "rising"
    if delta <= -strong:
        return "↓↓", "falling"
    if delta <= -step:
        return "↓", "falling"
    return "→", "steady"


def _points(score):
    if score is None:
        return None
    return int(round(float(score) * 100))


def _float(value):
    if value is None:
        return None
    return float(value)


def _round(value, digits):
    if value is None:
        return None
    return round(float(value), digits)


def _trim(value: float) -> str:
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _as_list(value):
    if isinstance(value, str):
        value = json.loads(value)
    return list(value or [])


def _join(items) -> str:
    items = [str(item) for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _sentence(parts: list[str]) -> str:
    text = _join(parts)
    if not text:
        return ""
    return text[0].upper() + text[1:] + "."


def _verb(kind: str) -> str:
    return {
        "field_validation": "Inspect",
        "monitor": "Monitor",
        "prepare": "Prepare",
        "review": "Review",
        "follow_up": "Follow up",
        "data_required": "Resolve data gap",
    }[kind]


def _audience(role: str) -> str:
    if role == "municipal":
        return "Municipal Agriculture Officer"
    if role == "guest":
        return "Guest"
    return "Agriculture Officer"


def _title(value: str) -> str:
    text = (value or "moderate").replace("_", " ")
    return text[:1].upper() + text[1:]


def brief_is_grounded(text: str) -> bool:
    """Reject a rewrite that diagnoses, prices, or asserts presence."""
    if len(text) > 900:
        return False
    lowered = text.lower()
    banned = ("confirmed", "outbreak", "detected", "pesos", "yield loss", "diagnos", "real-time", "realtime", "spreading", "disease score")
    if any(word in lowered for word in banned):
        return False
    cleaned = lowered.replace("does not mean the pest or disease is present", "")
    if " is present" in cleaned or " are present" in cleaned:
        return False
    return True


def _apply_relevance(shifts: list[dict], factor_ids: list[str]) -> None:
    used = {WEATHER_INPUTS[item] for item in factor_ids if item in WEATHER_INPUTS}
    for signal in shifts:
        signal["relevant"] = signal["id"] in used
