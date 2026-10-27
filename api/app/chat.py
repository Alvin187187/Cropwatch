"""Gemini function calling. The model only receives tool results, which are aggregates."""

from __future__ import annotations

import os
import time

import httpx

from app.gemini import gemini_post
from app.reports import algorithms, briefing, dataset_status, place_detail, priority

SYSTEM = """You are the CROPWATCH briefing assistant for rice officers in Nueva Ecija, Philippines.
Suggest where to monitor first. Use only numbers and place names that appear in tool results during this conversation.
Never say a pest or disease is present. Never diagnose a plant. Never estimate pesos, financial loss, or exact yield loss.
If a factor was skipped or a dataset is missing, say so in plain English.
Do not mention a missing factor, an assumption, or a data limit unless the officer asked what is missing. When they ask, use only what the tools returned. Describe data completeness as a count of stored records, not as a confidence word.
The wet or dry setting is not a crop-stage substitute. El Niño, when used, is a national modifier and does not separate towns.
Write one plain sentence, then the exact figures from the tool results. Use full municipality names. Do not say the word AI. Do not say outbreak, spreading, or confirmed infection.
If exposed hectares are unavailable, say that the map shows favorable conditions, not damaged hectares.
Keep the answer short enough to read aloud in a briefing.
"""

TOOLS = [
    {
        "name": "get_provincial_summary",
        "description": "Provincial risk counts, Ricelytics rice totals, exposure hectares, and which national figures are context only.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_priority_list",
        "description": "Municipalities ordered by risk class, then by exposed rice hectares when that number exists.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_municipality_detail",
        "description": "Weather, risk class, fired factors, skipped factors, and exposure for one municipality.",
        "parameters": {
            "type": "object",
            "properties": {"municipality_slug": {"type": "string"}},
            "required": ["municipality_slug"],
        },
    },
    {
        "name": "get_algorithms",
        "description": "Priority order, high-risk clusters, and the inspection route for the selected threat and day.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_provincial_situation",
        "description": "Operational situation: attention counts, changes, 72-hour outlook, and recommended actions. Hazard is not a probability.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_threat_analytics",
        "description": "Threat analytics for the selected threat. Threats stay independent. There is no combined disease score.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_rice_profile",
        "description": "Rice statistics, exposure, crop stage, and climate context. Exposure is not damaged hectares.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather_context",
        "description": "Threat-relevant model weather for the selected forecast day. This is not a live sensor.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_data_availability",
        "description": "Which datasets are loaded, empty, or partial, with their stored status text.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_inspection_context",
        "description": "Recommended actions and the stored inspection order for the selected threat.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_situation_layer",
        "description": "Province-wide monitoring copy already written from the situation record: attention, emerging areas, forecast, convergence, rice, weather, inspections, the daily brief, and the stored route.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def narrate_brief(record: dict) -> dict:
    """Rewrite a finished situation record. Figures stay in the record either way."""
    fallback = (record.get("brief") or {}).get("text") or ""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {"configured": False, "source": "rules", "text": fallback}
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    payload = record.get("narration_input") or {}
    system = (
        "You rewrite a CROPWATCH situation record into 3 or 4 short sentences for a rice officer in Nueva Ecija. "
        "Use only place names, numbers, classes, drivers, and actions that appear in the JSON. "
        "Do not add a cause that is not in the JSON. "
        "Do not say a pest or disease is present, detected, or confirmed. "
        "Do not estimate pesos, financial loss, or yield loss. "
        "Do not call the inspection priority a risk score or a hazard score. "
        "If something is listed as missing, keep it missing. "
        "Return prose only, with no title and no bullet list."
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json_dumps(payload)}]}],
    }
    try:
        response = gemini_post(json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    except Exception:
        return {"configured": True, "source": "rules", "text": fallback}
    from app.command import brief_is_grounded

    if not text or not brief_is_grounded(text):
        return {"configured": True, "source": "rules", "text": fallback}
    return {"configured": True, "source": "assistant", "text": text}


def narrate_analytics(record: dict) -> dict:
    """Rewrite a finished analytics record. Figures stay in the record either way."""
    fallback = record.get("summary_text") or ""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {"configured": False, "source": "rules", "text": fallback}
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    payload = record.get("narration_input") or {}
    system = (
        "You rewrite a CROPWATCH analytics record into 3 or 4 short sentences for a rice officer in Nueva Ecija. "
        "Use only threat names, place names, numbers, classes, and factors that appear in the JSON. "
        "Do not add a cause that is not in the JSON. "
        "Do not say a pest or disease is present, spreading, detected, or confirmed. "
        "Do not estimate pesos, financial loss, yield loss, or a probability. "
        "Do not create a combined disease score. "
        "Hazard score and inspection priority stay separate. "
        "Return prose only, with no title and no bullet list."
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json_dumps(payload)}]}],
    }
    try:
        response = gemini_post(json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    except Exception:
        return {"configured": True, "source": "rules", "text": fallback}
    from app.analytics import analytics_is_grounded

    if not text or not analytics_is_grounded(text):
        return {"configured": True, "source": "rules", "text": fallback}
    return {"configured": True, "source": "assistant", "text": text}


def narrate_rice(record: dict) -> dict:
    """Rewrite a finished rice-context record. Figures stay in the record either way."""
    fallback = record.get("summary_text") or ""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {"configured": False, "source": "rules", "text": fallback}
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    payload = record.get("narration_input") or {}
    system = (
        "You rewrite a CROPWATCH rice-context record into 3 or 4 short sentences for a rice officer in Nueva Ecija. "
        "Use only numbers, periods, sources, place names, and factor names that appear in the JSON. "
        "Do not convert a hazard score into crop damage, hectares damaged, pesos, or yield loss. "
        "Do not say farmers are at risk. Do not say a pest or disease is present or caused a vegetation change. "
        "Hazard score and inspection priority stay separate. "
        "Return prose only, with no title and no bullet list."
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json_dumps(payload)}]}],
    }
    try:
        response = gemini_post(json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    except Exception:
        return {"configured": True, "source": "rules", "text": fallback}
    from app.rice import rice_is_grounded

    if not text or not rice_is_grounded(text):
        return {"configured": True, "source": "rules", "text": fallback}
    return {"configured": True, "source": "assistant", "text": text}


def chat_is_supported(text: str) -> bool:
    """Reject a chat reply that diagnoses, prices, or asserts presence."""
    lowered = text.lower()
    banned = (
        "confirmed",
        "outbreak",
        "detected",
        "pesos",
        "yield loss",
        "diagnos",
        "real-time sensor",
        "realtime sensor",
        "live sensor",
        "spreading",
        "disease score",
        "crop damage",
        "damaged hectares",
        "financial loss",
        "farmers at risk",
        "farmers are at risk",
    )
    if any(word in lowered for word in banned):
        return False
    cleaned = lowered.replace("does not mean the pest or disease is present", "")
    if " is present" in cleaned or " are present" in cleaned:
        return False
    return True


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def answer(message: str, threat_id: str, season: str, forecast_day: int, municipality_slug: str | None, role: str = "provincial") -> dict:
    context = {
        "threat_id": threat_id,
        "season": season,
        "forecast_day": forecast_day,
        "municipality_slug": municipality_slug,
        "role": role,
    }
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    grounding = {
        "provincial_summary": briefing(threat_id, season, forecast_day),
        "priority_list": priority(threat_id, season, forecast_day, municipality_slug)[:8],
    }
    try:
        from app.layer import grounded_answer, situation_layer

        situation = situation_layer(threat_id, season, forecast_day, role, municipality_slug)
        context["situation"] = situation
        grounded = grounded_answer(message, situation)
    except Exception:
        grounded = None
    if grounded:
        return {"configured": bool(key), "reply": grounded, "grounding": grounding}
    if not key:
        return {
            "configured": False,
            "reply": "The assistant is not configured. Set GEMINI_API_KEY in the environment and restart the API. The lists on this page are the same figures the assistant is allowed to use.",
            "grounding": grounding,
        }
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    contents = [{"role": "user", "parts": [{"text": message}]}]
    system = SYSTEM + f"\nCurrent selection: threat={threat_id}, season={season}, forecast day={forecast_day}."
    if municipality_slug:
        system += f" The signed-in officer is scoped to municipality slug {municipality_slug}."
    system += "\nStored records for this selection (answer from these first; call a tool only when they do not cover the question):\n" + json_dumps(grounding)[:12000]
    try:
        reply = _run(model, key, system, contents, context)
    except Exception as exc:
        if grounded:
            return {"configured": True, "reply": grounded, "grounding": grounding}
        return {
            "configured": True,
            "reply": "The assistant is busy right now. Try again in a minute. The priority list and map still read the database directly.",
            "grounding": grounding,
        }
    if grounded and reply.startswith("That reply was rejected"):
        reply = grounded
    return {"configured": True, "reply": reply, "grounding": grounding}


def _run(model: str, key: str, system: str, contents: list, context: dict) -> str:
    deadline = time.monotonic() + 40
    for _ in range(4):
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"function_declarations": TOOLS}],
        }
        response = gemini_post(json=payload, timeout=15, deadline=deadline)
        response.raise_for_status()
        data = response.json()
        candidate = data["candidates"][0]["content"]
        parts = candidate.get("parts", [])
        calls = [part["functionCall"] for part in parts if "functionCall" in part]
        if not calls:
            texts = [part.get("text", "") for part in parts if part.get("text")]
            text = "\n".join(texts).strip() or "No briefing text was returned."
            if not chat_is_supported(text):
                return (
                    "That reply was rejected. It went beyond what the stored CROPWATCH records support. "
                    "Ask about the priority list, a municipality, rice statistics, weather, or the inspection order."
                )
            return text
        contents.append(candidate)
        response_parts = []
        for call in calls:
            response_parts.append(
                {
                    "functionResponse": {
                        "name": call["name"],
                        "response": _tool(call["name"], call.get("args") or {}, context),
                    }
                }
            )
        contents.append({"role": "user", "parts": response_parts})
    return "The assistant stopped before a final briefing. Use the priority list on the map."


def _tool(name: str, args: dict, context: dict) -> dict:
    threat_id = context["threat_id"]
    season = context["season"]
    forecast_day = context["forecast_day"]
    scoped = context["municipality_slug"]
    if name == "get_provincial_summary":
        return briefing(threat_id, season, forecast_day)
    if name == "get_priority_list":
        rows = priority(threat_id, season, forecast_day, scoped)
        return {"places": rows[:10]}
    if name == "get_algorithms":
        payload = algorithms(threat_id, season, forecast_day)
        if scoped:
            payload["priority"] = [row for row in payload["priority"] if row["slug"] == scoped]
            payload["route"] = {"stops": [], "path": [], "distance_km": None, "note": "Inspection route is shown for the provincial account."}
        return payload
    if name == "get_provincial_situation":
        from app.command import command_center

        record = command_center(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        return {
            "situation": record.get("situation"),
            "brief": (record.get("brief") or {}).get("lines"),
            "changes": record.get("changes"),
            "horizon": record.get("horizon"),
            "actions": [
                {"type": item.get("type_label"), "place": item.get("place"), "why": item.get("why"), "recommendation": item.get("recommendation")}
                for item in (record.get("actions") or [])[:6]
            ],
            "weather_impact": (record.get("weather") or {}).get("impact"),
        }
    if name == "get_threat_analytics":
        from app.analytics import analytics

        record = analytics(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        return {
            "summary": record.get("summary_text"),
            "combined_note": record.get("combined_note"),
            "distribution": record.get("distribution"),
            "fastest": record.get("fastest"),
            "transitions": (record.get("transitions") or {}).get("notable"),
            "drivers": record.get("drivers"),
            "coverage": (record.get("coverage") or {}).get("sentence") if isinstance(record.get("coverage"), dict) else None,
        }
    if name == "get_rice_profile":
        from app.rice import rice

        record = rice(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        return {
            "boundary": record.get("boundary"),
            "period_note": record.get("period_note"),
            "metrics": (record.get("situation") or {}).get("metrics"),
            "exposure": record.get("exposure"),
            "crop": (record.get("crop") or {}).get("sentence"),
            "climate": record.get("climate"),
            "satellite_note": ((record.get("conditions") or {}).get("satellite") or {}).get("note"),
        }
    if name == "get_weather_context":
        from app.command import command_center

        record = command_center(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        weather = record.get("weather") or {}
        return {
            "source": "Open-Meteo model weather. This is not a live sensor observation.",
            "forecast_date": record.get("forecast_date"),
            "current": weather.get("current"),
            "impact": weather.get("impact"),
            "signals": (record.get("why_now") or {}).get("signals"),
        }
    if name == "get_data_availability":
        return {"datasets": dataset_status()}
    if name == "get_inspection_context":
        from app.command import command_center

        payload = algorithms(threat_id, season, forecast_day)
        record = command_center(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        if scoped:
            payload["priority"] = [row for row in payload["priority"] if row["slug"] == scoped]
            payload["route"] = {"stops": [], "path": [], "distance_km": None, "note": "Inspection route is shown for the provincial account."}
        return {
            "route": payload.get("route"),
            "priority": (payload.get("priority") or [])[:8],
            "actions": [
                {"type": item.get("type_label"), "place": item.get("place"), "slug": item.get("slug"), "recommendation": item.get("recommendation")}
                for item in (record.get("actions") or [])[:8]
            ],
        }
    if name == "get_situation_layer":
        record = context.get("situation")
        if record is None:
            from app.layer import situation_layer

            record = situation_layer(threat_id, season, forecast_day, context.get("role") or "provincial", scoped)
        kept = (
            "source",
            "scope",
            "completeness",
            "attention",
            "emerging",
            "patterns",
            "forecast",
            "convergence",
            "rice",
            "weather",
            "inspections",
            "brief",
            "admin",
            "route",
            "rainfall",
            "empty",
        )
        return {key: record.get(key) for key in kept}
    if name == "get_municipality_detail":
        slug = args.get("municipality_slug") or scoped
        if scoped and slug != scoped:
            return {"error": "This account can request detail only for its own municipality."}
        detail = place_detail(slug, threat_id, season, forecast_day) if slug else None
        if not detail:
            return {"error": "Unknown municipality."}
        score = detail.get("score") or {}
        return {
            "name": detail["name"],
            "risk_class": score.get("risk_class"),
            "score": score.get("score"),
            "explanation": score.get("explanation"),
            "confidence": score.get("confidence"),
            "assumption_note": score.get("assumption_note"),
            "factors_used": score.get("factors_used"),
            "factors_skipped": score.get("factors_skipped"),
            "exposure_ha": score.get("exposure_ha"),
            "exposure_source": score.get("exposure_source"),
            "forecast": detail.get("forecast"),
            "terrain": detail.get("terrain"),
            "insight": (detail.get("insight") or {}).get("narrative"),
        }
    return {"error": "Unknown tool."}
