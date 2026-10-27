"""Reload cached Ricelytics, World Bank, NOAA ONI, and optional PAGASA CSVs.

The map does not scrape these sites on each click. Ricelytics and World Bank
figures already sit in data/cache from the build. This command reloads them
and any CSV an officer drops in data/inbox/pagasa or data/inbox/climap.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.db import connect
from app.paths import data_dir
from app.seed import _parse_oni, _ricelytics, _world_bank, mark_status


def load() -> None:
    root = data_dir()
    import json

    ricelytics = json.loads((root / "cache" / "ricelytics_nueva_ecija.json").read_text(encoding="utf-8"))
    world_bank = json.loads((root / "cache" / "world_bank_ph.json").read_text(encoding="utf-8"))
    oni_rows = _parse_oni((root / "cache" / "oni.txt").read_text(encoding="utf-8"))
    with connect() as conn:
        conn.execute("DELETE FROM provincial_stats")
        conn.execute("DELETE FROM national_indicators")
        _ricelytics(conn, ricelytics)
        _world_bank(conn, world_bank)
        for season_code, year, total, anomaly in oni_rows:
            conn.execute(
                """
                INSERT INTO enso_oni (season_code, year, total_c, anomaly_c)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (season_code, year) DO UPDATE SET anomaly_c = EXCLUDED.anomaly_c
                """,
                (season_code, year, total, anomaly),
            )
        normals = _csv_rows(root / "inbox" / "pagasa")
        climap = _csv_rows(root / "inbox" / "climap")
        for row in normals + climap:
            if not row.get("element") or row.get("value") in (None, ""):
                continue
            conn.execute(
                """
                INSERT INTO climate_normals (station, month, element, value, unit, period, source, place_slug)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.get("station") or row.get("municipality") or "Nueva Ecija",
                    int(row["month"]) if row.get("month") else None,
                    row.get("element") or row.get("rainfall_mm") and "rainfall_mm",
                    float(row["value"]) if row.get("value") else float(row.get("rainfall_mm") or row.get("temp_mean_c") or 0),
                    row.get("unit"),
                    row.get("period"),
                    row.get("source") or "PAGASA",
                    row.get("municipality"),
                ),
            )
        conn.commit()
    if normals or climap:
        mark_status("pagasa_normals", "loaded", "Climate baseline CSV imported from data/inbox.")
    mark_status("ricelytics", "loaded", "Provincial Ricelytics snapshot reloaded from cache.")
    mark_status("world_bank", "loaded", "National World Bank indicators reloaded. Not used in the municipal score.")


def _csv_rows(folder: Path) -> list[dict]:
    if not folder.exists():
        return []
    rows = []
    for path in folder.glob("*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


if __name__ == "__main__":
    load()
    print("portals reloaded")
