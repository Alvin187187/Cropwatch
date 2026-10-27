"""Explainable risk scores. Missing optional factors are skipped, not invented.

Each threat has its own curves. A temperature that is ideal for one pest can
be ordinary or poor for another. Thresholds are unchecked starting points.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CLASS_LABELS = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "very_high": "Very High",
    "insufficient_data": "Insufficient data",
}

DISCLAIMER = "Thresholds are unchecked starting points, not PhilRice or IRRI guidance."


def load_rules(rules_dir: Path) -> list[dict]:
    rules = []
    for path in sorted(rules_dir.glob("*.yaml")):
        rule = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule["_path"] = str(path)
        rules.append(rule)
    return rules


def factor_score(value: float, spec: dict) -> float:
    mode = spec.get("mode", "band")
    if mode == "peak":
        return _peak(value, spec)
    if mode == "stage":
        return _stage(value, spec)
    if mode == "light_rain":
        return _light_rain(value, spec)
    if mode == "heavy_penalty":
        return _heavy_penalty(value, spec)
    favorable = spec["favorable"]
    low = float(favorable["min"])
    high = float(favorable["max"])
    if mode == "high":
        if value <= low:
            return 0.0
        if value >= high:
            return 1.0
        return (value - low) / (high - low)
    if mode == "low":
        if value <= low:
            return 1.0
        if value >= high:
            return 0.0
        return (high - value) / (high - low)
    soft = float(spec.get("soft", 0))
    if low <= value <= high:
        return 1.0
    if value < low:
        if soft <= 0:
            return 0.0
        return max(0.0, 1 - (low - value) / soft)
    if soft <= 0:
        return 0.0
    return max(0.0, 1 - (value - high) / soft)


def lapse_adjust(temp: float, model_elevation: float, surface_elevation: float) -> float:
    """Shift a model temperature by 0.65 C per 100 m of elevation difference."""
    return float(temp) - 0.0065 * (float(surface_elevation) - float(model_elevation))


def leaf_wetness_by_day(hours: list[dict], gate: dict) -> dict[str, int]:
    """Longest qualifying wet run that touches each date, including runs past midnight."""
    by_day: dict[str, int] = {}
    run = 0
    run_dates: list[str] = []

    def close() -> None:
        nonlocal run, run_dates
        if run and run_dates:
            for day in set(run_dates):
                by_day[day] = max(by_day.get(day, 0), run)
        run = 0
        run_dates = []

    for hour in hours:
        if _hour_is_wet(hour, gate):
            run += 1
            run_dates.append(hour["date"])
        else:
            close()
    close()
    return by_day


def apply_infection_gate(result: dict, wet_hours, rule: dict, ndvi=None) -> dict:
    """Hold rice blast at Low when the wet run is too short or the canopy is not rice."""
    reasons = []
    gate = rule.get("gate") or {}
    minimum = gate.get("min_hours")
    if minimum is not None and wet_hours is not None and float(wet_hours) < float(minimum):
        reasons.append(
            f"Leaf wetness ran {float(wet_hours):g} hours, short of the {float(minimum):g} hours rice blast needs, so the class is held at Low."
        )
    ndvi_min = rule.get("exposure_ndvi_min")
    if ndvi_min is not None and ndvi is not None and float(ndvi) < float(ndvi_min):
        reasons.append("Canopy greenness is below the rice threshold, so the class is held at Low.")
    if not reasons:
        return result
    gated = dict(result)
    gated["score"] = 0
    gated["risk_class"] = "low"
    gated["explanation"] = " ".join(reasons) + " " + (result.get("explanation") or "")
    return gated


def _hour_is_wet(hour: dict, gate: dict) -> bool:
    temp = hour.get("temp_c")
    rh = hour.get("rh_pct")
    if temp is None or rh is None:
        return False
    return float(rh) >= float(gate["rh_min"]) and float(gate["temp_min"]) <= float(temp) <= float(gate["temp_max"])


def storm_partial(wind, gust, active) -> float:
    """Strong wind raises bacterial leaf blight. A recent storm keeps it raised."""
    speed = 0.0
    if wind is not None:
        speed = max(speed, float(wind))
    if gust is not None:
        speed = max(speed, float(gust))
    if speed <= 12:
        base = 0.0
    elif speed >= 40:
        base = 1.0
    else:
        base = (speed - 12) / 28
    if active:
        base = max(base, 0.85)
    return base


def leaf_wetness_hours(hours_rh90, rh_pct) -> tuple[float | None, bool]:
    """Hours at or above 90% humidity. Daily mean humidity is only a stand-in."""
    if hours_rh90 is not None:
        return float(hours_rh90), False
    if rh_pct is None:
        return None, False
    rh = float(rh_pct)
    if rh < 78:
        return 0.0, True
    return min(14.0, (rh - 78) * 0.7), True


def climate_score(season: str, oni: float | None, threat_id: str) -> float:
    """Wet or dry season, plus a small national El Niño nudge."""
    dry = 0.35 if threat_id == "rice_black_bug" else 0.5
    base = 1.0 if season == "wet" else dry
    if oni is None:
        return base
    nudge = max(-0.12, min(0.12, -0.06 * float(oni)))
    return round(max(0.0, min(1.0, base + nudge)), 3)


def score_place(rule: dict, factors: dict, season: str) -> dict:
    """Return a class, the fired factors, and the factors that were skipped."""
    values = dict(factors)
    if "season_score" in rule:
        values["season_score"] = float(rule["season_score"][season])
    used = []
    skipped = []
    missing_required = []
    for spec in rule["factors"]:
        partial, raw, label, assumed, missing = _evaluate(spec, values)
        if missing:
            entry = {"id": spec["id"], "label": spec["label"], "reason": "No data for this factor"}
            skipped.append(entry)
            if spec.get("required"):
                missing_required.append(spec["label"])
            continue
        item = {
            "id": spec["id"],
            "label": label,
            "weight": float(spec["weight"]),
            "partial": round(float(partial), 3),
            "value": raw,
            "assumed": assumed,
        }
        if spec.get("note") and (not spec.get("note_unless") or values.get(spec["note_unless"]) is None):
            item["note"] = spec["note"]
        used.append(item)
    if missing_required:
        return {
            "score": None,
            "risk_class": "insufficient_data",
            "confidence": "moderate",
            "confidence_note": None,
            "assumption_note": None,
            "season_role": rule.get("season_role", "none"),
            "factors_used": [],
            "factors_skipped": skipped,
            "explanation": "Insufficient data. Required factors missing: " + ", ".join(missing_required) + ".",
        }
    weight_sum = sum(item["weight"] for item in used)
    score = 0.0
    phrases = []
    for item in used:
        share = item["weight"] / weight_sum
        contribution = share * item["partial"]
        item["share"] = round(share, 3)
        item["contribution"] = round(contribution, 3)
        score += contribution
        if item["partial"] >= 0.6 and not item["assumed"]:
            phrases.append(item["label"].lower())
    score = round(score, 3)
    cuts = rule["cuts"]
    if score >= cuts["very_high"]:
        risk_class = "very_high"
    elif score >= cuts["high"]:
        risk_class = "high"
    elif score >= cuts["moderate"]:
        risk_class = "moderate"
    else:
        risk_class = "low"
    assumed_weight = sum(item["weight"] for item in used if item["assumed"])
    assumed_share = assumed_weight / weight_sum if weight_sum else 0.0
    assumed_names = [item["label"] for item in used if item["assumed"]]
    assumption_note = None
    if assumed_share >= 0.5:
        assumption_note = "This score is based mostly on assumptions: " + ", ".join(assumed_names) + "."
    elif assumed_names:
        assumption_note = "Includes an assumption: " + ", ".join(assumed_names) + "."
    confidence = "low" if rule.get("confidence") == "low" or assumed_share >= 0.5 else "moderate"
    confidence_note = rule.get("confidence_note")
    if phrases:
        why = "Favorable conditions: " + ", ".join(phrases) + "."
    else:
        why = "No factor is strongly favorable."
    if skipped:
        why += " Not used: " + ", ".join(item["label"] for item in skipped) + "."
    if any(item["id"] == "crop_stage" for item in skipped):
        why += " Crop stage was left out because no planting date or Sentinel start-of-season is loaded. The season setting is not used in its place."
    if rule.get("season_role") == "modifier":
        why += " Wet or dry season is only a climate modifier. Any El Niño adjustment is national and does not separate towns."
    notes = [item["note"] for item in used if item.get("note")]
    if notes:
        why += " " + " ".join(notes)
    if confidence_note:
        why += " " + confidence_note
    if assumption_note:
        why += " " + assumption_note
    why += f" Weights were renormalized across {len(used)} available factors."
    why += " This is a risk class for monitoring, not a statement that the pest or disease is present."
    why += " " + DISCLAIMER
    return {
        "score": score,
        "risk_class": risk_class,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "assumption_note": assumption_note,
        "season_role": rule.get("season_role", "none"),
        "factors_used": used,
        "factors_skipped": skipped,
        "explanation": why,
    }


def _evaluate(spec: dict, values: dict):
    mode = spec.get("mode", "band")
    label = spec["label"]
    assumed = False
    if mode == "storm":
        wind = values.get("wind_speed_kmh")
        gust = values.get("wind_gust_kmh")
        active = values.get("storm_active")
        if wind is None and gust is None and not active:
            return 0.0, None, label, False, True
        return storm_partial(wind, gust, active), wind, label, False, False
    raw = values.get(spec["field"])
    if raw is None and "assumed_value" in spec:
        raw = spec["assumed_value"]
        assumed = True
        label = spec.get("assumed_label", label)
    if raw is None:
        return 0.0, None, label, False, True
    if spec.get("assumed_flag") and values.get(spec["assumed_flag"]):
        assumed = True
        label = spec.get("assumed_label", label)
    if mode == "peak" and spec.get("night"):
        partial = _peak_with_night(float(raw), spec, values)
    else:
        partial = factor_score(float(raw), spec)
    return partial, raw, label, assumed, False


def _peak_with_night(mean: float, spec: dict, values: dict) -> float:
    day = factor_score(mean, spec)
    night_spec = spec["night"]
    night_raw = values.get(night_spec.get("field", "temp_min_c"))
    if night_raw is None:
        return day
    night = factor_score(
        float(night_raw),
        {"mode": "peak", "core": night_spec["core"], "hard": night_spec["hard"]},
    )
    blend = float(night_spec.get("blend", 0.4))
    return (1 - blend) * day + blend * night


def _peak(value: float, spec: dict) -> float:
    core = spec["core"]
    hard = spec["hard"]
    low_core = float(core["min"])
    high_core = float(core["max"])
    low_zero = float(hard["min"])
    high_zero = float(hard["max"])
    if low_core <= value <= high_core:
        return 1.0
    if value <= low_zero or value >= high_zero:
        return 0.0
    if value < low_core:
        return (value - low_zero) / (low_core - low_zero)
    return (high_zero - value) / (high_zero - high_core)


def _stage(value: float, spec: dict) -> float:
    for step in spec["stages"]:
        if value <= float(step["max_day"]):
            return float(step["score"])
    return 0.0


def _light_rain(value: float, spec: dict) -> float:
    sweet_max = float(spec["favorable"]["max"])
    heavy = float(spec.get("heavy", sweet_max + 40))
    if value <= 0:
        return 0.15
    if value <= sweet_max:
        return 0.35 + 0.65 * min(1.0, value / 5.0)
    if value >= heavy:
        return 0.2
    return 1.0 - 0.8 * (value - sweet_max) / (heavy - sweet_max)


def _heavy_penalty(value: float, spec: dict) -> float:
    """Light rain stays near neutral. A very heavy day falls toward zero."""
    light_max = float(spec["favorable"]["max"])
    heavy = float(spec["heavy"])
    if value <= 0:
        return 0.5
    if value <= light_max:
        return 0.5 + 0.25 * min(1.0, value / light_max)
    if value >= heavy:
        return 0.0
    return 0.75 * (heavy - value) / (heavy - light_max)
