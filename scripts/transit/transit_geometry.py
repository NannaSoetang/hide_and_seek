"""Station normalization and route geometry operations for GTFS output."""

from __future__ import annotations

import math
import re
from typing import Any

from shapely.geometry import LineString, mapping, shape
from shapely.ops import unary_union


def clean_station_name(name: str) -> str:
    return re.sub(r"\s*\(Metro\)\s*", "", str(name or "")).strip()


def normalize_station_name(name: str) -> str:
    normalized = str(name or "").casefold().replace("ø", "o").replace("å", "a").replace("æ", "ae")
    normalized = re.sub(r"\(.*?\)", "", normalized)
    normalized = re.sub(r"\bst\.?\b", "", normalized)
    normalized = normalized.replace("station", "")
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def add_station_feature(
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    stop: dict[str, str],
    line: str,
    network: str,
) -> None:
    name = clean_station_name(stop.get("stop_name", stop["stop_id"]))
    if not name:
        return
    lat = float(stop["stop_lat"])
    lon = float(stop["stop_lon"])
    key = (normalize_station_name(name), round(lat, 6), round(lon, 6))
    station = station_index.setdefault(key, {
        "type": "Feature",
        "properties": {
            "name": name,
            "lines": [],
            "networks": [],
            "stop_id": stop["stop_id"],
            "source": "Rejseplanen GTFS",
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    })
    if line not in station["properties"]["lines"]:
        station["properties"]["lines"].append(line)
    if network not in station["properties"]["networks"]:
        station["properties"]["networks"].append(network)


def dedupe_coords(coords: list[list[float]]) -> list[list[float]]:
    if not coords:
        return coords
    output = [coords[0]]
    for point in coords[1:]:
        if point[0] != output[-1][0] or point[1] != output[-1][1]:
            output.append(point)
    return output


def merge_route_segments(segments: list[list[list[float]]], gap_tolerance: float = 0.002) -> list[list[float]]:
    if not segments:
        return []
    remaining = [segment[:] for segment in segments if len(segment) >= 2]
    if not remaining:
        return []
    merged = remaining.pop(0)
    while remaining:
        best_index = None
        best_mode = None
        best_candidate = None
        best_distance = float("inf")
        for candidate_index, candidate in enumerate(remaining):
            for mode, anchor, candidate_point in (
                ("append_same", merged[-1], candidate[0]),
                ("append_reverse", merged[-1], candidate[-1]),
                ("prepend_same", merged[0], candidate[0]),
                ("prepend_reverse", merged[0], candidate[-1]),
            ):
                distance = math.hypot(candidate_point[0] - anchor[0], candidate_point[1] - anchor[1])
                if distance <= gap_tolerance and distance < best_distance:
                    best_distance = distance
                    best_index = candidate_index
                    best_mode = mode
                    best_candidate = candidate
        if best_index is None or best_mode is None or best_candidate is None:
            break
        candidate = remaining.pop(best_index)
        if best_mode == "append_same":
            merged = merged + candidate[1:]
        elif best_mode == "append_reverse":
            merged = merged + candidate[::-1][1:]
        elif best_mode == "prepend_same":
            merged = candidate + merged[1:]
        else:
            merged = candidate[::-1] + merged[1:]
    return dedupe_coords(merged)


def route_shape_quality(coords: list[list[float]]) -> float:
    if len(coords) < 2:
        return -float("inf")
    total_length = 0.0
    reversal_penalty = 0.0
    repeated_points = 0
    seen: set[tuple[float, float]] = set()
    for index, point in enumerate(coords):
        key = (round(point[0], 6), round(point[1], 6))
        if key in seen:
            repeated_points += 1
        seen.add(key)
        if index == 0:
            continue
        previous = coords[index - 1]
        total_length += math.hypot(point[0] - previous[0], point[1] - previous[1])
        if index >= 2:
            before = coords[index - 2]
            previous_vector = (previous[0] - before[0], previous[1] - before[1])
            current_vector = (point[0] - previous[0], point[1] - previous[1])
            previous_norm = math.hypot(*previous_vector)
            current_norm = math.hypot(*current_vector)
            if previous_norm > 0 and current_norm > 0:
                dot = sum(left * right for left, right in zip(previous_vector, current_vector)) / (previous_norm * current_norm)
                if dot < 0:
                    reversal_penalty += 1.0
    return total_length - repeated_points * 5000.0 - reversal_penalty * 2500.0


def select_best_route_shape(candidates: list[list[list[float]]]) -> list[list[float]]:
    cleaned = [coords for coords in candidates if len(coords) >= 2]
    return max(cleaned, key=route_shape_quality) if cleaned else []


def trim_route_to_zone_stops(coords, ordered_stops, stop_rows, stop_rows_all):
    if len(coords) < 2 or not ordered_stops:
        return coords
    in_zone = [stop_id for stop_id in ordered_stops if stop_id in stop_rows]
    if len(in_zone) < 2:
        return coords
    first_stop = stop_rows_all.get(in_zone[0])
    last_stop = stop_rows_all.get(in_zone[-1])
    if not first_stop or not last_stop:
        return coords
    first_point = [float(first_stop["stop_lon"]), float(first_stop["stop_lat"])]
    last_point = [float(last_stop["stop_lon"]), float(last_stop["stop_lat"])]

    def nearest_index(point):
        return min(range(len(coords)), key=lambda index: math.hypot(coords[index][0] - point[0], coords[index][1] - point[1]))

    start_index = nearest_index(first_point)
    end_index = nearest_index(last_point)
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    trimmed = coords[start_index:end_index + 1]
    return dedupe_coords(trimmed) if len(trimmed) >= 2 else coords


def clip_route_to_zone_shapes(coords: list[list[float]], allowed_zone_shapes: list[Any] | None) -> list[list[float]]:
    if not allowed_zone_shapes or len(coords) < 2:
        return coords
    try:
        clipped = LineString(coords).intersection(unary_union(allowed_zone_shapes))
        if clipped.is_empty:
            return []
        if clipped.geom_type == "LineString":
            segments = [clipped]
        elif clipped.geom_type == "MultiLineString":
            segments = list(clipped.geoms)
        elif clipped.geom_type == "GeometryCollection":
            segments = [geometry for geometry in clipped.geoms if geometry.geom_type in {"LineString", "MultiLineString"}]
            segments = [part for geometry in segments for part in (geometry.geoms if geometry.geom_type == "MultiLineString" else [geometry])]
        else:
            return []
        if not segments:
            return []
        best = max(segments, key=lambda geometry: geometry.length)
        return [list(point) for point in mapping(best)["coordinates"]]
    except Exception:
        return coords
