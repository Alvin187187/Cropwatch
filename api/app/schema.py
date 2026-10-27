"""Add columns introduced after the first database volume was created."""

from __future__ import annotations


def ensure_schema(conn) -> None:
    statements = [
        "ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS temp_min_c DOUBLE PRECISION",
        "ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS hours_rh90 DOUBLE PRECISION",
        "ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS wind_gust_kmh DOUBLE PRECISION",
        "ALTER TABLE weather_daily ADD COLUMN IF NOT EXISTS temp_min_c DOUBLE PRECISION",
        "ALTER TABLE weather_daily ADD COLUMN IF NOT EXISTS hours_rh90 DOUBLE PRECISION",
        "ALTER TABLE risk_score ADD COLUMN IF NOT EXISTS confidence TEXT",
        "ALTER TABLE risk_score ADD COLUMN IF NOT EXISTS assumption_note TEXT",
        """
        CREATE TABLE IF NOT EXISTS risk_history (
          place_type TEXT NOT NULL,
          place_id INTEGER NOT NULL,
          threat_id TEXT NOT NULL,
          season TEXT NOT NULL,
          observed_on DATE NOT NULL,
          score DOUBLE PRECISION,
          risk_class TEXT NOT NULL,
          PRIMARY KEY (place_type, place_id, threat_id, season, observed_on)
        )
        """,
    ]
    for statement in statements:
        conn.execute(statement)
