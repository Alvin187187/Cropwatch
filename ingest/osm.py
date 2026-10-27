"""Cache canals, rivers, and main roads for Nueva Ecija from Overpass.

Run this by hand. The website never calls Overpass.
"""

from __future__ import annotations

import httpx
from shapely.geometry import LineString, mapping

from app.algorithms import haversine_km
from app.db import connect
from app.seed import mark_status

QUERY = """
[out:json][timeout:90];
(
  way["highway"~"^(primary|secondary|tertiary)$"](15.15,120.35,16.15,121.35);
  way["waterway"~"^(river|canal)$"](15.15,120.35,16.15,121.35);
);
out geom;
"""


def load() -> dict:
    response = httpx.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": QUERY},
        timeout=120,
        headers={"User-Agent": "CROPWATCH-school-project"},
    )
    response.raise_for_status()
    elements = response.json().get("elements", [])
    stored = {"road": 0, "river": 0, "canal": 0}
    with connect() as conn:
        places = conn.execute(
            """
            SELECT id, ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lon
            FROM municipalities
            """
        ).fetchall()
        conn.execute("DELETE FROM osm_features")
        for element in elements:
            geometry = element.get("geometry") or []
            if len(geometry) < 2:
                continue
            kind = _kind(element.get("tags") or {})
            if not kind:
                continue
            line = LineString([(node["lon"], node["lat"]) for node in geometry])
            conn.execute(
                "INSERT INTO osm_features (kind, name, geojson) VALUES (%s, %s, %s::jsonb)",
                (kind, (element.get("tags") or {}).get("name"), _json(mapping(line))),
            )
            stored[kind] += 1
            _link_places(conn, places, line, kind)
        conn.commit()
    detail = f"Overpass extract: {stored['road']} roads, {stored['river']} rivers, {stored['canal']} canals."
    mark_status("osm", "loaded", detail)
    return stored


def _kind(tags: dict) -> str | None:
    if tags.get("waterway") == "canal":
        return "canal"
    if tags.get("waterway") == "river":
        return "river"
    if tags.get("highway") in ("primary", "secondary", "tertiary"):
        return "road"
    return None


def _link_places(conn, places, line: LineString, kind: str) -> None:
    near = []
    for place in places:
        if line.distance(_point(place)) < 0.03:
            near.append(place)
    edge_kind = "road" if kind == "road" else kind
    for index, left in enumerate(near):
        for right in near[index + 1 :]:
            cost = haversine_km(left["lon"], left["lat"], right["lon"], right["lat"])
            conn.execute(
                """
                INSERT INTO edges (place_type, place_a, place_b, kind, cost_km)
                VALUES ('municipality', %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (min(left["id"], right["id"]), max(left["id"], right["id"]), edge_kind, cost),
            )


def _point(place):
    from shapely.geometry import Point

    return Point(place["lon"], place["lat"])


def _json(payload):
    import json

    return json.dumps(payload)


if __name__ == "__main__":
    print(load())
