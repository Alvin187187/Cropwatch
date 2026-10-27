"""Intelligence Map read model.

This does not score anything. It reads stored municipality scores, the same
inspection-priority band as the Command Center, and the factors already saved
on each score.
"""

from __future__ import annotations

from collections import defaultdict

from app.command import (
    PRIORITY_BAND_DEFINITION,
    RANK,
    TYPE_LABELS,
    _action_type,
    _as_list,
    _join,
    _rule,
    priority_band,
)
from app.scoring import CLASS_LABELS

FORECAST_LABELS = ["Now", "+24h", "+48h", "+72h", "+4d", "+5d", "+6d"]
HAZARD_RISE = 0.03
FAVORABLE_PARTIAL = 0.6
LOW_PARTIAL = 0.35

LAYER_RULES = {
    "temp": (["temperature"], "Temperature"),
    "rain": (["recent_rain", "forecast_rain"], "Rainfall"),
    "humidity": (["humidity"], "Relative humidity"),
    "wind": (["storm"], "Wind"),
    "soil": (["soil_moisture"], "Soil moisture"),
    "leaf": (["leaf_wetness"], "Leaf wetness"),
}


def points(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value) * 100))


def class_from_score(score, cuts: dict | None) -> str:
    if score is None or not cuts:
        return "insufficient_data"
    value = float(score)
    if value >= float(cuts["very_high"]):
        return "very_high"
    if value >= float(cuts["high"]):
        return "high"
    if value >= float(cuts["moderate"]):
        return "moderate"
    return "low"


def change_bucket(risk_class: str | None, trend: dict | None, cuts: dict | None) -> str:
    """One map color for the change since the earlier saved score."""
    trend = trend or {}
    if not trend.get("available") or trend.get("earlier_score") is None:
        return "unknown"
    earlier_class = class_from_score(trend.get("earlier_score"), cuts)
    current = risk_class or "insufficient_data"
    if current in ("high", "very_high") and earlier_class not in ("high", "very_high"):
        return "new_high"
    if trend.get("direction") == "rising":
        return "increased"
    if trend.get("direction") == "falling":
        return "decreased"
    return "unchanged"


def factor_status(partial, assumed) -> str:
    """Favorable uses the same partial >= 0.6 cutoff as the scoring phrases."""
    if assumed:
        return "Estimated"
    if partial is None:
        return "Not available"
    value = float(partial)
    if value >= FAVORABLE_PARTIAL:
        return "Favorable"
    if value <= LOW_PARTIAL:
        return "Low"
    return "Neutral"


def factor_rows(score) -> list[dict]:
    if not score:
        return []
    used = _as_list(score.get("factors_used") if hasattr(score, "get") else None)
    skipped = _as_list(score.get("factors_skipped") if hasattr(score, "get") else None)
    rows = []
    seen = set()
    for item in used:
        if not isinstance(item, dict):
            continue
        seen.add(item.get("id"))
        rows.append(
            {
                "id": item.get("id"),
                "label": item.get("label") or item.get("id") or "Factor",
                "status": factor_status(item.get("partial"), item.get("assumed")),
                "used": True,
            }
        )
    for item in skipped:
        if not isinstance(item, dict) or item.get("id") in seen:
            continue
        rows.append(
            {
                "id": item.get("id"),
                "label": item.get("label") or item.get("id") or "Factor",
                "status": "Not available",
                "used": False,
            }
        )
    return rows


def why_line(threat_name: str, score) -> str:
    if not score:
        return "No score is stored for this place."
    favorable = [row["label"].lower() for row in factor_rows(score) if row["status"] == "Favorable"]
    klass = score.get("risk_class")
    if favorable and klass in ("moderate", "high", "very_high"):
        named = _join(favorable)
        return (
            f"The current score is elevated because the {threat_name} rules identify favorable {named}. "
            "This does not mean the pest or disease is present."
        )
    if favorable:
        return (
            f"The {threat_name} rules identify favorable {_join(favorable)}. "
            "This does not mean the pest or disease is present."
        )
    return (
        f"The {threat_name} rules did not mark a strongly favorable factor for this score. "
        "This does not mean the pest or disease is present."
    )


def why_now(trend: dict | None, score) -> dict:
    trend = trend or {}
    hazard = points(score.get("score")) if score else None
    earlier = points(trend.get("earlier_score")) if trend.get("available") else None
    favorable = [row["label"] for row in factor_rows(score) if row["status"] == "Favorable"]
    note = "Factor-by-factor history is not stored, so the factors listed are the ones in the current score."
    if not trend.get("available") or earlier is None or hazard is None:
        return {
            "available": False,
            "from_points": earlier,
            "to_points": hazard,
            "direction": None,
            "sentence": "No earlier municipality score is saved, so a rise or fall is not shown.",
            "factors": favorable,
            "note": note,
        }
    sentence = (
        f"Hazard score moved from {earlier} to {hazard} compared with the saved score about three days earlier."
    )
    if trend.get("direction") == "rising":
        sentence += " These conditions increased the rule-based hazard score."
    return {
        "available": True,
        "from_points": earlier,
        "to_points": hazard,
        "direction": trend.get("direction"),
        "sentence": sentence,
        "factors": favorable,
        "note": note,
    }


def score_origin(requested_barangay: bool, stored_place_type: str | None) -> tuple[str, str]:
    if requested_barangay and stored_place_type == "barangay":
        return "barangay", "Barangay-specific score."
    if requested_barangay:
        return "municipality", "Barangay-level risk unavailable. Showing municipality-level risk."
    return "municipality", "Municipality score."


def compare_forecast(by_slug: dict, base: int, ahead: int) -> dict:
    increased = []
    class_up = []
    for slug, days in by_slug.items():
        now = days.get(base)
        later = days.get(ahead)
        if not now or not later or now.get("score") is None or later.get("score") is None:
            continue
        item = {
            "slug": slug,
            "name": now.get("name") or slug,
            "from_points": points(now["score"]),
            "to_points": points(later["score"]),
            "from_class": now.get("risk_class"),
            "to_class": later.get("risk_class"),
        }
        if float(later["score"]) - float(now["score"]) >= HAZARD_RISE:
            increased.append(item)
        if RANK.get(later.get("risk_class"), -1) > RANK.get(now.get("risk_class"), -1):
            class_up.append(dict(item))
    increased.sort(key=lambda item: item["name"])
    class_up.sort(key=lambda item: item["name"])
    return {"increased": increased, "class_up": class_up}


def horizon_sentence(increased: list, class_up: list, hours: int, available: bool) -> str:
    if not available:
        return "This is the last stored forecast day, so a later step is not in the data."
    up = len(increased)
    moved = len(class_up)
    up_noun = "municipality has" if up == 1 else "municipalities have"
    move_noun = "municipality moves" if moved == 1 else "municipalities move"
    return (
        f"{up} {up_noun} a hazard score at least 3 points higher over the next {hours} hours. "
        f"{moved} {move_noun} into a higher risk class. "
        "Both counts compare stored municipality scores for this threat."
    )


def layer_notes(factor_ids: list[str]) -> dict:
    notes = {
        "risk": "Hazard risk is the stored rule score for this threat. It is not a chance of disease.",
        "priority": "Inspection priority is where to spend attention. It is not the hazard score and not a chance of disease.",
        "change": "Risk change compares the stored hazard score with the saved score about three days earlier.",
    }
    known = set(factor_ids or [])
    for key, (needed, label) in LAYER_RULES.items():
        if any(item in known for item in needed):
            notes[key] = f"{label} is an input to this threat's rules. The color is the measurement, not the hazard score."
        else:
            notes[key] = f"This threat's rules do not use {label.lower()}. Showing it does not mean it explains the risk."
    notes["rice"] = "Rice hectares feed inspection priority when a rice-area file is loaded. They are not a hazard-rule result."
    for key, label in {
        "rice_fraction": "Rice fraction",
        "canopy": "NDVI",
        "evi": "EVI",
        "water": "NDWI",
        "lswi": "LSWI",
        "flood": "Flood fraction",
        "lst": "Land surface temperature",
        "elevation": "Elevation",
    }.items():
        notes[key] = f"{label} is context. It is not a pest-risk result, and this threat's rules do not score it."
    return notes


def _index_scores(rows: list[dict]) -> dict:
    by_slug = defaultdict(dict)
    for row in rows:
        by_slug[row["slug"]][int(row["forecast_day"])] = row
    return by_slug


def _data_status(datasets: list[dict], counts: dict) -> dict:
    states = {item["dataset"]: item.get("state") for item in datasets or []}
    weather = "Available" if states.get("open_meteo") == "loaded" or counts.get("weather") else "Missing"
    rice = "Available" if counts.get("rice") or states.get("rice_mask") == "loaded" else "Missing"
    satellite_count = counts.get("satellite") or 0
    municipality_count = counts.get("municipalities") or 0
    if satellite_count <= 0 and states.get("satellite") != "loaded":
        satellite = "Missing"
    elif municipality_count and 0 < satellite_count < municipality_count:
        satellite = "Partial"
    else:
        satellite = "Available"
    surveillance = "Available" if counts.get("occurrences") or states.get("occurrences") == "loaded" else "Missing"
    checks = [
        {"id": "weather", "label": "Weather", "value": weather},
        {"id": "rice", "label": "Rice area", "value": rice},
        {"id": "management", "label": "Management", "value": "Missing"},
        {"id": "satellite", "label": "Satellite", "value": satellite},
        {"id": "surveillance", "label": "Surveillance", "value": surveillance},
    ]
    sentences = []
    if weather == "Available":
        sentences.append("Current risk uses the weather inputs stored for this threat.")
    else:
        sentences.append("Weather inputs were not available for this run.")
    if rice == "Available":
        sentences.append("Rice area is loaded and is used only in inspection priority, not as a hazard result.")
    else:
        sentences.append("Rice area was not available for this run.")
    if satellite == "Partial":
        sentences.append("Satellite coverage is partial.")
    elif satellite == "Missing":
        sentences.append("Satellite inputs were not available for this run.")
    else:
        sentences.append("Satellite values are loaded as context, not as a pest-risk result.")
    sentences.append("Management data was not available for this run.")
    if surveillance == "Missing":
        sentences.append("Surveillance records were not available for this run.")
    else:
        sentences.append("Surveillance records are loaded.")
    sentences.append("The map is not more certain than these inputs.")
    return {"checks": checks, "interpretation": " ".join(sentences)}


def _geometry_note(counts: dict) -> tuple[str, str]:
    if not counts.get("barangay_outlines"):
        return "municipality", "Official barangay polygons are not loaded. The map shows municipalities."
    if not counts.get("barangay_scores"):
        return "municipality", "Barangay-level risk unavailable. Showing municipality-level risk."
    return (
        "barangay",
        "A barangay uses its own score when one is stored. Otherwise the color is the municipality score, marked municipality-derived.",
    )


def _clusters(board: list[dict], edges, threat_name: str, scope_slug: str | None) -> list[dict]:
    from app.algorithms import connected_components

    by_id = {row["id"]: row for row in board if row.get("id") is not None}
    high_ids = [row["id"] for row in board if row.get("risk_class") in ("high", "very_high") and row.get("id") is not None]
    clusters = []
    number = 1
    for component in connected_components(high_ids, edges):
        members = [by_id[place_id] for place_id in component if place_id in by_id]
        if len(members) < 2:
            continue
        slugs = [row["slug"] for row in members]
        if scope_slug and scope_slug not in slugs:
            continue
        visible = [row for row in members if not scope_slug or row["slug"] == scope_slug]
        hazards = [points(row.get("score")) for row in visible if row.get("score") is not None]
        priorities = [(row.get("priority") or {}).get("points") for row in visible]
        priorities = [item for item in priorities if item is not None]
        hidden = len(members) - len(visible)
        clusters.append(
            {
                "id": f"{number:02d}",
                "label": f"Risk cluster {number:02d}",
                "size": len(members),
                "names": [row["name"] for row in visible],
                "slugs": [row["slug"] for row in visible],
                "hidden_neighbors": hidden,
                "threat": threat_name,
                "mean_hazard": round(sum(hazards) / len(hazards)) if hazards else None,
                "priority_points": round(sum(priorities) / len(priorities)) if priorities else None,
                "priority_note": "Mean inspection priority of the municipalities shown here. This is not a hazard score.",
                "action": "Validate selected fields within the cluster.",
                "sentence": "A risk cluster is a spatial grouping of municipalities that are currently high or very high. It is not an outbreak.",
                "scope_note": (
                    f"Grouped with {hidden} neighboring municipalities. Their names and scores are not shown on this account."
                    if hidden
                    else ""
                ),
            }
        )
        number += 1
    return clusters


def _count_line(count: int, singular: str, plural: str) -> str:
    if count == 1:
        return f"1 municipality {singular}"
    return f"{count} municipalities {plural}"


def build_intel(context: dict) -> dict:
    rule_cuts = context.get("cuts") or {}
    factor_ids = context.get("factor_ids") or []
    threat_name = context["threat_name"]
    forecast_day = int(context["forecast_day"])
    ahead = min(6, forecast_day + 3)
    hours = (ahead - forecast_day) * 24
    by_slug = _index_scores(context.get("scores") or [])
    compared = compare_forecast(by_slug, forecast_day, ahead) if ahead > forecast_day else {"increased": [], "class_up": []}
    summary = horizon_sentence(compared["increased"], compared["class_up"], hours, ahead > forecast_day)
    board = context.get("board") or []
    board_by_slug = {row["slug"]: row for row in board}
    selected_day = {
        row["slug"]: row
        for row in context.get("scores") or []
        if int(row["forecast_day"]) == forecast_day
    }
    places = []
    increased = []
    decreased = []
    new_high = []
    unchanged = 0
    unknown = 0
    validation = []
    for slug, row in board_by_slug.items():
        stored = selected_day.get(slug) or row
        trend = row.get("trend") or {}
        bucket = change_bucket(row.get("risk_class"), trend, rule_cuts)
        hazard = points(row.get("score"))
        earlier = points(trend.get("earlier_score")) if trend.get("available") else None
        change = {
            "slug": slug,
            "name": row["name"],
            "from_points": earlier,
            "to_points": hazard,
            "from_class": class_from_score(trend.get("earlier_score"), rule_cuts) if trend.get("available") else None,
            "to_class": row.get("risk_class"),
        }
        if bucket == "increased":
            increased.append(change)
        elif bucket == "decreased":
            decreased.append(change)
        elif bucket == "new_high":
            new_high.append(change)
        elif bucket == "unchanged":
            unchanged += 1
        else:
            unknown += 1
        horizon_row = by_slug.get(slug, {}).get(ahead) if ahead > forecast_day else None
        priority_points = (row.get("priority") or {}).get("points")
        kind = _action_type(
            {
                "risk_class": row.get("risk_class") or "insufficient_data",
                "trend": trend,
                "priority_points": priority_points,
                "horizon_score": None if not horizon_row else horizon_row.get("score"),
                "horizon_class": None if not horizon_row else horizon_row.get("risk_class"),
                "score": row.get("score"),
                "note_count": 0,
            }
        )
        if kind == "field_validation":
            validation.append(slug)
        factors = factor_rows(stored)
        places.append(
            {
                "slug": slug,
                "name": row["name"],
                "risk_class": row.get("risk_class"),
                "risk_label": CLASS_LABELS.get(row.get("risk_class") or "", row.get("risk_class")),
                "hazard_points": hazard,
                "priority_points": priority_points,
                "trend_direction": trend.get("direction"),
                "trend_arrow": trend.get("arrow") or "",
                "change_bucket": bucket,
                "factors": factors,
                "why": why_line(threat_name, stored if stored.get("factors_used") is not None or stored.get("factors_skipped") is not None else {
                    "risk_class": row.get("risk_class"),
                    "factors_used": row.get("factors_used"),
                    "factors_skipped": [],
                }),
                "action": TYPE_LABELS.get(kind) if kind else None,
                "action_id": kind,
                "exposure": "Available" if (stored.get("exposure_ha") if hasattr(stored, "get") else None) is not None or row.get("exposure_ha") is not None else "Not loaded",
                "confidence": stored.get("confidence") if hasattr(stored, "get") else None,
            }
        )
    places.sort(key=lambda item: (-(item.get("priority_points") or -1), item["name"]))
    # Same cap as the Command Center action list, so the map highlight matches those cards.
    validation = [item["slug"] for item in places if item.get("action_id") == "field_validation"][:3]
    band = priority_band(places)
    level, geometry_note = _geometry_note(context.get("counts") or {})
    timeline = []
    dates = context.get("forecast_dates") or {}
    for day in range(7):
        high = 0
        for days in by_slug.values():
            sample = days.get(day)
            if sample and sample.get("risk_class") in ("high", "very_high"):
                high += 1
        timeline.append(
            {
                "day": day,
                "label": FORECAST_LABELS[day],
                "date": dates.get(day),
                "high_or_very_high": high,
            }
        )
    for group in (increased, decreased, new_high):
        group.sort(key=lambda item: item["name"])
    return {
        "unit": "municipality",
        "threat": {"id": context["threat_id"], "name": threat_name},
        "season": context["season"],
        "forecast_day": forecast_day,
        "level": level,
        "geometry_note": geometry_note,
        "band": band,
        "band_definition": PRIORITY_BAND_DEFINITION,
        "rise_rule": "A municipality increases when its stored hazard score is at least 3 points higher. That is the same 0.03 threshold the trend engine uses.",
        "summary": summary,
        "horizon": {
            "day": ahead,
            "hours": hours,
            "available": ahead > forecast_day,
            "municipalities_up": len(compared["increased"]),
            "municipalities_class_up": len(compared["class_up"]),
            "up": compared["increased"],
            "class_up": compared["class_up"],
            "sentence": summary,
        },
        "timeline": timeline,
        "changes": {
            "basis": "Compared with the saved municipality hazard score about three days before this forecast day.",
            "increased": increased,
            "decreased": decreased,
            "new_high": new_high,
            "unchanged": unchanged,
            "unknown": unknown,
        },
        "clusters": _clusters(board, context.get("edges") or [], threat_name, context.get("scope_slug")),
        "command": {
            "field_validation": {
                "count": len(validation),
                "slugs": validation,
                "sentence": _count_line(
                    len(validation),
                    "is recommended for field validation.",
                    "are recommended for field validation.",
                ),
            },
            "rising_72": {
                "count": len(compared["increased"]),
                "slugs": [item["slug"] for item in compared["increased"]],
                "sentence": summary,
            },
            "top_band": {
                "count": band["count"],
                "slugs": band["slugs"],
                "sentence": _count_line(
                    band["count"],
                    "is in the top inspection-priority band.",
                    "are in the top inspection-priority band.",
                )
                + " "
                + PRIORITY_BAND_DEFINITION,
            },
        },
        "places": places,
        "layer_notes": layer_notes(factor_ids),
        "data": _data_status(context.get("datasets") or [], context.get("counts") or {}),
        "scope": {
            "role": context.get("role"),
            "label": context.get("scope_label") or "Nueva Ecija",
            "can_act": context.get("role") != "guest",
            "can_plan": context.get("role") != "guest",
            "can_recompute": context.get("role") == "provincial",
        },
    }


def map_intel(threat_id: str, season: str, forecast_day: int, role: str, municipality_slug: str | None) -> dict:
    from app.db import connect
    from app.insights import load_board

    rule = _rule(threat_id)
    with connect() as conn:
        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, rule["name"])
        scope_id = None
        scope_name = None
        if municipality_slug:
            scope = conn.execute("SELECT id, name FROM municipalities WHERE slug = %s", (municipality_slug,)).fetchone()
            if scope:
                scope_id = scope["id"]
                scope_name = scope["name"]
                board = [row for row in board if row["slug"] == municipality_slug]
            else:
                board = []
                scope_name = "This municipality"
        scores = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, m.name, r.forecast_day, r.score, r.risk_class,
                       r.factors_used, r.factors_skipped, r.confidence, r.exposure_ha
                FROM municipalities m
                JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
                WHERE r.threat_id = %s AND r.season = %s
                  AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (threat_id, season, scope_id, scope_id),
            ).fetchall()
        ]
        forecast_dates = {
            int(row["day_offset"]): row["forecast_date"].isoformat() if row["forecast_date"] else None
            for row in conn.execute(
                """
                SELECT day_offset, MIN(forecast_date) AS forecast_date
                FROM weather_forecast
                WHERE place_type = 'municipality'
                GROUP BY day_offset
                """
            ).fetchall()
        }
        edges = [
            (row["place_a"], row["place_b"])
            for row in conn.execute(
                "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind = 'boundary'"
            ).fetchall()
        ]
        datasets = [dict(row) for row in conn.execute("SELECT dataset, state, detail FROM dataset_status ORDER BY dataset").fetchall()]
        counts = {
            "weather": conn.execute(
                """
                SELECT COUNT(*) AS n FROM weather_forecast
                WHERE place_type = 'municipality' AND day_offset = %s
                  AND (%s::int IS NULL OR place_id = %s::int)
                """,
                (forecast_day, scope_id, scope_id),
            ).fetchone()["n"],
            "rice": conn.execute(
                """
                SELECT COUNT(*) AS n FROM rice_area
                WHERE place_type = 'municipality' AND rice_ha IS NOT NULL
                  AND (%s::int IS NULL OR place_id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchone()["n"],
            "satellite": conn.execute(
                """
                SELECT COUNT(*) AS n FROM satellite
                WHERE place_type = 'municipality' AND ndvi IS NOT NULL
                  AND (%s::int IS NULL OR place_id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchone()["n"],
            "occurrences": conn.execute(
                """
                SELECT COUNT(*) AS n FROM occurrence
                WHERE place_type = 'municipality' AND threat_id = %s
                  AND (%s::int IS NULL OR place_id = %s::int)
                """,
                (threat_id, scope_id, scope_id),
            ).fetchone()["n"],
            "municipalities": len(board),
            "barangay_outlines": conn.execute(
                """
                SELECT COUNT(*) AS n FROM barangays
                WHERE (%s::int IS NULL OR municipality_id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchone()["n"],
            "barangay_scores": conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM risk_score r
                JOIN barangays b ON b.id = r.place_id
                WHERE r.place_type = 'barangay' AND r.threat_id = %s AND r.season = %s AND r.forecast_day = %s
                  AND (%s::int IS NULL OR b.municipality_id = %s::int)
                """,
                (threat_id, season, forecast_day, scope_id, scope_id),
            ).fetchone()["n"],
        }
    return build_intel(
        {
            "threat_id": threat_id,
            "threat_name": rule["name"],
            "factor_ids": [item["id"] for item in rule.get("factors") or []],
            "cuts": rule.get("cuts") or {},
            "season": season,
            "forecast_day": forecast_day,
            "role": role,
            "scope_label": scope_name or "Nueva Ecija",
            "scope_slug": municipality_slug if scope_id else None,
            "board": board,
            "scores": scores,
            "forecast_dates": forecast_dates,
            "edges": edges,
            "datasets": datasets,
            "counts": counts,
        }
    )
