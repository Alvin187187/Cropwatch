Drop agency files here. Templates are ignored by the loader because their names start with `template`.

- `surveillance/` PRIME, BPI, or PhilRice occurrence CSV. `threat_id` is `rice_black_bug`, `brown_planthopper`, `rice_blast`, or `bacterial_leaf_blight`. Put the office name in `source`. Do not include farmer names.
- `prism/` rice area CSV or GeoJSON.
- `management/` nitrogen, variety, residue. Blank columns stay unused in the score.
- `gee/` zonal CSV from `python -m ingest.gee_export`.
- `boundaries/` barangay GeoJSON with `municipality` and `name` properties.
- `pagasa/` and `climap/` climate-baseline CSVs.
- `advisories/` dated drought or flood notes.
- `srtm/` optional DEM tiles. The running app uses the elevation already stored from Open-Meteo.

After adding files:

```
docker compose exec api python -m ingest.inbox
```
