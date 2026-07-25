"""Build the requested end-to-end Copenhagen S-tog paths from GTFS."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = ROOT / "web" / "public" / "data"
GTFS_ZIP = ROOT / "data" / "raw" / "gtfs.zip"

S_LINES = {"A", "B", "C", "F"}
S_LINE_COLORS = {
    "A": "#1f4e9e",
    "B": "#2f9e44",
    "C": "#f28e2b",
    "F": "#f2a900",
}
LINE_ENDPOINTS = {
    "A": ("lyngby", "vallensbaek"),
    "B": ("buddinge", "glostrup"),
    "C": ("klampenborg", "herlev"),
    "F": ("klampenborg", "kobenhavn syd"),
}


def rows(archive: zipfile.ZipFile, filename: str):
    with archive.open(filename) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))


def clean_name(value: str) -> str:
    normalized = value.casefold().replace("ø", "o").replace("å", "a").replace("æ", "ae")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\bst\s*$", "", normalized)
    return " ".join(normalized.split())


def write_geojson(path: Path, features: list[dict]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    if not GTFS_ZIP.exists():
        raise FileNotFoundError(f"Missing GTFS feed: {GTFS_ZIP}")

    with zipfile.ZipFile(GTFS_ZIP) as archive:
        routes = {
            row["route_id"]: row
            for row in rows(archive, "routes.txt")
            if row.get("route_short_name") in S_LINES and row.get("route_type") == "109"
        }
        trip_rows = [row for row in rows(archive, "trips.txt") if row.get("route_id") in routes]
        trip_routes = {trip["trip_id"]: trip["route_id"] for trip in trip_rows}
        stop_times: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for row in rows(archive, "stop_times.txt"):
            if row.get("trip_id") in trip_routes:
                stop_times[row["trip_id"]].append((int(row.get("stop_sequence") or 0), row["stop_id"]))
        stop_rows = {row["stop_id"]: row for row in rows(archive, "stops.txt")}

    paths_by_line: dict[str, list[list[str]]] = defaultdict(list)
    for trip in trip_rows:
        line = routes[trip["route_id"]]["route_short_name"]
        collapsed: list[str] = []
        for _, stop_id in sorted(stop_times[trip["trip_id"]]):
            if not collapsed or clean_name(stop_rows[collapsed[-1]].get("stop_name", "")) != clean_name(stop_rows[stop_id].get("stop_name", "")):
                collapsed.append(stop_id)
        if len(collapsed) >= 2:
            paths_by_line[line].append(collapsed)

    selected_paths: dict[str, list[str]] = {}
    for line, (start_name, target_name) in LINE_ENDPOINTS.items():
        names_to_stop: dict[str, str] = {}
        adjacency: dict[str, set[str]] = defaultdict(set)
        for path in paths_by_line[line]:
            for stop_id in path:
                names_to_stop.setdefault(clean_name(stop_rows[stop_id].get("stop_name", "")), stop_id)
            for left, right in zip(path, path[1:]):
                adjacency[left].add(right)
                adjacency[right].add(left)

        start = names_to_stop.get(start_name)
        target = names_to_stop.get(target_name)
        if not start or not target:
            raise ValueError(f"Could not find endpoints for {line}: {start_name} -> {target_name}")
        queue = deque([start])
        previous = {start: None}
        while queue and target not in previous:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in previous:
                    previous[neighbor] = current
                    queue.append(neighbor)
        if target not in previous:
            raise ValueError(f"No connected route for {line}: {start_name} -> {target_name}")
        path = []
        current = target
        while current is not None:
            path.append(current)
            current = previous[current]
        selected_paths[line] = list(reversed(path))

    line_features = []
    station_keys: set[tuple[str, float, float]] = set()
    station_lines: dict[tuple[str, float, float], set[str]] = defaultdict(set)
    for line in sorted(S_LINES):
        path = selected_paths[line]
        coordinates = []
        for stop_id in path:
            stop = stop_rows[stop_id]
            coordinates.append([float(stop["stop_lon"]), float(stop["stop_lat"])])
            key = (stop.get("stop_name", stop_id), round(float(stop["stop_lat"]), 6), round(float(stop["stop_lon"]), 6))
            station_keys.add(key)
            station_lines[key].add(line)
        line_features.append({
            "type": "Feature",
            "properties": {"line": line, "color": S_LINE_COLORS[line], "source": "Rejseplanen GTFS"},
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })

    station_features = [{
        "type": "Feature",
        "properties": {"name": name, "lines": sorted(station_lines[(name, lat, lon)]), "source": "Rejseplanen GTFS"},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    } for name, lat, lon in sorted(station_keys)]
    write_geojson(PUBLIC_DATA / "s-tog-lines.geojson", line_features)
    write_geojson(PUBLIC_DATA / "s-tog-stations.geojson", station_features)
    print(f"Wrote {len(line_features)} S-tog line geometries and {len(station_features)} stations")


if __name__ == "__main__":
    main()
