from app.algorithms import connected_components, dijkstra, inspection_route, rank_places
from app.paths import rules_dir
from app.scoring import (
    apply_infection_gate,
    factor_score,
    lapse_adjust,
    leaf_wetness_by_day,
    load_rules,
    score_place,
    storm_partial,
)

GATE = {"min_hours": 6, "rh_min": 90, "temp_min": 20, "temp_max": 28}

RULE = {
    "cuts": {"moderate": 0.35, "high": 0.55, "very_high": 0.72},
    "season_score": {"wet": 1.0, "dry": 0.2},
    "factors": [
        {
            "id": "temperature",
            "label": "Temperature",
            "required": True,
            "weight": 0.5,
            "field": "temp_c",
            "mode": "band",
            "favorable": {"min": 24, "max": 28},
            "soft": 4,
        },
        {
            "id": "humidity",
            "label": "Humidity",
            "required": True,
            "weight": 0.5,
            "field": "rh_pct",
            "mode": "high",
            "favorable": {"min": 80, "max": 100},
        },
        {
            "id": "ndvi",
            "label": "NDVI",
            "required": False,
            "weight": 0.5,
            "field": "ndvi",
            "mode": "high",
            "favorable": {"min": 0.4, "max": 0.8},
        },
    ],
}


def test_band_and_high_modes():
    assert factor_score(26, RULE["factors"][0]) == 1
    assert factor_score(20, RULE["factors"][0]) == 0
    assert factor_score(90, RULE["factors"][1]) == 0.5


def test_required_missing_is_insufficient():
    result = score_place(RULE, {"rh_pct": 90}, "wet")
    assert result["risk_class"] == "insufficient_data"
    assert result["score"] is None


def test_optional_missing_is_named_and_renormalized():
    result = score_place(RULE, {"temp_c": 26, "rh_pct": 100, "ndvi": None}, "wet")
    assert result["risk_class"] == "very_high"
    assert result["score"] == 1
    assert any(item["id"] == "ndvi" for item in result["factors_skipped"])
    assert "Not used: NDVI" in result["explanation"]


def test_leaf_wetness_keeps_a_run_that_crosses_midnight():
    hours = [
        {"date": "2026-10-20", "temp_c": 24, "rh_pct": 95},
        {"date": "2026-10-20", "temp_c": 24, "rh_pct": 95},
        {"date": "2026-10-21", "temp_c": 24, "rh_pct": 92},
        {"date": "2026-10-21", "temp_c": 24, "rh_pct": 92},
        {"date": "2026-10-21", "temp_c": 33, "rh_pct": 95},
    ]
    by_day = leaf_wetness_by_day(hours, GATE)
    assert by_day["2026-10-20"] == 4
    assert by_day["2026-10-21"] == 4


def test_blast_gate_blocks_a_high_score_without_six_wet_hours():
    gated = apply_infection_gate(
        {
            "score": 0.8,
            "risk_class": "very_high",
            "factors_used": [],
            "factors_skipped": [],
            "explanation": "Favorable conditions.",
        },
        4,
        {"gate": GATE},
    )
    assert gated["risk_class"] == "low"
    assert gated["score"] == 0


def test_blast_gate_stays_open_when_the_wet_run_is_long_enough():
    gated = apply_infection_gate(
        {
            "score": 0.62,
            "risk_class": "high",
            "factors_used": [],
            "factors_skipped": [],
            "explanation": "Favorable conditions.",
        },
        7,
        {"gate": GATE},
    )
    assert gated["risk_class"] == "high"
    assert gated["score"] == 0.62


def test_low_canopy_zeroes_exposure():
    gated = apply_infection_gate(
        {
            "score": 0.7,
            "risk_class": "high",
            "factors_used": [],
            "factors_skipped": [],
            "explanation": "Favorable conditions.",
        },
        8,
        {"gate": GATE, "exposure_ndvi_min": 0.2},
        ndvi=0.1,
    )
    assert gated["risk_class"] == "low"
    assert gated["score"] == 0


def test_lapse_rate_cools_higher_ground():
    assert abs(lapse_adjust(25, 100, 200) - 24.35) < 1e-9


def _rules():
    return {rule["id"]: rule for rule in load_rules(rules_dir())}


def _spec(rule, factor_id):
    return next(item for item in rule["factors"] if item["id"] == factor_id)


def test_temperature_bands_do_not_share_one_scale():
    rules = _rules()
    reading = 27.2
    blast = factor_score(reading, _spec(rules["rice_blast"], "temperature"))
    blight = factor_score(reading, _spec(rules["bacterial_leaf_blight"], "temperature"))
    hopper = factor_score(reading, _spec(rules["brown_planthopper"], "temperature"))
    assert blast < 1
    assert blight < 1
    assert len({round(blast, 3), round(blight, 3), round(hopper, 3)}) > 1


def test_each_rule_uses_its_own_weights():
    for rule in _rules().values():
        assert abs(sum(item["weight"] for item in rule["factors"]) - 1) < 1e-9
    blast_ids = {item["id"] for item in _rules()["rice_blast"]["factors"]}
    assert "spread" not in blast_ids
    assert "soil_moisture" not in blast_ids
    assert "climate" not in blast_ids
    assert "crop_stage" in blast_ids


def test_heavy_rain_lowers_planthopper_and_storm_raises_blight():
    rules = _rules()
    rain = _spec(rules["brown_planthopper"], "forecast_rain")
    assert factor_score(80, rain) < factor_score(8, rain)
    assert storm_partial(10, None, False) < storm_partial(10, None, True)
    calm = score_place(
        rules["bacterial_leaf_blight"],
        {"temp_c": 29, "rh_pct": 85, "rain_mm": 2, "wind_speed_kmh": 10, "storm_active": 0},
        "wet",
    )
    storm = score_place(
        rules["bacterial_leaf_blight"],
        {"temp_c": 29, "rh_pct": 85, "rain_mm": 2, "wind_speed_kmh": 45, "storm_active": 1},
        "wet",
    )
    assert storm["score"] > calm["score"]


def test_black_bug_is_low_confidence_and_assumptions_are_named():
    result = score_place(
        _rules()["rice_black_bug"],
        {"temp_c": 27, "rh_pct": 85, "rain_sum_7d": 40, "soil_moisture": 0.3, "climate_score": 1},
        "wet",
    )
    assert result["confidence"] == "low"
    assert "Low confidence" in result["explanation"]
    assumed = score_place(
        {
            "cuts": {"moderate": 0.35, "high": 0.55, "very_high": 0.72},
            "factors": [
                {
                    "id": "real",
                    "label": "Measured",
                    "weight": 0.2,
                    "field": "x",
                    "mode": "high",
                    "favorable": {"min": 0, "max": 1},
                },
                {
                    "id": "guess",
                    "label": "Guess",
                    "assumed_label": "Guess (regional assumption)",
                    "weight": 0.8,
                    "field": "y",
                    "mode": "high",
                    "favorable": {"min": 0, "max": 1},
                    "assumed_value": 1,
                },
            ],
        },
        {"x": 1},
        "wet",
    )
    assert assumed["confidence"] == "low"
    assert assumed["assumption_note"].startswith("This score is based mostly on assumptions")


def test_priority_queue_orders_risk_then_hectares():
    ranked = rank_places(
        [
            {"id": 1, "name": "Aliaga", "risk_class": "high", "exposure_ha": 10},
            {"id": 2, "name": "Guimba", "risk_class": "very_high", "exposure_ha": 5},
            {"id": 3, "name": "Licab", "risk_class": "very_high", "exposure_ha": 40},
            {"id": 4, "name": "Laur", "risk_class": "very_high", "exposure_ha": None},
        ]
    )
    assert [row["name"] for row in ranked] == ["Licab", "Guimba", "Laur", "Aliaga"]


def test_clusters_and_dijkstra():
    components = connected_components([1, 2, 3, 9], [(1, 2), (2, 3), (8, 9)])
    assert components[0] == [1, 2, 3]
    assert [9] in components
    path, cost = dijkstra(1, 3, {1: [(2, 2.0)], 2: [(1, 2.0), (3, 4.0)], 3: [(2, 4.0)]})
    assert path == [1, 2, 3]
    assert cost == 6
    route = inspection_route([1, 3], {1: [(2, 2.0)], 2: [(1, 2.0), (3, 4.0)], 3: [(2, 4.0)]})
    assert route["path"][0] == 1
    assert route["path"][-1] == 3
