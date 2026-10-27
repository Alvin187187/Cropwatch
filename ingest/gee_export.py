"""Earth Engine zonal export. The website never calls Earth Engine.

Authenticate once on the presentation laptop:

    earthengine authenticate

Then run:

    python -m ingest.gee_export

The script writes data/inbox/gee/municipal_zonal.csv. Import it with:

    python -m ingest.inbox
"""

from __future__ import annotations

import os
from pathlib import Path

from app.paths import data_dir

CSV_PATH = data_dir() / "inbox" / "gee" / "municipal_zonal.csv"


def export_zonal() -> Path:
    try:
        import ee
    except ImportError as exc:
        raise SystemExit("Install earthengine-api in the API image before running this export.") from exc
    project = os.environ.get("EE_PROJECT")
    ee.Initialize(project=project) if project else ee.Initialize()
    bbox = ee.Geometry.Rectangle([120.35, 15.15, 121.35, 16.15])
    municipalities = _municipal_collection()
    sentinel2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(bbox)
        .filterDate("2026-09-01", "2026-10-18")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(_s2_indices)
        .median()
    )
    sentinel1 = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(bbox)
        .filterDate("2026-09-01", "2026-10-18")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .select(["VV", "VH"])
        .median()
    )
    rice_fraction = sentinel1.select("VH").lt(-18).rename("rice_fraction")
    flood_fraction = sentinel1.select("VV").lt(-17).rename("flood_fraction")
    landsat_lst = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(bbox)
        .filterDate("2026-09-01", "2026-10-18")
        .map(_landsat_lst)
        .median()
        .rename("lst_c")
    )
    modis_lst = (
        ee.ImageCollection("MODIS/061/MOD11A2")
        .filterBounds(bbox)
        .filterDate("2026-09-01", "2026-10-18")
        .select("LST_Day_1km")
        .median()
        .multiply(0.02)
        .subtract(273.15)
        .rename("lst_modis_c")
    )
    chirps = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterBounds(bbox)
        .filterDate("2026-09-01", "2026-10-18")
        .select("precipitation")
        .sum()
        .rename("chirps_mm")
    )
    image = sentinel2.addBands(rice_fraction).addBands(flood_fraction).addBands(landsat_lst).addBands(modis_lst).addBands(chirps)
    reduced = image.reduceRegions(collection=municipalities, reducer=ee.Reducer.mean(), scale=100)
    rows = reduced.getInfo().get("features", [])
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "municipality",
        "sensor",
        "observed_on",
        "ndvi",
        "evi",
        "ndwi",
        "lswi",
        "swir",
        "lst_c",
        "rice_fraction",
        "flood_fraction",
        "ndvi_change",
        "sos_date",
    ]
    lines = [",".join(headers)]
    for feature in rows:
        props = feature["properties"]
        values = [
            props.get("name", ""),
            "Sentinel-2/Sentinel-1/Landsat/MODIS/CHIRPS",
            "2026-10-18",
            _num(props.get("ndvi")),
            _num(props.get("evi")),
            _num(props.get("ndwi")),
            _num(props.get("lswi")),
            _num(props.get("swir")),
            _num(props.get("lst_c") or props.get("lst_modis_c")),
            _num(props.get("rice_fraction")),
            _num(props.get("flood_fraction")),
            "",
            "",
        ]
        lines.append(",".join(values))
    CSV_PATH.write_text("\n".join(lines), encoding="utf-8")
    return CSV_PATH


def _municipal_collection():
    import json

    import ee

    from app.paths import data_dir

    payload = json.loads((data_dir() / "boundaries" / "nueva_ecija_municipalities.geojson").read_text(encoding="utf-8"))
    return ee.FeatureCollection(payload)


def _s2_indices(image):
    import ee

    scaled = image.divide(10000)
    ndvi = scaled.normalizedDifference(["B8", "B4"]).rename("ndvi")
    evi = scaled.expression(
        "2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)",
        {"NIR": scaled.select("B8"), "RED": scaled.select("B4"), "BLUE": scaled.select("B2")},
    ).rename("evi")
    ndwi = scaled.normalizedDifference(["B3", "B8"]).rename("ndwi")
    lswi = scaled.normalizedDifference(["B8", "B11"]).rename("lswi")
    swir = scaled.select("B11").rename("swir")
    return ndvi.addBands(evi).addBands(ndwi).addBands(lswi).addBands(swir)


def _landsat_lst(image):
    import ee

    return image.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)


def _num(value) -> str:
    if value is None:
        return ""
    return str(round(float(value), 4))


if __name__ == "__main__":
    print(export_zonal())
