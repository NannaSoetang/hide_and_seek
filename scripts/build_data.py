"""Build the Copenhagen runtime datasets from local boundary and public sources."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PUBLIC_DIR = ROOT / "web" / "public" / "data"
GTFS_URL = "https://www.rejseplanen.info/labs/GTFS.zip"
GTFS_ZIP = RAW_DIR / "gtfs.zip"
KOMMUNER_GEOJSON = RAW_DIR / "kommuner.geojson"
POSTNUMRE_GEOJSON = RAW_DIR / "postnumre.geojson"
OPSTILLINGSKREDSE_GEOJSON = RAW_DIR / "opstillingskredse.geojson"
SOGNE_GEOJSON = RAW_DIR / "sogne.geojson"
KOMMUNER_URL = "https://api.dataforsyningen.dk/kommuner?format=geojson"
POSTNUMRE_URL = "https://api.dataforsyningen.dk/postnumre?format=geojson"
OPSTILLINGSKREDSE_URL = "https://api.dataforsyningen.dk/opstillingskredse?format=geojson"
SOGNE_URL = "https://api.dataforsyningen.dk/sogne?format=geojson"
ADMIN_SIMPLIFY_TOLERANCE = {
    "municipalities": 0.00008,
    "postnumre": 0.00012,
    "opstillingskredse": 0.00010,
    "sogne": 0.00008,
}
METRO_LINE_COLORS = {"M1": "#00a650", "M2": "#f5c400", "M3": "#e03b3b", "M4": "#0072bc"}
STOG_LINES = {"A", "B", "C", "F"}
STOG_LINE_COLORS = {
    "A": "#1f4e9e",
    "B": "#2f9e44",
    "C": "#f28e2b",
    "F": "#f2a900",
}
STOG_LINE_ENDPOINTS = {
    "A": ("lyngby", "vallensbaek"),
    "B": ("buddinge", "glostrup"),
    "C": ("klampenborg", "herlev"),
    "F": ("klampenborg", "kobenhavn syd"),
}


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def download_if_missing(url: str, destination: Path) -> None:
    """Download a file only when it is not already present."""
    if destination.exists():
        return
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)


def load_region_boundary_feature() -> dict[str, Any]:
    """Read the committed Copenhagen playable-area boundary."""
    boundary_path = PUBLIC_DIR / "boundary.geojson"
    collection = json.loads(boundary_path.read_text())
    feature = (collection.get("features") or [None])[0]
    if not feature:
        raise RuntimeError(f"Boundary GeoJSON contains no feature: {boundary_path}")
    return feature


def load_csv_from_zip(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    """Read a smaller CSV file from a GTFS ZIP archive."""
    with archive.open(name) as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))


def iter_csv_from_zip(archive: zipfile.ZipFile, name: str):
    """Yield CSV rows from a GTFS ZIP archive without materializing the full file."""
    with archive.open(name) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))


def load_selected_routes_and_trips(
    archive: zipfile.ZipFile,
    route_selector,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    route_rows = load_csv_from_zip(archive, "routes.txt")
    routes = {row["route_id"]: row for row in route_rows if route_selector(row)}
    trip_rows = [row for row in load_csv_from_zip(archive, "trips.txt") if row.get("route_id") in routes]
    return routes, trip_rows


def load_selected_stop_rows(
    archive: zipfile.ZipFile,
    stop_ids_by_route: dict[str, set[str]],
) -> dict[str, dict[str, str]]:
    selected_stop_ids = {stop_id for ids in stop_ids_by_route.values() for stop_id in ids}
    return {
        row["stop_id"]: row
        for row in load_csv_from_zip(archive, "stops.txt")
        if row.get("stop_id") in selected_stop_ids
    }


def clean_station_name(name: str) -> str:
    return re.sub(r"\s*\(Metro\)\s*", "", str(name or "")).strip()


def normalize_station_name(name: str) -> str:
    normalized = str(name or "").casefold().replace("ø", "o").replace("å", "a").replace("æ", "ae")
    normalized = re.sub(r"\(.*?\)", "", normalized)
    normalized = re.sub(r"\bst\.?\b", "", normalized)
    normalized = normalized.replace("station", "")
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def build_sogne_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized sogne dataset clipped to the game boundary."""
    download_if_missing(SOGNE_URL, SOGNE_GEOJSON)
    source = json.loads(SOGNE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["sogne"],
        lambda props: {
            "name": _first_non_empty(
                props,
                "navn",
                "name",
                "sognenavn",
                "SOGNENAVN",
            )
            or "Ukendt sogn",
            "code": _first_non_empty(
                props,
                "sognekode",
                "kode",
                "sognenr",
                "SOGNEKODE",
            )
            or "-",
            "source": "Dataforsyningen sogne",
        },
        sort_key=lambda feat: feat["properties"]["name"],
    )


def _first_non_empty(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _build_admin_dataset(
    source: dict[str, Any],
    boundary_shape: Any,
    simplify_tolerance: float,
    properties_builder,
    sort_key,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for feature in source.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue

        raw_shape = shape(geometry)
        if not raw_shape.intersects(boundary_shape):
            continue

        clipped = raw_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue

        simplified = clipped.simplify(simplify_tolerance, preserve_topology=True)
        if simplified.is_empty:
            continue

        props = feature.get("properties", {}) or {}
        features.append(
            {
                "type": "Feature",
                "properties": properties_builder(props),
                "geometry": mapping(simplified),
            }
        )

    features.sort(key=sort_key)
    return {"type": "FeatureCollection", "features": features}


def build_municipalities_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized kommune boundaries from the official dataset."""
    download_if_missing(KOMMUNER_URL, KOMMUNER_GEOJSON)
    source = json.loads(KOMMUNER_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["municipalities"],
        lambda props: {
            "name": _first_non_empty(props, "navn", "name", "kommunenavn", "KOMMUNENAVN")
            or "Ukendt kommune",
            "code": _first_non_empty(props, "kode", "kommunekode", "kommunenr", "KOMMUNEKODE")
            or "-",
            "source": "Dataforsyningen kommuner",
        },
        sort_key=lambda feat: feat["properties"]["name"],
    )


def build_postnumre_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized postområde boundaries grouped by postnummernavn."""
    download_if_missing(POSTNUMRE_URL, POSTNUMRE_GEOJSON)
    source = json.loads(POSTNUMRE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    grouped_geometries: dict[str, list[Any]] = defaultdict(list)
    for feature in source.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue

        raw_shape = shape(geometry)
        if not raw_shape.intersects(boundary_shape):
            continue

        clipped = raw_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue

        props = feature.get("properties", {}) or {}
        label = _first_non_empty(props, "navn", "postnrnavn", "postnummernavn")
        if not label:
            label = "Ukendt postområde"
        grouped_geometries[label].append(clipped)

    features: list[dict[str, Any]] = []
    for label, geometries in grouped_geometries.items():
        merged = unary_union(geometries)
        simplified = merged.simplify(ADMIN_SIMPLIFY_TOLERANCE["postnumre"], preserve_topology=True)
        if simplified.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "postnummernavn": label,
                    "source": "Dataforsyningen postnumre",
                },
                "geometry": mapping(simplified),
            }
        )

    features.sort(key=lambda feat: feat["properties"]["postnummernavn"])
    return {"type": "FeatureCollection", "features": features}


def build_opstillingskredse_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized opstillingskredse boundaries."""
    download_if_missing(OPSTILLINGSKREDSE_URL, OPSTILLINGSKREDSE_GEOJSON)
    source = json.loads(OPSTILLINGSKREDSE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["opstillingskredse"],
        lambda props: {
            "name": _first_non_empty(props, "navn", "name", "opstillingskredsnavn")
            or "Ukendt opstillingskreds",
            "number": _first_non_empty(props, "nummer", "nr", "opstillingskredsnummer")
            or "-",
            "source": "Dataforsyningen opstillingskredse",
        },
        sort_key=lambda feat: (feat["properties"]["name"], feat["properties"]["number"]),
    )


def _add_station_feature(
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
    station = station_index.setdefault(
        key,
        {
            "type": "Feature",
            "properties": {
                "name": name,
                "lines": [],
                "networks": [],
                "stop_id": stop["stop_id"],
                "source": "Rejseplanen GTFS",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
        },
    )
    if line not in station["properties"]["lines"]:
        station["properties"]["lines"].append(line)
    if network not in station["properties"]["networks"]:
        station["properties"]["networks"].append(network)


def build_metro_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
) -> list[dict[str, Any]]:
    routes, trip_rows = load_selected_routes_and_trips(
        archive,
        lambda row: row.get("route_short_name") in METRO_LINE_COLORS,
    )
    shape_ids_by_route: dict[str, set[str]] = defaultdict(set)
    for trip in trip_rows:
        if trip.get("shape_id"):
            shape_ids_by_route[trip["route_id"]].add(trip["shape_id"])

    selected_shape_ids = {shape_id for ids in shape_ids_by_route.values() for shape_id in ids}
    shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for row in iter_csv_from_zip(archive, "shapes.txt"):
        shape_id = row.get("shape_id")
        if shape_id not in selected_shape_ids:
            continue
        shape_points[shape_id].append(
            (
                int(row.get("shape_pt_sequence") or 0),
                float(row["shape_pt_lon"]),
                float(row["shape_pt_lat"]),
            )
        )

    stop_ids_by_route: dict[str, set[str]] = defaultdict(set)
    trip_route = {trip["trip_id"]: trip["route_id"] for trip in trip_rows}
    for row in iter_csv_from_zip(archive, "stop_times.txt"):
        route_id = trip_route.get(row.get("trip_id"))
        if route_id:
            stop_ids_by_route[route_id].add(row["stop_id"])

    stop_rows = load_selected_stop_rows(archive, stop_ids_by_route)

    line_features: list[dict[str, Any]] = []
    for route_id, route in sorted(routes.items(), key=lambda item: item[1]["route_short_name"]):
        line = route["route_short_name"]
        for shape_id in sorted(shape_ids_by_route[route_id]):
            points = sorted(shape_points.get(shape_id, []))
            if len(points) < 2:
                continue
            line_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "network": "metro",
                        "line": line,
                        "route_id": route_id,
                        "shape_id": shape_id,
                        "color": METRO_LINE_COLORS[line],
                        "source": "Rejseplanen GTFS",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for _, lon, lat in points],
                    },
                }
            )

    for route_id, stop_ids in stop_ids_by_route.items():
        line = routes[route_id]["route_short_name"]
        for stop_id in stop_ids:
            stop = stop_rows.get(stop_id)
            if not stop or not stop.get("stop_lat") or not stop.get("stop_lon"):
                continue
            _add_station_feature(station_index, stop, line, "metro")

    return line_features


def build_stog_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
) -> list[dict[str, Any]]:
    routes, trip_rows = load_selected_routes_and_trips(
        archive,
        lambda row: row.get("route_short_name") in STOG_LINES and row.get("route_type") == "109",
    )
    trip_routes = {trip["trip_id"]: trip["route_id"] for trip in trip_rows}
    stop_times: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in iter_csv_from_zip(archive, "stop_times.txt"):
        trip_id = row.get("trip_id")
        if trip_id in trip_routes:
            stop_times[trip_id].append((int(row.get("stop_sequence") or 0), row["stop_id"]))
    stop_rows = load_selected_stop_rows(
        archive,
        {trip_id: {stop_id for _, stop_id in entries} for trip_id, entries in stop_times.items()},
    )

    paths_by_line: dict[str, list[list[str]]] = defaultdict(list)
    for trip in trip_rows:
        line = routes[trip["route_id"]]["route_short_name"]
        collapsed: list[str] = []
        for _, stop_id in sorted(stop_times[trip["trip_id"]]):
            current_stop = stop_rows[stop_id]
            if not collapsed:
                collapsed.append(stop_id)
                continue
            previous_stop = stop_rows[collapsed[-1]]
            if normalize_station_name(current_stop.get("stop_name", "")) != normalize_station_name(previous_stop.get("stop_name", "")):
                collapsed.append(stop_id)
        if len(collapsed) >= 2:
            paths_by_line[line].append(collapsed)

    selected_paths: dict[str, list[str]] = {}
    for line, (start_name, target_name) in STOG_LINE_ENDPOINTS.items():
        names_to_stop: dict[str, str] = {}
        adjacency: dict[str, set[str]] = defaultdict(set)
        for path in paths_by_line[line]:
            for stop_id in path:
                names_to_stop.setdefault(normalize_station_name(stop_rows[stop_id].get("stop_name", "")), stop_id)
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

    line_features: list[dict[str, Any]] = []
    for line in sorted(STOG_LINES):
        path = selected_paths[line]
        coordinates = []
        for stop_id in path:
            stop = stop_rows[stop_id]
            coordinates.append([float(stop["stop_lon"]), float(stop["stop_lat"])])
            _add_station_feature(station_index, stop, line, "s-tog")
        line_features.append(
            {
                "type": "Feature",
                "properties": {
                    "network": "s-tog",
                    "line": line,
                    "color": STOG_LINE_COLORS[line],
                    "source": "Rejseplanen GTFS",
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        )

    return line_features


def build_transport_datasets() -> tuple[dict[str, Any], dict[str, Any]]:
    download_if_missing(GTFS_URL, GTFS_ZIP)
    station_index: dict[tuple[str, float, float], dict[str, Any]] = {}
    with zipfile.ZipFile(GTFS_ZIP) as archive:
        line_features = build_metro_transport_features(archive, station_index)
        line_features.extend(build_stog_transport_features(archive, station_index))

    station_features = list(station_index.values())
    for station in station_features:
        station["properties"]["lines"].sort()
        station["properties"]["networks"].sort()
    line_features.sort(key=lambda feat: (feat["properties"]["network"], feat["properties"]["line"], feat["properties"].get("shape_id", "")))
    station_features.sort(key=lambda feat: feat["properties"]["name"])
    return (
        {"type": "FeatureCollection", "features": line_features},
        {"type": "FeatureCollection", "features": station_features},
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def main() -> None:
    """Build all derived data files for the Copenhagen playable area."""
    ensure_dirs()
    boundary_feature = load_region_boundary_feature()
    transport_lines, transport_stations = build_transport_datasets()
    municipalities = build_municipalities_dataset(boundary_feature)
    postnumre = build_postnumre_dataset(boundary_feature)
    opstillingskredse = build_opstillingskredse_dataset(boundary_feature)
    sogne = build_sogne_dataset(boundary_feature)
    boundary = {
        "type": "FeatureCollection",
        "features": [boundary_feature],
    }

    write_json(PUBLIC_DIR / "municipalities.geojson", municipalities)
    write_json(PUBLIC_DIR / "postnumre.geojson", postnumre)
    write_json(PUBLIC_DIR / "opstillingskredse.geojson", opstillingskredse)
    write_json(PUBLIC_DIR / "sogne.geojson", sogne)
    write_json(PUBLIC_DIR / "boundary.geojson", boundary)
    write_json(PUBLIC_DIR / "transport-lines.geojson", transport_lines)
    write_json(PUBLIC_DIR / "transport-stations.geojson", transport_stations)


if __name__ == "__main__":
    main()
