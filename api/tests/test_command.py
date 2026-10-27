from app.command import brief_is_grounded, build_situation


def _place(**overrides):
    base = {
        "slug": "science-city-of-munoz",
        "name": "Science City of Muñoz",
        "risk_class": "high",
        "score": 0.76,
        "priority_points": 92,
        "priority_reasons": ["Risk is rising"],
        "priority_limits": ["Surveillance records are not loaded"],
        "trend": {"available": True, "direction": "rising", "arrow": "↑", "points": 15, "earlier_score": 0.61},
        "horizon_score": 0.82,
        "horizon_class": "very_high",
        "factors_used": [
            {"id": "humidity", "label": "Forecast relative humidity", "partial": 0.9, "assumed": False},
            {"id": "temperature", "label": "Forecast temperature", "partial": 0.8, "assumed": False},
        ],
        "factors_skipped": [{"id": "crop_stage", "label": "Crop stage"}],
        "hotspot_kind": "none",
        "hotspot_sentence": "",
        "exposure_ha": None,
        "note_count": 0,
        "confidence": "moderate",
    }
    base.update(overrides)
    return base


def _context(**overrides):
    places = overrides.pop(
        "places",
        [
            _place(),
            _place(
                slug="gapan",
                name="Gapan",
                risk_class="moderate",
                score=0.52,
                priority_points=64,
                trend={"available": True, "direction": "rising", "arrow": "↑", "points": 11, "earlier_score": 0.41},
                horizon_score=0.68,
                horizon_class="high",
                factors_used=[{"id": "humidity", "label": "Forecast relative humidity", "partial": 0.7, "assumed": False}],
            ),
            _place(
                slug="talavera",
                name="Talavera",
                risk_class="high",
                score=0.78,
                priority_points=78,
                priority_reasons=["Exposed rice area is loaded"],
                trend={"available": True, "direction": "stable", "arrow": "→", "points": 1, "earlier_score": 0.77},
                horizon_score=0.85,
                horizon_class="very_high",
                factors_used=[{"id": "temperature", "label": "Forecast temperature", "partial": 0.4, "assumed": False}],
            ),
            _place(
                slug="guimba",
                name="Guimba",
                risk_class="low",
                score=0.30,
                priority_points=40,
                priority_reasons=[],
                priority_limits=[],
                trend={"available": True, "direction": "stable", "arrow": "→", "points": 0, "earlier_score": 0.30},
                horizon_score=0.48,
                horizon_class="moderate",
                factors_used=[],
                factors_skipped=[],
            ),
        ],
    )
    base = {
        "threat_id": "rice_blast",
        "threat_name": "Rice blast",
        "threat_confidence": "moderate",
        "rule_factor_ids": ["leaf_wetness", "temperature", "humidity", "recent_rain", "forecast_rain", "crop_stage"],
        "season": "wet",
        "forecast_day": 0,
        "horizon_day": 3,
        "horizon_hours": 72,
        "role": "provincial",
        "scope_label": "Nueva Ecija",
        "scope_level": "municipalities",
        "updated_at": "2026-10-26T00:42:00+00:00",
        "forecast_date": "2026-10-26",
        "weather_today": {"temp_c": 29, "rh_pct": 84, "rain_mm": 12, "wind_speed_kmh": 10, "hours_rh90": 4},
        "weather_ahead": {"temp_c": 29.2, "rh_pct": 91, "rain_mm": 16.2, "wind_speed_kmh": 22, "hours_rh90": 8},
        "north_rain": None,
        "datasets": [
            {"dataset": "open_meteo", "state": "loaded", "detail": "Forecast cached."},
            {"dataset": "rice_mask", "state": "missing", "detail": "No rice file."},
            {"dataset": "satellite", "state": "missing", "detail": "No satellite file."},
            {"dataset": "occurrences", "state": "missing", "detail": "No surveillance file."},
        ],
        "planting_dates": 0,
        "rice_places": 0,
        "satellite_places": 0,
        "occurrence_rows": 0,
        "clusters": [{"names": ["Science City of Muñoz", "Talavera"], "size": 2, "zone": True}],
        "class_delta": {"comparable": False, "current_high": 2, "previous_high": None},
        "new_notes": 0,
        "places": places,
    }
    base.update(overrides)
    return base


def test_actions_follow_the_record_not_one_verb():
    record = build_situation(_context())
    kinds = {item["slug"]: item["type"] for item in record["actions"] if item.get("slug")}
    assert kinds["science-city-of-munoz"] == "field_validation"
    assert kinds["gapan"] == "monitor"
    assert kinds["talavera"] == "review"
    assert kinds["guimba"] == "prepare"
    gaps = [item["id"] for item in record["actions"] if item["type"] == "data_required"]
    assert "data:crop-stage" in gaps
    assert "data:rice-area" in gaps


def test_brief_keeps_hazard_and_priority_apart():
    record = build_situation(_context())
    text = record["brief"]["text"].lower()
    assert "science city of muñoz" in text
    assert "inspection priority" in text
    assert "hazard score" in text
    assert "not the hazard score" in text
    assert "does not mean the pest or disease is present" in text
    assert "bacterial" not in text
    munoz = record["priorities"][0]
    assert munoz["hazard_points"] == 76
    assert munoz["priority_points"] == 92
    priority = next(item for item in record["situation"]["indicators"] if item["id"] == "priority")
    assert priority["value"] == 1
    assert priority["detail"].startswith("Top inspection-priority band")
    assert "at least 70" in priority["detail"]
    summary = record["situation"]["summary"]
    assert "1 municipality is in the top inspection-priority band" in summary
    assert "within 5 points of the highest, and at least 70" in summary
    assert "2 municipalities have a rising hazard score" in summary
    assert record["situation"]["band"]["unit"] == "municipality"
    assert record["situation"]["band"]["count"] == 1
    assert "not the hazard score" in munoz["priority_note"].lower()


def test_weather_impact_uses_only_rule_inputs():
    record = build_situation(_context())
    impact = record["weather"]["impact"].lower()
    assert "humidity" in impact
    assert "rainfall" in impact
    assert "leaf wetness" in impact
    assert "wind" not in impact
    assert "bacterial" not in impact
    labels = [item["label"] for item in record["why_now"]["signals"]]
    assert "Wind" not in labels
    assert "Rice canopy" in labels
    rain = next(item for item in record["changes"] if item["id"] == "rain")
    assert rain["value"] == "+35%"
    assert not any(item["value"].startswith("+") and item["id"] == "clusters" for item in record["changes"])
    high = next(item for item in record["changes"] if item["id"] == "high-class")
    assert not high["value"].startswith("+")
    assert "not a change" in high["detail"]


def test_horizon_and_windows_are_separate_from_today():
    record = build_situation(_context())
    today = {item["name"] for item in record["today"]}
    upcoming = {item["name"] for item in record["upcoming"]}
    assert "Science City of Muñoz" in today
    assert "Gapan" in today
    assert "Guimba" in upcoming
    assert "Talavera" in upcoming
    assert record["horizon"]["hours"] == 72
    assert record["horizon"]["class_up"] == 4
    assert "4 municipalities are projected to enter a higher risk class" in record["horizon"]["class_up_sentence"]
    assert "at least 3 points higher" in record["horizon"]["forecast_up_sentence"]
    assert any(area["name"] == "Talavera" and area["from_points"] == 78 for area in record["horizon"]["areas"])


def test_guest_cannot_act_and_empty_board_stays_honest():
    guest = build_situation(_context(role="guest"))
    assert guest["scope"]["can_act"] is False
    assert guest["scope"]["can_plan"] is False
    empty = build_situation(_context(places=[], role="provincial"))
    assert "No scores are loaded" in empty["brief"]["text"]
    assert empty["actions"]
    assert all(item["type"] == "data_required" for item in empty["actions"])


def test_rewrite_rejects_a_diagnosis():
    assert brief_is_grounded("Muñoz has inspection priority 92. The hazard score is 76.")
    assert not brief_is_grounded("Rice blast is present in Muñoz.")
    assert not brief_is_grounded("Confirmed outbreak with yield loss of 20 pesos.")
    assert not brief_is_grounded("Rice blast is spreading across Nueva Ecija.")
    assert brief_is_grounded("This does not mean the pest or disease is present.")
