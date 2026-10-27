"""Terrain notes.

Elevation is already stored from the Open-Meteo elevation field, which uses a
SRTM/Copernicus DEM. Slope and a simple wetness index are the elevation
difference with neighboring municipalities. A full raster slope would need a
local HGT tile and is not queried from EarthExplorer at runtime.

Dropping HGT files into data/inbox/srtm does not change the live map until a
raster library is added. The current neighbor method is what the score can cite.
"""

from app.seed import mark_status


def describe() -> str:
    detail = (
        "Elevation from Open-Meteo DEM (SRTM/Copernicus). "
        "Slope and wetness are neighbor elevation differences, computed when boundaries are seeded."
    )
    mark_status("terrain", "loaded", detail)
    return detail


if __name__ == "__main__":
    print(describe())
