from app.map_intel import (
    change_bucket,
    compare_forecast,
    factor_rows,
    factor_status,
    horizon_sentence,
    why_line,
    why_now,
)


CUTS = {"moderate": 0.40, "high": 0.60, "very_high": 0.80}


def test_horizon_counts_are_municipalities_from_stored_scores():
    rows = {
        "a": {
            0: {"name": "A", "score": 0.40, "risk_class": "moderate"},
            3: {"name": "A", "score": 0.62, "risk_class": "high"},
        },
        "b": {
            0: {"name": "B", "score": 0.70, "risk_class": "high"},
            3: {"name": "B", "score": 0.71, "risk_class": "high"},
        },
    }
    compared = compare_forecast(rows, 0, 3)
    assert [item["name"] for item in compared["increased"]] == ["A"]
    assert [item["name"] for item in compared["class_up"]] == ["A"]
    sentence = horizon_sentence(compared["increased"], compared["class_up"], 72, True)
    assert sentence.startswith("1 municipality has a hazard score at least 3 points higher")
    assert "1 municipality moves into a higher risk class" in sentence
    assert "stored municipality scores" in sentence


def test_change_bucket_marks_a_new_high_without_calling_it_an_outbreak():
    trend = {"available": True, "direction": "rising", "earlier_score": 0.48}
    assert change_bucket("high", trend, CUTS) == "new_high"
    assert change_bucket("high", {"available": True, "direction": "rising", "earlier_score": 0.66}, CUTS) == "increased"
    assert change_bucket("moderate", {"available": False}, CUTS) == "unknown"


def test_factor_status_uses_only_saved_factors():
    score = {
        "risk_class": "high",
        "factors_used": [
            {"id": "humidity", "label": "Relative humidity", "partial": 0.8, "assumed": False},
            {"id": "temperature", "label": "Temperature", "partial": 0.5, "assumed": False},
            {"id": "recent_rain", "label": "Recent rain", "partial": 0.2, "assumed": False},
        ],
        "factors_skipped": [{"id": "crop_stage", "label": "Crop stage"}],
    }
    rows = {item["id"]: item["status"] for item in factor_rows(score)}
    assert rows == {
        "humidity": "Favorable",
        "temperature": "Neutral",
        "recent_rain": "Low",
        "crop_stage": "Not available",
    }
    assert factor_status(0.9, True) == "Estimated"
    text = why_line("Rice Blast", score).lower()
    assert "rice blast rules identify favorable relative humidity" in text
    assert "does not mean the pest or disease is present" in text
    assert "spreading" not in text
    now = why_now({"available": True, "direction": "rising", "earlier_score": 0.48}, {"score": 0.74, **score})
    assert now["from_points"] == 48
    assert now["to_points"] == 74
    assert "rule-based hazard score" in now["sentence"]
    assert "not stored" in now["note"]


def test_last_forecast_day_does_not_invent_a_later_step():
    assert "last stored forecast day" in horizon_sentence([], [], 0, False)
