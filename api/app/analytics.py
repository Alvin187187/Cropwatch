"""Risk and analytics read model.

Figures come from stored municipality scores, the shared hazard-trend threshold,
and the factors saved on each score. This module does not score anything and
does not build a combined disease score.
"""

from __future__ import annotations

from collections import defaultdict

from app.command import (
    CLASS_LABELS,
    PRIORITY_BAND_DEFINITION,
    RANK,
    TYPE_LABELS,
    _action_type,
    brief_is_grounded,
    priority_band,
)
from app.map_intel import HAZARD_RISE, _clusters, _data_status, factor_rows, points

CLASS_ORDER = ["low", "moderate", "high", "very_high"]
ELEVATED = {"high", "very_high"}
TREND_RULE = (
    "Rising means the stored hazard score is at least 3 points higher than the saved score about three days earlier. "
    "Stable means the change stays inside that 3-point band. "
    "Falling means the stored hazard score is at least 3 points lower. "
    "Inspection priority is a separate output. It is not the hazard score and it is not a chance of disease."
)
CHART_NOTE = (
    "The hazard chart uses stored score runs for the available historical and current period, "
    "and the stored forecast scores through +72h. "
    "It does not show which rule factor changed."
)


def analytics_is_grounded(text: str) -> bool:
    if not brief_is_grounded(text):
        return False
    lowered = text.lower()
    banned = ("percent chance", "% chance", "probability", "peso", "overall disease", "damaged rice")
    return not any(phrase in lowered for phrase in banned)


def _noun(count: int, singular: str, plural: str) -> str:
    if count == 1:
        return f"1 municipality {singular}"
    return f"{count} municipalities {plural}"


def distribution(classes: list[str]) -> dict:
    counts = {key: 0 for key in (*CLASS_ORDER, "insufficient_data")}
    for klass in classes:
        counts[klass if klass in counts else "insufficient_data"] += 1
    return counts


def transition_matrix(pairs: list[tuple[str, str]]) -> dict:
    matrix = {left: {right: 0 for right in CLASS_ORDER} for left in CLASS_ORDER}
    skipped = 0
    for current, ahead in pairs:
        if current not in matrix or ahead not in CLASS_ORDER:
            skipped += 1
            continue
        matrix[current][ahead] += 1
    notable = []
    for current in CLASS_ORDER:
        for ahead in CLASS_ORDER:
            count = matrix[current][ahead]
            if count and RANK[ahead] > RANK[current]:
                notable.append(
                    {
                        "from_class": current,
                        "to_class": ahead,
                        "from_label": CLASS_LABELS.get(current, current),
                        "to_label": CLASS_LABELS.get(ahead, ahead),
                        "count": count,
                    }
                )
    notable.sort(key=lambda item: (-item["count"], item["from_class"], item["to_class"]))
    return {"matrix": matrix, "notable": notable, "excluded": skipped}


def driver_counts(places: list[dict]) -> list[dict]:
    """Count municipalities where a stored factor is favorable. No other factors are added."""
    found = {}
    for place in places:
        seen = set()
        for factor in factor_rows(place):
            if factor["status"] != "Favorable":
                continue
            key = factor.get("id") or factor["label"]
            if key in seen:
                continue
            seen.add(key)
            row = found.setdefault(key, {"id": factor.get("id"), "label": factor["label"], "municipalities": 0})
            row["municipalities"] += 1
    rows = list(found.values())
    rows.sort(key=lambda item: (-item["municipalities"], item["label"]))
    return rows


def convergence_rows(threats: list[dict]) -> list[dict]:
    by_slug = {}
    for threat in threats:
        for place in threat["places"]:
            if place.get("risk_class") not in ELEVATED:
                continue
            bucket = by_slug.setdefault(
                place["slug"],
                {"slug": place["slug"], "name": place["name"], "threats": []},
            )
            bucket["threats"].append(
                {"id": threat["id"], "name": threat["name"], "risk_label": CLASS_LABELS.get(place["risk_class"], place["risk_class"])}
            )
    rows = []
    for item in by_slug.values():
        if len(item["threats"]) < 2:
            continue
        count = len(item["threats"])
        item["count"] = count
        item["sentence"] = (
            f"{count} threats currently have elevated rule-based risk in this municipality. "
            "This does not mean the municipality has those pests or diseases."
        )
        rows.append(item)
    rows.sort(key=lambda item: (-item["count"], item["name"]))
    return rows


def _chart(history: list[dict], current_score, forecast_days: dict, current_day: int) -> list[dict]:
    items = []
    for row in (history or [])[-2:]:
        if row.get("score") is None:
            continue
        items.append({"label": row.get("label") or "Earlier", "points": points(row["score"]), "kind": "history"})
    items.append({"label": "Now", "points": points(current_score), "kind": "current"})
    for offset, label in ((1, "+24h"), (2, "+48h"), (3, "+72h")):
        day = current_day + offset
        score = forecast_days.get(day)
        if day <= 6 and score is not None:
            items.append({"label": label, "points": points(score), "kind": "forecast"})
    return items


def _threat_summary(threat: dict, hours: int, hours_available: bool) -> dict:
    places = threat["places"]
    band = priority_band(places)
    rising = [place for place in places if (place.get("trend") or {}).get("direction") == "rising"]
    fastest = None
    if rising:
        top = max(rising, key=lambda place: place["trend"].get("points") or 0)
        fastest = {
            "slug": top["slug"],
            "name": top["name"],
            "points": int(top["trend"].get("points") or 0),
            "from_points": points(top["trend"].get("earlier_score")),
            "to_points": points(top.get("score")),
            "days": top["trend"].get("days"),
        }
    high_plus = sum(1 for place in places if place.get("risk_class") in ELEVATED)
    forecast_up = 0
    forecast_down = 0
    class_up = 0
    pairs = []
    if hours_available:
        for place in places:
            current = place.get("score")
            ahead = place.get("horizon_score")
            if current is not None and ahead is not None:
                delta = float(ahead) - float(current)
                if delta >= HAZARD_RISE:
                    forecast_up += 1
                elif delta <= -HAZARD_RISE:
                    forecast_down += 1
            current_class = place.get("risk_class") or "insufficient_data"
            ahead_class = place.get("horizon_class") or "insufficient_data"
            pairs.append((current_class, ahead_class))
            if RANK.get(ahead_class, -1) > RANK.get(current_class, -1):
                class_up += 1
    return {
        "id": threat["id"],
        "name": threat["name"],
        "high_plus": high_plus,
        "rising": len(rising),
        "fastest": fastest,
        "band": band,
        "forecast_up": forecast_up,
        "forecast_down": forecast_down,
        "class_up": class_up,
        "pairs": pairs,
        "hours": hours,
    }


def _ranking(threat: dict) -> list[dict]:
    rows = []
    for place in threat["places"]:
        trend = place.get("trend") or {}
        rows.append(
            {
                "slug": place["slug"],
                "name": place["name"],
                "hazard_points": points(place.get("score")),
                "priority_points": place.get("priority_points"),
                "risk_class": place.get("risk_class"),
                "risk_label": CLASS_LABELS.get(place.get("risk_class") or "", place.get("risk_class")),
                "trend_direction": trend.get("direction"),
                "trend_arrow": trend.get("arrow") or "",
                "trend_points": trend.get("points") if trend.get("available") else None,
                "rice": "Available" if place.get("exposure_ha") is not None else "Not loaded",
                "rice_ha": place.get("exposure_ha"),
                "confidence": place.get("confidence"),
                "factors": factor_rows(place),
                "series": _chart(place.get("history") or [], place.get("score"), place.get("forecast_days") or {}, threat.get("forecast_day") or 0),
                "horizon_points": points(place.get("horizon_score")),
                "horizon_class": place.get("horizon_class"),
            }
        )
    rows.sort(key=lambda item: (-(item.get("priority_points") or -1), item["name"]))
    return rows


def _outlook(threat: dict, hours: int, available: bool) -> dict:
    increasing = []
    decreasing = []
    staying_high = []
    class_crossings = []
    insufficient = 0
    for place in threat["places"]:
        if place.get("risk_class") == "insufficient_data" or place.get("score") is None:
            insufficient += 1
        current = place.get("score")
        ahead = place.get("horizon_score")
        if not available or current is None or ahead is None:
            continue
        item = {
            "slug": place["slug"],
            "name": place["name"],
            "from_points": points(current),
            "to_points": points(ahead),
            "from_class": CLASS_LABELS.get(place.get("risk_class") or "", place.get("risk_class")),
            "to_class": CLASS_LABELS.get(place.get("horizon_class") or "", place.get("horizon_class")),
        }
        delta = float(ahead) - float(current)
        if delta >= HAZARD_RISE:
            increasing.append(item)
        elif delta <= -HAZARD_RISE:
            decreasing.append(item)
        if place.get("risk_class") in ELEVATED and place.get("horizon_class") in ELEVATED:
            staying_high.append({"slug": place["slug"], "name": place["name"]})
        if RANK.get(place.get("horizon_class"), -1) > RANK.get(place.get("risk_class"), -1):
            class_crossings.append(item)
    increasing.sort(key=lambda item: (item["to_points"] or 0) - (item["from_points"] or 0), reverse=True)
    decreasing.sort(key=lambda item: (item["from_points"] or 0) - (item["to_points"] or 0), reverse=True)
    sentence = (
        f"{_noun(len(increasing), 'is', 'are')} projected to increase by at least 3 hazard points over the next {hours} hours. "
        f"{_noun(len(class_crossings), 'is', 'are')} projected to move into a higher risk class. "
        "Both counts compare stored municipality scores."
        if available
        else "This is the last stored forecast day, so a 72-hour step is not in the data."
    )
    return {
        "available": available,
        "hours": hours,
        "sentence": sentence,
        "increasing": increasing,
        "decreasing": decreasing,
        "staying_high": staying_high,
        "class_crossings": class_crossings,
        "insufficient": insufficient,
        "cluster_note": "An earlier cluster snapshot is not stored, so the cluster count is the current grouping, not a count of new clusters.",
    }


def _actions(places: list[dict]) -> list[dict]:
    chosen = []
    for place in places:
        kind = _action_type(
            {
                "risk_class": place.get("risk_class") or "insufficient_data",
                "trend": place.get("trend") or {},
                "priority_points": place.get("priority_points"),
                "horizon_score": place.get("horizon_score"),
                "horizon_class": place.get("horizon_class"),
                "score": place.get("score"),
                "note_count": 0,
            }
        )
        if not kind or kind == "data_required":
            continue
        chosen.append(
            {
                "type": kind,
                "type_label": TYPE_LABELS.get(kind, kind),
                "slug": place["slug"],
                "name": place["name"],
                "hazard_points": points(place.get("score")),
                "priority_points": place.get("priority_points"),
            }
        )
    order = {"field_validation": 0, "monitor": 1, "prepare": 2, "review": 3, "follow_up": 4}
    chosen.sort(key=lambda item: (order.get(item["type"], 9), -(item.get("priority_points") or -1), item["name"]))
    kept = []
    counts = defaultdict(int)
    for item in chosen:
        if counts[item["type"]] >= (3 if item["type"] == "field_validation" else 2):
            continue
        if len(kept) >= 5:
            break
        counts[item["type"]] += 1
        kept.append(item)
    return kept


def _gaps(data: dict, factor_ids: list[str], planting_dates: int) -> list[dict]:
    by_id = {item["id"]: item["value"] for item in data.get("checks") or []}
    gaps = []
    if by_id.get("management") == "Missing":
        gaps.append(
            {
                "label": "Management data unavailable",
                "detail": "No management inputs are loaded for this run.",
                "effect": "Management-sensitive rule factors are not included where that input is missing.",
            }
        )
    if by_id.get("surveillance") == "Missing":
        gaps.append(
            {
                "label": "Surveillance observations unavailable",
                "detail": "No surveillance records are loaded for this threat.",
                "effect": "Inspection priority does not use a surveillance term for this run.",
            }
        )
    if by_id.get("satellite") in ("Missing", "Partial"):
        gaps.append(
            {
                "label": "Satellite coverage " + by_id["satellite"].lower(),
                "detail": "Satellite values are context. They are not a pest-risk result.",
                "effect": "A partial or missing satellite layer is not filled in.",
            }
        )
    if by_id.get("rice") == "Missing":
        gaps.append(
            {
                "label": "Rice area unavailable",
                "detail": "Rice hectares are not loaded.",
                "effect": "Inspection priority does not use hectares. The hazard score does not use hectares either.",
            }
        )
    if "crop_stage" in factor_ids and not planting_dates:
        gaps.append(
            {
                "label": "Crop stage unavailable",
                "detail": "No planting date is stored for this scope.",
                "effect": "The crop-stage factor is skipped rather than estimated as a season.",
            }
        )
    return gaps


def _coverage(threat: dict, data: dict) -> dict:
    factor_ids = list(threat.get("factor_ids") or [])
    used = set()
    for place in threat["places"]:
        for factor in factor_rows(place):
            if factor.get("used") and factor.get("id"):
                used.add(factor["id"])
    present = [item for item in factor_ids if item in used]
    return {
        "used": len(present),
        "total": len(factor_ids),
        "sentence": (
            f"{threat['name']} currently has stored values for {len(present)} of {len(factor_ids)} rule factors "
            "in at least one municipality."
            if factor_ids
            else f"No rule factors are defined for {threat['name']}."
        ),
        "checks": data.get("checks") or [],
        "interpretation": data.get("interpretation") or "",
        "level": _confidence_level(data),
    }


def _confidence_level(data: dict) -> str:
    values = [item["value"] for item in data.get("checks") or []]
    if values and all(value == "Available" for value in values):
        return "High"
    if not values or all(value == "Missing" for value in values):
        return "Limited"
    return "Moderate"


def build_report(context: dict) -> dict:
    threats = context["threats"]
    selected_id = context.get("threat_id")
    selected = next((item for item in threats if item["id"] == selected_id), None)
    mode = "all" if selected is None else "threat"
    hours = int(context.get("hours") or 0)
    hours_available = bool(context.get("hours_available"))
    summaries = [_threat_summary(item, hours, hours_available) for item in threats]
    data = _data_status(context.get("datasets") or [], context.get("counts") or {})
    convergence = convergence_rows(threats)
    threat_rows = []
    for item in summaries:
        fastest = item["fastest"]
        threat_rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "high_plus": item["high_plus"],
                "rising": item["rising"],
                "fastest_name": fastest["name"] if fastest else None,
                "fastest_points": fastest["points"] if fastest else None,
                "fastest_slug": fastest["slug"] if fastest else None,
            }
        )
    scope = {
        "role": context.get("role"),
        "label": context.get("scope_label") or "Nueva Ecija",
        "can_plan": context.get("role") != "guest",
        "can_act": context.get("role") != "guest",
    }
    base = {
        "mode": mode,
        "unit": "municipality",
        "season": context.get("season"),
        "forecast_day": context.get("forecast_day"),
        "forecast_date": context.get("forecast_date"),
        "scope": scope,
        "trend_rule": TREND_RULE,
        "chart_note": CHART_NOTE,
        "band_definition": PRIORITY_BAND_DEFINITION,
        "threats": threat_rows,
        "convergence": convergence,
        "combined_score": None,
        "combined_note": "All threats keeps each threat separate. There is no combined disease score.",
    }
    if mode == "all" or selected is None:
        lines = [
            "All threats shows each threat on its own. There is no combined disease score.",
            "High or very high, rising hazard, and fastest-rising hazard are counted separately for each threat.",
        ]
        base.update(
            {
                "threat": None,
                "summary": {"lines": lines, "band_count": None, "rising": None, "class_up": None, "forecast_up": None, "clusters": None},
                "distribution": None,
                "movement": None,
                "transitions": None,
                "outlook": None,
                "fastest": [],
                "ranking": [],
                "chart": None,
                "drivers": [],
                "driver_note": "Select one threat to count its stored favorable factors.",
                "coverage": None,
                "gaps": [],
                "actions": [],
                "clusters": [],
                "matrix": _matrix(threats),
                "summary_text": " ".join(lines),
            }
        )
        base["narration_input"] = {
            "mode": "all",
            "scope": scope["label"],
            "threats": threat_rows,
            "convergence": [{"name": item["name"], "threats": [row["name"] for row in item["threats"]]} for item in convergence],
            "note": base["combined_note"],
        }
        return base

    summary = next(item for item in summaries if item["id"] == selected["id"])
    classes_now = [place.get("risk_class") or "insufficient_data" for place in selected["places"]]
    classes_ahead = [place.get("horizon_class") or "insufficient_data" for place in selected["places"]] if hours_available else []
    movement = []
    now_counts = distribution(classes_now)
    ahead_counts = distribution(classes_ahead) if hours_available else None
    for key in (*CLASS_ORDER, "insufficient_data"):
        movement.append(
            {
                "id": key,
                "label": CLASS_LABELS.get(key, key),
                "now": now_counts[key],
                "ahead": None if ahead_counts is None else ahead_counts[key],
            }
        )
    ranking = _ranking({**selected, "forecast_day": context.get("forecast_day") or 0})
    fastest_rows = [
        row for row in ranking if row.get("trend_direction") == "rising" and (row.get("trend_points") or 0) > 0
    ]
    fastest_rows.sort(key=lambda item: item["trend_points"], reverse=True)
    focus = fastest_rows[0] if fastest_rows else (ranking[0] if ranking else None)
    outlook = _outlook(selected, hours, hours_available)
    transitions = transition_matrix(summary["pairs"]) if hours_available else {"matrix": None, "notable": [], "excluded": 0}
    drivers = driver_counts(selected["places"])
    clusters = context.get("clusters") or []
    actions = _actions(selected["places"])
    lines = [
        f"{_noun(summary['band']['count'], 'is', 'are')} in the top inspection-priority band. {PRIORITY_BAND_DEFINITION}",
        f"{_noun(summary['rising'], 'has', 'have')} a rising hazard score.",
        f"{_noun(summary['class_up'], 'is', 'are')} projected to move into a higher risk class.",
        f"{len(clusters)} active risk {'cluster' if len(clusters) == 1 else 'clusters'}.",
        f"{_noun(summary['forecast_up'], 'is', 'are')} projected to increase by at least 3 hazard points over the next {hours} hours.",
    ]
    fastest_line = None
    if summary["fastest"]:
        fastest_line = (
            f"Fastest-rising hazard score: {summary['fastest']['name']} "
            f"{summary['fastest']['points']:+d} points over the available comparison period."
        )
        lines.append(fastest_line)
    base.update(
        {
            "threat": {"id": selected["id"], "name": selected["name"]},
            "summary": {
                "lines": lines,
                "band_count": summary["band"]["count"],
                "rising": summary["rising"],
                "class_up": summary["class_up"],
                "forecast_up": summary["forecast_up"],
                "clusters": len(clusters),
                "fastest": summary["fastest"],
            },
            "distribution": {"current": now_counts, "forecast": ahead_counts, "rows": movement},
            "movement": movement,
            "transitions": transitions,
            "outlook": outlook,
            "fastest": [
                {
                    "slug": row["slug"],
                    "name": row["name"],
                    "points": row["trend_points"],
                    "from_points": points(next(place["trend"].get("earlier_score") for place in selected["places"] if place["slug"] == row["slug"])),
                    "to_points": row["hazard_points"],
                }
                for row in fastest_rows[:5]
            ],
            "ranking": ranking,
            "chart": None
            if focus is None
            else {
                "slug": focus["slug"],
                "name": focus["name"],
                "series": focus["series"],
                "note": CHART_NOTE if any(point["kind"] == "history" for point in focus["series"]) else CHART_NOTE + " Earlier score runs are not on this chart.",
            },
            "drivers": drivers,
            "driver_note": (
                "Analytics displays only factor statuses returned by the rule engine. "
                "It does not derive drivers from the hazard chart. "
                "A factor is listed only when that score stored it as favorable."
            ),
            "coverage": _coverage(selected, data),
            "gaps": _gaps(data, selected.get("factor_ids") or [], context.get("planting_dates") or 0),
            "actions": actions,
            "clusters": clusters,
            "matrix": _matrix(threats),
            "summary_text": " ".join(lines),
        }
    )
    base["narration_input"] = {
        "mode": "threat",
        "threat": selected["name"],
        "scope": scope["label"],
        "band_count": summary["band"]["count"],
        "rising": summary["rising"],
        "forecast_up": summary["forecast_up"],
        "class_up": summary["class_up"],
        "fastest": summary["fastest"],
        "favorable_factors": [item["label"] for item in drivers[:4]],
        "missing": [item["label"] for item in base["gaps"]],
        "convergence": [{"name": item["name"], "count": item["count"]} for item in convergence[:5]],
        "note": "Hazard score and inspection priority are separate. Do not call either a chance of disease.",
    }
    return base


def _matrix(threats: list[dict]) -> list[dict]:
    by_slug = {}
    for threat in threats:
        for place in threat["places"]:
            row = by_slug.setdefault(place["slug"], {"slug": place["slug"], "name": place["name"], "classes": {}, "elevated": 0})
            label = CLASS_LABELS.get(place.get("risk_class") or "", place.get("risk_class"))
            row["classes"][threat["id"]] = label
            if place.get("risk_class") in ELEVATED:
                row["elevated"] += 1
    rows = [row for row in by_slug.values() if row["elevated"]]
    rows.sort(key=lambda item: (-item["elevated"], item["name"]))
    return rows[:16]


def _place_from_board(row: dict, horizon: dict | None, history: list[dict], forecast_days: dict, factors: dict | None) -> dict:
    trend = row.get("trend") or {}
    labeled_history = []
    for item in history:
        observed = item.get("observed_on")
        label = observed.isoformat() if hasattr(observed, "isoformat") else str(observed or "Earlier")
        labeled_history.append({"label": label, "score": item.get("score")})
    stored = factors or {}
    return {
        "slug": row["slug"],
        "name": row["name"],
        "score": row.get("score"),
        "risk_class": row.get("risk_class"),
        "horizon_score": None if not horizon else horizon.get("score"),
        "horizon_class": None if not horizon else horizon.get("risk_class"),
        "trend": trend,
        "priority_points": (row.get("priority") or {}).get("points"),
        "exposure_ha": row.get("exposure_ha"),
        "confidence": stored.get("confidence"),
        "factors_used": stored.get("factors_used") if stored.get("factors_used") is not None else row.get("factors_used"),
        "factors_skipped": stored.get("factors_skipped") or [],
        "history": labeled_history,
        "forecast_days": forecast_days,
    }


def analytics(threat_id: str | None, season: str, forecast_day: int, role: str, municipality_slug: str | None) -> dict:
    from app.command import _rule
    from app.db import connect
    from app.insights import load_board
    from app.reports import threat_list
    from app.scoring import load_rules
    from app.paths import rules_dir

    rules = {rule["id"]: rule for rule in load_rules(rules_dir())}
    catalog = threat_list()
    selected = None if threat_id in (None, "", "all") else threat_id
    if selected and selected not in rules:
        selected = catalog[0]["id"] if catalog else None
    ahead = min(6, forecast_day + 3)
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
        score_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.id, m.slug, m.name, r.threat_id, r.forecast_day, r.score, r.risk_class,
                       r.factors_used, r.factors_skipped, r.exposure_ha, r.confidence
                FROM municipalities m
                JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
                WHERE r.season = %s AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (season, scope_id, scope_id),
            ).fetchall()
        ]
        history_rows = []
        if selected:
            history_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT m.slug, h.observed_on, h.score
                    FROM risk_history h
                    JOIN municipalities m ON m.id = h.place_id
                    WHERE h.place_type = 'municipality' AND h.threat_id = %s AND h.season = %s
                      AND (%s::int IS NULL OR m.id = %s::int)
                    ORDER BY h.observed_on
                    """,
                    (selected, season, scope_id, scope_id),
                ).fetchall()
            ]
        edges = [
            (row["place_a"], row["place_b"])
            for row in conn.execute(
                "SELECT place_a, place_b FROM edges WHERE place_type = 'municipality' AND kind = 'boundary'"
            ).fetchall()
        ]
        datasets = [dict(row) for row in conn.execute("SELECT dataset, state FROM dataset_status").fetchall()]
        planting = conn.execute(
            """
            SELECT COUNT(*) AS n FROM rice_area
            WHERE place_type = 'municipality' AND planting_date IS NOT NULL
              AND (%s::int IS NULL OR place_id = %s::int)
            """,
            (scope_id, scope_id),
        ).fetchone()["n"]
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
                WHERE place_type = 'municipality' AND (%s::text IS NULL OR threat_id = %s)
                  AND (%s::int IS NULL OR place_id = %s::int)
                """,
                (selected, selected, scope_id, scope_id),
            ).fetchone()["n"],
            "municipalities": 0,
        }
        forecast_date = conn.execute(
            """
            SELECT MIN(forecast_date) AS start_date FROM weather_forecast
            WHERE place_type = 'municipality' AND day_offset = %s
            """,
            (forecast_day,),
        ).fetchone()
        grouped = defaultdict(lambda: defaultdict(dict))
        for row in score_rows:
            grouped[row["threat_id"]][row["slug"]][int(row["forecast_day"])] = row
        history_by_slug = defaultdict(list)
        for row in history_rows:
            history_by_slug[row["slug"]].append(row)
        threats = []
        cluster_payload = []
        for item in catalog:
            rule = rules.get(item["id"]) or _rule(item["id"])
            board, _forecast_on = load_board(conn, item["id"], season, forecast_day, rule["name"])
            if scope_id is not None:
                board = [row for row in board if row["slug"] == municipality_slug]
            elif municipality_slug and scope_id is None:
                board = []
            places = []
            for row in board:
                days = grouped.get(item["id"], {}).get(row["slug"], {})
                current = days.get(forecast_day) or {}
                horizon = days.get(ahead) if ahead != forecast_day else None
                forecast_days = {day: sample.get("score") for day, sample in days.items()}
                places.append(
                    _place_from_board(
                        row,
                        horizon,
                        history_by_slug.get(row["slug"], []) if item["id"] == selected else [],
                        forecast_days,
                        current,
                    )
                )
            threats.append(
                {
                    "id": item["id"],
                    "name": rule.get("name") or item["name"],
                    "factor_ids": [factor["id"] for factor in rule.get("factors") or []],
                    "places": places,
                }
            )
            if item["id"] == selected:
                counts["municipalities"] = len(places)
                cluster_payload = _clusters(board, edges, rule.get("name") or item["name"], municipality_slug if scope_id else None)
    return build_report(
        {
            "threat_id": selected,
            "season": season,
            "forecast_day": forecast_day,
            "forecast_date": forecast_date["start_date"].isoformat() if forecast_date and forecast_date["start_date"] else None,
            "hours": (ahead - forecast_day) * 24,
            "hours_available": ahead > forecast_day,
            "role": role,
            "scope_label": scope_name or "Nueva Ecija",
            "threats": threats,
            "clusters": cluster_payload,
            "datasets": datasets,
            "counts": counts,
            "planting_dates": planting,
        }
    )
