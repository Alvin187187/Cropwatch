"""Ranking, clusters, and inspection order.

These functions are the ones the algorithms panel calls. They are ordinary
Python so a defense can read them without opening the database.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

CLASS_RANK = {
    "very_high": 4,
    "high": 3,
    "moderate": 2,
    "low": 1,
    "insufficient_data": 0,
}


def rank_places(rows: list[dict]) -> list[dict]:
    """Priority queue: higher risk class first, then known rice hectares."""
    heap: list[tuple] = []
    for row in rows:
        hectares = row.get("exposure_ha")
        known = 1 if hectares is not None else 0
        heapq.heappush(
            heap,
            (
                -CLASS_RANK.get(row["risk_class"], 0),
                -known,
                -(hectares or 0.0),
                row["name"],
                row["id"],
            ),
        )
    ordered = []
    rank = 1
    while heap:
        class_key, known_key, hectares_key, name, place_id = heapq.heappop(heap)
        ordered.append(
            {
                "rank": rank,
                "id": place_id,
                "name": name,
                "risk_class": _class_from_rank(-class_key),
                "exposure_ha": None if known_key == 0 else -hectares_key,
            }
        )
        rank += 1
    return ordered


def _class_from_rank(rank: int) -> str:
    for name, value in CLASS_RANK.items():
        if value == rank:
            return name
    return "insufficient_data"


def connected_components(high_ids: list[int], edges: list[tuple[int, int]]) -> list[list[int]]:
    """BFS over neighboring High and Very High places."""
    allowed = set(high_ids)
    adjacency: dict[int, set[int]] = {place_id: set() for place_id in allowed}
    for left, right in edges:
        if left in allowed and right in allowed and left != right:
            adjacency[left].add(right)
            adjacency[right].add(left)
    seen: set[int] = set()
    components: list[list[int]] = []
    for start in high_ids:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for nxt in adjacency[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(sorted(component))
    components.sort(key=len, reverse=True)
    return components


def dijkstra(
    start: int,
    goal: int,
    adjacency: dict[int, list[tuple[int, float]]],
) -> tuple[list[int] | None, float | None]:
    """Shortest path by kilometers. Returns the node list and the distance."""
    heap: list[tuple[float, int]] = [(0.0, start)]
    best: dict[int, float] = {start: 0.0}
    previous: dict[int, int] = {}
    while heap:
        cost, node = heapq.heappop(heap)
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(previous[path[-1]])
            path.reverse()
            return path, cost
        if cost > best.get(node, math.inf):
            continue
        for nxt, weight in adjacency.get(node, []):
            proposed = cost + weight
            if proposed < best.get(nxt, math.inf):
                best[nxt] = proposed
                previous[nxt] = node
                heapq.heappush(heap, (proposed, nxt))
    return None, None


def inspection_route(
    ordered_ids: list[int],
    adjacency: dict[int, list[tuple[int, float]]],
    limit: int = 5,
) -> dict:
    """Visit the top priority places, using Dijkstra between each stop."""
    stops = [place_id for place_id in ordered_ids if place_id in adjacency][:limit]
    if len(stops) < 2:
        return {"stops": stops, "path": stops, "distance_km": 0.0, "segments": []}
    remaining = stops[1:]
    current = stops[0]
    full_path = [current]
    distance = 0.0
    segments = []
    visit_order = [current]
    while remaining:
        best_goal = None
        best_path = None
        best_cost = math.inf
        for goal in remaining:
            path, cost = dijkstra(current, goal, adjacency)
            if path is not None and cost is not None and cost < best_cost:
                best_goal = goal
                best_path = path
                best_cost = cost
        if best_goal is None or best_path is None:
            break
        full_path.extend(best_path[1:])
        distance += best_cost
        segments.append({"from": current, "to": best_goal, "distance_km": round(best_cost, 2), "path": best_path})
        visit_order.append(best_goal)
        remaining.remove(best_goal)
        current = best_goal
    return {
        "stops": visit_order,
        "path": full_path,
        "distance_km": round(distance, 2),
        "segments": segments,
    }


def build_adjacency(edges: list[tuple[int, int, float]]) -> dict[int, list[tuple[int, float]]]:
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    seen = set()
    for left, right, cost in edges:
        key = tuple(sorted((left, right)))
        if key in seen or left == right:
            continue
        seen.add(key)
        adjacency[left].append((right, cost))
        adjacency[right].append((left, cost))
    return adjacency


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))
