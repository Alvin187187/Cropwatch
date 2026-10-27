from app.rice import build_rice, rice_is_grounded

RULE = {
    "id": "rice_blast",
    "name": "Rice blast",
    "season_role": "none",
    "factors": [
        {
            "id": "crop_stage",
            "stages": [
                {"max_day": 35, "score": 1.0},
                {"max_day": 55, "score": 0.45},
                {"max_day": 90, "score": 1.0},
                {"max_day": 120, "score": 0.25},
            ],
        }
    ],
}


def _place(**overrides):
    row = {
        "slug": "laur",
        "name": "Laur",
        "score": 0.71,
        "risk_class": "high",
        "priority_points": 83,
        "trend": {"direction": "stable", "points": 2, "arrow": "→", "available": True, "earlier_score": 0.69},
        "horizon_score": 0.74,
        "horizon_class": "high",
        "rice_ha": 1850,
        "rice_source": "PRiSM",
        "planting_date": None,
        "days_after_planting": None,
        "factors_used": [{"id": "humidity", "label": "Humidity", "partial": 0.8, "assumed": False}],
        "factors_skipped": [],
    }
    row.update(overrides)
    return row


def _context(places):
    return {
        "role": "provincial",
        "scope_label": "Nueva Ecija",
        "season": "wet",
        "forecast_day": 0,
        "forecast_date": "2026-10-26",
        "hours": 72,
        "hours_available": True,
        "threat": {"id": "rice_blast", "name": "Rice blast", "rule": RULE},
        "places": places,
        "stats": [
            {"metric": "farmers", "value": 108064, "unit": "farmers", "source_name": "Ricelytics", "period": "June 2026", "retrieved_on": "2026-10-18"},
            {"metric": "production", "value": 1067752, "unit": "metric tons", "source_name": "Ricelytics", "period": "Semester 1 2026", "retrieved_on": "2026-10-18"},
            {"metric": "harvested_area", "value": 165913, "unit": "hectares", "source_name": "Ricelytics", "period": "Semester 1 2026", "retrieved_on": "2026-10-18"},
            {"metric": "yield", "value": 6.44, "unit": "metric tons per hectare", "source_name": "Ricelytics", "period": "Semester 1 2026", "retrieved_on": "2026-10-18"},
        ],
        "weather": {"temp_c": 27.6, "rh_pct": 76.6, "rain_mm": 0.3, "soil_moisture": 0.198, "soil_places": 2, "places": 2, "source": "Open-Meteo forecast", "forecast_date": "2026-10-26"},
        "satellite": {"observations": 0},
        "drought_rows": 0,
        "enso": {"anomaly_c": 1.39, "label": "El Nino", "season": "MJJ 2026"},
        "season_modifiers": ["Rice black bug", "Brown planthopper"],
        "drivers": ["Humidity"],
        "surveillance": "Missing",
    }


def test_exposure_uses_rice_area_and_does_not_scale_the_hazard():
    places = [
        _place(
            slug="general-mamerto-natividad",
            name="General Mamerto Natividad",
            score=0.74,
            priority_points=85,
            trend={"direction": "rising", "points": 38, "arrow": "↑", "available": True, "earlier_score": 0.36},
            rice_ha=2100,
            days_after_planting=50,
        ),
        _place(rice_ha=1850, risk_class="moderate", score=0.4),
        _place(slug="gabaldon", name="Gabaldon", rice_ha=None, rice_source=None),
    ]
    report = build_rice(_context(places))
    assert report["damage_ha"] is None
    assert report["loss_estimate"] is None
    assert report["rice_health_score"] is None
    assert report["exposure"]["hectares"] == 2100
    assert "not estimated crop damage" in report["exposure"]["sentence"]
    assert "not calculated from hazard scores" in report["summary_text"]
    assert "not a count of farmers at risk" in report["summary_text"]
    natividad = report["profiles"][0]
    assert natividad["name"] == "General Mamerto Natividad"
    assert natividad["crop_stage"]["approaching"] is True
    assert natividad["crop_stage"]["relevant"] is False
    assert "Heading" not in natividad["crop_stage"]["sentence"]
    assert report["crop"]["approaching"][0]["name"] == "General Mamerto Natividad"
    assert report["climate"]["used_by_selected"] is False
    assert "Not used by Rice blast scoring." in report["climate"]["threat_sentence"]
    assert report["climate"]["modifier_threats"] == ["Rice black bug", "Brown planthopper"]
    assert report["conditions"]["satellite"]["available"] is False
    assert "not shown" in report["conditions"]["satellite"]["note"]
    production = next(row for row in report["situation"]["metrics"] if row["id"] == "production")
    assert production["period"] == "Semester 1 2026"
    assert production["source"] == "Ricelytics"


def test_missing_rice_area_is_not_invented():
    report = build_rice(_context([_place(rice_ha=None, rice_source=None, days_after_planting=None)]))
    assert report["exposure"]["available"] is False
    assert report["exposure"]["hectares"] is None
    assert "not taken from the hazard score" in report["exposure"]["sentence"]
    assert report["profiles"][0]["rice_label"] == "Not loaded"
    assert report["crop"]["available"] is False
    assert "Crop stage unavailable" in report["crop"]["sentence"]


def test_rice_narration_rejects_damage_and_farmer_risk():
    assert rice_is_grounded("Harvested area is 165,913 ha for Semester 1 2026.")
    assert not rice_is_grounded("High risk means 1,480 hectares of damaged rice.")
    assert not rice_is_grounded("1,240 farmers are at risk.")
    assert not rice_is_grounded("Rice blast caused the NDVI decline.")
