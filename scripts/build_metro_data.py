"""Build static Copenhagen Metro GeoJSON from the Rejseplanen GTFS feed.

Source: https://www.rejseplanen.info/labs/GTFS.zip
The feed's attributions.txt identifies the feed attribution. Rejseplanen's
published terms should be checked before redistributing outside this project.
This script deliberately processes only routes whose short name is M1-M4.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = ROOT / "web" / "public" / "data"
GTFS_URL = "https://www.rejseplanen.info/labs/GTFS.zip"
GTFS_ZIP = ROOT / "data" / "raw" / "gtfs.zip"
LINE_COLORS = {"M1": "#00a650", "M2": "#f5c400", "M3": "#e03b3b", "M4": "#0072bc"}


def ensure_feed() -> None:
    GTFS_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if not GTFS_ZIP.exists():
        urllib.request.urlretrieve(GTFS_URL, GTFS_ZIP)


def rows(archive: zipfile.ZipFile, filename: str):
    with archive.open(filename) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))


def write_geojson(path: Path, features: list[dict]) -> None:
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    ensure_feed()
    with zipfile.ZipFile(GTFS_ZIP) as archive:
        route_rows = list(rows(archive, "routes.txt"))
        metro_routes = {
            row["route_id"]: row
            for row in route_rows
            if row.get("route_short_name") in LINE_COLORS
        }
        trip_rows = [
            row for row in rows(archive, "trips.txt") if row.get("route_id") in metro_routes
        ]
        shape_ids_by_route: dict[str, set[str]] = defaultdict(set)
        for trip in trip_rows:
            if trip.get("shape_id"):
                shape_ids_by_route[trip["route_id"]].add(trip["shape_id"])

        shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
        for row in rows(archive, "shapes.txt"):
            if row.get("shape_id") in {sid for ids in shape_ids_by_route.values() for sid in ids}:
                shape_points[row["shape_id"]].append(
                    (
                        int(row.get("shape_pt_sequence") or 0),
                        float(row["shape_pt_lon"]),
                        float(row["shape_pt_lat"]),
                    )
                )

        stop_ids_by_route: dict[str, set[str]] = defaultdict(set)
        trip_route = {trip["trip_id"]: trip["route_id"] for trip in trip_rows}
        for row in rows(archive, "stop_times.txt"):
            route_id = trip_route.get(row.get("trip_id"))
            if route_id:
                stop_ids_by_route[route_id].add(row["stop_id"])

        stop_rows = {
            row["stop_id"]: row
            for row in rows(archive, "stops.txt")
            if row.get("stop_id") in {sid for ids in stop_ids_by_route.values() for sid in ids}
        }

    line_features = []
    for route_id, route in sorted(metro_routes.items(), key=lambda item: item[1]["route_short_name"]):
        line = route["route_short_name"]
        for shape_id in sorted(shape_ids_by_route[route_id]):
            points = sorted(shape_points.get(shape_id, []))
            if len(points) < 2:
                continue
            line_features.append({
                "type": "Feature",
                "properties": {
                    "line": line,
                    "route_id": route_id,
                    "shape_id": shape_id,
                    "color": LINE_COLORS[line],
                    "source": "Rejseplanen GTFS",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for _, lon, lat in points],
                },
            })

    station_index: dict[tuple[str, float, float], dict] = {}
    for route_id, stop_ids in stop_ids_by_route.items():
        line = metro_routes[route_id]["route_short_name"]
        for stop_id in stop_ids:
            stop = stop_rows.get(stop_id)
            if not stop or not stop.get("stop_lat") or not stop.get("stop_lon"):
                continue
            name = stop.get("stop_name", stop_id)
            key = (name, round(float(stop["stop_lat"]), 6), round(float(stop["stop_lon"]), 6))
            station = station_index.setdefault(key, {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "lines": [],
                    "stop_id": stop_id,
                    "source": "Rejseplanen GTFS",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(stop["stop_lon"]), float(stop["stop_lat"])],
                },
            })
            if line not in station["properties"]["lines"]:
                station["properties"]["lines"].append(line)

    station_features = list(station_index.values())
    for station in station_features:
        station["properties"]["lines"].sort()

    station_features.sort(key=lambda feature: feature["properties"]["name"])
    write_geojson(PUBLIC_DATA / "metro-lines.geojson", line_features)
    write_geojson(PUBLIC_DATA / "metro-stations.geojson", station_features)
    print(f"Wrote {len(line_features)} Metro line geometries and {len(station_features)} stations")


if __name__ == "__main__":
    main()
