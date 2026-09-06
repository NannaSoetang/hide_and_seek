"""Build the Copenhagen runtime datasets from local boundary and public sources."""

from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.config.data_config import (
    ADMIN_SIMPLIFY_TOLERANCE,
    DEFAULT_TRANSIT_SELECTION_RULES,
    DEFAULT_TRANSIT_SERVICE,
    DEFAULT_TRANSIT_ZONES,
    GTFS_URL,
    GTFS_ZIP,
    KOMMUNER_GEOJSON,
    KOMMUNER_URL,
    MOVIA_ZONES_GEOJSON,
    MOVIA_ZONES_URL,
    OPSTILLINGSKREDSE_GEOJSON,
    OPSTILLINGSKREDSE_URL,
    POSTNUMRE_GEOJSON,
    POSTNUMRE_URL,
    PUBLIC_DIR,
    RAW_DIR,
    SOGNE_GEOJSON,
    SOGNE_URL,
    load_transit_config,
    load_transit_rules,
)
from scripts.io.data_io import (
    download_if_missing,
    ensure_dirs as _ensure_dirs,
    iter_csv_from_zip,
    write_json,
)
from scripts.transit.transit_data import (
    load_selected_routes_and_trips,
    load_selected_stop_rows,
    matches_transit_rule,
    service_id_active_on_day as _service_id_active_on_day,
)
from scripts.transit import transit_geometry as _transit_geometry
from scripts.geography import geographic_data as _geographic_data
from scripts.config.theme import LINE_COLORS


def ensure_dirs() -> None:
    _ensure_dirs(RAW_DIR, PUBLIC_DIR)


def build_transit_features_for_rules(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    rules: list[dict[str, str]],
    network_name: str,
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Generic GTFS route builder shared by metro, S-train, and bus selections."""
    route_selector = lambda row: any(
        matches_transit_rule(row.get("route_short_name"), rule, row.get("route_type"))
        for rule in rules
    )
    routes, trip_rows = load_selected_routes_and_trips(archive, route_selector, service_window=DEFAULT_TRANSIT_SERVICE)
    if not routes:
        return []

    shape_ids_by_route: dict[str, set[str]] = defaultdict(set)
    for trip in trip_rows:
        shape_id = trip.get("shape_id")
        if shape_id:
            shape_ids_by_route[trip["route_id"]].add(shape_id)

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
    stop_times_by_trip: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in iter_csv_from_zip(archive, "stop_times.txt"):
        trip_id = row.get("trip_id")
        if trip_id in trip_route:
            stop_times_by_trip[trip_id].append((int(row.get("stop_sequence") or 0), row["stop_id"]))

    ordered_stops_by_route: dict[str, list[str]] = {}
    for trip in trip_rows:
        route_id = trip["route_id"]
        trip_id = trip["trip_id"]
        entries = stop_times_by_trip.get(trip_id)
        if not entries:
            continue
        ordered = [stop_id for _, stop_id in sorted(entries)]
        if len(ordered) < 2:
            continue
        ordered_stops_by_route.setdefault(route_id, []).append(ordered)

    route_stop_ids_by_route: dict[str, set[str]] = {
        route_id: {stop_id for ordered in sequences for stop_id in ordered}
        for route_id, sequences in ordered_stops_by_route.items()
    }
    stop_rows_all = load_selected_stop_rows(archive, route_stop_ids_by_route, allowed_zone_shapes=None, allowed_zones=None)
    stop_rows = load_selected_stop_rows(
        archive,
        route_stop_ids_by_route,
        allowed_zone_shapes=allowed_zone_shapes,
        allowed_zones=set(DEFAULT_TRANSIT_ZONES),
    )

    trip_stop_paths: dict[str, list[list[float]]] = defaultdict(list)
    for route_id, sequences in ordered_stops_by_route.items():
        for ordered in sequences:
            filtered = [stop_id for stop_id in ordered if stop_id in stop_rows]
            if len(filtered) < 2:
                continue
            stop_path = [[float(stop_rows_all[stop_id]["stop_lon"]), float(stop_rows_all[stop_id]["stop_lat"])] for stop_id in filtered]
            if len(stop_path) >= 2:
                trip_stop_paths[route_id].append(_dedupe_coords(stop_path))

    for route_id, sequences in ordered_stops_by_route.items():
        route_candidates = [
            [stop_id for stop_id in ordered if stop_id in stop_rows]
            for ordered in sequences
            if len([stop_id for stop_id in ordered if stop_id in stop_rows]) >= 2
        ]
        if route_candidates:
            best = max(route_candidates, key=len)
            stop_ids_by_route[route_id] = set(best)
            ordered_stops_by_route[route_id] = best
        else:
            stop_ids_by_route[route_id] = set()
            ordered_stops_by_route[route_id] = []

    line_features_by_line: dict[str, dict[str, Any]] = {}
    for route_id, route in sorted(routes.items(), key=lambda item: item[1].get("route_short_name", "")):
        line = route.get("route_short_name")
        if not line:
            continue

        route_stop_ids = stop_ids_by_route.get(route_id, set())
        if not any(stop_id in stop_rows for stop_id in route_stop_ids):
            continue

        ordered = ordered_stops_by_route.get(route_id)
        raw_segments: list[list[list[float]]] = []
        if trip_stop_paths.get(route_id):
            raw_segments.extend(trip_stop_paths[route_id])
        if not raw_segments:
            for shape_id in sorted(shape_ids_by_route.get(route_id, [])):
                points = sorted(shape_points.get(shape_id, []))
                if len(points) < 2:
                    continue
                shape_coords = [[lon, lat] for _, lon, lat in points]
                if len(shape_coords) >= 2:
                    raw_segments.append(shape_coords)

        if not raw_segments and ordered:
            filtered_indices = [i for i, stop_id in enumerate(ordered) if stop_id in stop_rows]
            if filtered_indices:
                start_idx, end_idx = filtered_indices[0], filtered_indices[-1]
                fallback_coords: list[list[float]] = []
                for stop_id in ordered[start_idx : end_idx + 1]:
                    stop = stop_rows_all.get(stop_id)
                    if stop:
                        fallback_coords.append([float(stop["stop_lon"]), float(stop["stop_lat"])])
                if len(fallback_coords) >= 2:
                    raw_segments.append(fallback_coords)

        merged_shape = merge_route_segments(raw_segments)
        candidate_coords = select_best_route_shape([merged_shape] if merged_shape else raw_segments)
        if trip_stop_paths.get(route_id):
            stop_sequence = max(trip_stop_paths[route_id], key=len)
            if stop_sequence and len(stop_sequence) >= 2:
                candidate_coords = stop_sequence
        if ordered and stop_rows:
            candidate_coords = trim_route_to_zone_stops(candidate_coords, ordered, stop_rows, stop_rows_all)
        coords = clip_route_to_zone_shapes(candidate_coords, allowed_zone_shapes)
        if not coords and candidate_coords and allowed_zone_shapes:
            coords = candidate_coords
        coords = _dedupe_coords(coords)
        if len(coords) < 2:
            continue

        route_label = ""
        if ordered:
            filtered_indices = [i for i, stop_id in enumerate(ordered) if stop_id in stop_rows]
            if filtered_indices:
                start_idx, end_idx = filtered_indices[0], filtered_indices[-1]
                first_stop = stop_rows_all.get(ordered[start_idx])
                last_stop = stop_rows_all.get(ordered[end_idx])
                if first_stop and last_stop:
                    route_label = f"{clean_station_name(first_stop.get('stop_name', ''))} – {clean_station_name(last_stop.get('stop_name', ''))}"

        feature = {
            "type": "Feature",
            "properties": {
                "network": network_name,
                "line": line,
                "route_id": route_id,
                "route": route_label,
                "color": LINE_COLORS.get(line, "#6a6a6a"),
                "source": "Rejseplanen GTFS",
                "service_state": route.get("service_state", ""),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        current = line_features_by_line.get(line)
        if current is None or len(coords) > len(current["geometry"]["coordinates"]):
            line_features_by_line[line] = feature

    line_features = list(line_features_by_line.values())

    for route_id, stop_ids in stop_ids_by_route.items():
        line = routes[route_id].get("route_short_name")
        for stop_id in stop_ids:
            stop = stop_rows.get(stop_id)
            if not stop or not stop.get("stop_lat") or not stop.get("stop_lon"):
                continue
            _add_station_feature(station_index, stop, line, network_name)

    return line_features


def build_metro_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return build_transit_features_for_rules(
        archive,
        station_index,
        [{"type": "metro"}],
        network_name="metro",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_stog_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return build_transit_features_for_rules(
        archive,
        station_index,
        [{"type": "s-train"}],
        network_name="s-tog",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_bus_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
    transit_rules: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build all bus routes matching the configured GTFS patterns, without hardcoded route lists."""
    if transit_rules is None:
        transit_rules = [rule for rule in DEFAULT_TRANSIT_SELECTION_RULES if rule.get("type") == "bus"]

    return build_transit_features_for_rules(
        archive,
        station_index,
        transit_rules,
        network_name="bus",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_transport_datasets(allowed_zone_shapes: list[Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    download_if_missing(GTFS_URL, GTFS_ZIP)
    station_index: dict[tuple[str, float, float], dict[str, Any]] = {}
    with zipfile.ZipFile(GTFS_ZIP) as archive:
        line_features = build_metro_transport_features(archive, station_index, allowed_zone_shapes=allowed_zone_shapes)
        line_features.extend(build_stog_transport_features(archive, station_index, allowed_zone_shapes=allowed_zone_shapes))
        line_features.extend(
            build_bus_transport_features(
                archive,
                station_index,
                allowed_zone_shapes=allowed_zone_shapes,
                transit_rules=[rule for rule in DEFAULT_TRANSIT_SELECTION_RULES if rule.get("type") == "bus"],
            )
        )

    station_features = list(station_index.values())
    for station in station_features:
        station["properties"]["lines"].sort()
        station["properties"]["networks"].sort()
    line_features.sort(key=lambda feat: (feat["properties"]["network"], feat["properties"]["line"], feat["properties"].get("shape_id", "")))
    station_features.sort(key=lambda feat: feat["properties"]["name"])
    print(
        "Transit import summary: "
        f"routes={len(line_features)} stations={len(station_features)} "
        f"networks={ {feat['properties']['network'] for feat in line_features} }"
    )
    return (
        {"type": "FeatureCollection", "features": line_features},
        {"type": "FeatureCollection", "features": station_features},
    )


def load_region_boundary_feature() -> dict[str, Any]:
    return _geographic_data.load_region_boundary_feature(PUBLIC_DIR)


def load_movia_zone_shapes(boundary_shape: Any, allowed_names: set[str]) -> list[Any]:
    return _geographic_data.load_movia_zone_shapes(
        boundary_shape,
        allowed_names,
        MOVIA_ZONES_GEOJSON,
        MOVIA_ZONES_URL,
        downloader=download_if_missing,
    )


def build_sogne_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    return _geographic_data.build_sogne_dataset(boundary_feature, downloader=download_if_missing)


def build_municipalities_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    return _geographic_data.build_municipalities_dataset(boundary_feature, downloader=download_if_missing)


def build_postnumre_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    return _geographic_data.build_postnumre_dataset(boundary_feature, downloader=download_if_missing)


def build_opstillingskredse_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    return _geographic_data.build_opstillingskredse_dataset(boundary_feature, downloader=download_if_missing)


clean_station_name = _transit_geometry.clean_station_name
normalize_station_name = _transit_geometry.normalize_station_name
_add_station_feature = _transit_geometry.add_station_feature
_dedupe_coords = _transit_geometry.dedupe_coords
merge_route_segments = _transit_geometry.merge_route_segments
select_best_route_shape = _transit_geometry.select_best_route_shape
trim_route_to_zone_stops = _transit_geometry.trim_route_to_zone_stops
clip_route_to_zone_shapes = _transit_geometry.clip_route_to_zone_shapes


def main() -> None:
    """Build all derived data files for the Copenhagen playable area."""
    ensure_dirs()
    boundary_feature = load_region_boundary_feature()
    boundary_shape = shape(boundary_feature["geometry"])
    movia_zones = load_movia_zone_shapes(boundary_shape, DEFAULT_TRANSIT_ZONES)

    transport_lines, transport_stations = build_transport_datasets(allowed_zone_shapes=movia_zones)
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
