"""Situation-record copy for the monitoring surfaces.

Every sentence is built from stored scores, weather, rice figures, notes,
history, and the inspection route. This module does not score anything and
does not invent a place, a number, or a factor.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from app.command import CLASS_LABELS, _as_list, _join
from app.map_intel import points

SOURCE = "From the situation record."
EMPTY = "No municipality currently needs elevated monitoring for this threat."
ELEVATED = {"high", "very_high"}
RANK = {"insufficient_data": -1, "low": 0, "moderate": 1, "high": 2, "very_high": 3}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
FAVORABLE = 0.6
MANILA = timezone(timedelta(hours=8))
BANNED = (
    "outbreak",
    "spreading",
    "confirmed infection",
    "pesos",
    "yield loss",
    "damaged rice",
    "damaged hectares",
    "diagnos",
    "is present",
    "are present",
)


def _label(risk_class: str | None) -> str:
    if not risk_class:
        return ""
    return CLASS_LABELS.get(risk_class, risk_class.replace("_", " ").title())


def _rank(risk_class: str | None) -> int:
    return RANK.get(risk_class or "", -1)


def _date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _stamp(value) -> str | None:
    parsed = _date(value)
    if not parsed:
        return None
    return f"{parsed.day} {MONTHS[parsed.month - 1]} {parsed.year}"


def _manila_day(value) -> date | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _date(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(MANILA).date()
    return _date(value)


def _num(value, digits: int = 0) -> str | None:
    if value is None:
        return None
    number = float(value)
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _hours_phrase(hours: int) -> str:
    return f"in about {hours} hours"


def _card(sentence: str, evidence: list[str] | None = None) -> dict:
    lines = []
    for item in evidence or []:
        text = str(item).strip()
        if text and text not in lines:
            lines.append(text if text.endswith(".") else f"{text}.")
    return {"sentence": sentence, "evidence": lines}


def _gap(place: dict, as_of: date | None) -> str | None:
    """Return a gap kind from stored notes. Validation is not a separate record."""
    last = _date(place.get("last_note_on"))
    if last is None:
        return "none"
    if as_of is None:
        return None
    if last < as_of - timedelta(days=7):
        return "stale"
    return None


def _gap_lines(place: dict, kind: str | None) -> list[str]:
    if kind == "none":
        return ["No field note is stored.", "No field validation is stored."]
    if kind == "stale":
        stamp = _stamp(place.get("last_note_on"))
        lines = ["No field note is stored in the last 7 days."]
        if stamp:
            lines.insert(0, f"Last field note {stamp}.")
        return lines
    return []


def _favorable(place: dict) -> list[dict]:
    rows = []
    for item in place.get("factors_used") or []:
        if not isinstance(item, dict) or item.get("assumed"):
            continue
        partial = item.get("partial")
        if partial is None or float(partial) < FAVORABLE or item.get("value") is None:
            continue
        label = item.get("label") or item.get("id")
        if not label:
            continue
        rows.append({"id": item.get("id") or "", "label": str(label), "value": item.get("value")})
    return rows


def _reading(factor: dict) -> str:
    label = factor["label"]
    value = factor["value"]
    factor_id = str(factor.get("id") or "").lower()
    name = label.lower()
    if "temp" in factor_id or "temp" in name:
        return f"{label} {_num(value, 1)} C"
    if "humid" in factor_id or "rh" == factor_id or "humid" in name:
        return f"{label} {_num(value, 0)}%"
    if "rain" in factor_id or "rain" in name:
        return f"{label} {_num(value, 1)} mm"
    if "wind" in factor_id or "wind" in name:
        return f"{label} {_num(value, 0)} km/h"
    if "soil" in factor_id or "soil" in name:
        return f"{label} {_num(value, 2)}"
    if "wet" in factor_id or "wet" in name or "hour" in name:
        return f"{label} {_num(value, 0)} hours"
    return f"{label} {_num(value, 1)}"


def _weather_line(place: dict) -> str | None:
    weather = place.get("weather") or {}
    bits = []
    if weather.get("temp_c") is not None:
        bits.append(f"temperature {_num(weather['temp_c'], 1)} C")
    if weather.get("rh_pct") is not None:
        bits.append(f"humidity {_num(weather['rh_pct'], 0)}%")
    if weather.get("rain_mm") is not None:
        bits.append(f"rainfall {_num(weather['rain_mm'], 1)} mm")
    if not bits:
        return None
    return f"{place['name']}, {', '.join(bits)}"


def _forecast_step(place: dict) -> dict | None:
    current = _rank(place.get("risk_class"))
    current_points = points(place.get("score"))
    best = None
    for step in place.get("forecast") or []:
        offset = int(step.get("offset") or 0)
        if offset <= 0:
            continue
        ahead_points = points(step.get("score"))
        ahead_rank = _rank(step.get("risk_class"))
        class_up = ahead_rank > current and ahead_rank >= 0 and current >= 0
        class_down = ahead_rank < current and ahead_rank >= 0 and current >= 0
        score_up = (
            current_points is not None
            and ahead_points is not None
            and ahead_points - current_points >= 3
        )
        score_down = (
            current_points is not None
            and ahead_points is not None
            and current_points - ahead_points >= 3
        )
        if not (class_up or class_down or score_up or score_down):
            continue
        direction = "up" if class_up or (score_up and not class_down) else "down"
        candidate = {
            "offset": offset,
            "hours": offset * 24,
            "direction": direction,
            "from_points": current_points,
            "to_points": ahead_points,
            "from_class": place.get("risk_class"),
            "to_class": step.get("risk_class"),
            "date": step.get("date"),
        }
        if best is None or (direction == "up" and best["direction"] != "up") or offset < best["offset"]:
            best = candidate
            if direction == "up":
                break
    return best


def _rising(place: dict) -> bool:
    trend = place.get("trend") or {}
    return bool(trend.get("available") and trend.get("direction") == "rising")


def _falling(place: dict) -> bool:
    trend = place.get("trend") or {}
    return bool(trend.get("available") and trend.get("direction") == "falling")


def _rapid(place: dict) -> bool:
    trend = place.get("trend") or {}
    return _rising(place) and int(trend.get("points") or 0) >= 10


def _local_groups(places: list[dict], edges: list[tuple[str, str]]) -> list[list[str]]:
    """A place plus the neighbors that are changing with it. Not the whole connected province."""
    flagged = {
        place["slug"]
        for place in places
        if _rising(place) or ((_forecast_step(place) or {}).get("direction") == "up")
    }
    graph: dict[str, set[str]] = {slug: set() for slug in flagged}
    for left, right in edges:
        if left in graph and right in graph and left != right:
            graph[left].add(right)
            graph[right].add(left)
    ordered = sorted((place for place in places if place["slug"] in flagged), key=_sort_key)
    groups = []
    seen = set()
    for place in ordered:
        members = tuple(sorted({place["slug"], *graph[place["slug"]]}))
        if len(members) < 2 or members in seen:
            continue
        seen.add(members)
        groups.append(list(members))
        if len(groups) == 3:
            break
    return groups


def _hazard_evidence(place: dict) -> list[str]:
    trend = place.get("trend") or {}
    current = points(place.get("score"))
    earlier = points(trend.get("earlier_score")) if trend.get("available") else None
    lines = []
    if earlier is not None and current is not None:
        lines.append(f"Hazard {earlier} to {current}.")
    elif current is not None:
        lines.append(f"Hazard {current}.")
    label = _label(place.get("risk_class"))
    if label and label != "Insufficient data":
        lines.append(f"Class {label}.")
    if place.get("priority_points") is not None:
        lines.append(f"Inspection priority {int(place['priority_points'])}.")
    return lines


def _forecast_evidence(place: dict, step: dict | None) -> list[str]:
    if not step:
        return []
    lines = []
    origin = _label(step.get("from_class"))
    dest = _label(step.get("to_class"))
    if origin and dest and origin != dest:
        lines.append(f"Projected class {origin} to {dest}.")
    elif dest:
        lines.append(f"Projected class {dest}.")
    if step.get("from_points") is not None and step.get("to_points") is not None:
        lines.append(f"Projected hazard {step['from_points']} to {step['to_points']}.")
    stamp = _stamp(step.get("date"))
    if stamp:
        lines.append(f"Forecast date {stamp}.")
    return lines


def _signal(place: dict, emerging: set[str], step: dict | None, gap: str | None) -> str | None:
    elevated = place.get("risk_class") in ELEVATED
    if _rapid(place):
        return "Rapidly rising hazard"
    if step and step["direction"] == "up":
        return "Forecast escalation"
    if place["slug"] in emerging and (_rising(place) or (step and step["direction"] == "up")):
        return "Emerging monitoring area"
    trend_known = bool((place.get("trend") or {}).get("available"))
    if elevated and gap:
        return "Monitoring gap"
    if elevated and trend_known and not _rising(place) and not _falling(place):
        return "Persistent elevated condition"
    if _rising(place):
        return "Rising hazard"
    if elevated:
        return "Monitoring priority"
    return None


def _candidate(place: dict, signal: str | None) -> bool:
    if signal:
        return True
    return place.get("risk_class") in ELEVATED or _rising(place)


def _attention_sentence(name: str, threat: str, signal: str) -> str:
    if signal == "Rapidly rising hazard":
        return f"{name} is a monitoring priority for {threat} because the stored hazard is rising."
    if signal == "Forecast escalation":
        return f"{name} is a monitoring priority for {threat} because the stored forecast moves the class up."
    if signal == "Emerging monitoring area":
        return f"{name} is inside an emerging monitoring area for {threat}."
    if signal == "Monitoring gap":
        return f"{name} has elevated monitoring conditions for {threat} and no recent field note."
    if signal == "Persistent elevated condition":
        return f"{name} remains an elevated monitoring area for {threat}."
    return f"{name} is a monitoring priority for {threat}."


def _when(forecast_day: int) -> str:
    return "today" if forecast_day == 0 else "for this forecast day"


def _action(forecast_day: int) -> str:
    if forecast_day == 0:
        return "Field validation is recommended today."
    return "Field validation is recommended for this forecast day."


def _urgency(place: dict) -> str:
    priority = place.get("priority_points")
    if place.get("risk_class") == "very_high" or _rapid(place) or (priority is not None and int(priority) >= 70):
        return "High"
    return "Moderate"


def _sort_key(place: dict):
    return (-(place.get("priority_points") if place.get("priority_points") is not None else -1), -(points(place.get("score")) or -1), place["name"])


def _names(places: list[dict], slugs: list[str]) -> list[str]:
    by_slug = {place["slug"]: place["name"] for place in places}
    return [by_slug[slug] for slug in slugs if slug in by_slug]


def _count_phrase(count: int, singular: str, plural: str) -> str:
    if count == 1:
        return f"One {singular}"
    word = "Two" if count == 2 else str(count)
    return f"{word} {plural}"


def _pattern_card(title: str, names: list[str], sentence: str) -> dict:
    evidence = [f"{name}." for name in names[:8]]
    if len(names) > 8:
        evidence.append(f"{len(names) - 8} more municipalities are on the record.")
    return {"id": title, "title": title, "sentence": sentence, "evidence": evidence, "names": names}


def _history_events(place: dict) -> list[dict]:
    events = []
    rows = []
    for row in place.get("history") or []:
        observed = _date(row.get("observed_on"))
        if observed is None or row.get("score") is None:
            continue
        rows.append(row)
    rows.sort(key=lambda row: str(row.get("observed_on")))
    previous = None
    for row in rows:
        stamp = _stamp(row.get("observed_on"))
        current = points(row.get("score"))
        klass = _label(row.get("risk_class"))
        if previous is None:
            detail = f"Hazard {current}."
            if klass:
                detail = f"{detail[:-1]}, class {klass}."
            events.append({"when": stamp, "label": "Score stored", "detail": detail})
        else:
            earlier = points(previous.get("score"))
            before = _label(previous.get("risk_class"))
            bits = []
            if earlier is not None and current is not None and earlier != current:
                bits.append(f"Hazard {earlier} to {current}")
            if before and klass and before != klass:
                bits.append(f"{before} to {klass}")
            if bits:
                events.append({"when": stamp, "label": "Score change", "detail": f"{', '.join(bits)}."})
        previous = row
    for note in place.get("notes") or []:
        stamp = _stamp(_manila_day(note.get("created_at")) or note.get("created_at"))
        body = " ".join(str(note.get("body") or "").split())
        if len(body) > 180:
            body = body[:177].rstrip() + "..."
        detail = f"Note: {body}" if body else "A field note is stored."
        events.append({"when": stamp, "label": "Field note", "detail": detail})
    step = _forecast_step(place)
    if step and step["direction"] == "up":
        origin = _label(step.get("from_class"))
        dest = _label(step.get("to_class"))
        detail = f"Projected class {origin} to {dest}." if origin and dest and origin != dest else "Projected hazard rises."
        events.append({"when": _stamp(step.get("date")), "label": "Forecast", "detail": detail})
    events.sort(key=lambda item: item.get("when") or "")
    return events[-8:]


def _rice_bits(place: dict) -> list[str]:
    lines = []
    if place.get("rice_ha") is not None:
        lines.append(f"Mapped rice area {_num(place['rice_ha'])} ha.")
    if place.get("harvested_ha") is not None:
        lines.append(f"Harvested area {_num(place['harvested_ha'])} ha.")
    if place.get("yield_t_ha") is not None:
        lines.append(f"Yield {_num(place['yield_t_ha'], 2)} metric tons per hectare.")
    if place.get("rice_fraction") is not None:
        lines.append(f"Rice fraction {_num(place['rice_fraction'], 2)}.")
    stage = place.get("crop_stage")
    if stage and stage not in ("Crop stage unavailable.", "Crop stage unavailable. This threat has no crop-stage factor."):
        lines.append(stage if str(stage).endswith(".") else f"{stage}.")
    return lines


def build_layer(context: dict) -> dict:
    threat = context.get("threat_name") or "This threat"
    places = list(context.get("places") or [])
    as_of = _date(context.get("as_of"))
    forecast_day = int(context.get("forecast_day") or 0)
    by_slug = {place["slug"]: place for place in places}
    groups = _local_groups(places, list(context.get("edges") or []))
    emerging_slugs = {slug for group in groups for slug in group}
    prepared = []
    for place in places:
        step = _forecast_step(place)
        gap = _gap(place, as_of)
        signal = _signal(place, emerging_slugs, step, gap)
        prepared.append({**place, "_step": step, "_gap": gap, "_signal": signal})

    ranked = [place for place in prepared if _candidate(place, place["_signal"])]
    ranked.sort(key=_sort_key)
    attention = []
    for index, place in enumerate(ranked[:5], start=1):
        readings = [f"{_reading(factor)} in {place['name']}." for factor in _favorable(place)[:3]]
        evidence = _hazard_evidence(place) + _forecast_evidence(place, place["_step"]) + _gap_lines(place, place["_gap"]) + readings
        stamp = _stamp(as_of)
        if stamp:
            evidence.append(f"Record date {stamp}.")
        action = _action(forecast_day)
        attention.append(
            {
                "rank": index,
                "slug": place["slug"],
                "name": place["name"],
                "threat": threat,
                "signal": place["_signal"] or "Monitoring priority",
                "sentence": _attention_sentence(place["name"], threat, place["_signal"] or "Monitoring priority"),
                "evidence": _card("", evidence)["evidence"],
                "action": action,
                "urgency": _urgency(place),
                "field": f"{place['name']}. {action}",
            }
        )

    emerging = []
    for group in groups[:3]:
        members = sorted((by_slug[slug] for slug in group if slug in by_slug), key=lambda place: place["name"])
        names = [place["name"] for place in members]
        readings = []
        labels = []
        for place in members:
            for factor in _favorable(place)[:2]:
                if factor["label"] not in labels:
                    labels.append(factor["label"])
                readings.append(f"{_reading(factor)} in {place['name']}.")
        sentence = f"{_count_phrase(len(names), 'adjacent municipality is', 'adjacent municipalities are')} showing increasing {threat} hazard."
        if labels:
            sentence = sentence[:-1] + ", and stored factors for those municipalities fall in the favorable range used by the model."
        evidence = [f"{name}." for name in names]
        for place in members:
            evidence.extend(_hazard_evidence(place)[:2])
        evidence.extend(readings[:6])
        emerging.append(
            {
                "label": "Emerging monitoring area",
                "slugs": group,
                "names": names,
                "sentence": sentence,
                "evidence": _card("", evidence)["evidence"],
            }
        )

    def pattern_names(predicate) -> list[str]:
        return [place["name"] for place in sorted(prepared, key=lambda item: item["name"]) if predicate(place)]

    rising_names = pattern_names(_rising)
    persistent_names = pattern_names(
        lambda place: place.get("risk_class") in ELEVATED and not _rising(place) and not _falling(place) and (place.get("trend") or {}).get("available")
    )
    emerging_names = []
    for group in groups:
        for name in _names(places, group):
            if name not in emerging_names:
                emerging_names.append(name)
    declining_names = pattern_names(_falling)
    forecast_names = [place["name"] for place in prepared if (place["_step"] or {}).get("direction") == "up"]
    patterns = [
        _pattern_card(
            "Rising areas",
            rising_names,
            f"{_count_phrase(len(rising_names), 'municipality has', 'municipalities have')} a rising stored hazard."
            if rising_names
            else "No rising municipality is stored for this day.",
        ),
        _pattern_card(
            "Persistent areas",
            persistent_names,
            f"{_count_phrase(len(persistent_names), 'municipality remains', 'municipalities remain')} elevated on the stored record."
            if persistent_names
            else "No persistent elevated municipality is stored for this day.",
        ),
        _pattern_card(
            "Emerging areas",
            emerging_names,
            f"{_count_phrase(len(emerging_names), 'municipality is', 'municipalities are')} in an emerging monitoring area."
            if emerging_names
            else "No emerging monitoring area is stored for this threat.",
        ),
        _pattern_card(
            "Declining areas",
            declining_names,
            f"{_count_phrase(len(declining_names), 'municipality has', 'municipalities have')} a falling stored hazard."
            if declining_names
            else "No declining municipality is stored for this day.",
        ),
        _pattern_card(
            "Forecast transition areas",
            forecast_names,
            f"{_count_phrase(len(forecast_names), 'municipality is', 'municipalities are')} projected to move up on the stored forecast."
            if forecast_names
            else "No forecast transition is stored for this day.",
        ),
    ]

    forecast_cards = []
    for place in sorted(prepared, key=_sort_key):
        step = place["_step"]
        if not step or step["direction"] != "up":
            continue
        sentence = f"Conditions are projected to become more favorable to the configured model {_hours_phrase(step['hours'])}."
        evidence = [f"{place['name']}."] + _forecast_evidence(place, step)
        forecast_cards.append({"slug": place["slug"], "name": place["name"], "sentence": sentence, "evidence": _card("", evidence)["evidence"]})
        if len(forecast_cards) == 5:
            break

    convergence = []
    for row in context.get("convergence") or []:
        threats = [item for item in row.get("threats") or [] if item.get("name") and item.get("risk_label")]
        if len(threats) < 2:
            continue
        evidence = [f"{item['name']}: {item['risk_label']}." for item in threats]
        convergence.append(
            {
                "slug": row.get("slug"),
                "name": row.get("name"),
                "threats": threats,
                "evidence": evidence,
                "sentence": f"Multiple independent threat models currently identify elevated monitoring conditions in {row.get('name')}.",
            }
        )

    rice_places = [place for place in ranked if _rice_bits(place)][:5]
    if not rice_places:
        rice_places = [place for place in prepared if place.get("risk_class") in ELEVATED and _rice_bits(place)][:5]
    rice = None
    if rice_places:
        sentence = (
            f"{_count_phrase(len(rice_places), 'high-priority monitoring area contains', 'high-priority monitoring areas contain')} mapped rice area. "
            "These locations may warrant closer field monitoring."
        )
        evidence = []
        for place in rice_places:
            for bit in _rice_bits(place):
                evidence.append(f"{place['name']}: {bit[:-1] if bit.endswith('.') else bit}.")
        for key, title in (
            ("production", "Nueva Ecija production"),
            ("harvested_area", "Nueva Ecija harvested area"),
            ("yield", "Nueva Ecija yield"),
        ):
            stat = (context.get("province_rice") or {}).get(key)
            if not stat or stat.get("value") is None:
                continue
            unit = stat.get("unit") or ""
            period = stat.get("period")
            tail = f", {period}" if period else ""
            evidence.append(f"{title} {_num(stat['value'], 2 if key == 'yield' else 0)} {unit}{tail}.".replace("  ", " "))
        rice = _card(sentence, evidence)

    weather = None
    elevated_places = [place for place in prepared if place.get("risk_class") in ELEVATED and _favorable(place)]
    if elevated_places:
        evidence = []
        focus = elevated_places[0]["name"] if len(elevated_places) == 1 else None
        for place in elevated_places[:5]:
            for factor in _favorable(place)[:3]:
                evidence.append(f"{_reading(factor)} in {place['name']}.")
        where = f" in {focus}" if focus else ""
        weather = _card(
            f"Current {threat} scoring{where} is elevated partly because stored factors fall in the favorable range used by the model.",
            evidence,
        )
    elif any(_weather_line(place) for place in prepared):
        evidence = [_weather_line(place) for place in prepared if _weather_line(place)][:5]
        weather = _card("Stored weather for this day is on the record.", evidence)

    inspections = []
    for place in ranked:
        if place.get("risk_class") not in ELEVATED and not _rapid(place) and (place["_step"] or {}).get("direction") != "up":
            continue
        action = _action(forecast_day)
        inspections.append(
            {
                "slug": place["slug"],
                "name": place["name"],
                "sentence": f"Field validation is recommended for {place['name']}.",
                "field": f"{place['name']}. {action}",
                "action": action,
                "urgency": _urgency(place),
                "evidence": _card("", _hazard_evidence(place) + _forecast_evidence(place, place["_step"]) + _gap_lines(place, place["_gap"]))["evidence"],
            }
        )
        if len(inspections) == 5:
            break

    route = _route_card(context, by_slug, as_of)
    admin = _admin(threat, attention, prepared, as_of)
    timeline = []
    seen = set()
    for place in ranked[:5]:
        if place["slug"] in seen:
            continue
        seen.add(place["slug"])
        events = _history_events(place)
        if not events:
            continue
        count = len(events)
        noun = "stored change" if count == 1 else "stored changes"
        timeline.append(
            {
                "slug": place["slug"],
                "name": place["name"],
                "sentence": f"{place['name']} has {count} {noun} on the monitoring record.",
                "events": events,
            }
        )

    scored = sum(1 for place in places if place.get("score") is not None)
    total = int(context.get("municipality_count") or len(places))
    completeness = _card(
        f"Data completeness: {scored} of {total} municipalities have a stored {threat} score for this day."
    )
    brief = {
        "weather": weather or _card("No weather reading is stored for this day."),
        "emerging": _card(emerging[0]["sentence"], emerging[0]["evidence"]) if emerging else _card("No emerging monitoring area is stored for this threat."),
        "priorities": _card(attention[0]["sentence"], [item["name"] + "." for item in attention]) if attention else _card(EMPTY),
        "forecast": _card(forecast_cards[0]["sentence"], forecast_cards[0]["evidence"]) if forecast_cards else _card("No municipality is projected to become more favorable to the configured model on the stored forecast."),
        "actions": _card(inspections[0]["sentence"], [inspections[0]["action"], *inspections[0]["evidence"]]) if inspections else _card(EMPTY),
    }
    prompts = _prompts(threat, attention)
    return {
        "source": SOURCE,
        "scope": context.get("scope_label") or "Nueva Ecija",
        "threat": {"id": context.get("threat_id"), "name": threat},
        "as_of": as_of.isoformat() if as_of else None,
        "forecast_day": forecast_day,
        "completeness": completeness,
        "empty": EMPTY if not attention else None,
        "attention": attention,
        "emerging": emerging,
        "patterns": patterns,
        "forecast": forecast_cards,
        "convergence": convergence,
        "rice": rice,
        "weather": weather,
        "inspections": inspections,
        "brief": brief,
        "admin": admin,
        "route": route,
        "timeline": timeline,
        "prompts": prompts,
    }


def _route_card(context: dict, by_slug: dict, as_of: date | None) -> dict | None:
    route = context.get("route") or {}
    stops = [stop for stop in route.get("stops") or [] if stop.get("name")]
    scope = context.get("scope_slug")
    if scope:
        stops = [stop for stop in stops if stop.get("slug") == scope]
    if len(stops) < 1:
        return None
    if len(stops) == 1 and scope:
        sentence = f"{stops[0]['name']} is a stop on the stored inspection route."
    else:
        sentence = "The stored route visits " + _join([stop["name"] for stop in stops]) + "."
    evidence = ["Suggested order follows the stored route."]
    if route.get("distance_km") is not None and not scope:
        evidence.append(f"Expected travel {_num(route['distance_km'], 1)} km.")
    if route.get("graph"):
        evidence.append(str(route["graph"]))
    for index, stop in enumerate(stops, start=1):
        place = by_slug.get(stop.get("slug")) or {}
        bits = [f"Stop {index}, {stop['name']}"]
        label = _label(place.get("risk_class"))
        if label and label != "Insufficient data":
            bits.append(label)
        if place.get("priority_points") is not None:
            bits.append(f"inspection priority {int(place['priority_points'])}")
        evidence.append(", ".join(bits) + ".")
        tomorrow = place.get("tomorrow") or {}
        if tomorrow.get("rain_mm") is not None:
            stamp = _stamp(tomorrow.get("date") or (as_of + timedelta(days=1) if as_of else None))
            when = f" on {stamp}" if stamp else ""
            evidence.append(f"Stored rainfall {_num(tomorrow['rain_mm'], 1)} mm in {stop['name']}{when}.")
    return _card(sentence, evidence) | {"stops": stops}


def _admin(threat: str, attention: list[dict], places: list[dict], as_of: date | None) -> dict:
    overdue = [place for place in places if place.get("risk_class") in ELEVATED and place.get("_gap")]
    overdue.sort(key=lambda place: place["name"])
    noted = [place for place in places if place.get("last_note_on")]
    workload = _card(
        f"Today's monitoring workload for {threat} is {len(attention)} {'municipality' if len(attention) == 1 else 'municipalities'} on the attention list."
        if attention
        else EMPTY,
        [f"{item['rank']}. {item['name']}, {item['signal']}." for item in attention],
    )
    overdue_card = _card(
        f"{_count_phrase(len(overdue), 'municipality has', 'municipalities have')} elevated monitoring conditions and no field note in the last 7 days."
        if overdue
        else "No elevated municipality is missing a field note from the last 7 days.",
        [place["name"] + "." for place in overdue[:8]],
    )
    assignment = _card(
        "Field validation is recommended for those municipalities. No assignment record is stored, so an officer still assigns the visit."
        if overdue
        else "No municipality is waiting on an assignment in the stored notes.",
        [place["name"] + "." for place in overdue[:8]],
    )
    note_card = _card(
        f"Field notes are stored for {_count_phrase(len(noted), 'municipality', 'municipalities').lower()}."
        if noted
        else "No field note is stored for this scope.",
        [
            f"{place['name']}, last note {_stamp(place.get('last_note_on'))}."
            for place in sorted(noted, key=lambda item: item["name"])[:8]
            if _stamp(place.get("last_note_on"))
        ],
    )
    if as_of and overdue_card["sentence"].startswith("No elevated") and any(place.get("_gap") == "none" for place in places):
        pass
    return {"workload": workload, "overdue": overdue_card, "assignment": assignment, "notes": note_card}


def _prompts(threat: str, attention: list[dict]) -> list[dict]:
    top = attention[0]["name"] if attention else "the top municipality"
    rows = [
        ("worse", f"Which municipalities are getting worse for {threat}?", f"Which municipalities are getting worse for {threat}?"),
        ("rain", "What is tomorrow's rainfall?", "What is tomorrow's rainfall?"),
        ("high", "Which areas are projected to become High?", "Which areas are projected to become High?"),
        ("gap", "Which high-priority areas have no field note in the last 7 days?", "Which high-priority areas have no field note in the last 7 days?"),
        ("rice", "Which high-monitoring municipalities have mapped rice area?", "Which high-monitoring municipalities have mapped rice area?"),
        ("why", f"Why is {top} a monitoring priority?", f"Why is {top} a monitoring priority?"),
        ("do", "What field validation is recommended?", "What field validation is recommended?"),
    ]
    return [{"id": key, "label": label, "message": message} for key, label, message in rows]


def _reply(card: dict | None, empty: str) -> str:
    if not card or not card.get("sentence"):
        return f"{empty}\n\n{SOURCE}"
    lines = [card["sentence"], ""]
    lines.extend(card.get("evidence") or [])
    lines.extend(["", SOURCE])
    return "\n".join(lines).strip()


def _question(message: str) -> str:
    lines = message.strip().splitlines()
    if lines and lines[0].lower().startswith("officer context:"):
        lines = lines[1:]
    return " ".join(lines).strip().lower()


def _place_named(message: str, record: dict) -> dict | None:
    names = []
    for bucket in (record.get("attention") or [], record.get("inspections") or [], record.get("timeline") or [], record.get("convergence") or []):
        for item in bucket:
            if isinstance(item, dict) and item.get("name"):
                names.append(item)
    names.sort(key=lambda item: len(item.get("name") or ""), reverse=True)
    for item in names:
        if item["name"].lower() in message:
            return item
    return None


def grounded_answer(message: str, record: dict) -> str | None:
    """Answer the selected province questions from the situation record."""
    text = _question(message)
    if not text:
        return None
    if any(phrase in text for phrase in ("what is missing", "what's missing", "which factors", "data limit", "incomplete", "what are the limits")):
        lines = [record["completeness"]["sentence"], ""]
        lines.extend(record["completeness"].get("evidence") or [])
        overdue = (record.get("admin") or {}).get("overdue") or {}
        if overdue.get("sentence"):
            lines.extend(["", overdue["sentence"], *overdue.get("evidence", [])])
        lines.extend(["", SOURCE])
        return "\n".join(lines).strip()
    named = _place_named(text, record)
    if named and text.startswith("why"):
        return _reply(named if named.get("sentence") else None, "That municipality is not in the stored attention list for this threat and day.")
    if "rainfall" in text or ("rain" in text and "tomorrow" in text):
        return _reply(record.get("rainfall"), "No rainfall is stored for tomorrow.")
    if "become high" in text or "projected to become" in text or "become more favorable" in text:
        cards = record.get("forecast") or []
        if not cards:
            return _reply(None, "No municipality is projected to become High on the stored forecast.")
        evidence = []
        for card in cards:
            evidence.extend(card.get("evidence") or [])
        return _reply(_card(cards[0]["sentence"], evidence), EMPTY)
    if any(phrase in text for phrase in ("no field note", "last 7", "7 days", "not been inspected", "no recent", "uninspected")):
        return _reply((record.get("admin") or {}).get("overdue"), "No elevated municipality is missing a field note from the last 7 days.")
    if "rice area" in text or "mapped rice" in text or "rice inside" in text:
        return _reply(record.get("rice"), "No mapped rice area is stored for the high-monitoring municipalities.")
    if any(phrase in text for phrase in ("getting worse", "worsening", "rising hazard", "increasing hazard")):
        card = next((item for item in record.get("patterns") or [] if item.get("id") == "Rising areas"), None)
        return _reply(card, "No rising municipality is stored for this day.")
    if "route" in text or "plan my inspection" in text or "stop order" in text:
        return _reply(record.get("route"), "No inspection route is stored for this threat and day.")
    if any(phrase in text for phrase in ("field validation", "what should we do", "attention list", "recommended", "inspect", "visit first", "go first", "priorit")):
        card = (record.get("brief") or {}).get("actions")
        return _reply(card, EMPTY)
    if "convergence" in text or "multiple threat" in text or "other threats" in text:
        rows = record.get("convergence") or []
        if not rows:
            return _reply(None, "No municipality has two elevated threat models on the stored record.")
        evidence = []
        for row in rows[:5]:
            evidence.extend(row.get("evidence") or [])
            evidence.append(row["sentence"])
        return _reply(_card(rows[0]["sentence"], evidence), EMPTY)
    if "workload" in text or "overdue" in text:
        return _reply((record.get("admin") or {}).get("workload"), EMPTY)
    if text.startswith("why is") or text.startswith("why does"):
        return _reply(None, "That municipality is not in the stored attention list for this threat and day.")
    return None


def read_note(body: str) -> dict:
    """Restate a field note. Do not turn the words into a diagnosis."""
    text = " ".join((body or "").split()).strip()
    clauses = []
    for chunk in re.split(r"[.;!?]+", text):
        parts = re.split(r"\s+and\s+", chunk, flags=re.IGNORECASE)
        for part in parts:
            cleaned = part.strip(" ,")
            if len(cleaned) >= 3:
                clauses.append(cleaned[0].lower() + cleaned[1:] if cleaned[:1].isupper() else cleaned)
    observations = []
    for clause in clauses:
        clause = re.sub(r"^(there are|there is|i saw|we saw)\s+", "", clause, flags=re.IGNORECASE).strip()
        if clause and f"Noted: {clause}." not in observations:
            observations.append(f"Noted: {clause}.")
    lowered = text.lower()
    missing = []
    if not any(word in lowered for word in ("stage", "seedling", "tillering", "panicle", "flowering", "heading", "maturity", "ripening", "vegetative", "booting")):
        missing.append("Crop stage")
    if not any(word in lowered for word in ("hectare", " ha", "percent", "%", "extent", "patch", "widespread", "whole field", "part of the field", "most of the field")):
        missing.append("Approximate extent")
    suggested = []
    if not any(word in lowered for word in ("photo", "picture", "image")):
        suggested.append("Attach a field photo.")
    return {
        "observations": observations,
        "missing": missing,
        "suggested": suggested,
        "boundary": "These lines restate the note. They are not a model result.",
        "source": SOURCE,
    }


INDICATOR_BANNED = BANNED + ("confirmed", "infection", "disease", "pest")


def _safe_indicators(items) -> list[str]:
    kept = []
    for item in items or []:
        text = " ".join(str(item).split())
        if not text or len(text) > 140:
            continue
        lowered = text.lower()
        if any(word in lowered for word in INDICATOR_BANNED):
            continue
        if text not in kept:
            kept.append(text)
        if len(kept) == 4:
            break
    return kept


def review_image_text(payload: dict | None, quality: str | None = None) -> dict:
    """Wrap a vision result. The sentence is never a diagnosis."""
    data = payload or {}
    image_quality = (quality or data.get("quality") or "").lower()
    if image_quality in ("unclear", "poor", "unusable"):
        return {
            "configured": True,
            "sentence": "The image is not clear enough to describe. Field validation is still required.",
            "indicators": [],
            "questions": ["What crop stage is in the frame?", "About how much of the field looks like this?"],
            "source": SOURCE,
        }
    indicators = _safe_indicators(data.get("indicators"))
    questions = _safe_indicators(data.get("questions")) or [
        "What crop stage is in the frame?",
        "About how much of the field looks like this?",
    ]
    if not indicators:
        return {
            "configured": True,
            "sentence": "The image was checked. No separate visual note was kept. Field validation is still required.",
            "indicators": [],
            "questions": questions[:3],
            "source": SOURCE,
        }
    return {
        "configured": True,
        "sentence": "Possible visual indicators detected. Field validation recommended.",
        "indicators": indicators,
        "questions": questions[:3],
        "source": SOURCE,
    }


def parse_image_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def review_image(media_type: str, data_base64: str) -> dict:
    if media_type not in ("image/jpeg", "image/png", "image/webp"):
        return {"configured": False, "sentence": "Use a JPEG, PNG, or WebP field photo. Field validation is still required.", "indicators": [], "questions": [], "source": SOURCE}
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except Exception:
        return {"configured": False, "sentence": "The image could not be read. Field validation is still required.", "indicators": [], "questions": [], "source": SOURCE}
    if len(raw) < 32 or len(raw) > 4_000_000:
        return {"configured": False, "sentence": "The image could not be read. Field validation is still required.", "indicators": [], "questions": [], "source": SOURCE}
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {"configured": False, "sentence": "The image was not read. Field validation is still required.", "indicators": [], "questions": [], "source": SOURCE}
    from app.gemini import gemini_post

    system = (
        "You look at a rice-field photo for an agriculture office in Nueva Ecija. "
        "Return JSON only with keys quality, indicators, and questions. "
        "quality is usable or unclear. "
        "indicators are short visible features such as leaf color, spots, or insects. "
        "Do not name a disease. Do not name a pest species. Do not say anything is confirmed, present, spreading, or an outbreak. "
        "Do not estimate damage, hectares, or pesos. questions are field questions, at most three."
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Describe only what is visible. Return JSON."},
                    {"inline_data": {"mime_type": media_type, "data": data_base64}},
                ],
            }
        ],
    }
    try:
        response = gemini_post(json=body, timeout=30)
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    except Exception:
        return {"configured": True, "sentence": "The image was not read. Field validation is still required.", "indicators": [], "questions": [], "source": SOURCE}
    return review_image_text(parse_image_json(text))


def situation_layer(threat_id: str, season: str, forecast_day: int, role: str, municipality_slug: str | None) -> dict:
    from app.db import connect
    from app.reports import algorithms
    from app.rice import _stage_reading
    from app.scoring import load_rules
    from app.paths import rules_dir

    rules = {rule["id"]: rule for rule in load_rules(rules_dir())}
    rule = rules.get(threat_id) or {"id": threat_id, "name": threat_id, "factors": []}
    with connect() as conn:
        scope_id = None
        scope_name = "Nueva Ecija"
        if municipality_slug:
            scope = conn.execute("SELECT id, name FROM municipalities WHERE slug = %s", (municipality_slug,)).fetchone()
            if scope:
                scope_id = scope["id"]
                scope_name = scope["name"]
            else:
                scope_name = "This municipality"
        municipalities = [
            dict(row)
            for row in conn.execute(
                "SELECT id, slug, name FROM municipalities WHERE (%s::int IS NULL OR id = %s::int) ORDER BY name",
                (scope_id, scope_id),
            ).fetchall()
        ]
        scores = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, r.threat_id, r.forecast_day, r.score, r.risk_class, r.factors_used, r.exposure_ha
                FROM municipalities m
                JOIN risk_score r ON r.place_id = m.id AND r.place_type = 'municipality'
                WHERE r.season = %s AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (season, scope_id, scope_id),
            ).fetchall()
        ]
        history_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, h.observed_on, h.score, h.risk_class
                FROM risk_history h
                JOIN municipalities m ON m.id = h.place_id
                WHERE h.place_type = 'municipality' AND h.threat_id = %s AND h.season = %s
                  AND (%s::int IS NULL OR m.id = %s::int)
                ORDER BY h.observed_on
                """,
                (threat_id, season, scope_id, scope_id),
            ).fetchall()
        ]
        notes = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, f.body, f.created_at
                FROM field_notes f
                JOIN municipalities m ON m.id = f.place_id
                WHERE f.place_type = 'municipality' AND (%s::int IS NULL OR m.id = %s::int)
                UNION ALL
                SELECT m.slug, f.body, f.created_at
                FROM field_notes f
                JOIN barangays b ON b.id = f.place_id
                JOIN municipalities m ON m.id = b.municipality_id
                WHERE f.place_type = 'barangay' AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (scope_id, scope_id, scope_id, scope_id),
            ).fetchall()
        ]
        weather_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, w.day_offset, w.forecast_date, w.temp_c, w.rh_pct, w.rain_mm,
                       w.wind_speed_kmh, w.soil_moisture, w.hours_rh90
                FROM weather_forecast w
                JOIN municipalities m ON m.id = w.place_id
                WHERE w.place_type = 'municipality' AND w.day_offset IN (%s, %s)
                  AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (forecast_day, min(6, forecast_day + 1), scope_id, scope_id),
            ).fetchall()
        ]
        rice_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, a.rice_ha, a.harvested_ha, a.yield_t_ha, a.planting_date
                FROM rice_area a
                JOIN municipalities m ON m.id = a.place_id
                WHERE a.place_type = 'municipality' AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchall()
        ]
        fractions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT m.slug, s.rice_fraction
                FROM satellite s
                JOIN municipalities m ON m.id = s.place_id
                WHERE s.place_type = 'municipality' AND s.rice_fraction IS NOT NULL
                  AND (%s::int IS NULL OR m.id = %s::int)
                """,
                (scope_id, scope_id),
            ).fetchall()
        ]
        edges = [
            (row["a"], row["b"])
            for row in conn.execute(
                """
                SELECT ma.slug AS a, mb.slug AS b
                FROM edges e
                JOIN municipalities ma ON ma.id = e.place_a
                JOIN municipalities mb ON mb.id = e.place_b
                WHERE e.place_type = 'municipality' AND e.kind = 'boundary'
                """
            ).fetchall()
        ]
        stats = [
            dict(row)
            for row in conn.execute(
                "SELECT metric, period, value, unit FROM provincial_stats WHERE metric IN ('production', 'harvested_area', 'yield')"
            ).fetchall()
        ]
        forecast_date = conn.execute(
            "SELECT MIN(forecast_date) AS start_date FROM weather_forecast WHERE day_offset = %s",
            (forecast_day,),
        ).fetchone()
        from app.insights import load_board

        board, _forecast_on = load_board(conn, threat_id, season, forecast_day, rule.get("name") or threat_id)
    as_of = forecast_date["start_date"] if forecast_date and forecast_date["start_date"] else None
    priority_by = {row["slug"]: (row.get("priority") or {}).get("points") for row in board}
    trend_by = {row["slug"]: row.get("trend") or {} for row in board}
    by_place_day: dict[tuple[str, str, int], dict] = {}
    for row in scores:
        by_place_day[(row["slug"], row["threat_id"], int(row["forecast_day"]))] = row
    history_by: dict[str, list] = {}
    for row in history_rows:
        history_by.setdefault(row["slug"], []).append(row)
    notes_by: dict[str, list] = {}
    for row in notes:
        notes_by.setdefault(row["slug"], []).append(row)
    weather_by: dict[tuple[str, int], dict] = {}
    for row in weather_rows:
        weather_by[(row["slug"], int(row["day_offset"]))] = row
    rice_by = {}
    for row in rice_rows:
        current = rice_by.get(row["slug"])
        if current is None or (current.get("rice_ha") is None and row.get("rice_ha") is not None):
            rice_by[row["slug"]] = row
    fraction_by = {row["slug"]: row["rice_fraction"] for row in fractions}
    threat_names = {item["id"]: item["name"] for item in rules.values()}
    for item_id, item in rules.items():
        threat_names[item_id] = item.get("name") or item_id
    places = []
    convergence_bucket: dict[str, dict] = {}
    for muni in municipalities:
        selected = by_place_day.get((muni["slug"], threat_id, forecast_day))
        forecast = []
        for offset in range(1, 7 - forecast_day + 1):
            ahead = by_place_day.get((muni["slug"], threat_id, forecast_day + offset))
            if not ahead:
                continue
            weather_ahead = weather_by.get((muni["slug"], forecast_day + offset))
            forecast.append(
                {
                    "offset": offset,
                    "score": ahead.get("score"),
                    "risk_class": ahead.get("risk_class"),
                    "date": weather_ahead.get("forecast_date").isoformat() if weather_ahead and weather_ahead.get("forecast_date") else None,
                }
            )
        trend = trend_by.get(muni["slug"]) or {"available": False}
        rice_row = rice_by.get(muni["slug"]) or {}
        planting = rice_row.get("planting_date")
        days = None
        if planting and as_of and _date(as_of) and _date(planting):
            span = (_date(as_of) - _date(planting)).days
            days = span if span >= 0 else None
        stage = _stage_reading(rule, days)
        note_rows = notes_by.get(muni["slug"], [])
        last_note = None
        for note in note_rows:
            day = _manila_day(note.get("created_at"))
            if day and (last_note is None or day > last_note):
                last_note = day
        weather = weather_by.get((muni["slug"], forecast_day)) or {}
        tomorrow = weather_by.get((muni["slug"], forecast_day + 1)) if forecast_day < 6 else None
        places.append(
            {
                "slug": muni["slug"],
                "name": muni["name"],
                "score": selected.get("score") if selected else None,
                "risk_class": selected.get("risk_class") if selected else None,
                "priority_points": priority_by.get(muni["slug"]),
                "trend": trend,
                "forecast": forecast,
                "factors_used": _as_list(selected.get("factors_used")) if selected else [],
                "weather": {
                    "temp_c": weather.get("temp_c"),
                    "rh_pct": weather.get("rh_pct"),
                    "rain_mm": weather.get("rain_mm"),
                    "wind_speed_kmh": weather.get("wind_speed_kmh"),
                    "soil_moisture": weather.get("soil_moisture"),
                    "hours_rh90": weather.get("hours_rh90"),
                },
                "tomorrow": {
                    "rain_mm": (tomorrow or {}).get("rain_mm"),
                    "date": (tomorrow or {}).get("forecast_date").isoformat() if tomorrow and tomorrow.get("forecast_date") else None,
                },
                "rice_ha": rice_row.get("rice_ha"),
                "harvested_ha": rice_row.get("harvested_ha"),
                "yield_t_ha": rice_row.get("yield_t_ha"),
                "rice_fraction": fraction_by.get(muni["slug"]),
                "crop_stage": stage.get("sentence"),
                "last_note_on": last_note.isoformat() if last_note else None,
                "history": [
                    {
                        "observed_on": row["observed_on"].isoformat() if hasattr(row["observed_on"], "isoformat") else row["observed_on"],
                        "score": row["score"],
                        "risk_class": row["risk_class"],
                    }
                    for row in history_by.get(muni["slug"], [])
                ],
                "notes": [
                    {"created_at": note["created_at"].isoformat() if hasattr(note["created_at"], "isoformat") else note["created_at"], "body": note["body"]}
                    for note in note_rows
                ],
            }
        )
        for row in scores:
            if row["slug"] != muni["slug"] or int(row["forecast_day"]) != forecast_day:
                continue
            if row.get("risk_class") not in ELEVATED:
                continue
            bucket = convergence_bucket.setdefault(muni["slug"], {"slug": muni["slug"], "name": muni["name"], "threats": []})
            bucket["threats"].append(
                {
                    "id": row["threat_id"],
                    "name": threat_names.get(row["threat_id"], row["threat_id"]),
                    "risk_label": CLASS_LABELS.get(row["risk_class"], row["risk_class"]),
                }
            )
    province = {}
    for row in stats:
        province[row["metric"]] = {"value": row["value"], "unit": row["unit"], "period": row["period"]}
    route_payload = algorithms(threat_id, season, forecast_day)
    name_to_slug = {muni["name"]: muni["slug"] for muni in municipalities}
    stops = []
    for name in (route_payload.get("route") or {}).get("stops") or []:
        stops.append({"name": name, "slug": name_to_slug.get(name)})
    rainfall_evidence = []
    if forecast_day < 6:
        for place in places:
            rain = (place.get("tomorrow") or {}).get("rain_mm")
            if rain is None:
                continue
            stamp = _stamp((place.get("tomorrow") or {}).get("date"))
            when = f" on {stamp}" if stamp else ""
            rainfall_evidence.append((float(rain), f"{place['name']} {_num(rain, 1)} mm{when}."))
    rainfall_evidence.sort(key=lambda item: item[0], reverse=True)
    record = build_layer(
        {
            "threat_id": threat_id,
            "threat_name": rule.get("name") or threat_id,
            "season": season,
            "forecast_day": forecast_day,
            "as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else as_of,
            "scope_label": scope_name,
            "scope_slug": municipality_slug if scope_id else None,
            "municipality_count": len(municipalities),
            "places": places,
            "edges": edges,
            "convergence": list(convergence_bucket.values()),
            "province_rice": province,
            "route": {
                "stops": stops,
                "distance_km": (route_payload.get("route") or {}).get("distance_km"),
                "graph": route_payload.get("graph"),
            },
            "role": role,
        }
    )
    if rainfall_evidence:
        record["rainfall"] = _card("Rainfall for tomorrow is stored for these municipalities.", [item[1] for item in rainfall_evidence[:5]])
    else:
        record["rainfall"] = None
    return record
