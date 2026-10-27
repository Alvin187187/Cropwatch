from app.layer import BANNED, EMPTY, build_layer, grounded_answer, read_note, review_image_text


def _place(**kwargs):
    base = {
        "slug": "natividad",
        "name": "General Mamerto Natividad",
        "score": 0.74,
        "risk_class": "high",
        "priority_points": 85,
        "trend": {"available": True, "direction": "rising", "points": 38, "earlier_score": 0.36},
        "forecast": [{"offset": 2, "score": 0.82, "risk_class": "very_high", "date": "2026-10-29"}],
        "factors_used": [
            {"id": "humidity", "label": "Relative humidity", "partial": 0.8, "value": 91, "assumed": False},
            {"id": "temperature", "label": "Temperature", "partial": 0.7, "value": 27.5, "assumed": False},
            {"id": "crop_stage", "label": "Crop stage", "partial": None, "value": None, "assumed": False},
        ],
        "weather": {"temp_c": 27.5, "rh_pct": 91, "rain_mm": 4.2},
        "tomorrow": {"rain_mm": 12.0, "date": "2026-10-28"},
        "rice_ha": 1240,
        "harvested_ha": 800,
        "yield_t_ha": 4.2,
        "rice_fraction": 0.62,
        "crop_stage": "The selected threat's crop-stage factor treats this day count as a high-relevance band.",
        "last_note_on": None,
        "history": [
            {"observed_on": "2026-10-24", "score": 0.36, "risk_class": "moderate"},
            {"observed_on": "2026-10-27", "score": 0.74, "risk_class": "high"},
        ],
        "notes": [],
    }
    base.update(kwargs)
    return base


def _context():
    laur = _place(
        slug="laur",
        name="Laur",
        score=0.66,
        risk_class="high",
        priority_points=70,
        trend={"available": True, "direction": "rising", "points": 12, "earlier_score": 0.54},
        forecast=[{"offset": 2, "score": 0.7, "risk_class": "high", "date": "2026-10-29"}],
        factors_used=[{"id": "humidity", "label": "Relative humidity", "partial": 0.8, "value": 90, "assumed": False}],
        rice_ha=900,
        last_note_on="2026-10-20",
    )
    quiet = _place(
        slug="munoz",
        name="Science City of Muñoz",
        score=0.2,
        risk_class="low",
        priority_points=20,
        trend={"available": True, "direction": "stable", "points": 0, "earlier_score": 0.2},
        forecast=[{"offset": 2, "score": 0.2, "risk_class": "low", "date": "2026-10-29"}],
        factors_used=[],
        rice_ha=None,
        harvested_ha=None,
        yield_t_ha=None,
        rice_fraction=None,
        crop_stage=None,
        last_note_on="2026-10-26",
    )
    return {
        "threat_id": "rice_blast",
        "threat_name": "Rice blast",
        "forecast_day": 0,
        "as_of": "2026-10-27",
        "scope_label": "Nueva Ecija",
        "municipality_count": 3,
        "places": [_place(), laur, quiet],
        "edges": [("natividad", "laur")],
        "convergence": [
            {
                "slug": "laur",
                "name": "Laur",
                "threats": [
                    {"name": "Rice blast", "risk_label": "High"},
                    {"name": "Brown planthopper", "risk_label": "High"},
                    {"name": "Rice black bug", "risk_label": "Moderate"},
                ],
            }
        ],
        "province_rice": {"production": {"value": 12000, "unit": "metric tons", "period": "2024"}},
        "route": {
            "stops": [
                {"name": "General Mamerto Natividad", "slug": "natividad"},
                {"name": "Laur", "slug": "laur"},
            ],
            "distance_km": 18.4,
            "graph": "Shared municipal borders.",
        },
    }


def _dump(record: dict) -> str:
    import json

    return json.dumps(record).lower()


def test_attention_is_a_sentence_plus_exact_figures_and_stops_at_five():
    record = build_layer(_context())
    assert record["source"] == "From the situation record."
    assert record["empty"] is None
    assert len(record["attention"]) == 2
    top = record["attention"][0]
    assert top["name"] == "General Mamerto Natividad"
    assert top["signal"] == "Rapidly rising hazard"
    assert "36" not in top["sentence"]
    assert "Hazard 36 to 74." in top["evidence"]
    assert top["action"] == "Field validation is recommended today."
    assert top["urgency"] == "High"
    assert "Crop stage" not in " ".join(top["evidence"])


def test_missing_factor_stays_out_of_the_wording():
    record = build_layer(_context())
    text = _dump(record)
    assert "crop stage was" not in text
    assert "not used" not in text
    assert "favorable range" in record["weather"]["sentence"]
    assert any("Relative humidity 91%" in line for line in record["weather"]["evidence"])
    assert "crop stage" not in record["weather"]["sentence"].lower()


def test_forecast_uses_model_language_and_puts_the_date_in_evidence():
    record = build_layer(_context())
    card = record["forecast"][0]
    assert card["sentence"] == "Conditions are projected to become more favorable to the configured model in about 48 hours."
    assert "Forecast date 29 Oct 2026." in card["evidence"]
    assert "48" not in card["evidence"][0]


def test_emerging_area_uses_neighbors_and_not_outbreak_language():
    record = build_layer(_context())
    area = record["emerging"][0]
    assert area["label"] == "Emerging monitoring area"
    assert area["names"] == ["General Mamerto Natividad", "Laur"]
    assert "adjacent municipalities" in area["sentence"]
    assert "outbreak" not in area["sentence"].lower()


def test_convergence_lists_each_model_then_the_sentence():
    record = build_layer(_context())
    row = record["convergence"][0]
    assert row["evidence"] == [
        "Rice blast: High.",
        "Brown planthopper: High.",
        "Rice black bug: Moderate.",
    ]
    assert row["sentence"] == "Multiple independent threat models currently identify elevated monitoring conditions in Laur."


def test_rice_names_stored_metrics_and_skips_loss():
    record = build_layer(_context())
    text = " ".join(record["rice"]["evidence"])
    assert "Mapped rice area 1,240 ha." in text
    assert "Harvested area 800 ha." in text
    assert "Yield 4.2 metric tons per hectare." in text
    assert "Rice fraction 0.62." in text
    assert "Nueva Ecija production 12,000 metric tons, 2024." in text
    assert "loss" not in text.lower()


def test_empty_record_uses_the_quiet_line():
    record = build_layer(
        {
            "threat_name": "Rice blast",
            "forecast_day": 0,
            "as_of": "2026-10-27",
            "municipality_count": 1,
            "places": [
                _place(
                    score=0.1,
                    risk_class="low",
                    priority_points=10,
                    trend={"available": True, "direction": "stable", "points": 0, "earlier_score": 0.1},
                    forecast=[],
                    factors_used=[],
                )
            ],
        }
    )
    assert record["empty"] == EMPTY
    assert record["attention"] == []
    assert record["brief"]["priorities"]["sentence"] == EMPTY


def test_route_explains_the_stored_order():
    record = build_layer(_context())
    assert record["route"]["sentence"] == "The stored route visits General Mamerto Natividad and Laur."
    assert "Expected travel 18.4 km." in record["route"]["evidence"]
    assert "Stop 1, General Mamerto Natividad, High, inspection priority 85." in record["route"]["evidence"]


def test_copy_does_not_use_forbidden_claims_or_the_word_ai():
    text = _dump(build_layer(_context()))
    for word in BANNED:
        assert word not in text
    assert " ai " not in f" {text} "


def test_questions_are_answered_from_the_record():
    record = build_layer(_context())
    record["rainfall"] = {"sentence": "Rainfall for tomorrow is stored for these municipalities.", "evidence": ["Laur 12 mm on 28 Oct 2026."]}
    worse = grounded_answer("Which municipalities are getting worse for Rice blast?", record)
    assert "General Mamerto Natividad" in worse
    assert worse.endswith("From the situation record.")
    rain = grounded_answer("Officer context: workspace map\nWhat is tomorrow's rainfall?", record)
    assert "Laur 12 mm" in rain
    high = grounded_answer("Which areas are projected to become High?", record)
    assert "in about 48 hours" in high
    gap = grounded_answer("Which high-priority areas have no field note in the last 7 days?", record)
    assert "General Mamerto Natividad" in gap
    rice = grounded_answer("Which high-monitoring municipalities have mapped rice area?", record)
    assert "1,240" in rice
    assert grounded_answer("Hello there", record) is None


def test_note_reader_separates_observations_from_missing_fields():
    reading = read_note("Leaves look unusual and there are several insects around the crop.")
    assert reading["observations"] == [
        "Noted: leaves look unusual.",
        "Noted: several insects around the crop.",
    ]
    assert reading["missing"] == ["Crop stage", "Approximate extent"]
    assert reading["suggested"] == ["Attach a field photo."]
    assert "model result" in reading["boundary"]


def test_image_result_never_becomes_a_diagnosis():
    safe = review_image_text(
        {
            "quality": "usable",
            "indicators": ["Pale patches on a leaf", "Confirmed rice blast infection"],
            "questions": ["How many leaves look like this?"],
        }
    )
    assert safe["sentence"] == "Possible visual indicators detected. Field validation recommended."
    assert safe["indicators"] == ["Pale patches on a leaf"]
    unclear = review_image_text({"quality": "unclear", "indicators": ["A lesion"]})
    assert "not clear enough" in unclear["sentence"]
    assert unclear["indicators"] == []
