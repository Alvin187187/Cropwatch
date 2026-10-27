"""Pull overlapping barangay polygons apart so shared borders touch once.

NAMRIA extracts often digitize the same strip into both neighbors. The strip
goes to the smaller barangay, which keeps a poblacion from disappearing
under the municipality around it.
"""

from __future__ import annotations

from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

# About one metre. Snapping closes gaps that are only a rounding error.
GRID_DEGREES = 1e-5


def _polygonal(geom):
    geom = make_valid(geom)
    if geom.is_empty:
        return geom
    if geom.geom_type == "GeometryCollection":
        parts = [part for part in geom.geoms if part.geom_type in ("Polygon", "MultiPolygon")]
        geom = unary_union(parts) if parts else geom
    return geom


def separate_borders(features: list[dict]) -> list[dict]:
    """Return a copy of the features whose polygons do not cover each other."""
    geoms = []
    for feature in features:
        raw = _polygonal(shape(feature["geometry"]))
        snapped = _polygonal(set_precision(raw, GRID_DEGREES))
        geoms.append(snapped if not snapped.is_empty else raw)

    lines = unary_union([geom.boundary for geom in geoms if not geom.is_empty])
    faces = [face for face in polygonize(lines) if face.area > 1e-12]
    tree = STRtree(geoms)
    buckets: list[list] = [[] for _ in geoms]
    for face in faces:
        point = face.representative_point()
        best = None
        best_key = None
        for index in tree.query(face):
            owner = geoms[int(index)]
            if owner.is_empty or not owner.intersects(face):
                continue
            overlap = owner.intersection(face).area
            if overlap < face.area * 0.5 and not owner.covers(point):
                continue
            # A strip claimed by two barangays goes to whichever center is closer,
            # so the cut falls between them instead of erasing the smaller one.
            key = (1 if owner.covers(point) else 0, -point.distance(owner.representative_point()), -int(index))
            if best_key is None or key > best_key:
                best = int(index)
                best_key = key
        if best is not None:
            buckets[best].append(face)

    cleaned = []
    for feature, original, parts in zip(features, geoms, buckets):
        geom = unary_union(parts) if parts else original
        item = dict(feature)
        item["geometry"] = mapping(_polygonal(geom))
        cleaned.append(item)
    return cleaned
