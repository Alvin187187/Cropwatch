from app.analytics import analytics_is_grounded, build_report, driver_counts, transition_matrix


def _place(slug, name, score, risk, horizon, horizon_class, trend_points, direction, factors, priority):
    return {
        "slug": slug,
        "name": name,
        "score": score,
        "risk_class": risk,
        "horizon_score": horizon,
        "horizon_class": horizon_class,
        "trend": {
            "available": True,
            "direction": direction,
            "arrow": "↑" if direction == "rising" else "→",
            "points": trend_points,
            "earlier_score": score - (trend_points / 100),
            "days": 3,
        },
        "priority_points": priority,
        "exposure_ha": 10,
        "confidence": "moderate",
        "factors_used": factors,
        "factors_skipped": [{"id": "crop_stage", "label": "Crop stage"}],
        "history": [{"label": "Earlier", "score": score - (trend_points / 100)}],
        "forecast_days": {0: score, 1: horizon, 2: horizon, 3: horizon},
    }


def _context():
    blast = {
        "id": "rice_blast",
        "name": "Rice blast",
        "factor_ids": ["humidity", "temperature", "recent_rain", "crop_stage"],
        "places": [
            _place(
                "natividad",
                "General Mamerto Natividad",
                0.74,
                "high",
                0.82,
                "very_high",
                38,
                "rising",
                [
                    {"id": "humidity", "label": "Relative humidity", "partial": 0.8, "assumed": False},
                    {"id": "temperature", "label": "Temperature", "partial": 0.7, "assumed": False},
                    {"id": "recent_rain", "label": "Recent rainfall", "partial": 0.2, "assumed": False},
                ],
                85,
            ),
            _place(
                "munoz",
                "Science City of Muñoz",
                0.51,
                "moderate",
                0.50,
                "moderate",
                2,
                "stable",
                [{"id": "humidity", "label": "Relative humidity", "partial": 0.7, "assumed": False}],
                60,
            ),
        ],
    }
    bug = {
        "id": "rice_black_bug",
        "name": "Rice black bug",
        "factor_ids": ["humidity"],
        "places": [
            _place("natividad", "General Mamerto Natividad", 0.66, "high", 0.66, "high", 1, "stable", [], 70),
            _place("munoz", "Science City of Muñoz", 0.20, "low", 0.20, "low", 0, "stable", [], 20),
        ],
    }
    return {
        "threat_id": "rice_blast",
        "season": "wet",
        "forecast_day": 0,
        "hours": 72,
        "hours_available": True,
        "role": "provincial",
        "scope_label": "Nueva Ecija",
        "threats": [blast, bug],
        "clusters": [{"id": "01", "label": "Risk cluster 01", "names": ["General Mamerto Natividad"], "sentence": "Not an outbreak."}],
        "datasets": [],
        "counts": {"weather": 2, "rice": 0, "satellite": 0, "occurrences": 0, "municipalities": 2},
        "planting_dates": 0,
    }


def test_single_threat_keeps_hazard_and_priority_apart_and_names_only_favorable_factors():
    report = build_report(_context())
    assert report["combined_score"] is None
    text = report["summary_text"].lower()
    assert "1 municipality is in the top inspection-priority band" in text
    assert "1 municipality has a rising hazard score" in text
    assert "fastest-rising hazard score" in text
    assert "spreading" not in text
    labels = [item["label"] for item in report["drivers"]]
    assert "Relative humidity" in labels
    assert "Temperature" in labels
    assert "Recent rainfall" not in labels
    natividad = report["ranking"][0]
    assert natividad["hazard_points"] == 74
    assert natividad["priority_points"] == 85
    assert report["transitions"]["matrix"]["high"]["very_high"] == 1
    assert any(item["from_label"] == "High" and item["to_label"] == "Very High" for item in report["transitions"]["notable"])
    assert report["outlook"]["increasing"][0]["name"] == "General Mamerto Natividad"
    assert report["outlook"]["increasing"][0]["from_points"] == 74
    assert report["outlook"]["increasing"][0]["to_points"] == 82
    assert "which rule factor changed" in report["chart"]["note"].lower()
    assert report["convergence"][0]["name"] == "General Mamerto Natividad"
    assert "does not mean" in report["convergence"][0]["sentence"]


def test_all_threats_does_not_build_a_combined_score():
    context = _context()
    context["threat_id"] = None
    report = build_report(context)
    assert report["mode"] == "all"
    assert report["combined_score"] is None
    assert "no combined disease score" in report["summary_text"].lower()
    assert {item["id"] for item in report["threats"]} == {"rice_blast", "rice_black_bug"}
    assert report["ranking"] == []


def test_transition_and_driver_helpers_do_not_invent_factors():
    matrix = transition_matrix([("moderate", "high"), ("moderate", "moderate"), ("insufficient_data", "high")])
    assert matrix["matrix"]["moderate"]["high"] == 1
    assert matrix["excluded"] == 1
    rows = driver_counts(
        [
            {
                "factors_used": [{"id": "humidity", "label": "Relative humidity", "partial": 0.9, "assumed": False}],
                "factors_skipped": [{"id": "leaf_wetness", "label": "Leaf wetness"}],
            }
        ]
    )
    assert [item["label"] for item in rows] == ["Relative humidity"]


def test_analytics_narration_rejects_a_diagnosis():
    assert analytics_is_grounded("Rice blast hazard is rising in 1 municipality. This does not mean the pest or disease is present.")
    assert not analytics_is_grounded("Rice blast is spreading across Nueva Ecija.")
    assert not analytics_is_grounded("The disease score is 91 with a 40 percent chance.")
