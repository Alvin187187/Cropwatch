CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('provincial', 'municipal', 'guest')),
  municipality_slug TEXT,
  display_name TEXT NOT NULL
);

CREATE TABLE sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE municipalities (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  source TEXT NOT NULL,
  source_id TEXT,
  area_ha DOUBLE PRECISION,
  geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX municipalities_geom_idx ON municipalities USING GIST (geom);

CREATE TABLE barangays (
  id SERIAL PRIMARY KEY,
  municipality_id INTEGER NOT NULL REFERENCES municipalities(id),
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  source TEXT NOT NULL,
  area_ha DOUBLE PRECISION,
  geom geometry(Geometry, 4326) NOT NULL,
  UNIQUE (municipality_id, slug)
);
CREATE INDEX barangays_geom_idx ON barangays USING GIST (geom);

CREATE TABLE edges (
  place_type TEXT NOT NULL CHECK (place_type IN ('municipality', 'barangay')),
  place_a INTEGER NOT NULL,
  place_b INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('boundary', 'canal', 'river', 'road')),
  cost_km DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (place_type, place_a, place_b, kind)
);

CREATE TABLE weather_daily (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  observed_on DATE NOT NULL,
  source TEXT NOT NULL,
  temp_c DOUBLE PRECISION,
  rh_pct DOUBLE PRECISION,
  rain_mm DOUBLE PRECISION,
  wind_speed_kmh DOUBLE PRECISION,
  wind_dir_deg DOUBLE PRECISION,
  soil_moisture DOUBLE PRECISION,
  soil_temp_c DOUBLE PRECISION,
  temp_min_c DOUBLE PRECISION,
  hours_rh90 DOUBLE PRECISION,
  PRIMARY KEY (place_type, place_id, observed_on, source)
);

CREATE TABLE weather_forecast (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  issued_on DATE NOT NULL,
  day_offset INTEGER NOT NULL CHECK (day_offset BETWEEN 0 AND 6),
  forecast_date DATE NOT NULL,
  source TEXT NOT NULL,
  temp_c DOUBLE PRECISION,
  temp_min_c DOUBLE PRECISION,
  rh_pct DOUBLE PRECISION,
  hours_rh90 DOUBLE PRECISION,
  rain_mm DOUBLE PRECISION,
  wind_speed_kmh DOUBLE PRECISION,
  wind_gust_kmh DOUBLE PRECISION,
  wind_dir_deg DOUBLE PRECISION,
  soil_moisture DOUBLE PRECISION,
  soil_temp_c DOUBLE PRECISION,
  PRIMARY KEY (place_type, place_id, day_offset, source)
);

CREATE TABLE terrain (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  elevation_m DOUBLE PRECISION,
  slope_index DOUBLE PRECISION,
  wetness_index DOUBLE PRECISION,
  source TEXT NOT NULL,
  PRIMARY KEY (place_type, place_id)
);

CREATE TABLE satellite (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  observed_on DATE,
  ndvi DOUBLE PRECISION,
  evi DOUBLE PRECISION,
  ndwi DOUBLE PRECISION,
  lswi DOUBLE PRECISION,
  swir DOUBLE PRECISION,
  lst_c DOUBLE PRECISION,
  ndvi_change DOUBLE PRECISION,
  rice_fraction DOUBLE PRECISION,
  flood_fraction DOUBLE PRECISION,
  sos_date DATE,
  PRIMARY KEY (place_type, place_id, sensor)
);

CREATE TABLE rice_area (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  source TEXT NOT NULL,
  rice_ha DOUBLE PRECISION,
  planting_date DATE,
  yield_t_ha DOUBLE PRECISION,
  flood_ha DOUBLE PRECISION,
  drought_ha DOUBLE PRECISION,
  harvested_ha DOUBLE PRECISION,
  PRIMARY KEY (place_type, place_id, source)
);

CREATE TABLE occurrence (
  id SERIAL PRIMARY KEY,
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  observed_on DATE NOT NULL,
  threat_id TEXT NOT NULL,
  severity TEXT,
  hectares_affected DOUBLE PRECISION,
  source TEXT NOT NULL,
  is_official BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE management (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  nitrogen_kg_ha DOUBLE PRECISION,
  fertilizer_note TEXT,
  variety TEXT,
  residue_note TEXT,
  source TEXT NOT NULL,
  PRIMARY KEY (place_type, place_id)
);

CREATE TABLE risk_score (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  threat_id TEXT NOT NULL,
  season TEXT NOT NULL CHECK (season IN ('wet', 'dry')),
  forecast_day INTEGER NOT NULL CHECK (forecast_day BETWEEN 0 AND 6),
  score DOUBLE PRECISION,
  risk_class TEXT NOT NULL,
  factors_used JSONB NOT NULL,
  factors_skipped JSONB NOT NULL,
  explanation TEXT NOT NULL,
  exposure_ha DOUBLE PRECISION,
  exposure_source TEXT,
  confidence TEXT,
  assumption_note TEXT,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (place_type, place_id, threat_id, season, forecast_day)
);

CREATE TABLE risk_history (
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  threat_id TEXT NOT NULL,
  season TEXT NOT NULL CHECK (season IN ('wet', 'dry')),
  observed_on DATE NOT NULL,
  score DOUBLE PRECISION,
  risk_class TEXT NOT NULL,
  PRIMARY KEY (place_type, place_id, threat_id, season, observed_on)
);

CREATE TABLE run_log (
  id SERIAL PRIMARY KEY,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  threat_id TEXT NOT NULL,
  season TEXT NOT NULL,
  forecast_day INTEGER NOT NULL,
  class_counts JSONB NOT NULL
);

CREATE TABLE provincial_stats (
  id SERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_url TEXT,
  retrieved_on DATE,
  metric TEXT NOT NULL,
  period TEXT,
  value DOUBLE PRECISION,
  unit TEXT,
  note TEXT
);

CREATE TABLE national_indicators (
  indicator_id TEXT NOT NULL,
  indicator TEXT NOT NULL,
  year INTEGER NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (indicator_id, year)
);

CREATE TABLE climate_normals (
  id SERIAL PRIMARY KEY,
  station TEXT NOT NULL,
  month INTEGER,
  element TEXT NOT NULL,
  value DOUBLE PRECISION,
  unit TEXT,
  period TEXT,
  source TEXT NOT NULL,
  place_slug TEXT
);

CREATE TABLE enso_oni (
  season_code TEXT NOT NULL,
  year INTEGER NOT NULL,
  total_c DOUBLE PRECISION,
  anomaly_c DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (season_code, year)
);

CREATE TABLE advisories (
  id SERIAL PRIMARY KEY,
  issued_on DATE NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL
);

CREATE TABLE field_notes (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  place_type TEXT NOT NULL,
  place_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE osm_features (
  id SERIAL PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('canal', 'river', 'road')),
  name TEXT,
  geojson JSONB NOT NULL
);

CREATE TABLE dataset_status (
  dataset TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  detail TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE met_points (
  id SERIAL PRIMARY KEY,
  lon DOUBLE PRECISION NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  elevation_m DOUBLE PRECISION,
  UNIQUE (lon, lat)
);

CREATE TABLE met_hourly (
  met_id INTEGER NOT NULL REFERENCES met_points(id) ON DELETE CASCADE,
  valid_time TIMESTAMPTZ NOT NULL,
  temp_c DOUBLE PRECISION,
  rh_pct DOUBLE PRECISION,
  rain_mm DOUBLE PRECISION,
  PRIMARY KEY (met_id, valid_time)
);

CREATE TABLE grid_cells (
  id SERIAL PRIMARY KEY,
  barangay_id INTEGER NOT NULL REFERENCES barangays(id) ON DELETE CASCADE,
  lon DOUBLE PRECISION NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  elevation_m DOUBLE PRECISION,
  met_id INTEGER REFERENCES met_points(id)
);
CREATE INDEX grid_cells_barangay_idx ON grid_cells (barangay_id);
