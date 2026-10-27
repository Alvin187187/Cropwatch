"""NASA POWER daily history for Nueva Ecija municipal points.

This is a cross-check and a long archive. Open-Meteo remains the forecast.
The script stores rows and does not change the risk score until recompute.
"""

from __future__ import annotations

import httpx

from app.db import connect
from app.seed import mark_status

PARAMETERS = "T2M,RH2M,PRECTOTCORR,WS2M,GWETTOP,ALLSKY_SFC_SW_DWN"


def load(start: str = "20150101", end: str = "20261016") -> int:
    with connect() as conn:
        places = conn.execute(
            """
            SELECT id, ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lon
            FROM municipalities ORDER BY id
            """
        ).fetchall()
    written = 0
    for place in places:
        url = (
            "https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters={PARAMETERS}&community=AG&longitude={place['lon']:.4f}"
            f"&latitude={place['lat']:.4f}&start={start}&end={end}&format=JSON"
        )
        response = httpx.get(url, timeout=120, headers={"User-Agent": "CROPWATCH-school-project"})
        response.raise_for_status()
        parameter = response.json()["properties"]["parameter"]
        days = parameter["T2M"].keys()
        with connect() as conn:
            for day in days:
                if day.startswith("20") is False:
                    continue
                observed = f"{day[0:4]}-{day[4:6]}-{day[6:8]}"
                conn.execute(
                    """
                    INSERT INTO weather_daily (
                      place_type, place_id, observed_on, source, temp_c, rh_pct, rain_mm,
                      wind_speed_kmh, soil_moisture
                    ) VALUES ('municipality', %s, %s, 'NASA POWER', %s, %s, %s, %s, %s)
                    ON CONFLICT (place_type, place_id, observed_on, source) DO UPDATE SET
                      temp_c = EXCLUDED.temp_c,
                      rh_pct = EXCLUDED.rh_pct,
                      rain_mm = EXCLUDED.rain_mm,
                      wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                      soil_moisture = EXCLUDED.soil_moisture
                    """,
                    (
                        place["id"],
                        observed,
                        _clean(parameter["T2M"][day]),
                        _clean(parameter["RH2M"][day]),
                        _clean(parameter["PRECTOTCORR"][day]),
                        _clean(parameter["WS2M"][day]),
                        _clean(parameter["GWETTOP"][day]),
                    ),
                )
                written += 1
            conn.commit()
    mark_status("nasa_power", "loaded", f"NASA POWER daily history {start} to {end}. Solar radiation is fetched but not a default rule term.")
    return written


def _clean(value):
    if value is None or value <= -900:
        return None
    return value


if __name__ == "__main__":
    print(load())
