from datetime import date

from app.insights import (
    driver_lines,
    hotspot_reading,
    inspection_priority,
    narrative,
    trend_from_series,
    weather_anomaly,
)


def test_trend_rising_and_week():
    series = [
        {"observed_on": date(2026, 10, 11), "score": 0.52},
        {"observed_on": date(2026, 10, 15), "score": 0.61},
    ]
    trend = trend_from_series(0.79, date(2026, 10, 18), series)
    assert trend["available"] is True
    assert trend["direction"] == "rising"
    assert trend["arrow"] == "↑"
    assert trend["points"] == 18
    assert trend["earlier_score"] == 0.61
    assert trend["week_delta"] == 0.27


def test_trend_stable_and_missing():
    series = [{"observed_on": date(2026, 10, 15), "score": 0.70}]
    trend = trend_from_series(0.71, date(2026, 10, 18), series)
    assert trend["direction"] == "stable"
    assert trend["arrow"] == "→"
    empty = trend_from_series(0.71, date(2026, 10, 18), [])
    assert empty["available"] is False


def test_drivers_are_contribution_points():
    lines = driver_lines(
        [
            {"id": "humidity", "label": "Forecast relative humidity", "contribution": 0.21, "partial": 0.9},
            {"id": "temperature", "label": "Forecast temperature", "contribution": 0.20, "partial": 0.8},
            {"id": "rain", "label": "Recent rainfall", "contribution": 0.11, "partial": 0.4},
        ]
    )
    assert lines["items"][0]["points"] == 21
    assert "humidity" in lines["sentence"]
    assert "present" not in lines["sentence"]


def test_anomaly_refuses_a_single_year():
    result = weather_anomaly(
        {"observed_on": date(2026, 10, 18), "rh_pct": 87, "rain_sum_7d": 92},
        [{"observed_on": date(2026, 10, day), "rh_pct": 80, "rain_mm": 5} for day in range(1, 17)],
    )
    assert result["available"] is False
    assert "multi-year" in result["sentence"]


def test_anomaly_uses_earlier_years():
    history = []
    for year in (2023, 2024, 2025):
        for day in range(1, 21):
            history.append({"observed_on": date(year, 10, day), "rh_pct": 78, "rain_mm": 4})
    result = weather_anomaly(
        {"observed_on": date(2026, 10, 18), "rh_pct": 87, "rain_sum_7d": 56},
        history,
    )
    assert result["available"] is True
    assert "+9" in result["sentence"]
    assert "2.0×" in result["sentence"]


def test_hotspot_cluster_is_not_mixed_into_a_formula_here():
    reading = hotspot_reading(
        "Guimba",
        "high",
        "brown planthopper",
        [
            {"name": "Muñoz", "risk_class": "high", "score": 0.8},
            {"name": "Talavera", "risk_class": "high", "score": 0.77},
        ],
    )
    assert reading["kind"] == "cluster"
    assert reading["neighbor_risk"] == 0.785
    assert "not added to the hazard formula" in reading["sentence"]
    isolated = hotspot_reading(
        "Bongabon",
        "high",
        "rice blast",
        [{"name": "Laur", "risk_class": "low", "score": 0.2}],
    )
    assert isolated["kind"] == "isolated"


def test_priority_drops_missing_parts():
    full = inspection_priority(
        {"risk": 0.8, "trend": "rising", "exposure_share": 1, "hotspot": "cluster", "occurrence": True}
    )
    partial = inspection_priority(
        {"risk": 0.8, "trend": "rising", "exposure_share": None, "hotspot": "cluster", "occurrence": None}
    )
    assert full["points"] > partial["points"]
    assert any("not loaded" in line for line in partial["limits"])
    assert "hazard score" in partial["sentence"]
    text = narrative(
        "Guimba",
        "Brown planthopper",
        {"score": 0.78, "risk_class": "high"},
        {"available": True, "arrow": "↑", "direction": "rising", "sentence": "Rising."},
        {"sentence": "Why this class: humidity."},
        {"sentence": "Baseline missing."},
        {"sentence": "Spatial hotspot."},
        partial,
        "Exposed rice area is not loaded.",
        [],
    )
    assert "does not mean the pest or disease is present" in text
    assert "detected rice" not in text.lower()
