"""Load agency files dropped into data/inbox. Empty folders are a normal state."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from shapely.geometry import mapping, shape

from ingest.borders import separate_borders
from app.db import connect
from app.engine import recompute
from app.paths import data_dir
from app.seed import mark_status, slugify


def load() -> dict:
    root = data_dir() / "inbox"
    counts = {
        "occurrences": _occurrences(root / "surveillance"),
        "rice": _rice(root / "prism"),
        "management": _management(root / "management"),
        "satellite": _satellite(root / "gee"),
        "barangays": _barangays(root / "boundaries"),
        "advisories": _advisories(root / "advisories"),
    }
    if any(counts.values()):
        recompute()
    return counts


def _occurrences(folder: Path) -> int:
    rows = _csvs(folder)
    if not rows:
        return 0
    written = 0
    with connect() as conn:
        for row in rows:
            place_id, place_type = _resolve(conn, row.get("municipality", ""), row.get("barangay") or "")
            if not place_id or not row.get("threat_id") or not row.get("observed_on") or not row.get("source"):
                continue
            official = str(row.get("is_official", "")).strip().lower() in ("1", "true", "yes")
            conn.execute(
                """
                INSERT INTO occurrence (
                  place_type, place_id, observed_on, threat_id, severity, hectares_affected, source, is_official
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    place_type,
                    place_id,
                    row["observed_on"],
                    row["threat_id"].strip(),
                    row.get("severity") or None,
                    _float(row.get("hectares_affected")),
                    row["source"].strip(),
                    official,
                ),
            )
            written += 1
        conn.commit()
    if written:
        mark_status("occurrences", "loaded", f"{written} surveillance rows from municipal and provincial agriculture offices.")
    return written


def _rice(folder: Path) -> int:
    written = 0
    with connect() as conn:
        for row in _csvs(folder):
            place_id, place_type = _resolve(conn, row.get("municipality", ""), row.get("barangay") or "")
            if not place_id:
                continue
            conn.execute(
                """
                INSERT INTO rice_area (
                  place_type, place_id, source, rice_ha, planting_date, yield_t_ha, flood_ha, drought_ha, harvested_ha
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (place_type, place_id, source) DO UPDATE SET
                  rice_ha = EXCLUDED.rice_ha,
                  planting_date = EXCLUDED.planting_date,
                  yield_t_ha = EXCLUDED.yield_t_ha,
                  flood_ha = EXCLUDED.flood_ha,
                  drought_ha = EXCLUDED.drought_ha,
                  harvested_ha = EXCLUDED.harvested_ha
                """,
                (
                    place_type,
                    place_id,
                    row.get("source") or "PRiSM",
                    _float(row.get("rice_ha")),
                    row.get("planting_date") or None,
                    _float(row.get("yield_t_ha")),
                    _float(row.get("flood_ha")),
                    _float(row.get("drought_ha")),
                    _float(row.get("harvested_ha")),
                ),
            )
            written += 1
        geojson_paths = list(folder.glob("*.geojson")) if folder.exists() else []
        for path in geojson_paths:
            written += _rice_geojson(conn, path)
        conn.commit()
    if written:
        mark_status("rice_mask", "loaded", "Rice area loaded from data/inbox/prism. Exposure hectares use this layer.")
    return written


def _rice_geojson(conn, path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    written = 0
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("municipality") or props.get("name") or ""
        place_id, place_type = _resolve(conn, name, props.get("barangay") or "")
        if not place_id:
            continue
        conn.execute(
            """
            INSERT INTO rice_area (place_type, place_id, source, rice_ha, planting_date, yield_t_ha, flood_ha, drought_ha)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (place_type, place_id, source) DO UPDATE SET rice_ha = EXCLUDED.rice_ha
            """,
            (
                place_type,
                place_id,
                props.get("source") or "PRiSM",
                _float(props.get("rice_ha")),
                props.get("planting_date"),
                _float(props.get("yield_t_ha")),
                _float(props.get("flood_ha")),
                _float(props.get("drought_ha")),
            ),
        )
        written += 1
    return written


def _management(folder: Path) -> int:
    written = 0
    with connect() as conn:
        for row in _csvs(folder):
            place_id, place_type = _resolve(conn, row.get("municipality", ""), row.get("barangay") or "")
            if not place_id:
                continue
            conn.execute(
                """
                INSERT INTO management (
                  place_type, place_id, nitrogen_kg_ha, fertilizer_note, variety, residue_note, source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (place_type, place_id) DO UPDATE SET
                  nitrogen_kg_ha = EXCLUDED.nitrogen_kg_ha,
                  fertilizer_note = EXCLUDED.fertilizer_note,
                  variety = EXCLUDED.variety,
                  residue_note = EXCLUDED.residue_note,
                  source = EXCLUDED.source
                """,
                (
                    place_type,
                    place_id,
                    _float(row.get("nitrogen_kg_ha")),
                    row.get("fertilizer_note") or None,
                    row.get("variety") or None,
                    row.get("residue_note") or None,
                    row.get("source") or "uploaded management file",
                ),
            )
            written += 1
        conn.commit()
    return written


def _satellite(folder: Path) -> int:
    rows = _csvs(folder)
    if not rows:
        return 0
    written = 0
    with connect() as conn:
        for row in rows:
            place_id, place_type = _resolve(conn, row.get("municipality", ""), row.get("barangay") or "")
            if not place_id or not row.get("sensor"):
                continue
            conn.execute(
                """
                INSERT INTO satellite (
                  place_type, place_id, sensor, observed_on, ndvi, evi, ndwi, lswi, swir, lst_c,
                  ndvi_change, rice_fraction, flood_fraction, sos_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (place_type, place_id, sensor) DO UPDATE SET
                  observed_on = EXCLUDED.observed_on,
                  ndvi = EXCLUDED.ndvi,
                  evi = EXCLUDED.evi,
                  ndwi = EXCLUDED.ndwi,
                  lswi = EXCLUDED.lswi,
                  swir = EXCLUDED.swir,
                  lst_c = EXCLUDED.lst_c,
                  ndvi_change = EXCLUDED.ndvi_change,
                  rice_fraction = EXCLUDED.rice_fraction,
                  flood_fraction = EXCLUDED.flood_fraction,
                  sos_date = EXCLUDED.sos_date
                """,
                (
                    place_type,
                    place_id,
                    row["sensor"],
                    row.get("observed_on") or None,
                    _float(row.get("ndvi")),
                    _float(row.get("evi")),
                    _float(row.get("ndwi")),
                    _float(row.get("lswi")),
                    _float(row.get("swir")),
                    _float(row.get("lst_c")),
                    _float(row.get("ndvi_change")),
                    _float(row.get("rice_fraction")),
                    _float(row.get("flood_fraction")),
                    row.get("sos_date") or None,
                ),
            )
            written += 1
        conn.commit()
    if written:
        mark_status("satellite", "loaded", "Earth Engine zonal CSV imported. The map reads these barangay or municipal means only.")
    return written


def _barangays(folder: Path) -> int:
    if not folder.exists():
        return 0
    written = 0
    with connect() as conn:
        for path in folder.glob("*.geojson"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            features = separate_borders(payload.get("features", []))
            for feature in features:
                props = feature.get("properties") or {}
                municipality = props.get("municipality") or props.get("mun_name") or ""
                name = props.get("name") or props.get("barangay") or ""
                parent = conn.execute(
                    "SELECT id FROM municipalities WHERE slug = %s OR name ILIKE %s",
                    (slugify(municipality), municipality),
                ).fetchone()
                if not parent or not name:
                    continue
                geom = shape(feature["geometry"])
                conn.execute(
                    """
                    INSERT INTO barangays (municipality_id, slug, name, source, geom)
                    VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    ON CONFLICT (municipality_id, slug) DO UPDATE SET geom = EXCLUDED.geom, source = EXCLUDED.source
                    """,
                    (parent["id"], slugify(name), name, props.get("source") or path.name, json.dumps(mapping(geom))),
                )
                written += 1
        conn.commit()
    if written:
        mark_status("barangays", "loaded", f"{written} barangay polygons loaded.")
    return written


def _advisories(folder: Path) -> int:
    rows = _csvs(folder)
    if not rows:
        return 0
    with connect() as conn:
        for row in rows:
            if not row.get("title") or not row.get("issued_on"):
                continue
            conn.execute(
                "INSERT INTO advisories (issued_on, kind, title, body) VALUES (%s, %s, %s, %s)",
                (row["issued_on"], row.get("kind") or "note", row["title"], row.get("body") or ""),
            )
        conn.commit()
    return len(rows)


def _resolve(conn, municipality: str, barangay: str):
    if barangay:
        row = conn.execute(
            """
            SELECT b.id FROM barangays b
            JOIN municipalities m ON m.id = b.municipality_id
            WHERE b.name ILIKE %s AND (m.name ILIKE %s OR m.slug = %s)
            """,
            (barangay, municipality, slugify(municipality)),
        ).fetchone()
        if row:
            return row["id"], "barangay"
    row = conn.execute(
        "SELECT id FROM municipalities WHERE name ILIKE %s OR slug = %s",
        (municipality, slugify(municipality)),
    ).fetchone()
    if row:
        return row["id"], "municipality"
    return None, None


def _csvs(folder: Path) -> list[dict]:
    if not folder.exists():
        return []
    rows = []
    for path in folder.glob("*.csv"):
        if path.name.startswith("template"):
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows.extend(list(csv.DictReader(handle)))
    return rows


def _float(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


if __name__ == "__main__":
    print(load())
